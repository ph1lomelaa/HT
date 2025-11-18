import asyncio
import uuid
import os

from aiogram import types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from pligrim_bot.config.keyboards import get_palm_sheet_buttons, preview_main_kb, build_palm_packages_kb, \
    get_palm_month_buttons
from pligrim_bot.config.settings import client
from pligrim_bot.core.google_sheets import *
from pligrim_bot.core.parsers.package_parser import *
from pligrim_bot.core.parsers.people_parser import get_person_name, human_room
from pligrim_bot.core.voucher.builder import ensure_chronological_city_order, base_payload_from
from pligrim_bot.core.voucher.render import (
    build_voucher_pdf,
    render_voucher_page1_png,
    pick_page2_bg,
    build_filename_from_payload,
)

from pligrim_bot.handlers.flight_handlers import USER_SHEETS_CACHE
from pligrim_bot.handlers.palm_edit_handlers import send_one_voucher_for_group, start_after_voucher_menu


@dp.callback_query(F.data.startswith("palm_pkg:"))
async def palm_pkg_clicked(callback: types.CallbackQuery):
    try:
        await callback.answer("Готовлю превью ваучеров…")
    except Exception:
        pass

    # 2) Разбор данных из callback
    _, month_key, ws_title, pkg_row_str = callback.data.split(":", 3)
    pkg_row = int(pkg_row_str)

    ss = client.open_by_key(PALM_SHEETS[month_key])
    ws = find_worksheet_by_title(ss, ws_title)

    # ДЕБАГ: вывести сырые данные
    data = ws.get_all_values()
    print(f"🔍 ДЕБАГ: Лист {ws_title}, строк: {len(data)}")

    # Показать первые 15 строк для диагностики
    for i, row in enumerate(data[:15]):
        print(f"Строка {i}: {row[:8]}")  # первые 8 ячеек

    packages = find_palm_packages(ws)
    print(f"📦 Найдено пакетов: {len(packages)}")

    for pkg in packages:
        print(f"Пакет: {pkg['title']} на строке {pkg['row']}")

    packages = find_palm_packages(ws)
    pkg_title = next((p["title"] for p in packages if p["row"] == pkg_row), ws_title)

    # 3.1) Паломники/комнаты/трансфер — собираем как раньше с листа паломников
    fallback = collect_voucher_by_package(ws, pkg_row, pkg_title, look_through_next_packages=2)
    voucher = fallback  # ← ПРОСТО ИСПОЛЬЗУЕМ fallback

    ensure_chronological_city_order(voucher)

    # 4) Выбор второй страницы по правилам
    page2_png = pick_page2_bg(voucher.get("city1"), voucher.get("transfer"))

    # 5) Кэшируем сборку до подтверждения пользователем
    cache_id = uuid.uuid4().hex[:10]
    PREVIEW_CACHE[cache_id] = {
        "voucher": voucher,
        "pkg_title": pkg_title,
        "page2_png": page2_png,
    }

    # 6) Показываем превью и кнопки "Отправить / Изменить / Отмена"
    header = f"📦 Пакет: {pkg_title}\n📄 Лист: {ws.title}\n\n"
    await callback.message.answer(
        header + preview_text(voucher),
        reply_markup=preview_main_kb(cache_id)
    )

    # ВАЖНО: НИЧЕГО НЕ ОТПРАВЛЯЕМ здесь — ждём нажатия кнопки "✅ Всё верно — отправить"
    return

@dp.callback_query(F.data.startswith("palm_sheet:"))
async def palm_sheet_selected(callback: types.CallbackQuery):
    try:
        # формат: palm_sheet:<MONTH_KEY>:<WS_TITLE>
        _, month_key, ws_title = callback.data.split(":", 2)
        ss = client.open_by_key(PALM_SHEETS[month_key])
        ws = find_worksheet_by_title(ss, ws_title)

        packages = find_palm_packages(ws)
        if not packages:
            await callback.message.answer("⚠️ На этом листе не нашёл пакетов (заголовков с диапазоном дат).")
            await callback.answer()
            return

        kb = build_palm_packages_kb(month_key, ws_title, packages)
        await callback.message.answer(f"📄 Лист: {ws_title}\nВыберите пакет:", reply_markup=kb)
        await callback.answer()

    except Exception as e:
        print(f"❌ Ошибка в palm_sheet_selected: {e}")
        await callback.answer("❌ Ошибка загрузки пакетов")
def preview_text(voucher: dict) -> str:
    base = base_payload_from(voucher)
    transfer = voucher.get("transfer") or base.get("transfer")

    def line(city, hotel, dates, checkin, city_num):
        city_display = city or f"Город {city_num} (не указан)"
        hotel = hotel or "—"
        dates = dates or "—"
        checkin = checkin or "—"
        return f"• {city_display}\n  🏨 {hotel}\n  📅 {dates}\n  ⏰ Заезд: {checkin}"

    p1 = line(voucher.get("city1"), voucher.get("hotel1"), voucher.get("dates1"), voucher.get("checkin1"), 1)
    p2 = line(voucher.get("city2"), voucher.get("hotel2"), voucher.get("dates2"), voucher.get("checkin2"), 2)

    meal = voucher.get("meal") or "—"
    guide = voucher.get("guide") or "—"
    excursions = voucher.get("excursions") or "—"

    text = (
        "Проверьте данные перед отправкой ваучеров:\n\n"
        f"{p1}\n\n{p2}\n\n"
        f"🍽 Питание: {meal}\n"
        f"🧭 Гид: {guide}\n"
        f"🗺 Экскурсии: {excursions}\n"
        f"🚐 Трансфер: {transfer}"
    )

    # Добавляем предупреждение, если города не заполнены
    if not voucher.get("city1") and not voucher.get("city2"):
        text += "\n\n⚠️ *Внимание:* Города не указаны! Нажмите '✏️ Изменить данные' чтобы добавить."

    return text

