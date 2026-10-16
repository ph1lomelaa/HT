import asyncio
import uuid
from aiogram import F, types
from aiogram.types import InputMediaPhoto, FSInputFile
from pligrim_bot.config.constants import dp, PREVIEW_CACHE, EDIT_STATE
from pligrim_bot.config import settings
from pligrim_bot.config.keyboards import get_palm_month_buttons,get_palm_sheet_buttons,build_palm_packages_kb,preview_main_kb,choose_background_kb
from pligrim_bot.data.sessions import resolve_callback
from pligrim_bot.core.google_sheets import find_worksheet_by_title
from pligrim_bot.core.parsers.package_parser import find_palm_packages,collect_voucher_by_package
from pligrim_bot.core.voucher.builder import base_payload_from
from pligrim_bot.core.voucher.validation import require_valid_voucher
from pligrim_bot.core.voucher.render import AVAILABLE_BACKGROUNDS
from pligrim_bot.handlers.palm_edit_handlers import send_one_voucher_for_group,start_after_voucher_menu


def _load(month,title):
    with settings._lock:
        ss=settings.get_google_client().open_by_key(settings.PALM_SHEETS[month])
        ws=find_worksheet_by_title(ss,title)
        rows=ws.get_all_values()
        class Snapshot:
            def get_all_values(self):return rows
        snap=Snapshot();snap.title=ws.title;snap.spreadsheet=ss
        return snap


def _owned(call,key):
    data=PREVIEW_CACHE.get(key)
    if not data or data.get('owner_id')!=call.from_user.id or data.get('chat_id')!=call.message.chat.id:
        raise ValueError('Сессия устарела или принадлежит другому пользователю')
    return data


@dp.callback_query(F.data=='get_month_buttons')
async def show_month_buttons(callback):
    await callback.message.answer('Выберите месяц:',reply_markup=get_palm_month_buttons());await callback.answer()


@dp.callback_query(F.data=='refresh_sheets')
async def refresh(callback):
    await callback.answer('Обновляю таблицы…')
    await asyncio.to_thread(settings.refresh_sheets)
    await callback.message.answer('Выберите месяц:',reply_markup=get_palm_month_buttons())


@dp.callback_query(F.data.startswith('palm_month:'))
async def palm_month_selected(callback):
    await callback.answer()
    month=callback.data.split(':',1)[1]
    kb,_=await asyncio.to_thread(get_palm_sheet_buttons,month)
    await callback.message.answer(f'Месяц: {month}. Выберите лист:',reply_markup=kb)


@dp.callback_query(F.data.startswith('palm_show_all:'))
async def palm_show_all_sheets(callback):
    await callback.answer()
    kb,_=await asyncio.to_thread(get_palm_sheet_buttons,callback.data.split(':',1)[1],True)
    await callback.message.answer('Все листы:',reply_markup=kb)


@dp.callback_query(F.data=='palm_back_to_months')
async def palm_back_to_months(callback):
    await show_month_buttons(callback)


@dp.callback_query(F.data.startswith('palm_sheet:'))
async def palm_sheet_selected(callback):
    month,title=resolve_callback(callback.data,'palm_sheet');await callback.answer()
    ws=await asyncio.to_thread(_load,month,title)
    packages=find_palm_packages(ws)
    if not packages:
        await callback.message.answer('Не найдены таблицы паломников. Проверьте заголовки ФИО / Last name / First name.');return
    await callback.message.answer(f'Лист: {title}. Выберите пакет:',reply_markup=build_palm_packages_kb(month,title,packages))


@dp.callback_query(F.data.startswith('palm_pkg:'))
async def palm_pkg_clicked(callback):
    month,title,row,expected_title=resolve_callback(callback.data,'palm_pkg');await callback.answer('Готовлю превью…')
    ws=await asyncio.to_thread(_load,month,title)
    packages=find_palm_packages(ws);p=next((p for p in packages if p['row']==row),None)
    if not p or p['title']!=expected_title:raise ValueError('Пакет изменился. Выберите его заново.')
    voucher=await asyncio.to_thread(collect_voucher_by_package,ws,row,p['title'])
    voucher['_owner_id']=callback.from_user.id
    key=uuid.uuid4().hex[:16]
    PREVIEW_CACHE[key]={'voucher':voucher,'pkg_title':p['title'],'owner_id':callback.from_user.id,'chat_id':callback.message.chat.id}
    from pligrim_bot.handlers.preview_handlers import preview_text
    await callback.message.answer(f"Пакет: {p['title']}\nЛист: {title}\n\n"+preview_text(voucher),reply_markup=preview_main_kb(key))


@dp.callback_query(F.data.startswith('pv_send:'))
async def on_preview_send_ask_bg(call):
    key=call.data.split(':',1)[1];data=_owned(call,key)
    require_valid_voucher(data['voucher']);await call.answer()
    media=[InputMediaPhoto(media=FSInputFile(path),caption=f'Вариант {i+1}') for i,path in enumerate(AVAILABLE_BACKGROUNDS)]
    await call.message.answer_media_group(media=media)
    await call.message.answer('Выберите дизайн:',reply_markup=choose_background_kb(key))


@dp.callback_query(F.data.startswith('sel_bg:'))
async def on_background_selected(call):
    _,key,index=call.data.rsplit(':',2);data=_owned(call,key)
    index=int(index)
    if index not in range(len(AVAILABLE_BACKGROUNDS)):raise ValueError('Неизвестный дизайн')
    if data.get('sent'):
        await call.answer('Ваучеры уже отправлены. Используйте меню редактирования.');return
    if data.get('sending'):
        await call.answer('Документы уже формируются');return
    require_valid_voucher(data['voucher'])
    data['sending']=True
    await call.answer('Формирую документы…')
    try:
        await send_vouchers_for_package(call.message,data['pkg_title'],data['voucher'],index,data.setdefault('sent_groups',set()))
        data['sent']=True
    finally:data['sending']=False


async def send_vouchers_for_package(message,pkg_title,voucher,bg_index=-1,sent_groups=None):
    require_valid_voucher(voucher)
    groups=voucher['people']['rooms'];base=base_payload_from(voucher)
    sent_groups=sent_groups if sent_groups is not None else set()
    for i,group in enumerate(groups,1):
        if i in sent_groups:continue
        await send_one_voucher_for_group(message,pkg_title,voucher,base,group,i,bg_index)
        sent_groups.add(i)
        if i<len(groups):await asyncio.sleep(.05)
    await start_after_voucher_menu(message,pkg_title,voucher,groups,base,bg_index)
