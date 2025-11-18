import os
from typing import List, Dict

from aiogram import types, F
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

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
):
    """
    Генерирует и отправляет ОДИН ваучер для конкретной комнаты/группы.
    Используется и при первичной отправке, и при пересборке после редактирования.
    """
    data = dict(base)

    names: List[str] = group.get("people") or []
    kind = (group.get("kind") or "").upper()
    human_ru = human_room(kind) if kind else ""

    data["pilgrims"] = names
    data["room1"] = data["room2"] = human_ru

    # 1️⃣ Красивая первая страница
    page1_png = render_voucher_page1_png(data)

    # 2️⃣ Имя файла по людям
    file_stem = build_filename_from_payload(data)
    pdf_path = os.path.join(TMP_DIR, f"{file_stem}.pdf")

    # 3️⃣ Собираем PDF
    build_voucher_pdf(
        page1_png,
        data.get("city1"),
        voucher.get("transfer"),
        pdf_path,
    )

    # 4️⃣ Подпись
    names_line = ", ".join(names) if names else "—"
    caption = (
        f"📄 {pkg_title}\n"
        f"🛏 {human_ru or 'Размещение не указано'} · {len(names)} pax\n"
        f"👥 {names_line}"
    )

    await message.answer_document(
        types.FSInputFile(pdf_path),
        caption=caption,
    )

    # 5️⃣ Чистим временные файлы
    try:
        os.remove(page1_png)
    except Exception:
        pass

    try:
        os.remove(pdf_path)
    except Exception:
        pass


async def start_after_voucher_menu(
        message: types.Message,
        pkg_title: str,
        voucher: dict,
        groups: List[dict],
        base: dict,
):
    """
    Вызывается после того, как ВСЕ ваучеры отправлены.
    Показывает две кнопки:
      ✏️ Внести изменения
      🔁 Начать заново
    И кладёт данные в кэш редактирования.
    """
    chat_id = message.chat.id

    EDIT_SESSIONS[chat_id] = {
        "pkg_title": pkg_title,
        "voucher": voucher,
        "groups": groups,
        "base": base,
    }

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Внести изменения в ваучер",
                    callback_data="palm_edit_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Начать заново",
                    callback_data="palm_restart",
                )
            ],
        ]
    )

    await message.answer(
        "Что вы хотите сделать дальше?",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "palm_edit_menu")
async def palm_edit_menu(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    sess = EDIT_SESSIONS.get(chat_id)
    if not sess or not sess.get("groups"):
        await callback.answer(
            "Нет данных для редактирования — отправьте ваучеры заново.",
            show_alert=True,
        )
        return

    groups: List[dict] = sess["groups"]

    text_lines = ["В какой ваучер хотите внести изменения?\n"]
    buttons = []

    for i, grp in enumerate(groups, start=1):
        kind = (grp.get("kind") or "").upper()
        pax = len(grp.get("people") or [])
        human_ru = human_room(kind)
        names_line = ", ".join(grp.get("people") or [])

        text_lines.append(
            f"{i}. {human_ru or kind or 'Комната'} ({pax} взр): {names_line}"
        )
        text_lines.append("")

        btn_text = f"{i}. {human_ru or kind or 'Комната'} ({pax} взр)"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=btn_text[:64],
                    callback_data=f"palm_edit_group:{i}",
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="palm_edit_back_root",
            )
        ]
    )

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = "\n".join(text_lines)

    # 🔧 Безопасное обновление: если нет текста – шлём новое сообщение
    if callback.message.text:
        await callback.message.edit_text(text, reply_markup=markup)
    else:
        await callback.message.answer(text, reply_markup=markup)

    await callback.answer()



@dp.callback_query(F.data == "palm_edit_back_root")
async def palm_edit_back_root(callback: CallbackQuery):
    """
    Возвращает к двум кнопкам: «внести изменения / начать заново».
    """
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Внести изменения в ваучер",
                    callback_data="palm_edit_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Начать заново",
                    callback_data="palm_restart",
                )
            ],
        ]
    )
    text = "Что вы хотите сделать дальше?"

    if callback.message.text:
        await callback.message.edit_text(text, reply_markup=kb)
    else:
        await callback.message.answer(text, reply_markup=kb)

    await callback.answer()



