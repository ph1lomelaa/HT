import asyncio
import uuid
import os
import traceback
import re

from aiogram import types, F
from aiogram.types import CallbackQuery, InputMediaPhoto, FSInputFile

# --- Импорты глобальных объектов ---
from pligrim_bot.config.constants import dp, PREVIEW_CACHE

# --- Импорты клавиатур и настроек ---
from pligrim_bot.config.keyboards import (
    get_palm_sheet_buttons, preview_main_kb, build_palm_packages_kb,
    get_palm_month_buttons, choose_background_kb
)
from pligrim_bot.config.settings import client, PALM_SHEETS

# --- ИСПРАВЛЕННЫЕ ИМПОРТЫ ---
from pligrim_bot.core.google_sheets import find_worksheet_by_title
# find_palm_packages берем отсюда:
from pligrim_bot.core.parsers.package_parser import collect_voucher_by_package, find_palm_packages

from pligrim_bot.core.voucher.builder import ensure_chronological_city_order, base_payload_from
from pligrim_bot.core.voucher.render import (
    AVAILABLE_BACKGROUNDS, pick_page2_bg
)
from pligrim_bot.handlers.flight_handlers import USER_SHEETS_CACHE
from pligrim_bot.handlers.palm_edit_handlers import send_one_voucher_for_group, start_after_voucher_menu


# =========================================================================
# 1. ЛОГИКА ВЫБОРА ФОНА (Картинки -> Выбор -> Рассылка)
# =========================================================================

@dp.callback_query(F.data.startswith("pv_send:"))
async def on_preview_send_ask_bg(call: CallbackQuery):
    """
    1. Показывает 3 картинки (варианты фона).
    2. Просит нажать 1, 2 или 3.
    """
    try:
        cache_id = call.data.split(":")[1]

        media_group = []
        for i, path in enumerate(AVAILABLE_BACKGROUNDS):
            if os.path.exists(path):
                # Подпись только под первой картинкой
                caption = "🎨 Выберите вариант дизайна (1, 2 или 3)" if i == 0 else None
                media_group.append(InputMediaPhoto(media=FSInputFile(path), caption=caption))

        if not media_group:
            await call.answer("❌ Ошибка: файлы фонов не найдены", show_alert=True)
            return

        # Отправляем альбом
        await call.message.answer_media_group(media=media_group)

        # Отправляем кнопки
        await call.message.answer(
            "Нажмите кнопку, соответствующую картинке выше:",
            reply_markup=choose_background_kb(cache_id)
        )
        await call.answer()
    except Exception as e:
        print(f"Error in pv_send: {e}")
        await call.answer("Произошла ошибка при отправке превью")


@dp.callback_query(F.data.startswith("sel_bg:"))
async def on_background_selected(call: CallbackQuery):
    """
    Пользователь нажал цифру (выбрал фон).
    Запускаем рассылку ваучеров всем паломникам с этим фоном.
    """
    try:
        # data format: sel_bg:CACHE_ID:INDEX
        parts = call.data.split(":")
        cache_id = parts[1]
        bg_index = int(parts[2])

        data = PREVIEW_CACHE.get(cache_id)
        if not data:
            await call.message.edit_text("⏳ Данные устарели. Начните заново.")
            return

        voucher = data["voucher"]
        pkg_title = data["pkg_title"]

        await call.message.edit_text(f"⏳ Генерирую ваучеры (Дизайн {bg_index + 1})...")

        # ВЫЗЫВАЕМ ФУНКЦИЮ РАССЫЛКИ (передаем выбор фона bg_index)
        await send_vouchers_for_package(call.message, pkg_title, voucher, bg_index=bg_index)

    except Exception as e:
        print(f"Error generating PDF: {e}")
        traceback.print_exc()
        await call.message.answer(f"❌ Ошибка: {e}")

    await call.answer()


# =========================================================================
# 2. НАВИГАЦИЯ (ВЫБОР МЕСЯЦА, ЛИСТА, ПАКЕТА)
# =========================================================================

@dp.callback_query(F.data == "get_month_buttons")
async def show_month_buttons(callback: CallbackQuery):
    await callback.message.edit_text(
        "🕋 Выберите месяц для паломников:",
        reply_markup=get_palm_month_buttons()
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("palm_pkg:"))
async def palm_pkg_clicked(callback: types.CallbackQuery):
    try:
        await callback.answer("Готовлю превью ваучеров...")
    except Exception:
        pass

    # Парсим callback
    _, month_key, ws_title, pkg_row_str = callback.data.split(":", 3)
    pkg_row = int(pkg_row_str)

    # Загружаем данные
    ss = client.open_by_key(PALM_SHEETS[month_key])
    ws = find_worksheet_by_title(ss, ws_title)

    packages = find_palm_packages(ws)
    pkg_title = next((p["title"] for p in packages if p["row"] == pkg_row), ws_title)

    # Собираем ваучер
    voucher = collect_voucher_by_package(ws, pkg_row, pkg_title, look_through_next_packages=2)
    ensure_chronological_city_order(voucher)

    # Кэшируем
    cache_id = uuid.uuid4().hex[:10]
    PREVIEW_CACHE[cache_id] = {
        "voucher": voucher,
        "pkg_title": pkg_title,
        # Автовыбор для совместимости (реальный выбор происходит позже)
        "page2_png": pick_page2_bg(voucher.get("city1"), voucher.get("transfer"))
    }

    header = f"📦 <b>Пакет:</b> {pkg_title}\n📄 <b>Лист:</b> {ws.title}\n\n"

    # Отправляем КРАСИВОЕ превью
    await callback.message.answer(
        header + preview_text(voucher),
        reply_markup=preview_main_kb(cache_id),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("palm_sheet:"))
