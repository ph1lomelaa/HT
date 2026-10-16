import asyncio
import copy
import os
import tempfile
from aiogram import F, types
from aiogram.types import FSInputFile,InlineKeyboardMarkup,InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State,StatesGroup
from pligrim_bot.config.constants import dp,TMP_DIR
from pligrim_bot.config.keyboards import citykey_for_value
from pligrim_bot.data.sessions import SessionCache
from pligrim_bot.core.voucher.builder import base_payload_from
from pligrim_bot.core.voucher.validation import apply_field,require_valid_voucher
from pligrim_bot.core.voucher.render import render_voucher_page1_png,build_voucher_pdf,build_filename_from_payload
from pligrim_bot.core.parsers.people_parser import human_room

EDIT_SESSIONS=SessionCache()
class EditVoucherState(StatesGroup):
    waiting_value=State()


def _effective(session,index):
    if not 1<=index<=len(session['groups']):raise ValueError('Группа не найдена')
    group=session['groups'][index-1]
    v=copy.deepcopy(session['voucher']);v.update(copy.deepcopy(group.get('overrides',{})))
    v['people']={'rooms':[copy.deepcopy(group)],'flat':list(group['people'])}
    return v


def _session(callback):
    sess=EDIT_SESSIONS.get(callback.message.chat.id)
    if not sess or sess.get('owner_id')!=callback.from_user.id:raise ValueError('Сессия устарела или принадлежит другому пользователю')
    return sess


def edit_voucher_fields_kb(chat_id,group_idx):
    sess=EDIT_SESSIONS.get(chat_id)
    if not sess:return InlineKeyboardMarkup(inline_keyboard=[])
    v=_effective(sess,group_idx);items=[]
    for i in (1,2):
        if v.get(f'city{i}'):
            key=citykey_for_value(v[f'city{i}'],str(i))
            for field,label in [('hotel','Отель'),('dates','Даты'),('checkin','Заезд')]:
                items.append((f'{label} ({v[f"city{i}"]})',f'{field}@{key}'))
    items += [('Размещение','room_type'),('Трансфер','transfer'),('Питание','meal'),('Гид','guide'),('Экскурсии','excursions'),('Тех. гид','tech_guide'),('Сервис','service')]
    rows=[[InlineKeyboardButton(text=label,callback_data=f'edit_field:{group_idx}:{field}')] for label,field in items]
    rows += [[InlineKeyboardButton(text='Отправить обновлённый ваучер',callback_data=f'send_edit:{group_idx}')],
             [InlineKeyboardButton(text='Назад к списку',callback_data='palm_edit_menu')]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_one_voucher_for_group(message,pkg_title,voucher,base,group,idx,bg_index=-1):
    effective=copy.deepcopy(voucher);effective.update(copy.deepcopy(group.get('overrides',{})))
    effective['people']={'rooms':[group],'flat':group.get('people',[])}
    require_valid_voucher(effective)
    data=base_payload_from(effective);data['pilgrims']=group['people']
    for i in (1,2):
        if data.get(f'city{i}'):data[f'room{i}']=human_room(group['kind'])
    def render(folder):
        png=render_voucher_page1_png(data)
        try:
            return build_voucher_pdf(png,data.get('city1'),data.get('transfer'),os.path.join(folder,'voucher.pdf'),bg_index)
        finally:
            if os.path.exists(png):os.unlink(png)
    with tempfile.TemporaryDirectory(prefix='voucher-',dir=TMP_DIR) as folder:
        pdf=await asyncio.to_thread(render,folder)
        name=f'{idx}_{build_filename_from_payload(data)}.pdf'
        from pligrim_bot.core.voucher.caption import voucher_caption
        await message.answer_document(FSInputFile(pdf,filename=name),caption=voucher_caption(pkg_title,group))


async def start_after_voucher_menu(message,pkg_title,voucher,groups,base,bg_index=-1):
    EDIT_SESSIONS[message.chat.id]={'pkg_title':pkg_title,'voucher':copy.deepcopy(voucher),'groups':copy.deepcopy(groups),'base':base,'bg_index':bg_index,'owner_id':voucher.get('_owner_id') or message.from_user.id}
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Изменить конкретный ваучер',callback_data='palm_edit_menu')],
        [InlineKeyboardButton(text='Создать ваучер',callback_data='palm_restart')]])
    await message.answer('Ваучеры отправлены. Что дальше?',reply_markup=kb)


@dp.callback_query(F.data=='palm_edit_menu')
async def palm_show_edit_list(callback):
    sess=_session(callback);rows=[]
    for i,g in enumerate(sess['groups'],1):
        rows.append([InlineKeyboardButton(text=f'#{i} {g["kind"]}: '+', '.join(g['people'])[:50],callback_data=f'edit_grp:{i}')])
    rows.append([InlineKeyboardButton(text='Создать ваучер',callback_data='palm_restart')])
    await callback.message.answer('Выберите ваучер:',reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await callback.answer()


@dp.callback_query(F.data.startswith('edit_grp:'))
async def edit_grp_clicked(callback):
    sess=_session(callback);index=int(callback.data.split(':')[1]);_effective(sess,index)
    await callback.message.answer(f'Редактирование ваучера #{index}',reply_markup=edit_voucher_fields_kb(callback.message.chat.id,index));await callback.answer()


@dp.callback_query(F.data.startswith('edit_field:'))
async def edit_voucher_field(callback,state:FSMContext):
    sess=_session(callback);_,index,field=callback.data.split(':',2);index=int(index);_effective(sess,index)
    await state.update_data(chat_id=callback.message.chat.id,group_idx=index,field=field)
    await state.set_state(EditVoucherState.waiting_value)
    await callback.message.answer('Введите новое значение. Даты: ДД/ММ/ГГГГ – ДД/ММ/ГГГГ.');await callback.answer()


@dp.message(EditVoucherState.waiting_value)
async def process_edit_value(message,state:FSMContext):
    data=await state.get_data();sess=EDIT_SESSIONS.get(message.chat.id)
    if not sess or sess.get('owner_id')!=message.from_user.id:
        await state.clear();await message.answer('Сессия устарела. Начните заново.');return
    if not message.text:
        await message.answer('Введите новое значение текстом.');return
    index=data['group_idx'];v=_effective(sess,index)
    try:apply_field(v,data['field'],message.text)
    except ValueError as exc:
        await message.answer(str(exc));return
    group=sess['groups'][index-1]
    group['kind']=v['people']['rooms'][0]['kind']
    group['overrides']={k:value for k,value in v.items() if k not in {'people','room_groups','_people_flat','source','warnings'}}
    await state.clear()
    await message.answer('Обновлён только выбранный ваучер.',reply_markup=edit_voucher_fields_kb(message.chat.id,index))


async def regenerate_and_send_voucher(message,chat_id,group_idx):
    sess=EDIT_SESSIONS.get(chat_id)
    if not sess:raise ValueError('Сессия устарела')
    v=_effective(sess,group_idx);group=sess['groups'][group_idx-1]
    await send_one_voucher_for_group(message,sess['pkg_title'],v,base_payload_from(v),group,group_idx,sess['bg_index'])


@dp.callback_query(F.data.startswith('send_edit:'))
async def send_updated_voucher(callback):
    _session(callback);index=int(callback.data.split(':')[1]);await callback.answer('Формирую документ…')
    await regenerate_and_send_voucher(callback.message,callback.message.chat.id,index)
