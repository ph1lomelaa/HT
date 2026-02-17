import re
from datetime import datetime
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from .constants import MONTHS_RU, PREVIEW_CACHE
from .settings import PALM_SHEETS
from ..core.google_sheets import get_palm_sheet_names
from ..core.utils.text_utils import safe_cb_text
from ..core.utils.validation import city_ru
from ..handlers.flight_handlers import get_available_sheets
from ..core.utils.date_utils import extract_start_date

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_scenario_kb() -> InlineKeyboardMarkup:
    """
    Главное меню: выбрать месяц (по пакетам) или создать индивидуальный ваучер
    """
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=" Выбрать месяц",
                callback_data="get_month_buttons"
            )
        ],
        [
            InlineKeyboardButton(
                text=" Создать индивидуально",
                callback_data="indv_voucher_start"
            )
        ],
    ])
    return kb

def choose_background_kb(cache_id: str) -> InlineKeyboardMarkup:
    """Кнопки выбора варианта дизайна (1, 2, 3)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1️⃣ Вариант 1", callback_data=f"sel_bg:{cache_id}:0"),
            InlineKeyboardButton(text="2️⃣ Вариант 2", callback_data=f"sel_bg:{cache_id}:1"),
            InlineKeyboardButton(text="3️⃣ Вариант 3", callback_data=f"sel_bg:{cache_id}:2"),
        ],
        [
            InlineKeyboardButton(text=" Отмена", callback_data=f"pv_cancel:{cache_id}")
        ]
    ])

def get_month_buttons():
    """Создаёт клавиатуру с текущим и ближайшими 3 месяцами"""
    sheets = get_available_sheets()
    now = datetime.now()
    current_month = MONTHS_RU[now.strftime("%B")]
    current_year = now.strftime("%Y")
    target_name = f"{current_month} {current_year}"

    if target_name in sheets:
        start_index = sheets.index(target_name)
        short_list = sheets[start_index:start_index + 4]
    else:
        short_list = sheets[:4]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
                            [InlineKeyboardButton(text=name, callback_data=f"sheet:{name}")]
                            for name in short_list
                        ] + [
                            [InlineKeyboardButton(text=" Показать все месяцы и пакеты", callback_data="show_all")]
                        ]
    )
    return keyboard


def get_month_sheets_buttons(sheet_titles, show_all=False):
    """Клавиатура для выбора листа с пагинацией"""
    from datetime import datetime

    # Фильтруем прошедшие даты
    current_date = datetime.now().strftime("%d.%m.%Y")
    filtered_titles = []

    for title in sheet_titles:
        # Извлекаем даты из названия (формат: DD.MM-DD.MM или DD.MM-YY.MM)
        date_match = re.search(r'(\d{2}\.\d{2})-(\d{2}\.\d{2})', title)
        if date_match:
            start_date_str = date_match.group(1) + f".{datetime.now().year}"
            end_date_str = date_match.group(2) + f".{datetime.now().year}"

            try:
                # Парсим даты
                start_date = datetime.strptime(start_date_str, "%d.%m.%Y")
                end_date = datetime.strptime(end_date_str, "%d.%m.%Y")
                current_dt = datetime.strptime(current_date, "%d.%m.%Y")

                # Оставляем только будущие даты или текущие
                if end_date >= current_dt:
                    filtered_titles.append(title)
            except:
                # Если не удалось распарсить даты, оставляем лист
                filtered_titles.append(title)
        else:
            # Если нет дат в формате, оставляем лист
            filtered_titles.append(title)

    # Сортируем по дате начала
    filtered_titles.sort(key=lambda x: extract_start_date(x))

    # Ограничиваем показ если не показаны все
    if not show_all and len(filtered_titles) > 8:
        display_titles = filtered_titles[:8]
        has_more = True
    else:
        display_titles = filtered_titles
        has_more = False

    # Создаем клавиатуру
    keyboard = []
    for title in display_titles:
        # Обрезаем длинные названия для кнопки
        button_text = title[:30] + "..." if len(title) > 30 else title
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"sheet:{title}")])

    # Добавляем кнопку "Показать все" если есть еще элементы
    if has_more:
        keyboard.append([InlineKeyboardButton(text=" Показать все", callback_data="show_all_sheets")])

    keyboard.append([InlineKeyboardButton(text=" Назад к месяцам", callback_data="back_to_months")])

    return InlineKeyboardMarkup(inline_keyboard=keyboard), filtered_titles


def extract_start_date(title):
    """Извлекает дату начала для сортировки"""
    date_match = re.search(r'(\d{2}\.\d{2})-\d{2}\.\d{2}', title)
    if date_match:
        start_date_str = date_match.group(1) + f".{datetime.now().year}"
        try:
            return datetime.strptime(start_date_str, "%d.%m.%Y")
        except:
            return datetime.min
    return datetime.min


def get_palm_month_buttons() -> InlineKeyboardMarkup:
    """Кнопки выбора месяца (по PALM_SHEETS)."""
    rows = [[InlineKeyboardButton(text=mk, callback_data=f"palm_month:{mk}")] for mk in PALM_SHEETS.keys()]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_palm_sheet_buttons(month_key: str, show_all=False) -> InlineKeyboardMarkup:
    """
    Кнопки листов для выбранного месяца с фильтрацией 'прошедших' по дате и пагинацией.
    """
    try:
        names = get_palm_sheet_names(month_key, include_past=False)

        if not names:
            names = ["— нет актуальных листов —"]

        # Ограничиваем показ если не показаны все
        if not show_all and len(names) > 8:
            display_names = names[:8]
            has_more = True
        else:
            display_names = names
            has_more = False

        # Создаем клавиатуру
        rows = []
        for n in display_names:
            button_text = n[:30] + "..." if len(n) > 30 else n
            callback_data = f"palm_sheet:{safe_cb_text(month_key)}:{safe_cb_text(n)}"
            rows.append([InlineKeyboardButton(
                text=button_text,
                callback_data=callback_data
            )])

        # Добавляем кнопку "Показать все" если есть еще элементы
        if has_more:
            rows.append([InlineKeyboardButton(
                text=" Показать все",
                callback_data=f"palm_show_all:{month_key}"
            )])

        rows.append([InlineKeyboardButton(text=" Назад к месяцам", callback_data="palm_back_to_months")])

        return InlineKeyboardMarkup(inline_keyboard=rows), names

    except Exception as e:
        print(f" Ошибка в get_palm_sheet_buttons: {e}")
        error_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=" Назад к месяцам", callback_data="palm_back_to_months")]
        ])
        return error_kb, []

def build_palm_packages_kb(month_key: str, ws_title: str, packages: list[dict]) -> InlineKeyboardMarkup:
    # callback запоминаем позицию найденного заголовка (row),
    # пригодится для дальнейшего парсинга конкретного пакета
    rows = [
        [InlineKeyboardButton(
            text=p["title"],
            callback_data=f"palm_pkg:{month_key}:{ws_title}:{p['row']}"
        )]
        for p in packages
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_package_keyboard(sheet_name, packages):
    """Создаёт кнопки для найденных пакетов"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p, callback_data=f"package:{sheet_name}:{p}")]
            for p in packages
        ]
    )

