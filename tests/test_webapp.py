import asyncio
import hashlib
import hmac
import io
import json
import time
import uuid
import zipfile
from pathlib import PurePosixPath
from unittest.mock import AsyncMock
from urllib.parse import urlencode
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from pligrim_bot.config.constants import API_TOKEN,bot
from pligrim_bot.web import auth,service
from pligrim_bot.web import app as web


def make_init(user=None,timestamp=None):
    fields={'user':json.dumps(user or {'id':101,'first_name':'Test'}),'auth_date':str(int(timestamp or time.time())),'query_id':'test-query'}
    secret=hmac.new(b'WebAppData',API_TOKEN.encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
    return urlencode(fields)


def body(flight=False,deliver=False):
    data={'title':'TEST VOUCHER','request_id':uuid.uuid4().hex,'background':1,'deliver_to_chat':deliver,
          'voucher':{'city1':'Madinah','hotel1':'Valy Hotel','dates1':'20/10/2026 – 23/10/2026','checkin1':'16:00',
                     'city2':'Makkah','hotel2':'Courtyard','dates2':'23/10/2026 – 27/10/2026','checkin2':'16:00',
                     'people':{'rooms':[{'kind':'DBL','people':['IVANOV IVAN','PETROVA ANNA'],'adults':2}]}}}
    if flight:data['flight']={'outbound':{'airline':'SCAT','number':'DV 499','origin':'Алматы · ALA','destination':'Медина · MED',
                                           'departure_date':'2026-10-20','arrival_date':'2026-10-20','departure_time':'05:30','arrival_time':'04:50'},'inbound':None}
    return data


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('WEB_STATE_DIR',str(tmp_path/'state'));monkeypatch.setenv('ALLOWED_USER_IDS','')
    monkeypatch.setenv('WEBAPP_URL','https://voucherhickmet.duckdns.org')
    monkeypatch.setattr(web,'_username','hickmet_test_bot')
    from pligrim_bot.core.voucher import render as R
    monkeypatch.setattr(R,'TMP_DIR',str(tmp_path))
    monkeypatch.setattr(bot,'send_document',AsyncMock())
    with TestClient(web.app,base_url='https://testserver') as client:
        yield client


def login(client,user=101):
    response=client.post('/api/auth/telegram',json={'init_data':make_init({'id':user,'first_name':'Test'})})
    assert response.status_code==200,response.text
    return response


@pytest.mark.parametrize('index,filename',[(0,'use-med 20.png'),(2,'uae-mec 20.png')])
def test_baggage_job_preview_and_saved_draft(client,tmp_path,monkeypatch,index,filename):
    from PIL import Image
    from pligrim_bot.core.voucher import render as R
    monkeypatch.setattr(R,'IMAGES_DIR',str(tmp_path))
    login(client)
    payload=body();payload.update(background=index,baggage='5_20')
    # A missing asset must fail before creating a render job.
    missing=client.post('/api/jobs',json=payload)
    assert missing.status_code==400 and 'ещё не загружена' in missing.text
    Image.new('RGB',(100,150),'red').save(tmp_path/filename)
    response=client.get(f'/api/designs/{index}?baggage=5_20')
    assert response.status_code==200 and response.content==(tmp_path/filename).read_bytes()
    assert client.post('/api/preview',json=payload).status_code==200
    response=client.post('/api/jobs',json=payload)
    assert response.status_code==200,response.text
    key=response.json()['id'];job=wait_job(client,key)
    assert job['status']=='done',job
    draft=client.get(f'/api/jobs/{key}/files/0/draft').json()
    assert draft['baggage']=='5_20' and draft['background']==index
    payload['baggage']='5'
    assert client.post('/api/jobs',json=payload).status_code==422


def wait_job(client,key):
    for _ in range(150):
        job=client.get('/api/jobs/'+key).json()
        if job['status'] not in {'queued','rendering','sending'}:return job
        time.sleep(.025)
    raise AssertionError('Job did not complete')


def test_authentication_required(client):
    assert client.get('/').status_code==200
    assert client.get('/api/me').status_code==401
    assert client.get('/api/catalog').status_code==401
    assert client.get('/api/jobs').status_code==401
    assert client.get('/api/flight-options',params={'month':'October 2026','sheet':'Flights'}).status_code==401
    assert client.post('/api/jobs',json=body()).status_code==401


def test_valid_miniapp_login_and_tampering(client):
    result=login(client)
    assert 'HttpOnly' in result.headers['set-cookie'] and 'Secure' in result.headers['set-cookie']
    assert client.get('/api/me').json()['user']['id']==101
    assert client.post('/api/auth/telegram',json={'init_data':make_init().replace('Test','Other')}).status_code==401
    assert client.post('/api/auth/telegram',json={'init_data':make_init(timestamp=time.time()-3700)}).status_code==401


def test_duplicate_auth_fields_rejected():
    with pytest.raises(ValueError):auth.verify_init_data(make_init()+'&auth_date=1')


def test_allowed_users_enforced(client,monkeypatch):
    monkeypatch.setenv('ALLOWED_USER_IDS','999')
    assert client.post('/api/auth/telegram',json={'init_data':make_init()}).status_code==401


def test_browser_login_one_time_challenge(client):
    challenge=client.post('/api/auth/challenge').json()
    assert challenge['telegram_url'].startswith('https://t.me/hickmet_test_bot?start=web_')
    assert client.post('/api/auth/poll',json=challenge).status_code==200
    auth.approve_challenge(challenge['challenge'],{'id':101,'first_name':'Test'})
    response=client.post('/api/auth/poll',json=challenge)
    assert response.status_code==200 and response.json()['user']['id']==101
    assert client.post('/api/auth/poll',json=challenge).status_code==400


def test_wrong_challenge_secret_rejected(client):
    challenge=client.post('/api/auth/challenge').json();challenge['secret']='wrong'
    assert client.post('/api/auth/poll',json=challenge).status_code==400


def test_csrf_other_origin_blocked(client):
    login(client)
    assert client.post('/api/jobs',json=body(),headers={'Origin':'https://another-site.example'}).status_code==403


def test_bearer_works_without_cookies(client):
    token=login(client).json()['session_token'];client.cookies.clear()
    assert client.get('/api/me',headers={'Authorization':'Bearer '+token}).status_code==200


@pytest.mark.parametrize('flight,pages',[(False,2),(True,3)])
def test_download_with_optional_flight(client,flight,pages):
    login(client);data=body(flight=flight)
    assert client.post('/api/preview',json=data).status_code==200
    response=client.post('/api/jobs',json=data);assert response.status_code==200,response.text
    key=response.json()['id'];job=wait_job(client,key)
    assert job['status']=='done',job
    assert job['files'][0]['pages']==pages
    assert job['files'][0]['name']=='IVANOV IVAN, PETROVA ANNA.pdf'
    pdf=client.get(job['files'][0]['download']);assert pdf.status_code==200
    assert len(PdfReader(io.BytesIO(pdf.content)).pages)==pages
    with zipfile.ZipFile(io.BytesIO(client.get(job['archive']).content)) as archive:
        assert archive.namelist()==['IVANOV IVAN, PETROVA ANNA.pdf']
    bot.send_document.assert_not_called()


def test_documents_sent_only_to_authenticated_user(client):
    login(client,101)
    data=body(deliver=True);data['chat_id']=999
    job=wait_job(client,client.post('/api/jobs',json=data).json()['id'])
    assert job['status']=='done' and job['sent']==1
    assert bot.send_document.call_args.kwargs['chat_id']==101
    assert bot.send_document.call_args.kwargs['document'].filename=='IVANOV IVAN, PETROVA ANNA.pdf'
    assert bot.send_document.call_args.kwargs['caption']=='📄 TEST VOUCHER\n🛏 Двухместный номер · 2 pax\n👥 IVANOV IVAN, PETROVA ANNA'
    edit_button=bot.send_document.call_args.kwargs['reply_markup'].inline_keyboard[0][0]
    assert edit_button.text=='Изменить этот ваучер'
    assert f"edit={job['id']}%3A0" in edit_button.web_app.url


def test_same_passenger_filenames_preserved_in_archive(client):
    login(client);data=body()
    data['voucher']['people']['rooms']*=2
    job=wait_job(client,client.post('/api/jobs',json=data).json()['id'])
    assert job['status']=='done',job
    expected='IVANOV IVAN, PETROVA ANNA.pdf'
    assert [file['name'] for file in job['files']]==[expected,expected]
    with zipfile.ZipFile(io.BytesIO(client.get(job['archive']).content)) as archive:
        names=archive.namelist()
        assert len(names)==len(set(names))==2
        assert all(PurePosixPath(name).name==expected for name in names)
        assert all(archive.read(name).startswith(b'%PDF') for name in names)


def test_edit_one_voucher_preserves_other_rooms_and_original_pdfs(client):
    login(client)
    data=body(flight=True)
    data['voucher']['people']['rooms'].append({'kind':'SGL','people':['SMIRNOV EGOR'],'adults':1})
    original=wait_job(client,client.post('/api/jobs',json=data).json()['id'])
    original_pdf=client.get(original['files'][1]['download']).content
    url=f"/api/jobs/{original['id']}/files/1/draft"
    draft=client.get(url).json()
    assert draft['voucher']['people']['rooms']==[data['voucher']['people']['rooms'][1]]
    assert draft['flight']['outbound']['number']=='DV 499' and draft['background']==1
    assert draft['request_id']!=data['request_id']
    draft['voucher']['hotel1']='Individual Hotel'
    draft['voucher']['meal']='Не включено'
    draft['deliver_to_chat']=True
    corrected=wait_job(client,client.post('/api/jobs',json=draft).json()['id'])
    assert corrected['status']=='done' and corrected['id']!=original['id']
    assert len(corrected['files'])==1 and corrected['sent']==1
    assert bot.send_document.call_args.kwargs['caption'].endswith('👥 SMIRNOV EGOR')
    assert client.get(url).json()['voucher']['hotel1']=='Valy Hotel'
    assert len(client.get('/api/jobs/'+original['id']).json()['files'])==2
    assert client.get(original['files'][1]['download']).content==original_pdf
    assert client.get(f"/api/jobs/{original['id']}/files/-1/draft").status_code==404
    assert client.get(f"/api/jobs/{original['id']}/files/2/draft").status_code==404
    login(client,999)
    assert client.get(url).status_code==404


def test_expired_voucher_cannot_be_opened_for_editing(client):
    login(client)
    job=wait_job(client,client.post('/api/jobs',json=body()).json()['id'])
    with auth.database() as db:
        db.execute('UPDATE jobs SET created=? WHERE id=?',(time.time()-86401,job['id']))
    assert client.get(f"/api/jobs/{job['id']}/files/0/draft").status_code==404


@pytest.mark.parametrize('with_return',[False,True])
def test_standalone_flight_pdf_without_hotels_and_its_edit_draft(client,with_return):
    login(client)
    data=body(flight=True,deliver=True)
    data.update(document_type='flight',voucher=None,title='FLIGHT ONLY')
    if with_return:
        data['flight']['inbound']={**data['flight']['outbound'],'origin':'MED','destination':'ALA',
                                  'departure_date':'2026-10-27','arrival_date':'2026-10-27'}
    preview=client.post('/api/preview',json=data)
    assert preview.status_code==200 and preview.json()['pages']==1
    job=wait_job(client,client.post('/api/jobs',json=data).json()['id'])
    assert job['status']=='done' and job['document_type']=='flight' and job['sent']==1
    assert len(job['files'])==1 and job['files'][0]['pages']==1
    pdf=client.get(job['files'][0]['download']).content
    assert len(PdfReader(io.BytesIO(pdf)).pages)==1
    draft=client.get(f"/api/jobs/{job['id']}/files/0/draft").json()
    assert draft['document_type']=='flight' and draft['voucher'] is None
    assert bool(draft['flight']['inbound'])==with_return
    assert bot.send_document.call_args.kwargs['caption'].startswith('📄 FLIGHT ONLY\n✈️ SCAT DV 499')
    draft['flight']['outbound']['number']='DV 999';draft['deliver_to_chat']=False
    corrected=wait_job(client,client.post('/api/jobs',json=draft).json()['id'])
    assert corrected['status']=='done' and corrected['document_type']=='flight'
    assert corrected['files'][0]['pages']==1
    assert client.get(f"/api/jobs/{job['id']}/draft").json()['flight']['outbound']['number']=='DV 499'


def test_document_requirements_and_history_owner_isolation(client):
    login(client)
    data=body();data['voucher']=None
    assert client.post('/api/jobs',json=data).status_code==422
    data['document_type']='flight'
    assert client.post('/api/jobs',json=data).status_code==422
    data=body(flight=True);data.update(document_type='flight',voucher=None)
    first=wait_job(client,client.post('/api/jobs',json=data).json()['id'])
    second=wait_job(client,client.post('/api/jobs',json=body()).json()['id'])
    history=client.get('/api/jobs').json()['jobs']
    assert [entry['id'] for entry in history]==[second['id'],first['id']]
    assert history[0]['document_type']=='voucher' and history[1]['document_type']=='flight'
    assert all('payload' not in entry and 'path' not in entry for entry in history)
    draft=client.get(f"/api/jobs/{first['id']}/draft").json()
    assert draft['document_type']=='flight' and draft['request_id']!=data['request_id']
    with auth.database() as db:
        db.execute('UPDATE jobs SET created=? WHERE id=?',(time.time()-86401,first['id']))
    assert [entry['id'] for entry in client.get('/api/jobs').json()['jobs']]==[second['id']]
    assert client.get(f"/api/jobs/{first['id']}/draft").status_code==404
    login(client,999)
    assert client.get('/api/jobs').json()['jobs']==[]
    assert client.get(f"/api/jobs/{second['id']}/draft").status_code==404


def test_saved_batch_draft_can_be_reopened_without_chat(client):
    login(client)
    data=body();data['voucher']['people']['rooms'].append({'kind':'SGL','people':['SMIRNOV EGOR'],'adults':1})
    job=wait_job(client,client.post('/api/jobs',json=data).json()['id'])
    draft=client.get(f"/api/jobs/{job['id']}/draft").json()
    assert len(draft['voucher']['people']['rooms'])==2
    assert draft['request_id']!=data['request_id']


def test_flight_options_from_same_schedule_as_legacy_chat(client,monkeypatch):
    from types import SimpleNamespace
    login(client)
    schedule=SimpleNamespace(title='расписание рейсов',get_all_values=lambda:[
        ['header'],['20.10.2026','KC263','08:00','11:00'],['27.10.2026','KC266','13:00','18:00']])
    source=SimpleNamespace(get_all_values=lambda:[['NIYET 7 DAYS','20/10/2026','27/10/2026']],
                           spreadsheet=SimpleNamespace(worksheets=lambda:[schedule]))
    monkeypatch.setattr(web,'snapshot',lambda *args:source)
    response=client.get('/api/flight-options',params={'month':'October 2026','sheet':'Flights'})
    assert response.status_code==200
    options=response.json()['options'];assert len(options)==1
    flight=options[0]['flight']
    assert flight['outbound']['number']=='KC263' and flight['outbound']['destination']=='MED'
    assert flight['inbound']['number']=='KC266' and flight['inbound']['origin']=='JED'
    assert flight['inbound']['departure_date']=='2026-10-27'
    data={'document_type':'flight','flight':flight,'title':options[0]['title'],'request_id':uuid.uuid4().hex,'deliver_to_chat':False}
    assert wait_job(client,client.post('/api/jobs',json=data).json()['id'])['status']=='done'
    source.spreadsheet=SimpleNamespace(worksheets=lambda:[])
    assert client.get('/api/flight-options',params={'month':'October 2026','sheet':'Flights'}).status_code==400
    def unavailable(*args):raise ConnectionError('offline')
    monkeypatch.setattr(web,'snapshot',unavailable)
    assert client.get('/api/flight-options',params={'month':'October 2026','sheet':'Flights'}).status_code==503


def test_retry_preserves_room_caption(client):
    login(client)
    bot.send_document.side_effect=[RuntimeError('offline'),None]
    job=wait_job(client,client.post('/api/jobs',json=body(deliver=True)).json()['id'])
    assert job['status']=='failed'
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code==200
    assert wait_job(client,job['id'])['status']=='done'
    captions=[call.kwargs['caption'] for call in bot.send_document.call_args_list]
    assert captions==['📄 TEST VOUCHER\n🛏 Двухместный номер · 2 pax\n👥 IVANOV IVAN, PETROVA ANNA']*2


def test_excluded_services_are_rendered_without_default_substitution(client,monkeypatch):
    from pligrim_bot.core.voucher import render
    original=render.draw_value
    values=[]
    def record(draw,text,*args,**kwargs):
        values.append(text)
        return original(draw,text,*args,**kwargs)
    monkeypatch.setattr(render,'draw_value',record)
    login(client)
    data=body()
    for key in ['service','transfer','meal','guide','excursions']:
        data['voucher'][key]='Не включено'
    job=wait_job(client,client.post('/api/jobs',json=data).json()['id'])
    assert job['status']=='done'
    assert values.count('Не включено')==5


def test_idempotency_and_other_user_cannot_download(client):
    login(client);data=body()
    first=client.post('/api/jobs',json=data).json()['id'];second=client.post('/api/jobs',json=data).json()['id']
    assert first==second
    job=wait_job(client,first)
    login(client,999)
    assert client.get('/api/jobs/'+first).status_code==404
    assert client.get(job['archive']).status_code==404
    assert client.get(job['files'][0]['download']).status_code==404


def test_incomplete_flight_and_dates_rejected(client):
    login(client);data=body(flight=True);data['flight']['outbound']['number']=''
    assert client.post('/api/jobs',json=data).status_code==422
    data=body();data['voucher']['dates1']='31/02/2026 – 23/10/2026'
    assert client.post('/api/jobs',json=data).status_code==400


def test_logout_revokes_bearer(client):
    token=login(client).json()['session_token']
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/me',headers={'Authorization':'Bearer '+token}).status_code==401


def test_bot_start_shows_webapp_button(monkeypatch):
    monkeypatch.setenv('WEBAPP_URL','https://voucherhickmet.duckdns.org')
    from pligrim_bot.config.keyboards import main_scenario_kb
    buttons=[b for row in main_scenario_kb().inline_keyboard for b in row]
    assert len(buttons)==1
    assert buttons[0].text=='Открыть Hickmet · Создать ваучер'
    assert buttons[0].web_app.url=='https://voucherhickmet.duckdns.org'


def test_native_telegram_download_link_supports_retries_and_expires(client):
    login(client)
    job=wait_job(client,client.post('/api/jobs',json=body()).json()['id'])
    link=client.post(f"/api/jobs/{job['id']}/download-link",json={'index':0})
    assert link.status_code==200
    path='/api/download/'+link.json()['url'].rsplit('/',1)[-1]
    client.cookies.clear()
    assert client.head(path).status_code==200
    response=client.get(path)
    assert response.status_code==200 and response.content.startswith(b'%PDF')
    assert response.headers['access-control-allow-origin']=='https://web.telegram.org'
    assert client.get(path).status_code==200
    partial=client.get(path,headers={'Range':'bytes=0-3'})
    assert partial.status_code==206 and partial.content==b'%PDF'
    with auth.database() as db:
        db.execute('UPDATE downloads SET expires=?',(time.time()-1,))
    assert client.get(path).status_code==410