@dp.callback_query(F.data.startswith("palm_edit_group:"))
async def palm_edit_group(callback: CallbackQuery):
    """
    Выбрали конкретную комнату — показываем,
    что именно можно поменять.
    """
    chat_id = callback.message.chat.id
    sess = EDIT_SESSIONS.get(chat_id)
    if not sess or not sess.get("groups"):
        await callback.answer(
            "Сессия редактирования не найдена.", show_alert=True
        )
        return

    _, idx_str = callback.data.split(":", 1)
    idx = int(idx_str)

    groups: List[dict] = sess["groups"]
    if not (1 <= idx <= len(groups)):
        await callback.answer("Некорректный номер комнаты.", show_alert=True)
        return

    grp = groups[idx - 1]
    kind = (grp.get("kind") or "").upper()
    human_ru = human_room(kind)
    names_line = ", ".join(grp.get("people") or [])
    pax = len(grp.get("people") or [])

    text = (
        f"Вы выбрали:\n"
        f"{human_ru or kind or 'Комната'} · {pax} pax\n"
        f"{names_line}\n\n"
        "Что хотите изменить?"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Имена людей",
                    callback_data=f"palm_edit_field:names:{idx}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛏 Размещение",
                    callback_data=f"palm_edit_field:room:{idx}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗺 Экскурсии",
                    callback_data=f"palm_edit_field:excursions:{idx}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚐 Трансфер",
                    callback_data=f"palm_edit_field:transfer:{idx}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к списку",
                    callback_data="palm_edit_menu",
                )
            ],
        ]
    )

    if callback.message.text:
        await callback.message.edit_text(text, reply_markup=kb)
    else:
        await callback.message.answer(text, reply_markup=kb)

    await callback.answer()



