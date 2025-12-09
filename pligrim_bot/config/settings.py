import gspread
from google.oauth2.service_account import Credentials
import os
import re
from datetime import datetime
from .constants import SCOPES, CREDENTIALS_FILE, SHEET_ID

print(f"🔄 Инициализация Google Sheets...")

# Глобальные переменные
_client = None
_spreadsheet = None
ALL_SHEETS = {}
PALM_SHEETS = {}

def get_google_client():
    """Создает и возвращает авторизованный клиент Google Sheets"""
    global _client
    if _client is not None:
        return _client

    try:
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(f"Credentials file not found: {CREDENTIALS_FILE}")

        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
        _client = gspread.authorize(creds)
        print("✅ Google Sheets клиент инициализирован")
        return _client
    except Exception as e:
        print(f"❌ Ошибка инициализации Google клиента: {e}")
        return None

# Создаем глобальный клиент для экспорта
client = get_google_client()

def get_all_accessible_sheets():
    """АВТОМАТИЧЕСКИ получает ВСЕ таблицы, доступные service account"""
    global client
    if not client:
        client = get_google_client()

    if not client:
        print("❌ Google Sheets клиент не инициализирован")
        return {}

    try:
        all_sheets = client.openall()
        sheets_map = {}

        for sheet in all_sheets:
            sheets_map[sheet.title] = sheet.id

        print(f"✅ Найдено таблиц: {len(sheets_map)}")
        for name in sheets_map.keys():
            print(f"   📄 {name}")

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

# ДИНАМИЧЕСКОЕ ПОЛУЧЕНИЕ ТАБЛИЦ ПРИ ЗАПУСКЕ
print("🔄 Получаем доступные таблицы...")
ALL_SHEETS = get_all_accessible_sheets()
PALM_SHEETS = detect_pilgrim_months(ALL_SHEETS)

print(f"🎯 Итог: найдено {len(PALM_SHEETS)} таблиц паломников")

def refresh_sheets():
    """Обновляет список таблиц"""
    global ALL_SHEETS, PALM_SHEETS, client
    ALL_SHEETS = get_all_accessible_sheets()
    PALM_SHEETS = detect_pilgrim_months(ALL_SHEETS)
    print(f"🔄 Обновлено! Доступно таблиц паломников: {len(PALM_SHEETS)}")

def get_worksheet(month_key: str, sheet_name: str):
    """Получает конкретный лист из таблицы по месяцу и названию листа"""
    global client
    if not client:
        client = get_google_client()

    if not client:
        return None

    try:
        if month_key not in PALM_SHEETS:
            print(f"❌ Таблица для месяца {month_key} не найдена")
            print(f"📋 Доступные месяцы: {list(PALM_SHEETS.keys())}")
            return None

        spreadsheet_id = PALM_SHEETS[month_key]
        spreadsheet = client.open_by_key(spreadsheet_id)

        # Пробуем найти лист
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            print(f"✅ Лист найден: {sheet_name} в {month_key}")
            return worksheet
        except Exception as e:
            print(f"❌ Лист {sheet_name} не найден в {month_key}: {e}")

            # Покажем доступные листы
            worksheets = spreadsheet.worksheets()
            print(f"📋 Доступные листы в {month_key}:")
            for ws in worksheets:
                print(f"   📄 {ws.title}")

            return None

    except Exception as e:
        print(f"❌ Ошибка получения листа {sheet_name} из {month_key}: {e}")
        return None