async def palm_sheet_selected(callback: types.CallbackQuery):
    try:
        _, month_key, ws_title = callback.data.split(":", 2)
        ss = client.open_by_key(PALM_SHEETS[month_key])
        ws = find_worksheet_by_title(ss, ws_title)

        packages = find_palm_packages(ws)
        if not packages:
            await callback.message.answer("⚠️ Нет пакетов на листе.")
            return

        kb = build_palm_packages_kb(month_key, ws_title, packages)
        await callback.message.answer(f"📄 Лист: {ws_title}\nВыберите пакет:", reply_markup=kb)
        await callback.answer()
    except Exception as e:
        print(f"Error: {e}")
        await callback.answer("❌ Ошибка")

@dp.callback_query(F.data.startswith("palm_month:"))
async def palm_month_selected(callback: CallbackQuery):
    try:
        month_key = callback.data.split(":", 1)[1]
        keyboard, all_titles = get_palm_sheet_buttons(month_key, show_all=False)
        USER_SHEETS_CACHE[callback.from_user.id] = all_titles
        await callback.message.edit_text(f"🕋 Месяц: {month_key}\nВыберите лист:", reply_markup=keyboard)
        await callback.answer()
    except Exception:
        await callback.answer("❌ Ошибка")

@dp.callback_query(F.data.startswith("palm_show_all:"))
async def palm_show_all_sheets(callback: CallbackQuery):
    month_key = callback.data.split(":", 1)[1]
    all_titles = USER_SHEETS_CACHE.get(callback.from_user.id, [])
    keyboard, _ = get_palm_sheet_buttons(month_key, show_all=True)
    await callback.message.edit_text("📋 Все листы:", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "palm_back_to_months")
async def palm_back_to_months(callback: CallbackQuery):
    await callback.message.edit_text("🕋 Выберите месяц:", reply_markup=get_palm_month_buttons())
    await callback.answer()


# =========================================================================
# 3. ФУНКЦИЯ РАССЫЛКИ И КРАСИВОГО ПРЕВЬЮ
# =========================================================================

def preview_text(voucher: dict) -> str:
    """Генерирует красивый текст предпросмотра"""
    base = base_payload_from(voucher)
    transfer = voucher.get("transfer") or base.get("transfer")

    def line(city, hotel, dates, checkin, num):
        c = city or f"Город {num} (не указан)"
        h = hotel or "—"
        d = dates or "—"
        ch = checkin or "—"
        return f"📍 <b>{c}</b>\n   🏨 Отель: {h}\n   📅 Даты: {d}\n   ⏰ Check-in: {ch}"

    p1 = line(voucher.get("city1"), voucher.get("hotel1"), voucher.get("dates1"), voucher.get("checkin1"), 1)
    p2 = line(voucher.get("city2"), voucher.get("hotel2"), voucher.get("dates2"), voucher.get("checkin2"), 2)

    meal = voucher.get("meal") or "—"
    guide = voucher.get("guide") or "—"
    excursions = voucher.get("excursions") or "—"
    tech_guide = voucher.get("tech_guide") or "—"
    service = voucher.get("service") or "—"

    text = (
        "📋 <b>ПРОВЕРЬТЕ ДАННЫЕ ПЕРЕД ГЕНЕРАЦИЕЙ:</b>\n\n"
        f"{p1}\n\n"
        f"{p2}\n\n"
        f"🍽 <b>Питание:</b> {meal}\n"
        f"🚐 <b>Трансфер:</b> {transfer}\n"
        f"🧭 <b>Гид:</b> {guide}\n"
        f"🗺 <b>Экскурсии:</b> {excursions}\n"
        f"📞 <b>Тех. гид:</b> {tech_guide}\n"
        f"🛡 <b>Сервис:</b> {service}"
    )

    if not voucher.get("city1") and not voucher.get("city2"):
        text += "\n\n⚠️ <i>Внимание: Города не заполнены! Нажмите '✏️ Изменить данные'.</i>"

    return text

async def send_vouchers_for_package(message: types.Message, pkg_title: str, voucher: dict, bg_index: int = -1):
    """
    Рассылает ваучеры всем комнатам, используя выбранный bg_index.
    """
    base = base_payload_from(voucher)
    ppl = voucher.get("people") or {}
    groups = ppl.get("rooms") or []

    # Если групп нет — одна общая
    if not groups:
        names = ppl.get("flat") or voucher.get("_people_flat") or []
        fake_group = {"kind": "", "people": names}
        # Передаем bg_index
        await send_one_voucher_for_group(message, pkg_title, voucher, base, fake_group, 1, bg_index=bg_index)

        # Запускаем сессию редактирования (меню "Что дальше"), сохраняя bg_index
        await start_after_voucher_menu(message, pkg_title, voucher, [fake_group], base, bg_index=bg_index)
        return

    # Если есть группы — шлем каждому
    for i, grp in enumerate(groups, start=1):
        await send_one_voucher_for_group(message, pkg_title, voucher, base, grp, i, bg_index=bg_index)
        await asyncio.sleep(0.2)

        # В конце показываем меню редактирования
    await start_after_voucher_menu(message, pkg_title, voucher, groups, base, bg_index=bg_index)