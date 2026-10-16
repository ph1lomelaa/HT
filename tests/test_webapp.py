import asyncio
import hashlib
import hmac
import io
import json
import time
import uuid
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
    pdf=client.get(job['files'][0]['download']);assert pdf.status_code==200
    assert len(PdfReader(io.BytesIO(pdf.content)).pages)==pages
    assert client.get(job['archive']).content[:2]==b'PK'
    bot.send_document.assert_not_called()


def test_documents_sent_only_to_authenticated_user(client):
    login(client,101)
    data=body(deliver=True);data['chat_id']=999
    job=wait_job(client,client.post('/api/jobs',json=data).json()['id'])
    assert job['status']=='done' and job['sent']==1
    assert bot.send_document.call_args.kwargs['chat_id']==101
    assert bot.send_document.call_args.kwargs['caption']=='📄 TEST VOUCHER\n🛏 Двухместный номер · 2 pax\n👥 IVANOV IVAN, PETROVA ANNA'


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
