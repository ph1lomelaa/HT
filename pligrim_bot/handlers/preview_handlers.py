from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from pligrim_bot.config.constants import *
from pligrim_bot.config.keyboards import slot_for_city, preview_main_kb, citykey_for_value
from pligrim_bot.core.utils.validation import city_ru
from pligrim_bot.core.voucher.builder import ensure_chronological_city_order, base_payload_from, nights_from_dates
from pligrim_bot.core.voucher.render import plural_nights
from pligrim_bot.handlers.pilgrim_handlers import send_vouchers_for_package
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

def preview_text(voucher: dict) -> str:
    base = base_payload_from(voucher)
    transfer = voucher.get("transfer") or base.get("transfer")

    def line(city, hotel, dates, checkin, city_num):
        city_display = city or f"Город {city_num} (не указан)"
        hotel = hotel or "—"
        dates = dates or "—"
        checkin = checkin or "—"
        return f"• {city_display}\n   {hotel}\n   {dates}\n  ⏰ Заезд: {checkin}"

    p1 = line(voucher.get("city1"), voucher.get("hotel1"), voucher.get("dates1"), voucher.get("checkin1"), 1)
    p2 = line(voucher.get("city2"), voucher.get("hotel2"), voucher.get("dates2"), voucher.get("checkin2"), 2)

    meal = voucher.get("meal") or "—"
    guide = voucher.get("guide") or "—"
    excursions = voucher.get("excursions") or "—"

    text = (
        "Проверьте данные перед отправкой ваучеров:\n\n"
        f"{p1}\n\n{p2}\n\n"
        f" Питание: {meal}\n"
        f" Гид: {guide}\n"
        f" Экскурсии: {excursions}\n"
        f" Трансфер: {transfer}"
    )

    # Добавляем предупреждение, если города не заполнены
    if not voucher.get("city1") and not voucher.get("city2"):
        text += "\n\n️ *Внимание:* Города не указаны! Нажмите '️ Изменить данные' чтобы добавить."

    return text

@dp.message(F.text & ~F.text.startswith("/"))
async def pv_text_input(message: types.Message):
    st = EDIT_STATE.get(message.from_user.id)
    if not st:
        return

    cache_id = st["cache_id"]; field = st["field"]
    data = PREVIEW_CACHE.get(cache_id)
    if not data:
        await message.answer("️ Сессия устарела. Начните заново.")
        EDIT_STATE.pop(message.from_user.id, None)
        return

    v = data["voucher"]
    new_val = message.text.strip()

    # Обработка добавления города
    if field.startswith("add_city@"):
        city_num = field.split("@")[1]  # 1 или 2

        try:
            # Парсим введенные данные
            parts = [part.strip() for part in new_val.split("|")]
            if len(parts) < 3:
                await message.answer(" Неверный формат. Нужно: город | отель | даты [| чек-ин]")
                return

            city_name = parts[0]
            hotel = parts[1]
            dates = parts[2]
            checkin = parts[3] if len(parts) > 3 else "16:00"

            # Нормализация дат
            m = re.findall(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})', dates)
            if len(m) >= 2:
                def _mk(t):
                    d,mth,y = t
                    y = ("20"+y) if len(y)==2 else y
                    return f"{d.zfill(2)}/{mth.zfill(2)}/{y}"
                dates = f"{_mk(m[0])} – {_mk(m[1])}"

            # Вычисляем количество ночей
            nights_count = nights_from_dates(dates)

            # Сохраняем данные
            v[f"city{city_num}"] = city_name
            v[f"hotel{city_num}"] = hotel
            v[f"dates{city_num}"] = dates
            v[f"checkin{city_num}"] = checkin
            v[f"stay{city_num}_nights"] = nights_count
            v[f"stay{city_num}"] = plural_nights(nights_count)

            # Автоматически определяем порядок городов по датам
            ensure_chronological_city_order(v)

            await message.answer(f" Город {city_num} успешно добавлен: {city_name}")

        except Exception as e:
            await message.answer(f" Ошибка при обработке данных: {e}")
            return

    else:
        # Обычное редактирование существующих полей
        base = field.split("@")[0]
        citykey = field.split("@")[1] if "@" in field else None

        # Нормализация дат
        if base == "dates":
            m = re.findall(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})', new_val)
            if len(m) >= 2:
                def _mk(t):
                    d,mth,y = t
                    y = ("20"+y) if len(y)==2 else y
                    return f"{d.zfill(2)}/{mth.zfill(2)}/{y}"
                new_val = f"{_mk(m[0])} – {_mk(m[1])}"

        # Определяем конечное поле (slot)
        if base in ("hotel","dates","checkin") and citykey:
            slot = slot_for_city(v, citykey)
            if slot is None:
                # Если город не найден, создаем его
                if citykey in ["madinah", "1"]:
                    slot = 1
                    v["city1"] = "Медина" if citykey == "madinah" else "Город 1"
                else:
                    slot = 2
                    v["city2"] = "Мекка" if citykey == "makkah" else "Город 2"

            key = f"{base}{slot}"
        else:
            key = base  # service/meal/guide/excursions/tech_guide/transfer

        # Применяем
        v[key] = new_val

        # Если правили даты — пересчитываем порядок и ночи
        if base == "dates":
            ensure_chronological_city_order(v)

    # Обновляем кэш и превью
    PREVIEW_CACHE[cache_id]["voucher"] = v
    EDIT_STATE.pop(message.from_user.id, None)

    await message.answer(" Обновлено.")
    await message.answer(preview_text(v), reply_markup=preview_main_kb(cache_id))

