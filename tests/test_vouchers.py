import asyncio
import copy
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pytest
from pypdf import PdfReader
from PIL import Image
from pligrim_bot.config import constants as C,settings,keyboards as K
import pligrim_bot.main
from pligrim_bot.core.parsers import people_parser as P,package_parser as PK
from pligrim_bot.core.voucher import builder as B,render as R
from pligrim_bot.core.voucher.validation import apply_field,voucher_errors
from pligrim_bot.core.utils.date_utils import norm_date_str,normalize_date_range
from pligrim_bot.handlers import preview_handlers as PV,indv_voucher_handlers as I,palm_edit_handlers as E,pilgrim_handlers as H
from pligrim_bot.data.sessions import CALLBACKS,resolve_callback,SessionCache
from aiogram.types import Message,User,Chat,CallbackQuery,Update

class Sheet:
    title='20.10-27.10'
    def __init__(self,rows):self.rows=rows;self.reads=0
    def get_all_values(self):self.reads+=1;return copy.deepcopy(self.rows)


def sheet_rows():
    return [['NIYET 7 DAYS 20.10-27.10'],['Last name','First name','Room type','Meal'],
            ['BROWN','AMALIA','DBL','HB'],['ANN-MARIE','MEDINA','','HB'],
            ['NIYET 7 DAYS'],['Madinah','Hotel A','20/10/2026','23/10/2026'],
            ['Makkah','Hotel B','23/10/2026','27/10/2026'],['Train MED-MAK']]


def voucher():
    v=PK.collect_voucher_by_package(Sheet(sheet_rows()),0)
    v['_owner_id']=101
    return v


def msg(text='test',uid=101):
    return Message(message_id=1,date=datetime.now(timezone.utc),chat=Chat(id=uid,type='private'),from_user=User(id=uid,is_bot=False,first_name='Test'),text=text).as_(C.bot)


def call(data,uid=101):
    return CallbackQuery(id='test',chat_instance='test',from_user=User(id=uid,is_bot=False,first_name='Test'),message=msg(uid=uid),data=data).as_(C.bot)


@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    C.PREVIEW_CACHE.clear();C.EDIT_STATE.clear();E.EDIT_SESSIONS.clear();CALLBACKS.clear()
    C.dp.fsm.storage.storage.clear()
    monkeypatch.setattr(R,'TMP_DIR',str(tmp_path));monkeypatch.setattr(E,'TMP_DIR',str(tmp_path))
    with patch.object(Message,'answer',new_callable=AsyncMock) as answer,patch.object(Message,'edit_text',new_callable=AsyncMock),patch.object(Message,'answer_document',new_callable=AsyncMock) as docs,patch.object(Message,'answer_media_group',new_callable=AsyncMock),patch.object(CallbackQuery,'answer',new_callable=AsyncMock):
        yield SimpleNamespace(answer=answer,docs=docs)


@pytest.mark.parametrize('name',['BROWN','SMART','AMALIA','ANN-MARIE',"O’NEILL",'ЖАН-ПОЛЬ','MEDINA','ARTUR','KAMALATDIN'])
def test_real_names(name):assert P.is_valid_name(name)


@pytest.mark.parametrize('headers',[['Name','Room type'],['ФИО','Тип номера'],['Last name','First name','Room type']])
def test_headers(headers):
    cols=P.detect_people_header(headers)
    assert cols and 'meal' not in cols


@pytest.mark.parametrize('kind,capacity',[('SGL',1),('DBL',2),('TWIN',2),('TRPL',3),('QUAD',4)])
def test_rooms(kind,capacity):
    rows=[['header']]+[['IVANOV','IVAN',kind if i==0 else '','HB'] for i in range(capacity*2)]
    p=P.collect_people_groups(rows,0,{'last':0,'first':1,'room':2,'meal':3},len(rows))
    assert len(p['rooms'])==2 and len(p['flat'])==capacity*2


def test_infant_stays_with_adults():
    rows=[[],['IVANOV','IVAN','DBL','HB'],['PETROVA','ANNA','','HB'],['IVANOV','EGOR','','INF']]
    p=P.collect_people_groups(rows,0,{'last':0,'first':1,'room':2,'meal':3},4)
    assert len(p['rooms'])==1 and p['rooms'][0]['count']==3 and p['rooms'][0]['adults']==2


