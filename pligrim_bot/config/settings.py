import json

import gspread
from google.oauth2.service_account import Credentials
import os
import re
from datetime import datetime
from .constants import SCOPES, CREDENTIALS_FILE

print(f"🔄 Инициализация Google Sheets...")

# Глобальные переменные
_client = None
_spreadsheet = None
ALL_SHEETS = {}
PALM_SHEETS = {}

def get_google_client():
    global _client
    if _client is not None:
        return _client

    try:
        creds = None
        # 1. Читаем переменную с сервера (Koyeb)
        json_creds = os.getenv("GOOGLE_CREDS")

        if json_creds:
            print("🔑 Использую ключи из переменной GOOGLE_CREDS")
            try:
                # Превращаем строку обратно в словарь
                creds_dict = json.loads(json_creds)
                creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            except json.JSONDecodeError as e:
                print(f"❌ Ошибка: В переменной GOOGLE_CREDS лежит невалидный JSON! {e}")
                return None

        # 2. Иначе ищем файл (локально)
        elif os.path.exists(CREDENTIALS_FILE):
            print(f"📂 Использую файл ключей: {CREDENTIALS_FILE}")
            creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)

        else:
            print("❌ ОШИБКА: Ключи не найдены ни в переменной, ни в файле.")
            return None

        _client = gspread.authorize(creds)
        print("✅ Успешное подключение к Google")
        return _client

    except Exception as e:
        print(f"❌ Критическая ошибка подключения: {e}")
        return None

# Глобальный клиент
client = get_google_client()

def get_all_accessible_sheets():
    if not client: return {}
    try:
        return {s.title: s.id for s in client.openall()}
    except Exception as e:
        print(f"Ошибка списка таблиц: {e}")
        return {}

def refresh_sheets():
    # Ваша логика обновления
    print("Обновление списка таблиц...")
    get_all_accessible_sheets()

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