@dp.callback_query(F.data.startswith("pv_cancel:"))
async def pv_cancel(callback: types.CallbackQuery):
    _, cache_id = callback.data.split(":", 1)
    PREVIEW_CACHE.pop(cache_id, None)
    EDIT_STATE.pop(callback.from_user.id, None)
    await callback.message.answer("Отменено. Вы можете начать заново с выбора пакета.")
    await callback.answer()

@dp.callback_query(F.data.startswith("pv_back:"))
async def pv_back(callback: types.CallbackQuery):
    _, cache_id = callback.data.split(":", 1)
    data = PREVIEW_CACHE.get(cache_id)
    if not data:
        await callback.message.answer("️ Сессия не найдена. Начните заново.")
        return
    await callback.message.answer(preview_text(data["voucher"]), reply_markup=preview_main_kb(cache_id))
    await callback.answer()

# REMOVED: Duplicate pv_send handler - the correct one is in pilgrim_handlers.py
# This old version skipped background selection and is no longer needed




@dp.callback_query(F.data.startswith("pv_edit:"))
async def pv_edit(callback: types.CallbackQuery):
    _, cache_id = callback.data.split(":", 1)
    if cache_id not in PREVIEW_CACHE:
        await callback.message.answer("️ Сессия не найдена. Начните заново.")
        return
    await callback.message.answer("Что хотите изменить?", reply_markup=edit_fields_kb(cache_id))
    await callback.answer()


@dp.callback_query(F.data.startswith("pv_field:"))
async def pv_field(callback: types.CallbackQuery):
    try:
        _, cache_id, field = callback.data.split(":", 2)
    except ValueError:
        await callback.answer(); return

    data = PREVIEW_CACHE.get(cache_id)
    if not data:
        await callback.message.answer("️ Сессия не найдена. Начните заново.")
        return

    # Обработка кнопки "Добавить город"
    if field.startswith("add_city@"):
        city_num = field.split("@")[1]  # 1 или 2
        EDIT_STATE[callback.from_user.id] = {"cache_id": cache_id, "field": f"add_city@{city_num}"}

        if city_num == "1":
            await callback.message.answer(
                "️ Введите данные для первого города:\n\n"
                "Формат: <город> | <отель> | <даты> | <чек-ин>\n"
                "Пример: Медина | Swissotel | 25/10/2024 – 28/10/2024 | 16:00"
            )
        else:
            await callback.message.answer(
                "️ Введите данные для второго города:\n\n"
                "Формат: <город> | <отель> | <даты> | <чек-ин>\n"
                "Пример: Мекка | Fairmont | 28/10/2024 – 01/11/2024 | 16:00"
            )
        await callback.answer()
        return

    pretty_map = {
        "hotel":    "Отель",
        "dates":    "Даты в формате DD/MM/YYYY – DD/MM/YYYY",
        "checkin":  "Чек-ин, например 16:00",
        "transfer": "Трансфер (например: Поезд, Автобус)",
        "meal":     "Питание (например: Завтрак и ужин)",
        "guide":    "Гид (например: Групповой гид)",
        "excursions":"Экскурсии (например: Мекка, Медина)",
        "tech_guide":"Технический гид (например: +966 56 328 0325)",
        "service":  "Сервис (например: Виза и страховка)",
    }

    # сохраняем «что именно правим»
    EDIT_STATE[callback.from_user.id] = {"cache_id": cache_id, "field": field}
    base = field.split("@")[0]
    city = field.split("@")[1] if "@" in field else None

    city_labels = {
        "madinah": " (Медина)",
        "makkah": " (Мекка)",
        "1": " (Город 1)",
        "2": " (Город 2)"
    }
    city_label = city_labels.get(city, "")

    await callback.message.answer(f"Введите новое значение для: {pretty_map.get(base, field)}{city_label}")
    await callback.answer()