def test_explicit_room_starts_new_room():
    rows=[[],['IVANOV','IVAN','DBL'],['PETROVA','ANNA','DBL']]
    assert len(P.collect_people_groups(rows,0,{'last':0,'first':1,'room':2},3)['rooms'])==2


@pytest.mark.parametrize('value,expected',[('05/11/26','05.11.2026'),('2026-11-05','05.11.2026'),('31.02.2026',None),('29.02.2024','29.02.2024'),('29.02.2026',None)])
def test_dates(value,expected):assert norm_date_str(value)==expected


def test_dates_recompute_and_swap():
    v=voucher();apply_field(v,'dates@madinah','20.10.26 - 25.10.26');assert v['stay1_nights']==5
    apply_field(v,'dates@makkah','18/10/2026 – 20/10/2026');assert v['city1']=='Makkah' and v['stay1_nights']==2 and v['stay2_nights']==5
    with pytest.raises(ValueError):apply_field(v,'dates@makkah','23/10/2026 – 20/10/2026')


@pytest.mark.parametrize('city',['Madinah','Medinah','Medina','Madina','Медина','Мадина'])
def test_city_aliases(city):assert R.pick_page2_bg(city,'Поезд')==R.JED_MED_TRAIN_PATH


def test_one_snapshot_and_full_names():
    ws=Sheet(sheet_rows());v=PK.collect_voucher_by_package(ws,0)
    assert ws.reads==1 and v['_people_flat']==['BROWN AMALIA','ANN-MARIE MEDINA']
    assert not voucher_errors(v)


def test_second_package_does_not_use_first_hotels():
    rows=sheet_rows()+[['NIYET 7 DAYS 01.11-08.11'],['Last name','First name','Room type'],['IVANOV','IVAN','SGL'],['NIYET'],['Madinah','Hotel C','01/11/2026','04/11/2026'],['Makkah','Hotel D','04/11/2026','08/11/2026']]
    v=PK.collect_voucher_by_package(Sheet(rows),8)
    assert v['hotel1']=='Hotel C' and v['dates1'].startswith('01/11/2026')


def test_duplicate_titles_remain_distinct():
    rows=sheet_rows()[:4]+[[]]+sheet_rows()[:4]
    packages=PK.find_palm_packages(Sheet(rows))
    assert len(packages)==2 and packages[0]['row']!=packages[1]['row']


def test_missing_guests_and_room_do_not_crash():
    rows=sheet_rows();rows[2]=['','','',''];rows[3]=['','','','']
    assert 'Нет паломников' in voucher_errors(PK.collect_voucher_by_package(Sheet(rows),0))
    rows=sheet_rows();rows[2][2]=''
    v=PK.collect_voucher_by_package(Sheet(rows),0)
    assert len(v['_people_flat'])==2 and any('размещение' in e for e in voucher_errors(v))


def test_no_cross_package_guest_fallback():
    rows=sheet_rows()[:2]+[[]]+[['HIKMA 20.10-27.10'],['Name','Room type'],['IVANOV IVAN','SGL']]
    v=PK.collect_voucher_by_package(Sheet(rows),0)
    assert not v['_people_flat']


def test_ambiguous_config_is_not_guessed():
    rows=sheet_rows()+[['NIYET'],['Madinah','Other A','20/10/2026','23/10/2026'],['Makkah','Other B','23/10/2026','27/10/2026']]
    v=PK.collect_voucher_by_package(Sheet(rows),0)
    assert not v['hotel1'] and v['warnings']


def test_short_callbacks_and_exact_titles():
    title='20.10-27.10: Паломники Алматы NIYET 7 DAYS'*3
    kb=K.build_palm_packages_kb('October 2026',title,[{'title':'NIYET','row':4}])
    payload=kb.inline_keyboard[0][0].callback_data
    assert len(payload.encode())<=64
    assert resolve_callback(payload,'palm_pkg')==('October 2026',title,4,'NIYET')


def test_expiring_cache(monkeypatch):
    now=[0.0];monkeypatch.setattr('pligrim_bot.data.sessions.time.monotonic',lambda:now[0])
    cache=SessionCache(ttl=10,maxsize=2);cache['a']=1;cache['b']=2;cache['c']=3
    assert cache.get('a') is None
    now[0]=11;assert cache.get('c') is None


@pytest.mark.parametrize('design',[0,1,2])
def test_actual_pdf_generation(design,tmp_path):
    v=voucher();p=B.base_payload_from(v);p['pilgrims']=v['_people_flat']
    png=R.render_voucher_page1_png(p);pdf=tmp_path/'sample.pdf'
    R.build_voucher_pdf(png,p['city1'],p['transfer'],str(pdf),design)
    assert len(PdfReader(pdf).pages)==2


