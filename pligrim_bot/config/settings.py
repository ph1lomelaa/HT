import os
import json
import gspread
from google.oauth2.service_account import Credentials
from .constants import SCOPES, CREDENTIALS_FILE

print(f"🔄 Инициализация Google Sheets...")

# Глобальные переменные
_client = None
ALL_SHEETS = {}
PALM_SHEETS = {}

def get_google_client():
    """Создает и возвращает авторизованный клиент Google Sheets"""
    global _client
    if _client is not None:
        return _client

    try:
        creds = None

        # 1. Сначала пробуем взять JSON из переменной окружения (для Сервера/Koyeb)
        json_creds = os.getenv("GOOGLE_CREDS")

        if json_creds:
            print("🔑 Нашел ключи в переменной окружения GOOGLE_CREDS")
            try:
                creds_dict = json.loads(json_creds)
                creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            except json.JSONDecodeError as e:
                print(f"❌ Ошибка в JSON ключа (Koyeb): {e}")
                return None

        # 2. Если переменной нет, ищем файл (для локального запуска)
        elif os.path.exists(CREDENTIALS_FILE):
            print(f"fv Нашел файл ключей: {CREDENTIALS_FILE}")
            creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)

        else:
            print("❌ ОШИБКА: Не найдены ключи! (Нет ни GOOGLE_CREDS, ни файла creds.json)")
            return None

        # Авторизуемся
        _client = gspread.authorize(creds)
        print("✅ Google Sheets клиент успешно инициализирован")
        return _client

    except Exception as e:
        print(f"❌ Критическая ошибка инициализации Google: {e}")
        return None

# Создаем глобальный клиент
client = get_google_client()

# --- Остальные функции (get_all_accessible_sheets и т.д.) оставляем как есть ---
def get_all_accessible_sheets():
    global client
    if not client:
        client = get_google_client()

    if not client:
        return {}

    try:
        all_sheets = client.openall()
        sheets_map = {}
        for sheet in all_sheets:
            sheets_map[sheet.title] = sheet.id
        return sheets_map
    except Exception as e:
        print(f"❌ Ошибка получения таблиц: {e}")
        return {}

def detect_pilgrim_months(sheets_map):
    # Ваша логика фильтрации
    # (Оставьте то, что у вас было в файле, или простую заглушку)
    return sheets_map

def refresh_sheets():
    global ALL_SHEETS, PALM_SHEETS
    ALL_SHEETS = get_all_accessible_sheets()
    PALM_SHEETS = ALL_SHEETS # Или ваша функция фильтрации
    print(f"🎯 Итог: найдено {len(PALM_SHEETS)} таблиц")
