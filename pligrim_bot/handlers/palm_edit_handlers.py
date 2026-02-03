import os
import re
from typing import List, Dict

from aiogram import types, F
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from pligrim_bot.config.constants import TMP_DIR, dp
from pligrim_bot.config.keyboards import slot_for_city, citykey_for_value
from pligrim_bot.core.parsers.people_parser import human_room
from pligrim_bot.core.utils.validation import city_ru
from pligrim_bot.core.voucher.builder import base_payload_from, ensure_chronological_city_order, nights_from_dates
from pligrim_bot.core.voucher.render import (
    render_voucher_page1_png,
    build_voucher_pdf,
    build_filename_from_payload,
    plural_nights,
)

# Глобальный кэш сессий редактирования: ключ — chat_id
EDIT_SESSIONS: Dict[int, Dict] = {}

class EditVoucherState(StatesGroup):
    waiting_value = State()


def edit_voucher_fields_kb(chat_id: int, group_idx: int) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора поля редактирования конкретного ваучера.
    """
    sess = EDIT_SESSIONS.get(chat_id)
    if not sess:
        return InlineKeyboardMarkup(inline_keyboard=[])

    voucher = sess["voucher"]
    c1 = city_ru(voucher.get("city1") or "")
    c2 = city_ru(voucher.get("city2") or "")

    has_city1 = bool(voucher.get("city1"))
    has_city2 = bool(voucher.get("city2"))

    items = []

    # Кнопки для первого города
    if has_city1:
        citykey1 = citykey_for_value(voucher.get("city1"), "1")
        items.append((f" Отель ({c1})", f"hotel@{citykey1}"))
        items.append((f" Даты ({c1})", f"dates@{citykey1}"))
        items.append((f"⏰ Чек-ин ({c1})", f"checkin@{citykey1}"))

    # Кнопки для второго города
    if has_city2:
        citykey2 = citykey_for_value(voucher.get("city2"), "2")
        items.append((f" Отель ({c2})", f"hotel@{citykey2}"))
        items.append((f" Даты ({c2})", f"dates@{citykey2}"))
        items.append((f"⏰ Чек-ин ({c2})", f"checkin@{citykey2}"))

    # Остальные сервисные кнопки
    items.extend([
        (" Трансфер", "transfer"),
        (" Питание", "meal"),
        (" Гид", "guide"),
        (" Экскурсии", "excursions"),
        (" Тех. гид", "tech_guide"),
        ("️ Сервис", "service"),
    ])

    rows = []
    for i in range(0, len(items), 2):
        row = []
        for j in (i, i+1):
            if j < len(items):
                txt, key = items[j]
                # callback: edit_field:GROUP_IDX:FIELD
                row.append(InlineKeyboardButton(text=txt, callback_data=f"edit_field:{group_idx}:{key}"))
        rows.append(row)

    rows.append([InlineKeyboardButton(text="Отправить обновленный ваучер", callback_data=f"send_edit:{group_idx}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="palm_edit_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def send_one_voucher_for_group(
        message: types.Message,
        pkg_title: str,
        voucher: dict,
        base: dict,
        group: dict,
        idx: int,
        bg_index: int = -1
):
    """
    Генерирует и отправляет ОДИН ваучер для конкретной комнаты/группы.
    """
    data = dict(base)

    names: List[str] = group.get("people") or []
    kind = (group.get("kind") or "").upper()
    human_ru = human_room(kind) if kind else ""

    data["pilgrims"] = names
    if human_ru:
        data["room1"] = human_ru
        data["room2"] = human_ru

    # 1. Рендерим PNG
    p1_path = render_voucher_page1_png(data)

    # 2. Формируем имя файла
    raw_name = build_filename_from_payload(data)
    # Добавляем idx, чтобы файлы не перезатирались, если имена одинаковые
    pdf_name = f"{idx}_{raw_name}.pdf"
    pdf_path = os.path.join(TMP_DIR, pdf_name)

    # 3. Собираем PDF с выбранным фоном
    build_voucher_pdf(
        page1_png=p1_path,
        city1=data.get("city1"),
        transfer_raw=data.get("transfer"),
        out_pdf_path=pdf_path,
        bg_index=bg_index
    )

    # --- ФОРМИРУЕМ КРАСИВУЮ ПОДПИСЬ (CAPTION) ---

    # Переводим тип комнаты на русский для красоты
    room_label = kind # Если не найдем, оставим как есть (QUAD)
    if "QUAD" in kind: room_label = "Четырёхместный номер"
    elif "TRIP" in kind: room_label = "Трёхместный номер"
    elif "DOUB" in kind or "DBL" in kind: room_label = "Двухместный номер"
    elif "SING" in kind or "SGL" in kind: room_label = "Одноместный номер"
    elif "5" in kind: room_label = "Пятиместный номер"

    pax_count = len(names)
    names_str = ", ".join(names)

    # Собираем текст
    caption = (
        f"📄 {pkg_title}\n"
        f"🛏 {room_label} · {pax_count} pax\n"
        f"👥 {names_str}"
    )

    # 4. Отправляем документ
    doc = FSInputFile(pdf_path)
    # Важно: parse_mode="HTML" не обязателен, если нет жирного шрифта,
    # но caption будет выглядеть аккуратно благодаря переносам строк.
    await message.answer_document(doc, caption=caption)


async def start_after_voucher_menu(
        message: types.Message,
        pkg_title: str,
        voucher: dict,
        groups: list,
        base: dict,
        bg_index: int = -1
):
    """
    Запускает меню «Что дальше?» (Редактировать / Заново)
    """
    chat_id = message.chat.id

    # Сохраняем сессию
    EDIT_SESSIONS[chat_id] = {
        "pkg_title": pkg_title,
        "voucher": voucher,
        "groups": groups,
        "base": base,
        "bg_index": bg_index
    }

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить конкретного паломника", callback_data="palm_edit_menu")],
        [InlineKeyboardButton(text="Создать ваучер", callback_data="palm_restart")]
    ])

    await message.answer("Все ваучеры отправлены.\nЧто дальше?", reply_markup=kb)


@dp.callback_query(F.data == "palm_edit_menu")
async def palm_show_edit_list(callback: CallbackQuery):
    """Показывает список комнат для редактирования"""
    sess = EDIT_SESSIONS.get(callback.message.chat.id)
    if not sess:
        await callback.answer("Сессия истекла", show_alert=True)
        return

    groups = sess["groups"]
    rows = []
    for i, grp in enumerate(groups, 1):
        ppl = ", ".join(grp.get("people", []))
        # В кнопке оставляем короткий вариант
        btn_text = f"#{i} {grp.get('kind')} ({ppl[:15]}..)"
        rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"edit_grp:{i}")])

    rows.append([InlineKeyboardButton(text="Создать ваучер", callback_data="palm_restart")])

    await callback.message.edit_text("Выберите, чей ваучер исправить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("edit_grp:"))
async def edit_grp_clicked(callback: CallbackQuery):
    """Показывает меню полей для редактирования выбранного ваучера"""
    sess = EDIT_SESSIONS.get(callback.message.chat.id)
    if not sess:
        await callback.answer("Сессия истекла", show_alert=True)
        return

    # Получаем индекс группы
    group_idx = int(callback.data.split(":")[1])

    # Сохраняем в сессию, какую группу редактируем
    sess["editing_group_idx"] = group_idx

    groups = sess["groups"]
    if group_idx < 1 or group_idx > len(groups):
        await callback.answer(" Группа не найдена", show_alert=True)
        return

    group = groups[group_idx - 1]
    ppl = ", ".join(group.get("people", []))

    await callback.message.edit_text(
        f"️ Редактирование ваучера #{group_idx}\n"
        f" {ppl}\n\n"
        f"Выберите поле для изменения:",
        reply_markup=edit_voucher_fields_kb(callback.message.chat.id, group_idx)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_field:"))
async def edit_voucher_field(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора конкретного поля для редактирования"""
    try:
        _, group_idx_str, field = callback.data.split(":", 2)
        group_idx = int(group_idx_str)
    except ValueError:
        await callback.answer(" Ошибка формата данных", show_alert=True)
        return

    sess = EDIT_SESSIONS.get(callback.message.chat.id)
    if not sess:
        await callback.answer("Сессия истекла", show_alert=True)
        return

    # Сохраняем в state, что редактируем
    await state.update_data(
        chat_id=callback.message.chat.id,
        group_idx=group_idx,
        field=field
    )
    await state.set_state(EditVoucherState.waiting_value)

    # Формируем подсказку для пользователя
    pretty_map = {
        "hotel": "Отель",
        "dates": "Даты в формате DD/MM/YYYY – DD/MM/YYYY",
        "checkin": "Чек-ин, например 16:00",
        "transfer": "Трансфер (например: Поезд, Автобус)",
        "meal": "Питание (например: Завтрак и ужин)",
        "guide": "Гид (например: Групповой гид)",
        "excursions": "Экскурсии (например: Мекка, Медина)",
        "tech_guide": "Технический гид (например: +966 56 328 0325)",
        "service": "Сервис (например: Виза и страховка)",
    }

    base = field.split("@")[0]
    city = field.split("@")[1] if "@" in field else None

    city_labels = {
        "madinah": " (Медина)",
        "makkah": " (Мекка)",
        "1": " (Город 1)",
        "2": " (Город 2)"
    }
    city_label = city_labels.get(city, "")

    await callback.message.answer(
        f"️ Введите новое значение для: {pretty_map.get(base, field)}{city_label}"
    )
    await callback.answer()


