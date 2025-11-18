import gspread
import os
import re
from datetime import datetime

# --- ВАЖНОЕ ИЗМЕНЕНИЕ ---
# Мы импортируем уже авторизованного клиента (gc) из constants.py
# Это работает и на Mac (через файл), и на Koyeb (через переменную)
try:
    from pligrim_bot.config.constants import gc
except ImportError:
    # Если вдруг не сработал абсолютный импорт, пробуем относительный
    from .constants import gc

print(f"🔄 Инициализация настроек Google Sheets...")

# Глобальные переменные
# Присваиваем глобальному клиенту уже готовое подключение
_client = gc
client = gc 

ALL_SHEETS = {}
PALM_SHEETS = {}

def get_google_client():
    """
    Возвращает авторизованный клиент Google Sheets.
    Берет его из constants.py, где он уже инициализирован.
    """
    global _client
    if _client is None:
        print("❌ Ошибка: Клиент Google не был инициализирован в constants.py")
        return None
    return _client

def get_all_accessible_sheets():
    """АВТОМАТИЧЕСКИ получает ВСЕ таблицы, доступные service account"""
    # Используем глобального клиента (gc)
    current_client = get_google_client()

    if not current_client:
        print("❌ Google Sheets клиент не инициализирован")
        return {}

    try:
        # Получаем список всех таблиц
        all_sheets = current_client.openall()
        sheets_map = {}

        for sheet in all_sheets:
            sheets_map[sheet.title] = sheet.id

        print(f"✅ Найдено таблиц: {len(sheets_map)}")
        # Выводим только первые 5, чтобы не засорять логи, или все если нужно
        for name in list(sheets_map.keys())[:10]:
            print(f"   📄 {name}")
        if len(sheets_map) > 10:
            print(f"   ... и еще {len(sheets_map) - 10}")

        return sheets_map
    except Exception as e:
        print(f"❌ Ошибка получения таблиц: {e}")
        return {}

def detect_pilgrim_months(sheets):
    """Автоматически определяет таблицы паломников по названиям месяцев"""
    month_pattern = r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\b'
    year_pattern = r'\b(20\d{2})\b'

    pilgrim_sheets = {}

    for sheet_name, sheet_id in sheets.items():
        name_lower = sheet_name.lower()

        # Ищем месяц в названии
        month_match = re.search(month_pattern, name_lower)
        if month_match:
            month = month_match.group(1).title()

            # Ищем год
            year_match = re.search(year_pattern, sheet_name)
            year = year_match.group(1) if year_match else str(datetime.now().year)

            key = f"{month} {year}"
            pilgrim_sheets[key] = sheet_id
            print(f"✅ Обнаружена таблица паломников: {key}")

    return pilgrim_sheets

# --- ДИНАМИЧЕСКОЕ ПОЛУЧЕНИЕ ТАБЛИЦ ПРИ ЗАПУСКЕ ---
if client:
    print("🔄 Получаем доступные таблицы...")
    ALL_SHEETS = get_all_accessible_sheets()
    PALM_SHEETS = detect_pilgrim_months(ALL_SHEETS)
    print(f"🎯 Итог: найдено {len(PALM_SHEETS)} таблиц паломников")
else:
    print("⚠️ Клиент не готов, пропускаем загрузку таблиц.")

def refresh_sheets():
    """Обновляет список таблиц"""
    global ALL_SHEETS, PALM_SHEETS
    ALL_SHEETS = get_all_accessible_sheets()
    PALM_SHEETS = detect_pilgrim_months(ALL_SHEETS)
    print(f"🔄 Обновлено! Доступно таблиц паломников: {len(PALM_SHEETS)}")

def get_worksheet(month_key: str, sheet_name: str):
    """Получает конкретный лист из таблицы по месяцу и названию листа"""
    current_client = get_google_client()

    if not current_client:
        return None

    try:
        if month_key not in PALM_SHEETS:
            print(f"❌ Таблица для месяца {month_key} не найдена")
            print(f"📋 Доступные месяцы: {list(PALM_SHEETS.keys())}")
            return None

        spreadsheet_id = PALM_SHEETS[month_key]
        spreadsheet = current_client.open_by_key(spreadsheet_id)

        # Пробуем найти лист
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            # print(f"✅ Лист найден: {sheet_name} в {month_key}") # Можно скрыть спам в логах
            return worksheet
        except Exception as e:
            print(f"❌ Лист {sheet_name} не найден в {month_key}: {e}")
            return None

    except Exception as e:
        print(f"❌ Ошибка получения листа {sheet_name} из {month_key}: {e}")
        return None