def test_large_family_long_hotel_and_unique_paths():
    p=B.base_payload_from(voucher());p['pilgrims']=['IVANOV IVAN']*6;p['hotel1']='GRAND ROYAL HOTEL '*8
    a=R.render_voucher_page1_png(p);b=R.render_voucher_page1_png(p)
    assert a!=b
    with Image.open(a) as image:assert image.width>0


def test_manual_dispatcher_end_to_end(isolate):
    async def run():
        async def feed(data=None,text=None):
            update=Update(update_id=1,callback_query=call(data)) if data else Update(update_id=1,message=msg(text))
            await C.dp.feed_update(C.bot,update)
        await feed(text='/start')
        assert any(b.callback_data=='indv_voucher_start' for row in isolate.answer.call_args.kwargs['reply_markup'].inline_keyboard for b in row)
        await feed(data='indv_voucher_start');await feed(text='IVANOV IVAN, PETROVA ANNA')
        state=C.dp.fsm.get_context(bot=C.bot,chat_id=101,user_id=101)
        assert await state.get_state()==I.IndvVoucherState.waiting_room.state
        await feed(data='indv_room:dbl');await feed(text='Madinah');await feed(text='Makkah')
        key=next(iter(C.PREVIEW_CACHE));assert ':' not in key
        for field,value in [('hotel@madinah','Hotel A'),('dates@madinah','20/10/2026 – 23/10/2026'),('hotel@makkah','Hotel B'),('dates@makkah','23/10/2026 – 27/10/2026')]:
            await feed(data=f'pv_field:{key}:{field}');await feed(text=value)
        await feed(data=f'pv_send:{key}');await feed(data=f'sel_bg:{key}:1')
        assert isolate.docs.await_count==1
        await feed(data=f'sel_bg:{key}:1');assert isolate.docs.await_count==1
        await feed(data='edit_field:1:hotel@madinah');await feed(text='Updated Hotel')
        await feed(data='send_edit:1');assert isolate.docs.await_count==2
        await feed(data='palm_restart');assert await state.get_state() is None
    asyncio.run(run())


def test_owner_and_incomplete_send(isolate):
    async def run():
        C.PREVIEW_CACHE['owned']={'owner_id':101,'chat_id':101,'voucher':voucher(),'pkg_title':'AUDIT'}
        await PV.pv_cancel(call('pv_cancel:owned',999));assert C.PREVIEW_CACHE.get('owned')
        await H.on_background_selected(call('sel_bg:owned:0',101));assert isolate.docs.await_count==1
        with pytest.raises(ValueError):await H.send_vouchers_for_package(msg(),'EMPTY',{'people':{'rooms':[]}},0)
    asyncio.run(run())


def test_group_edits_are_isolated_and_files_cleaned(isolate,tmp_path):
    async def run():
        v=voucher();groups=copy.deepcopy(v['people']['rooms']);groups.append(copy.deepcopy(groups[0]));v['people']['rooms']=groups
        await E.start_after_voucher_menu(msg(),'AUDIT',v,groups,B.base_payload_from(v))
        st=C.dp.fsm.get_context(bot=C.bot,chat_id=101,user_id=101)
        await E.edit_voucher_field(call('edit_field:1:hotel@madinah'),st)
        await E.process_edit_value(msg('Changed Hotel'),st)
        sess=E.EDIT_SESSIONS.get(101)
        assert E._effective(sess,1)['hotel1']=='Changed Hotel'
        assert E._effective(sess,2)['hotel1']=='Hotel A'
        await E.regenerate_and_send_voucher(msg(),101,1)
        assert not list(tmp_path.iterdir())
    asyncio.run(run())


def test_nontext_and_cancel_during_edit(isolate):
    async def run():
        v=voucher();await E.start_after_voucher_menu(msg(),'AUDIT',v,v['people']['rooms'],B.base_payload_from(v))
        st=C.dp.fsm.get_context(bot=C.bot,chat_id=101,user_id=101)
        await E.edit_voucher_field(call('edit_field:1:hotel@madinah'),st)
        await E.process_edit_value(msg().model_copy(update={'text':None}),st)
        assert await st.get_state()==E.EditVoucherState.waiting_value.state
        await C.dp.feed_update(C.bot,Update(update_id=1,message=msg('/cancel')))
        assert await st.get_state() is None
    asyncio.run(run())