@dp.message(EditVoucherState.waiting_value)
async def process_edit_value(message: types.Message, state: FSMContext):
    """Обработчик ввода нового значения для поля"""
    data = await state.get_data()
    chat_id = data.get("chat_id")
    group_idx = data.get("group_idx")
    field = data.get("field")

    sess = EDIT_SESSIONS.get(chat_id)
    if not sess:
        await message.answer("️ Сессия устарела. Начните заново.")
        await state.clear()
        return

    voucher = sess["voucher"]
    new_val = message.text.strip()

    # Обработка поля
    base = field.split("@")[0]
    citykey = field.split("@")[1] if "@" in field else None

    # Нормализация дат
    if base == "dates":
        m = re.findall(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})', new_val)
        if len(m) >= 2:
            def _mk(t):
                d, mth, y = t
                y = ("20" + y) if len(y) == 2 else y
                return f"{d.zfill(2)}/{mth.zfill(2)}/{y}"
            new_val = f"{_mk(m[0])} – {_mk(m[1])}"

    # Определяем конечное поле (slot)
    if base in ("hotel", "dates", "checkin") and citykey:
        slot = slot_for_city(voucher, citykey)
        if slot is None:
            # Если город не найден, создаем его
            if citykey in ["madinah", "1"]:
                slot = 1
                voucher["city1"] = "Медина" if citykey == "madinah" else "Город 1"
            else:
                slot = 2
                voucher["city2"] = "Мекка" if citykey == "makkah" else "Город 2"

        key = f"{base}{slot}"
    else:
        key = base  # service/meal/guide/excursions/tech_guide/transfer

    # Применяем изменение
    voucher[key] = new_val

    # Если правили даты — пересчитываем порядок и ночи
    if base == "dates":
        nights_count = nights_from_dates(new_val)
        slot_key = key.replace("dates", "")  # получаем "1" или "2"
        voucher[f"stay{slot_key}_nights"] = nights_count
        voucher[f"stay{slot_key}"] = plural_nights(nights_count)
        ensure_chronological_city_order(voucher)

    # Обновляем сессию
    EDIT_SESSIONS[chat_id]["voucher"] = voucher

    await message.answer(
        "✅ Значение обновлено! Можно изменить еще поля или отправить обновленный ваучер.",
        reply_markup=edit_voucher_fields_kb(chat_id, group_idx)
    )

    # Очищаем состояние
    await state.clear()


