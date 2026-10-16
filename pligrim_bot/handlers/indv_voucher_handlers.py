import uuid
from typing import List

from aiogram import F, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from pligrim_bot.config.constants import dp
from pligrim_bot.config.keyboards import preview_main_kb
from pligrim_bot.core.voucher.builder import base_payload_from
from pligrim_bot.core.parsers.people_parser import is_valid_name
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
    await state.clear()
    await callback.message.answer(
        " *Индивидуальный ваучер*\n\n"
        "1️⃣ Введите имена паломников через запятую.\n"
        "Пример: `IVANOV IVAN, IVANOVA ANNA`",
        parse_mode="Markdown",
    )
    await state.set_state(IndvVoucherState.waiting_names)
    await callback.answer()


@dp.message(IndvVoucherState.waiting_names)
async def indv_voucher_names(message: types.Message, state: FSMContext):
    """Обработка ввода имён"""

    # Проверяем, что это текстовое сообщение
    if not message.text:
        await message.answer("Пожалуйста, введите текстовые имена через запятую.")
        return

    raw = message.text
    names: List[str] = [n.strip() for n in raw.split(",") if n.strip()]


    if not names or len(names)>100 or any(not is_valid_name(n) or len(n)>120 for n in names):
        await message.answer(" Не смогла разобрать имена, введите ещё раз через запятую.")
        return

    await state.update_data(names=names)

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

@dp.callback_query(IndvVoucherState.waiting_room, F.data.startswith("indv_room:"))
async def indv_voucher_room(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа номера"""
    _, kind = callback.data.split(":", 1)
    if kind not in {"dbl","trpl","quad","sgl","twin"}:
        await callback.answer("Неизвестное размещение"); return
    await state.update_data(room_kind=kind.upper())

    await callback.message.answer(
        "3️⃣ Введите первый город (как в ваучере, например `Madinah`)."
    )
    await state.set_state(IndvVoucherState.waiting_city1)
    await callback.answer()


@dp.message(IndvVoucherState.waiting_city1, F.text)
async def indv_voucher_city1(message: types.Message, state: FSMContext):
    """Обработка ввода первого города"""
    city1 = (message.text or "").strip()
    if not city1 or len(city1)>80:
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
    city2 = (message.text or "").strip()
    if not city2 or len(city2)>80:
        await message.answer("Введите город или дефис, если второго города нет.");return
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

    capacity={"SGL":1,"DBL":2,"TWIN":2,"TRPL":3,"QUAD":4}[room_kind]
    rooms=[{"kind":room_kind,"people":names[i:i+capacity],"count":len(names[i:i+capacity]),"adults":len(names[i:i+capacity])} for i in range(0,len(names),capacity)]
    voucher['people']['rooms']=rooms
    voucher['room_groups']=rooms
    voucher['_owner_id']=message.from_user.id
    base = base_payload_from(voucher)

    cache_id = uuid.uuid4().hex[:16]
    PREVIEW_CACHE[cache_id] = {
        "voucher": voucher,
        "base": base,
        "pkg_title": "Индивидуальный ваучер",
        "mode": "manual",
        "owner_id": message.from_user.id,
        "chat_id": message.chat.id,
    }

    text = preview_text(voucher)

    await message.answer(
        "Проверьте данные перед отправкой ваучера:\n\n" + text,
        reply_markup=preview_main_kb(cache_id)
    )

    await state.clear()