def preview_main_kb(cache_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Всё верно — отправить", callback_data=f"pv_send:{cache_id}")],
        [InlineKeyboardButton(text="️ Изменить данные",      callback_data=f"pv_edit:{cache_id}")],
        [InlineKeyboardButton(text=" Отмена",               callback_data=f"pv_cancel:{cache_id}")],
    ])


# REMOVED: edit_fields_kb - duplicated in preview_handlers.py
# This function was not being imported or used anywhere

def citykey_for_value(value: str | None, fallback: str) -> str:
    """Определяет ключ города по строке. Если не Медина/Мекка — возвращает fallback."""
    s = (value or "").lower()
    if any(x in s for x in ("madinah", "medina", "madina", "медин", "медина")):
        return "madinah"
    if any(x in s for x in ("makkah", "mecca", "mekka", "макк", "мекка")):
        return "makkah"
    return fallback

def slot_for_city(v: dict, citykey: str) -> int | None:
    def key_of(s: str|None) -> str:
        s = (s or "").lower()
        if any(x in s for x in ("madinah","medina","madina","медин","медина")): return "madinah"
        if any(x in s for x in ("makkah","mecca","mekka","макк","мекка")):      return "makkah"
        return "other"

    # Проверяем оба города по их фактическому ключу
    city1_key = key_of(v.get("city1"))
    city2_key = key_of(v.get("city2"))

    # Если запрашивают Медину - возвращаем слот с Мединой
    if citykey == "madinah":
        if city1_key == "madinah": return 1
        if city2_key == "madinah": return 2
        # Если Медины нет вообще - возвращаем None, чтобы создать новый
        return None

    # Если запрашивают Мекку - возвращаем слот с Меккой
    elif citykey == "makkah":
        if city1_key == "makkah": return 1
        if city2_key == "makkah": return 2
        # Если Мекки нет вообще - возвращаем None, чтобы создать новый
        return None

    # Для других случаев (кнопки "Город 1"/"Город 2")
    elif citykey == "1":
        return 1
    elif citykey == "2":
        return 2

    return None