async def regenerate_and_send_voucher(message: types.Message, chat_id: int, group_idx: int):
    """Пересоздает и отправляет обновленный ваучер для конкретной группы"""
    sess = EDIT_SESSIONS.get(chat_id)
    if not sess:
        await message.answer("️ Сессия не найдена.")
        return

    pkg_title = sess["pkg_title"]
    voucher = sess["voucher"]
    groups = sess["groups"]
    base = base_payload_from(voucher)
    bg_index = sess.get("bg_index", -1)

    if group_idx < 1 or group_idx > len(groups):
        await message.answer(" Группа не найдена")
        return

    group = groups[group_idx - 1]

    await message.answer(f"🔄 Пересоздаю ваучер #{group_idx}...")

    # Отправляем обновленный ваучер
    await send_one_voucher_for_group(
        message, pkg_title, voucher, base, group, group_idx, bg_index=bg_index
    )

    await message.answer("✅ Обновленный ваучер отправлен!")


@dp.callback_query(F.data.startswith("send_edit:"))
async def send_updated_voucher(callback: CallbackQuery):
    try:
        _, group_idx_str = callback.data.split(":", 1)
        group_idx = int(group_idx_str)
    except ValueError:
        await callback.answer("Ошибка формата", show_alert=True)
        return

    chat_id = callback.message.chat.id
    await regenerate_and_send_voucher(callback.message, chat_id, group_idx)
    await callback.message.answer(
        "Можете продолжить редактировать этот ваучер или выбрать другой:",
        reply_markup=edit_voucher_fields_kb(chat_id, group_idx)
    )
    await callback.answer()
