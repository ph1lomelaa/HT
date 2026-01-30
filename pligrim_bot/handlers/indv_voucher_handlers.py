import time
from typing import List

from aiogram import F, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from pligrim_bot.config.constants import dp
from pligrim_bot.config.keyboards import preview_main_kb
from pligrim_bot.core.voucher.builder import base_payload_from
from pligrim_bot.core.voucher.render import (
    render_voucher_page1_png,
    build_voucher_pdf,
    build_filename_from_payload,
)
from pligrim_bot.handlers.preview_handlers import PREVIEW_CACHE, preview_text


class IndvVoucherState(StatesGroup):
    waiting_names = State()
    waiting_room = State()
    waiting_city1 = State()
    waiting_city2 = State()


@dp.callback_query(F.data == "indv_voucher_start")
async def indv_voucher_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания индивидуального ваучера"""
    print(" indv_voucher_start вызван!")
    await state.clear()
    await callback.message.answer(
        " *Индивидуальный ваучер*\n\n"
        "1️⃣ Введите имена паломников через запятую.\n"
        "Пример: `IVANOV IVAN, IVANOVA ANNA`",
        parse_mode="Markdown",
    )
    await state.set_state(IndvVoucherState.waiting_names)
    print(f" Состояние установлено: {await state.get_state()}")
    await callback.answer()


@dp.message(IndvVoucherState.waiting_names)
async def indv_voucher_names(message: types.Message, state: FSMContext):
    """Обработка ввода имён"""
    print(f" indv_voucher_names ВЫЗВАН! Текст: '{message.text}'")
    print(f" Тип сообщения: {message.content_type}")
    print(f" Текущее состояние: {await state.get_state()}")

    # Проверяем, что это текстовое сообщение
    if not message.text:
        print(" Сообщение не содержит текст")
        await message.answer("Пожалуйста, введите текстовые имена через запятую.")
        return

    raw = message.text
    names: List[str] = [n.strip() for n in raw.split(",") if n.strip()]

    print(f" Распознанные имена: {names}")

    if not names:
        await message.answer(" Не смогла разобрать имена, введите ещё раз через запятую.")
        return

    await state.update_data(names=names)
    print(f" Имена сохранены в состояние: {names}")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="DBL (2 чел)", callback_data="indv_room:dbl")],
            [InlineKeyboardButton(text="TRPL (3 чел)", callback_data="indv_room:trpl")],
            [InlineKeyboardButton(text="QUAD (4 чел)", callback_data="indv_room:quad")],
            [InlineKeyboardButton(text="SGL (1 чел)", callback_data="indv_room:sgl")],
        ]
    )

    await message.answer("2️⃣ Выберите размещение:", reply_markup=kb)
    await state.set_state(IndvVoucherState.waiting_room)
    print(f" Новое состояние установлено: {await state.get_state()}")

@dp.callback_query(F.data.startswith("indv_room:"))
async def indv_voucher_room(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа номера"""
    print(f" indv_voucher_room вызван! Callback: {callback.data}")
    _, kind = callback.data.split(":", 1)
    await state.update_data(room_kind=kind.upper())

    await callback.message.answer(
        "3️⃣ Введите первый город (как в ваучере, например `Madinah`)."
    )
    await state.set_state(IndvVoucherState.waiting_city1)
    await callback.answer()


@dp.message(IndvVoucherState.waiting_city1, F.text)
async def indv_voucher_city1(message: types.Message, state: FSMContext):
    """Обработка ввода первого города"""
    print(f" indv_voucher_city1 вызван! Текст: {message.text}")
    city1 = (message.text or "").strip()
    if not city1:
        await message.answer(" Город не распознан, введите ещё раз.")
        return

    await state.update_data(city1=city1)
    await message.answer(
        "4️⃣ Введите второй город (например `Makkah`).\n"
        "Если второго города нет — напишите просто `-`."
    )
    await state.set_state(IndvVoucherState.waiting_city2)


@dp.message(IndvVoucherState.waiting_city2, F.text)
async def indv_voucher_city2(message: types.Message, state: FSMContext):
    """Обработка ввода второго города и финальная генерация"""
    print(f" indv_voucher_city2 вызван! Текст: {message.text}")
    city2 = (message.text or "").strip()
    if city2 == "-":
        city2 = None

    data = await state.get_data()
    names: list[str] = data["names"]
    room_kind: str = data["room_kind"]
    city1: str = data["city1"]

    # Считаем, что все взрослые
    adults = len(names)

    voucher = {
        "city1": city1,
        "hotel1": None,
        "dates1": None,
        "stay1": None,
        "checkin1": "16:00",

        "city2": city2,
        "hotel2": None,
        "dates2": None,
        "stay2": None,
        "checkin2": "16:00",

        "service": "Виза и страховка",
        "meal": "Завтрак и ужин",
        "guide": "Групповой гид",
        "excursions": "Мекка, Медина",
        "transfer": "Автобус",
        "tech_guide": "+966 56 328 0325",
        "contacts": {
            "company": "Hickmet Group Saudi",
            "instagram": "@hickmet_travel",
            "email": "premium@hickmet.kz",
            "tech_guide": "+966 56 328 0325",
        },

        "kind": "manual",

        "people": {
            "rooms": [
                {
                    "kind": room_kind,
                    "count": len(names),
                    "people": names,
                    "adults": adults,
                }
            ],
            "flat": names,
        },

        "room_groups": [
            {
                "kind": room_kind,
                "count": len(names),
                "people": names,
                "adults": adults,
            }
        ],
        "_people_flat": names,
    }

    base = base_payload_from(voucher)

    cache_id = f"manual:{message.chat.id}:{int(time.time())}"
    PREVIEW_CACHE[cache_id] = {
        "voucher": voucher,
        "base": base,
        "pkg_title": "Индивидуальный ваучер",
        "mode": "manual",
    }

    text = preview_text(voucher)

    await message.answer(
        " *Проверьте данные перед отправкой ваучера:*\n\n" + text,
        reply_markup=preview_main_kb(cache_id),
        parse_mode="Markdown"
    )

    await state.clear()
    print(" Превью отправлено, состояние очищено")