def test_full_package_dispatcher_flow(isolate,monkeypatch):
    async def run():
        monkeypatch.setattr(H,'_load',lambda *args:Sheet(sheet_rows()))
        await C.dp.feed_update(C.bot,Update(update_id=1,callback_query=call(K.build_palm_packages_kb('October 2026','20.10-27.10',[{'row':0,'title':sheet_rows()[0][0]}]).inline_keyboard[0][0].callback_data)))
        key=next(iter(C.PREVIEW_CACHE))
        await C.dp.feed_update(C.bot,Update(update_id=2,callback_query=call(f'pv_send:{key}')))
        await C.dp.feed_update(C.bot,Update(update_id=3,callback_query=call(f'sel_bg:{key}:2')))
        assert isolate.docs.await_count==1
    asyncio.run(run())


def test_flight_schedule_and_ticket(tmp_path):
    from pligrim_bot.handlers.flight_handlers import _flight_pairs
    pairs=_flight_pairs([['NIYET 7 DAYS','20/10/2026','27/10/2026']]);assert len(pairs)==1
    schedule=Sheet([['header'],['20.10.2026','KC263','08:00','11:00'],['27.10.2026','KC266','13:00','18:00']])
    maps=B.build_maps_smart(schedule);v=B.assemble_voucher(*maps,pairs[0][1],pairs[0][2],'AMJA')
    png=tmp_path/'flight.png';R.generate_ticket(str(png),v)
    assert len(PdfReader(R.generate_pdf_from_png(str(png))).pages)==1


def test_refresh_keeps_imported_dictionary_references(monkeypatch):
    from datetime import date
    monkeypatch.setattr(settings,'current_date',lambda:date(2026,10,16))
    original=settings.PALM_SHEETS
    monkeypatch.setattr(settings,'get_all_accessible_sheets',lambda:{'OCTOBER 2026':'fake'})
    try:
        settings.refresh_sheets();assert settings.PALM_SHEETS is original and K.PALM_SHEETS.get('October 2026')=='fake'
    finally:settings.PALM_SHEETS.clear();settings.ALL_SHEETS.clear()


def test_month_filter_is_optional_and_explicit(monkeypatch):
    from datetime import date
    monkeypatch.setattr(settings,'current_date',lambda:date(2025,12,1))
    sheets={'FEBRUARY 2026':'feb','JUNE 2026':'jun','DECEMBER 2025':'dec'}
    monkeypatch.setattr(settings,'EXCLUDED_PILGRIM_MONTHS',set())
    assert set(settings.detect_pilgrim_months(sheets))=={'February 2026','June 2026','December 2025'}
    monkeypatch.setattr(settings,'EXCLUDED_PILGRIM_MONTHS',{'February 2026','December 2025'})
    assert settings.detect_pilgrim_months(sheets)=={'June 2026':'jun'}


def test_current_and_future_months_sorted_across_year_boundary(monkeypatch):
    from datetime import date
    monkeypatch.setattr(settings,'EXCLUDED_PILGRIM_MONTHS',set())
    sheets={'JANUARY 2027':'jan','SEPTEMBER 2026':'sep','OCTOBER 2026':'oct',
            'DECEMBER 2025':'old','NOVEMBER 2026':'nov','DECEMBER 2026':'dec'}
    assert list(settings.detect_pilgrim_months(sheets,as_of=date(2026,10,16)))==[
        'October 2026','November 2026','December 2026','January 2027']
    assert settings.detect_pilgrim_months(sheets,as_of=date(2027,1,1))=={'January 2027':'jan'}


def test_cached_bot_menu_hides_month_after_rollover(monkeypatch):
    from datetime import date
    monkeypatch.setattr(settings,'PALM_SHEETS',{'October 2026':'oct','November 2026':'nov'})
    monkeypatch.setattr(settings,'current_date',lambda:date(2026,11,1))
    rows=K.get_palm_month_buttons().inline_keyboard
    assert [row[0].text for row in rows]==['November 2026','Обновить таблицы']

@pytest.mark.parametrize('header',['First/Last Name','ФИО / Full name','First name / Имя','Last name\nФамилия'])
def test_combined_and_bilingual_headers(header):assert P.detect_people_header([header,'Room type'])


