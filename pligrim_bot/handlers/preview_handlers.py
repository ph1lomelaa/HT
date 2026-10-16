from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from pligrim_bot.config.constants import *
from pligrim_bot.config.keyboards import slot_for_city, preview_main_kb, citykey_for_value
from pligrim_bot.core.utils.validation import city_ru
from pligrim_bot.core.voucher.builder import ensure_chronological_city_order, base_payload_from, nights_from_dates
from pligrim_bot.core.voucher.render import plural_nights
from pligrim_bot.handlers.palm_edit_handlers import start_after_voucher_menu, EDIT_SESSIONS


def edit_fields_kb(cache_id: str) -> InlineKeyboardMarkup:
    v = PREVIEW_CACHE.get(cache_id, {}).get("voucher", {})
    c1 = city_ru(v.get("city1") or "")
    c2 = city_ru(v.get("city2") or "")

    # Если города не указаны, показываем общие кнопки для добавления
    has_city1 = bool(v.get("city1"))
    has_city2 = bool(v.get("city2"))

    items = []

    # Кнопки для первого города (всегда показываем)
    if has_city1:
        citykey1 = citykey_for_value(v.get("city1"), "1")
        items.append((f" Отель ({c1})", f"hotel@{citykey1}"))
        items.append((f" Даты ({c1})", f"dates@{citykey1}"))
        items.append((f"⏰ Чек-ин ({c1})", f"checkin@{citykey1}"))
    else:
        items.append((f" Добавить город 1", f"add_city@1"))

    # Кнопки для второго города (всегда показываем)
    if has_city2:
        citykey2 = citykey_for_value(v.get("city2"), "2")
        items.append((f" Отель ({c2})", f"hotel@{citykey2}"))
        items.append((f" Даты ({c2})", f"dates@{citykey2}"))
        items.append((f"⏰ Чек-ин ({c2})", f"checkin@{citykey2}"))
    else:
        items.append((f" Добавить город 2", f"add_city@2"))

    # Остальные сервисные кнопки
    items.extend([
        (" Размещение", "room_type"),
        (" Трансфер",   "transfer"),
        (" Питание",    "meal"),
        (" Гид",        "guide"),
        (" Экскурсии",  "excursions"),
        (" Тех. гид",   "tech_guide"),
        ("️ Сервис",    "service"),
    ])

    rows = []
    for i in range(0, len(items), 2):
        row = []
        for j in (i, i+1):
            if j < len(items):
                txt, key = items[j]
                row.append(InlineKeyboardButton(text=txt, callback_data=f"pv_field:{cache_id}:{key}"))
        rows.append(row)

    rows.append([InlineKeyboardButton(text="⬅️ Назад к превью", callback_data=f"pv_back:{cache_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def preview_text(voucher):
    from pligrim_bot.core.voucher.validation import voucher_errors
    lines=['Проверьте данные перед отправкой ваучеров:']
    for i in (1,2):
        if voucher.get(f'city{i}'):
            lines.append(f"{voucher.get(f'city{i}')} | {voucher.get(f'hotel{i}') or 'отель не указан'}\n{voucher.get(f'dates{i}') or 'даты не указаны'} | Заезд: {voucher.get(f'checkin{i}') or '16:00'}")
    for key,label in [('meal','Питание'),('transfer','Трансфер'),('guide','Гид'),('excursions','Экскурсии')]:
        lines.append(f"{label}: {voucher.get(key) or '—'}")
    rooms=voucher.get('people',{}).get('rooms',[])
    lines.append(f"Паломников: {sum(len(r.get('people',[])) for r in rooms)}; комнат: {len(rooms)}")
    errors=voucher_errors(voucher)
    if errors: lines.append('Нужно заполнить:\n• '+'\n• '.join(errors))
    return '\n\n'.join(lines)


from aiogram.filters import Filter
from pligrim_bot.core.voucher.validation import apply_field
from pligrim_bot.core.utils.date_utils import normalize_date_range

class WaitingPreviewInput(Filter):
    async def __call__(self,message):
        return bool(message.from_user and EDIT_STATE.get(message.from_user.id))


@dp.message(WaitingPreviewInput(), F.text & ~F.text.startswith('/'))
async def pv_text_input(message):
    st=EDIT_STATE.get(message.from_user.id)
    data=PREVIEW_CACHE.get(st['cache_id']) if st else None
    if not data:
        EDIT_STATE.pop(message.from_user.id,None)
        await message.answer('Сессия устарела. Начните заново.'); return
    if data.get('owner_id')!=message.from_user.id or data.get('chat_id')!=message.chat.id:
        await message.answer('Эта сессия принадлежит другому пользователю.');return
    v=data['voucher'];field=st['field'];value=message.text.strip()
    try:
        if field.startswith('add_city@'):
            slot=int(field.split('@')[1]);parts=[p.strip() for p in value.split('|')]
            if len(parts) not in (3,4) or not parts[0] or not parts[1]:
                raise ValueError('Формат: город | отель | даты | время заезда')
            dates=normalize_date_range(parts[2]);checkin=parts[3] if len(parts)==4 else '16:00'
            import re
            if not re.fullmatch(r'(?:[01]?\d|2[0-3]):[0-5]\d',checkin):raise ValueError('Проверьте время заезда')
            v.update({f'city{slot}':parts[0],f'hotel{slot}':parts[1],f'dates{slot}':dates,f'checkin{slot}':checkin})
            ensure_chronological_city_order(v)
        else: apply_field(v,field,value)
    except ValueError as exc:
        await message.answer(str(exc));return
    data.pop('sent',None);data.pop('sent_groups',None)
    EDIT_STATE.pop(message.from_user.id,None)
    await message.answer(preview_text(v),reply_markup=preview_main_kb(st['cache_id']))


async def _preview(callback):
    key=callback.data.split(':',1)[1]
    data=PREVIEW_CACHE.get(key)
    if not data or data.get('owner_id')!=callback.from_user.id or data.get('chat_id')!=callback.message.chat.id:
        await callback.answer('Сессия устарела или принадлежит другому пользователю',show_alert=True)
        return key,None
    return key,data


@dp.callback_query(F.data.startswith('pv_cancel:'))
async def pv_cancel(callback):
    key,data=await _preview(callback)
    if not data:return
    PREVIEW_CACHE.pop(key,None);EDIT_STATE.pop(callback.from_user.id,None)
    await callback.message.answer('Отменено. Начните заново через /start.');await callback.answer()


@dp.callback_query(F.data.startswith('pv_back:'))
async def pv_back(callback):
    key,data=await _preview(callback)
    if not data:return
    EDIT_STATE.pop(callback.from_user.id,None)
    await callback.message.answer(preview_text(data['voucher']),reply_markup=preview_main_kb(key));await callback.answer()


@dp.callback_query(F.data.startswith('pv_edit:'))
async def pv_edit(callback):
    key,data=await _preview(callback)
    if not data:return
    await callback.message.answer('Что хотите изменить?',reply_markup=edit_fields_kb(key));await callback.answer()


@dp.callback_query(F.data.startswith('pv_field:'))
async def pv_field(callback):
    _,key,field=callback.data.split(':',2)
    data=PREVIEW_CACHE.get(key)
    if not data or data.get('owner_id')!=callback.from_user.id or data.get('chat_id')!=callback.message.chat.id:
        await callback.answer('Сессия устарела или принадлежит другому пользователю',show_alert=True);return
    EDIT_STATE[callback.from_user.id]={'cache_id':key,'field':field}
    prompt=('Формат: город | отель | ДД/ММ/ГГГГ – ДД/ММ/ГГГГ | ЧЧ:ММ' if field.startswith('add_city@')
            else 'Введите новое значение. Даты: ДД/ММ/ГГГГ – ДД/ММ/ГГГГ; размещение: SGL/DBL/TWIN/TRPL/QUAD.')
    await callback.message.answer(prompt);await callback.answer()