@dp.callback_query(F.data.startswith("palm_month:"))
async def palm_month_selected(callback: CallbackQuery):
    try:
        month_key = callback.data.split(":", 1)[1]
        print(f"🔍 DEBUG: Выбран месяц: {month_key}")

        # Получаем листы с пагинацией
        keyboard, all_titles = get_palm_sheet_buttons(month_key, show_all=False)
        print(f"🔍 DEBUG: Получена клавиатура для месяца {month_key}")

        # Сохраняем полный список в кэш
        USER_SHEETS_CACHE[callback.from_user.id] = all_titles

        await callback.message.edit_text(
            f"🕋 Месяц: {month_key}\n"
            f"Выберите лист с группой паломников:\n\n"
            f"📊 Показано: {min(8, len(all_titles))} из {len(all_titles)}",
            reply_markup=keyboard
        )
        await callback.answer()

    except Exception as e:
        print(f"❌ DEBUG: Ошибка в palm_month_selected: {e}")
        import traceback
        traceback.print_exc()
        await callback.answer("❌ Произошла ошибка", show_alert=True)

# Обработчик "Показать все" для паломников
@dp.callback_query(F.data.startswith("palm_show_all:"))
async def palm_show_all_sheets(callback: CallbackQuery):
    month_key = callback.data.split(":", 1)[1]
    all_titles = USER_SHEETS_CACHE.get(callback.from_user.id, [])

    if not all_titles:
        await callback.answer("❌ Данные устарели")
        return

    # Создаем клавиатуру со всеми листами
    keyboard, _ = get_palm_sheet_buttons(month_key, show_all=True)

    await callback.message.edit_text(
        f"📋 Все доступные листы ({len(all_titles)}):",
        reply_markup=keyboard
    )
    await callback.answer()

def debug_voucher_package(ws, pkg_row: int, pkg_title: str):
    """
    Проверочная функция — показывает, почему collect_voucher_by_package
    не видит последний ваучер в листе.
    """
    print("\n================ DEBUG PACKAGE INSPECTOR ================")
    print(f"📄 Лист: {ws.title}")
    print(f"🔍 Пакет: {pkg_title} (строка {pkg_row})")

    all_values = ws.get_all_values()
    r0, r1, all_pk = package_bounds(ws, pkg_row)
    want = kind_from_title(pkg_title)

    print(f"🧩 Диапазон пакета: {r0} → {r1}")
    print(f"Всего строк в листе: {len(all_values)}")

    hdr, cols = find_people_header_in_range(all_values, r0, r1)
    if hdr is None:
        print("⚠️ Не найдена строка заголовков (Last Name / First Name)")
        return

    print(f"✅ Заголовок найден: строка {hdr}, колонки: {cols}")

    # Возьмем диапазон чуть шире, чтобы увидеть обрезание
    end_row_people = r1 + 5
    ppl = collect_people_groups(all_values, hdr, cols, end_row_people)
    rooms = ppl.get("rooms", [])
    flat = ppl.get("flat", [])

    print(f"👥 Найдено групп: {len(rooms)} / Всего имён: {len(flat)}")
    print("----------------------------------------------------------")
    for idx, g in enumerate(rooms, 1):
        print(f"{idx}) {g['kind']} ({len(g['people'])}) — {', '.join(g['people'])}")
    print("----------------------------------------------------------")

    # Проверим последние 10 строк листа, чтобы понять, где остановился парсер
    print("🔎 Последние 10 строк в пределах диапазона:")
    for r in range(max(hdr, end_row_people - 10), min(end_row_people, len(all_values))):
        row = all_values[r]
        troom = row[cols.get("room", 0)] if cols.get("room") is not None and cols.get("room") < len(row) else "-"
        fio = get_person_name(row, cols)
        print(f"{r+1:>3}: {fio or '-'} | {troom or '-'}")

    print("==========================================================\n")

async def send_vouchers_for_package(message: types.Message, pkg_title: str, voucher: dict):
    """
    Отправляет все ваучеры по пакету, а потом показывает две кнопки:
    1) Внести изменения в ваучер
    2) Начать заново
    """
    base = base_payload_from(voucher)

    ppl = voucher.get("people") or {}
    groups = ppl.get("rooms") or []

    # Если групп нет — один общий ваучер по списку имён
    if not groups:
        names = ppl.get("flat") or voucher.get("_people_flat") or []
        fake_group = {"kind": "", "people": names}
        await send_one_voucher_for_group(
            message=message,
            pkg_title=pkg_title,
            voucher=voucher,
            base=base,
            group=fake_group,
            idx=1,
        )
        # запускаем меню «что дальше»
        await start_after_voucher_menu(message, pkg_title, voucher, [fake_group], base)
        return

    # Иначе — ваучер на каждую комнату
    for i, grp in enumerate(groups, start=1):
        await send_one_voucher_for_group(
            message=message,
            pkg_title=pkg_title,
            voucher=voucher,
            base=base,
            group=grp,
            idx=i,
        )
        await asyncio.sleep(0.15)

    await start_after_voucher_menu(message, pkg_title, voucher, groups, base)

@dp.callback_query(F.data == "palm_back_to_months")
async def palm_back_to_months(callback: CallbackQuery):
    await callback.message.edit_text(
        "🕋 Выберите месяц для паломников:",
        reply_markup=get_palm_month_buttons()
    )
    await callback.answer()