def test_same_kind_different_hotel_variants():
    rows=sheet_rows();rows[0]=['IZI SWISSOTEL 20.10-27.10'];rows[4]=['IZI'];rows[6][1]='SWISSOTEL'
    rows += [['IZI'],['Madinah','ROTANA','20/10/2026','23/10/2026'],['Makkah','FAIRMONT','23/10/2026','27/10/2026']]
    assert PK.collect_voucher_by_package(Sheet(rows),0)['hotel2']=='SWISSOTEL'


def test_guests_after_configuration_not_included():
    rows=sheet_rows()+[['IVANOV','IVAN','DBL','HB']]
    assert len(PK.collect_voucher_by_package(Sheet(rows),0)['_people_flat'])==2


def test_room_capacity_when_service_marker_is_in_room_cell():
    rows=[[],['IVANOV','IVAN','DBL'],['PETROVA','ANNA',''],['SMIRNOV','EGOR','HB']]
    groups=P.collect_people_groups(rows,0,{'last':0,'first':1,'room':2},4)['rooms']
    assert [g['adults'] for g in groups]==[2,1]


def test_configuration_year_is_checked():
    ws=Sheet(sheet_rows());ws.spreadsheet=SimpleNamespace(title='OCTOBER 2027')
    assert not PK.collect_voucher_by_package(ws,0)['hotel1']


def test_retry_does_not_duplicate_successful_rooms(isolate,monkeypatch):
    async def run():
        v=voucher();v['people']['rooms']*=2
        sent=set();calls=[]
        async def fake(message,title,voucher,base,group,index,bg):
            calls.append(index)
            if index==2 and calls.count(2)==1:raise RuntimeError('network disconnected')
        monkeypatch.setattr(H,'send_one_voucher_for_group',fake)
        with pytest.raises(RuntimeError):await H.send_vouchers_for_package(msg(),'AUDIT',v,0,sent)
        await H.send_vouchers_for_package(msg(),'AUDIT',v,0,sent)
        assert calls==[1,2,2] and sent=={1,2}
    asyncio.run(run())


def test_flight_dispatcher_end_to_end(isolate,monkeypatch):
    from pligrim_bot.handlers import flight_handlers as F
    async def run():
        packages=Sheet([['NIYET 7 DAYS','20/10/2026','27/10/2026']]);packages.title='Рейсы с пакетами'
        schedule=Sheet([['header'],['20.10.2026','KC263','08:00','11:00'],['27.10.2026','KC266','13:00','18:00']]);schedule.title='расписание рейсов'
        ss=SimpleNamespace(worksheets=lambda:[packages,schedule])
        async def document(name):return ss
        monkeypatch.setattr(F,'_document',document)
        from pligrim_bot.data.sessions import callback_ref
        await C.dp.feed_update(C.bot,Update(update_id=1,callback_query=call(callback_ref('fsheet','October 2026',packages.title))))
        payload=isolate.answer.call_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data
        await C.dp.feed_update(C.bot,Update(update_id=2,callback_query=call(payload)))
        assert isolate.docs.await_count==1
    asyncio.run(run())


def test_two_digit_year_package_dates():
    rows=sheet_rows();rows[0]=['NIYET 20.10.26-27.10.26']
    assert PK.collect_voucher_by_package(Sheet(rows),0)['hotel1']=='Hotel A'


def test_family_label_repeated_on_both_city_rows():
    rows=sheet_rows()[:4]+[['NIYET','Madinah','Hotel A','20/10/2026','23/10/2026'],['NIYET','Makkah','Hotel B','23/10/2026','27/10/2026']]
    v=PK.collect_voucher_by_package(Sheet(rows),0)
    assert v['hotel1']=='Hotel A' and v['hotel2']=='Hotel B'


def test_standard_spelling_variants():
    rows=sheet_rows();rows[0]=['NIYET STANDARD 20.10-27.10'];rows[4]=['NIYET STANDART']
    assert PK.collect_voucher_by_package(Sheet(rows),0)['hotel1']=='Hotel A'


def test_changed_package_button_does_not_select_another_tour(monkeypatch):
    async def run():
        monkeypatch.setattr(H,'_load',lambda *args:Sheet(sheet_rows()))
        payload=K.build_palm_packages_kb('October 2026','sheet',[{'row':0,'title':'OLD PACKAGE'}]).inline_keyboard[0][0].callback_data
        with pytest.raises(ValueError):await H.palm_pkg_clicked(call(payload))
        assert not C.PREVIEW_CACHE
    asyncio.run(run())