@dp.callback_query(F.data.startswith("palm_edit_field:"))
async def palm_edit_field(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал, что редактировать:
      names / room / excursions / transfer
    """
    _, field, idx_str = callback.data.split(":", 2)
    idx = int(idx_str)

    await state.update_data(edit_field=field, group_idx=idx)

    prompts = {
        "names": "Введите новые имена паломников через запятую:",
        "room": "Введите новое размещение (например: DBL, TRPL, SGL):",
        "excursions": "Введите текст для поля 'Экскурсии':",
        "transfer": "Введите текст для поля 'Трансфер':",
    }

    await callback.message.answer(prompts.get(field, "Введите новое значение:"))
    await state.set_state(EditVoucherState.waiting_value)
    await callback.answer()


@dp.message(EditVoucherState.waiting_value)
async def palm_edit_value(message: types.Message, state: FSMContext):
    """
    Обрабатываем введённое новое значение, обновляем voucher,
    пересобираем payload и показываем ПРЕВЬЮ (картинка + текст),
    но сам PDF ещё не шлём — ждём подтверждения.
    """
    data_state = await state.get_data()
    field = data_state["edit_field"]
    group_idx = data_state["group_idx"]

    chat_id = message.chat.id
    sess = EDIT_SESSIONS.get(chat_id)
    if not sess or not sess.get("groups"):
        await message.answer("Сессия редактирования потеряна, начните заново.")
        await state.clear()
        return

    voucher = sess["voucher"]
    groups: List[dict] = sess["groups"]
    base = sess["base"]
    pkg_title = sess["pkg_title"]

    if not (1 <= group_idx <= len(groups)):
        await message.answer("Некорректный номер комнаты.")
        await state.clear()
        return

    grp = groups[group_idx - 1]
    text = message.text.strip()

    # --- применяем изменения ---
    if field == "names":
        names = [n.strip() for n in text.split(",") if n.strip()]
        if not names:
            await message.answer("Не удалось распознать имена, попробуйте ещё раз.")
            return
        grp["people"] = names

    elif field == "room":
        grp["kind"] = text.upper()

    elif field == "excursions":
        voucher["excursions"] = text

    elif field == "transfer":
        voucher["transfer"] = text

    # Обновляем плоский список имён внутри voucher
    flat = []
    for g in groups:
        flat.extend(g.get("people") or [])

    voucher.setdefault("people", {})["rooms"] = groups
    voucher["people"]["flat"] = flat
    voucher["_people_flat"] = flat

    # Пересобираем базовый payload (все поля обычного ваучера)
    base = base_payload_from(voucher)
    sess["base"] = base

    # --- Собираем данные для красивого превью ---
    kind = (grp.get("kind") or "").upper()
    human_ru = human_room(kind)
    names_line = ", ".join(grp.get("people") or []) or "—"

    city1    = base.get("city1") or ""
    hotel1   = base.get("hotel1") or ""
    dates1   = base.get("dates1") or ""
    stay1    = base.get("stay1") or ""
    city2    = base.get("city2") or ""
    hotel2   = base.get("hotel2") or ""
    dates2   = base.get("dates2") or ""
    stay2    = base.get("stay2") or ""
    service  = base.get("service") or ""
    transfer = base.get("transfer") or ""
    meal     = base.get("meal") or ""
    guide    = base.get("guide") or ""
    excursions = base.get("excursions") or ""
    tech_guide = base.get("tech_guide") or ""

    caption_lines = [
        "🧾 Превью обновлённого ваучера (без отправки)",
        f"Комната #{group_idx}: {human_ru or kind or 'Комната'}",
        f"Гости: {names_line}",
        "",
    ]

    if city1 or hotel1:
        caption_lines.append(f"🏙 {city1} · {hotel1}")
        if dates1 or stay1:
            caption_lines.append(f"   {dates1} · {stay1}")
    if city2 or hotel2:
        caption_lines.append(f"🏙 {city2} · {hotel2}")
        if dates2 or stay2:
            caption_lines.append(f"   {dates2} · {stay2}")

    if service:
        caption_lines.append(f"🧾 Услуги: {service}")
    if transfer:
        caption_lines.append(f"🚐 Трансфер: {transfer}")
    if excursions:
        caption_lines.append(f"🗺 Экскурсии: {excursions}")
    if meal:
        caption_lines.append(f"🍽 Питание: {meal}")
    if guide:
        caption_lines.append(f"👤 Гид: {guide}")
    if tech_guide:
        caption_lines.append(f"📞 Тех. поддержка: {tech_guide}")

    preview_caption = "\n".join(caption_lines)

    # Готовим payload для картинки-превью
    preview_data = dict(base)
    preview_data["pilgrims"] = grp.get("people") or []
    preview_data["room1"] = preview_data["room2"] = human_ru or kind or ""

    # Рендерим превью-страницу
    page1_png = render_voucher_page1_png(preview_data)

    # Клавиатура подтверждения
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📩 Отправить обновлённый ваучер",
                    callback_data=f"palm_edit_send:{group_idx}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить что-то ещё в этой комнате",
                    callback_data=f"palm_edit_group:{group_idx}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 К списку комнат",
                    callback_data="palm_edit_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Начать заново",
                    callback_data="palm_restart",
                )
            ],
        ]
    )

    # Шлём ПРЕВЬЮ (картинка + весь текст как в обычном ваучере)
    await message.answer_photo(
        types.FSInputFile(page1_png),
        caption=preview_caption,
        reply_markup=kb,
    )

    try:
        os.remove(page1_png)
    except Exception:
        pass

    await state.clear()



@dp.callback_query(F.data.startswith("palm_edit_send:"))
async def palm_edit_send(callback: CallbackQuery):
    """
    Отправляет уже обновлённый ваучер для выбранной комнаты
    после подтверждения.
    """
    chat_id = callback.message.chat.id
    sess = EDIT_SESSIONS.get(chat_id)
    if not sess or not sess.get("groups"):
        await callback.answer("Сессия редактирования не найдена.", show_alert=True)
        return

    _, idx_str = callback.data.split(":", 1)
    group_idx = int(idx_str)

    voucher = sess["voucher"]
    groups: List[dict] = sess["groups"]
    base = sess["base"]
    pkg_title = sess["pkg_title"]

    if not (1 <= group_idx <= len(groups)):
        await callback.answer("Некорректный номер комнаты.", show_alert=True)
        return

    grp = groups[group_idx - 1]

    # На всякий случай ещё раз пересобираем базовый payload
    base = base_payload_from(voucher)
    sess["base"] = base

    # Отправляем PDF ваучера
    await send_one_voucher_for_group(
        message=callback.message,
        pkg_title=pkg_title,
        voucher=voucher,
        base=base,
        group=grp,
        idx=group_idx,
    )

    # После отправки показываем корневое меню
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Продолжить редактирование",
                    callback_data="palm_edit_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Начать заново",
                    callback_data="palm_restart",
                )
            ],
        ]
    )

    await callback.message.answer(
        "✅ Обновлённый ваучер отправлен.\nЧто вы хотите сделать дальше?",
        reply_markup=kb,
    )
    await callback.answer()

