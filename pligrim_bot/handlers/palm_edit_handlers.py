import os
from typing import List, Dict

from aiogram import types, F
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile
)
from aiogram.fsm.state import StatesGroup, State

from pligrim_bot.config.constants import TMP_DIR, dp
from pligrim_bot.core.parsers.people_parser import human_room
from pligrim_bot.core.voucher.builder import base_payload_from
from pligrim_bot.core.voucher.render import (
    render_voucher_page1_png,
    build_voucher_pdf,
    build_filename_from_payload,
)

# Глобальный кэш сессий редактирования: ключ — chat_id
EDIT_SESSIONS: Dict[int, Dict] = {}

class EditVoucherState(StatesGroup):
    waiting_value = State()


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
        [InlineKeyboardButton(text="✏️ Редактировать конкретный ваучер", callback_data="palm_edit_menu")],
        [InlineKeyboardButton(text="🔁 Начать заново (выбор месяца)", callback_data="palm_restart")]
    ])

    await message.answer("✅ Все ваучеры отправлены.\nХотите внести изменения?", reply_markup=kb)


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

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="palm_restart")])

    await callback.message.edit_text("Выберите, чей ваучер исправить:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@dp.callback_query(F.data.startswith("edit_grp:"))
async def edit_grp_clicked(callback: CallbackQuery):
    # Тут должна быть ваша логика показа полей для редактирования.
    # Оставляю заглушку, так как вы этот код не присылали в последнем запросе,
    # но он у вас должен быть в старых версиях.
    await callback.answer("Здесь открывается меню полей (Отель, Даты и т.д.)")