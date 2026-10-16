"""Flight vouchers with explicit document context in every callback."""
import asyncio
import os
import tempfile
from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from pligrim_bot.config.constants import dp,TMP_DIR
from pligrim_bot.config import settings
from pligrim_bot.config.keyboards import main_scenario_kb,get_palm_month_buttons,button,markup
from pligrim_bot.data.sessions import SessionCache,callback_ref,resolve_callback
from pligrim_bot.core.google_sheets import find_worksheet_by_title
from pligrim_bot.core.voucher.builder import build_maps_smart,assemble_voucher
from pligrim_bot.core.voucher.render import generate_ticket,generate_pdf_from_png
from pligrim_bot.core.parsers.flight_parser import flight_pairs as _flight_pairs

USER_SHEETS_CACHE=SessionCache()

@dp.message(Command('start','cancel'))
async def start_handler(message,state:FSMContext):
    from pligrim_bot.handlers.palm_restart_handlers import reset_user
    payload=(message.text or '').partition(' ')[2].strip()
    if payload.startswith('web_'):
        from pligrim_bot.handlers.webapp_handlers import show_login_confirmation
        await show_login_confirmation(message,payload[4:]);return
    await reset_user(message.from_user.id,message.chat.id,state)
    await message.answer('Ассаляму алейкум! Откройте Hickmet, чтобы создать ваучер.',reply_markup=main_scenario_kb())


@dp.callback_query(F.data.startswith('scenario:'))
async def choose_scenario(callback):
    if callback.data=='scenario:palm':
        kb=get_palm_month_buttons()
    else:
        kb=markup([[button(name,callback_ref('fmonth',name))] for name in settings.ALL_SHEETS])
    await callback.message.answer('Выберите таблицу:',reply_markup=kb);await callback.answer()


async def _document(name):
    return await asyncio.to_thread(lambda:settings.get_google_client().open_by_key(settings.ALL_SHEETS[name]))


@dp.callback_query(F.data.startswith('fmonth:'))
async def sheet_selected(callback):
    name,=resolve_callback(callback.data,'fmonth');await callback.answer()
    ss=await _document(name);sheets=await asyncio.to_thread(ss.worksheets)
    rows=[[button(ws.title[:80],callback_ref('fsheet',name,ws.title))] for ws in sheets if 'расписание' not in ws.title.lower()]
    await callback.message.answer('Выберите лист с пакетами и датами:',reply_markup=markup(rows))


@dp.callback_query(F.data.startswith('fsheet:'))
async def package_selected(callback):
    name,title=resolve_callback(callback.data,'fsheet');await callback.answer()
    ss=await _document(name)
    def load():
        ws=find_worksheet_by_title(ss,title)
        schedules=[s for s in ss.worksheets() if 'расписание' in s.title.lower()]
        if not schedules:raise ValueError('В таблице не найден лист «расписание рейсов»')
        return _flight_pairs(ws.get_all_values()),build_maps_smart(schedules[0])
    pairs,maps=await asyncio.to_thread(load)
    rows=[]
    for package,dep,ret in pairs:
        for token in ('AJJA','AJMA','AMJA','AMMA'):
            data=assemble_voucher(*maps,dep,ret,token)
            if data:
                rows.append([button(f'{package[:25]} {dep} → {ret} {token}',callback_ref('fdate',data,package,callback.from_user.id,callback.message.chat.id))])
    if not rows:raise ValueError('Не найдены пары дат с подходящими рейсами в расписании')
    await callback.message.answer('Выберите пакет, даты и маршрут:',reply_markup=markup(rows))


@dp.callback_query(F.data.startswith('fdate:'))
async def flight_date_selected(callback):
    data,package,owner,chat=resolve_callback(callback.data,'fdate')
    if owner!=callback.from_user.id or chat!=callback.message.chat.id:raise ValueError('Этот ваучер принадлежит другому пользователю')
    await callback.answer('Готовлю документ…')
    with tempfile.TemporaryDirectory(prefix='flight-',dir=TMP_DIR) as folder:
        def render():
            png=os.path.join(folder,'flight.png');generate_ticket(png,data)
            return generate_pdf_from_png(png)
        pdf=await asyncio.to_thread(render)
        await callback.message.answer_document(FSInputFile(pdf,filename='flight_voucher.pdf'),caption=package[:1000])


def get_available_sheets():
    return list(settings.ALL_SHEETS)
