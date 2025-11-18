from aiogram import Bot, Dispatcher, F
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import re

# Базовые пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # папка config
PROJECT_ROOT = os.path.dirname(BASE_DIR)  # папка pligrim_bot
print(f"📍 BASE_DIR: {BASE_DIR}")
print(f"📍 PROJECT_ROOT: {PROJECT_ROOT}")

# Основные настройки
# Основные настройки
API_TOKEN = "7752089122:AAERQSfnEH-aMMehz8jnWhG9HbbcVpDQz7k"  # ← Этот токен неверный
TMP_DIR = os.path.join(PROJECT_ROOT, "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

# Google Sheets - ПРАВИЛЬНЫЙ ПУТЬ
CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "credentials", "hickmet-premium-bot-601501356d30.json")
# Google Sheets - расширенные права доступа
CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "credentials", "hickmet-premium-bot-601501356d30.json")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",  # ← Чтение и запись
    "https://www.googleapis.com/auth/drive.readonly"  # ← Доступ к списку файлов
]
SHEET_ID = "1sUo_1riAue-l0H-tKAn1EHy8XEHy3SBxc7jmZQqGwx4"

# 1. Пробуем получить ключи из переменной окружения (для сервера Koyeb)
json_config = os.getenv("GOOGLE_CREDS_JSON")

if json_config:
    print("✅ (Koyeb) Найдены ключи в переменной окружения")
    # Превращаем текст из переменной обратно в словарь
    creds_dict = json.loads(json_config)
    # Создаем объект доступов из словаря
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
else:
    # 2. Если переменной нет, ищем файл на диске (для локального запуска)
    CREDENTIALS_FILE = os.path.join(PROJECT_ROOT, "credentials", "hickmet-premium-bot-601501356d30.json")
    print(f"📍 (Local) Ищем файл ключей: {CREDENTIALS_FILE}")

    if os.path.exists(CREDENTIALS_FILE):
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    else:
        # Если нет ни переменной, ни файла — останавливаем программу, чтобы не мучиться
        raise FileNotFoundError("❌ ОШИБКА: Не найдены ключи Google! Добавьте файл локально или переменную GOOGLE_CREDS_JSON на сервер.")

# Авторизуемся в gspread прямо здесь
gc = gspread.authorize(creds)


# Инициализация бота
# (Совет: Токен бота тоже лучше брать из переменных, но пока оставим так)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Исключения ---
EXCLUDE_SHEETS = [
    "Доп услуги", "Подлетки", "расписание рейсов",
    "Рейсы с пакетами", "AUGUST 2025", "Лист16"
]

MONTHS_RU = {
    "January": "JANUARY", "February": "FEBRUARY", "March": "MARCH",
    "April": "APRIL", "May": "MAY", "June": "JUNE",
    "July": "JULY", "August": "AUGUST", "September": "SEPTEMBER",
    "October": "OCTOBER", "November": "NOVEMBER", "December": "DECEMBER"
}

DATE_ANY = re.compile(r'(\d{1,2})[./](\d{1,2})[./](\d{2,4})')
DATE_ISO = re.compile(r'(\d{4})-(\d{2})-(\d{2})')

# --- Возможные названия пакетов ---
PACKAGE_NAMES = [
    "NIYET ECONOM 7 DAYS", "NIYET 7 DAYS", "HIKMA 7 DAYS",
    "IZI SWISSOTEL", "IZI FAIRMONT", "4 YOU",
    "NIYET акционный 7 DAYS", "NIYET 11 DAYS",
    "HIKMA 11 DAYS", "AMAL 11 DAYS",
    "PARK REGIS 7 DAYS", "IZI 7 DAYS"
]

ROOM_HUMAN_RU = {
    "SGL":  "Одноместный номер",
    "DBL":  "Двухместный номер",
    "TWIN": "Двухместный номер (twin)",
    "TRPL": "Трёхместный номер",
    "QUAD": "Четырёхместный номер",

}
RANGE_RE = re.compile(r"(?<!\d)(\d{1,2})[.\-/](\d{1,2})\s*[–—-]\s*(\d{1,2})[.\-/](\d{1,2})(?!\d)")
HEADER_HINTS = {"№", "No", "N°"}  # признаки заголовка таблицы ниже

# рядом с остальными regex
BUS_WORD   = re.compile(r'(?i)\b(bus|автобус)\b')
DDMM_RE = re.compile(r'(?<!\d)(\d{1,2})[.\-/](\d{1,2})(?!\d)')

FLIGHT_RE = re.compile(r"\bKC\s*?(\d{3,4})\b", re.IGNORECASE)
TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\b")

# ----- пути к макетам второй страницы -----
SECOND_ASSETS = {
    "UAEmed":       "uae-med.png",
    "UAEmec":       "uae-mec.png",
    "JEDMED_TRAIN": "jed-med-train.png",
}

_XLSX_PATH = "OCTOBER 2025.xlsx"
_HOTELS_HINTS = ("hotel","hotels","отель","отели","размещение","accommodation")


# те же паттерны, что и при сборе транспорта
import re



TRAIN_RE    = re.compile(r'\b(train|Поезд|жд)\b', re.I)
BUS_RE      = re.compile(r'\b(bus|автобус)\b', re.I)
TRANSFER_RE = re.compile(r'\b(transfer|трансфер)\b', re.I)
ROUTE_RE    = re.compile(r'\b([A-Z]{3})\s*[-–/]\s*([A-Z]{3})\b', re.I)

# признак начала следующего пакета: новая «шапка» с датами/названием
NEXT_PACKAGE_HINT = re.compile(
    r'(\d{1,2}[./-]\d{1,2}\s*[–—-]\s*\d{1,2}[./-]\d{1,2})'
    r'|(niyet|hikma|izi|amal)\s*(\d+)?\s*(?:days|d)\b',
    re.I
)




# === PREVIEW / EDIT STATE ===
from typing import Dict

PREVIEW_CACHE: Dict[str, dict] = {}  # cache_id -> {"voucher":..., "pkg_title":..., "page2_png":...}
EDIT_STATE: Dict[int, dict] = {}     # user_id -> {"cache_id":..., "field":...}


# === 2. ОТРИСОВКА СТР.1 =========================================
# Координаты как у тебя (можно править под макет)
BBOX = {
    "pilgrims_box": (707, 323, 1013, 471),
    "city1":(563,517,1008,552),
    "hotel1":(563,567,1007,600),
    "stay1":(563,615,1007,645),
    "room1":(563,660,1007,689),"dates1":(563,706,1010,736),"checkin1":(563,751,1011,783),
    "city2":(563,822,1013,857),"hotel2":(563,872,1010,905),"stay2":(563,920,1008,951),
    "room2":(563,965,1013,995),"dates2":(563,1011,1011,1041),"checkin2":(563,1053,1007,1088),
    "tech_guide":(759,1500,994,1530),
    "service":(563,1164,943,1185),"transfer":(563,1200,943,1229),"meal":(563,1235,943,1265),
    "guide":(563,1269,943,1301),"excursions":(563,1304,943,1337),
}

DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})\b")


# Статические файлы
BG_PATH   = "v1.png"              # фон ваучера (первая страница)
TTF_PATH   = "fonts/Montserrat/static/Montserrat-Regular.ttf"

BG_UAE_MED = "uae-med.png"           # 2-я страница (первый город Медина)
BG_UAE_MEC = "uae-mec.png"           # 2-я страница (первый город Мекка)
BG_JED_MED_TRAIN = "jed-med-train.png"   # 2-я страница при поезде (Медина)

# === ГОРОДА ===
CITY_ALIASES = {
    "madinah": ["madinah", "medinah", "medina", "madina", "mdinah", "mdina", "мадина", "медина"],
    "makkah":  ["makkah", "makka", "mecca", "mekka", "makah", "макка", "мекка"],
}

CITY_ALIASES_HOTELS = {
    "madinah": ["madinah","medinah","medina","madina","мадина","медина"],
    "makkah":  ["makkah","makka","mecca","мекка","макка"],
    "jeddah":  ["jeddah","jed","джедда","джидда","джеддаh"],
    "alula":   ["al ula","al-ula","alula","аль-ула","алула"],
}
CITY_PRIORITY = ["madinah","makkah","jeddah","alula"]  # порядок по умолчанию


# === ТИПЫ ПАКЕТОВ ===
PKG_KIND_ALIASES = {
    # NIYET — включая все варианты и “акционный”
    "niyet": [
        "niyet", "ниет", "niyet economy", "niyet econom", "акцион", "акция", "акционный", "akcion"
    ],

    "niyet/7d": ["niyet/7d", "niyet 7 days"],
    "niyet/10d": ["niyet /10 d"],

    # HIKMA
    "hikma": ["hikma", "хикма"],


    # IZI / 4YOU
    "izi": [
        "izi", "izi swissotel", "izi fairmont", "izi 4u", "izi 4 you",
        "4 you", "4you", "4u", "swiss/4 you", "4 you shohada", "amal", "амал"
    ],

    # Прочие
    "aroya": ["aroya", "ароя", "arоya", "aroya only"],
    "aa": ["aa", "aa/7days", "aa/7 days"],
    "shohada": ["shohada"],
    "aktau": ["aktau"],
    "nqz": ["nqz"],
    "sco-med": ["sco-med", "sco med"],
    "ala-jed": ["ala-jed", "ala-med", "jed-med", "med-jed", "med-mak", "mak-med"],
    "standard": ["standard"],
}



# ==== People/rooms parsing (добавь рядом с остальными regex) ====
NAME_COMBINED_RE = re.compile(r'\b(фио|имя\s*и\s*фамилия|guest.?name|name)\b', re.I)
FIRST_NAME_RE    = re.compile(r'\b(имя|first.?name)\b', re.I)
LAST_NAME_RE     = re.compile(r'\b(фамилия|last.?name|surname)\b', re.I)
ROOM_COL_RE      = re.compile(r'\b(type\s*of\s*room|room\s*type|тип\s*номера|тип\s*размещения)\b', re.I)

# маркеры «следующей секции»: новая шапка, BUS/TRAIN/TRANSFER, новая «шапка» пакета
PEOPLE_STOP_RE   = re.compile(r'\b(bus|train|transfer|трансфер)\b', re.I)
PKG_TITLE_RE     = re.compile(r'\b(niyet|hikma|amal|izi|aroya|aa)\b', re.I)  # для строк «12.10-19.10 NIYET/7d»
HEADER_CELL_RE   = re.compile(r'^\s*№\s*$', re.I)

# вместимость по коду
ROOM_PATTERNS = [
    ("QUAD", 4, re.compile(r'\b(quad|quadro|quadruple|квадр|квад|4\s*-?\s*мест|4pax)\b', re.I)),
    ("TRPL", 3, re.compile(r'\b(trpl|triple|tpl|трипл|3\s*-?\s*мест)\b', re.I)),
    ("TWIN", 2, re.compile(r'\b(twin|twn)\b', re.I)),
    ("DBL",  2, re.compile(r'\b(dbl|double|двойн|2\s*-?\s*мест)\b', re.I)),
    ("SGL",  1, re.compile(r'\b(sgl|single|одномест|1\s*-?\s*мест|single\s*use)\b', re.I)),
]

# рядом с HDR_ALIASES
HDR_ALIASES = {
    "room":  ("type of room", "room type", "тип номера", "тип размещения", "room"),
    "last":  ("last name", "фамилия", "surname"),
    "first": ("first name", "имя"),
    "name":  ("name", "guest name", "guestname", "фио", "имя и фамилия"),
    "meal":  ("meal a day", "meal", "питание"),
    "gender": ("gender", "sex", "пол", "м/ж", "m/f"),
}


# расширенная карта синонимов + явная ёмкость
CAP = {"quad": 4, "trpl": 3, "dbl": 2, "twin": 2, "sgl": 1}
ROOM_ALIASES = {
    "quad": ("quad", "quadro", "quadruple", "quard", "quattro", "квадр"),
    "trpl": ("trpl", "triple", "tpl", "трипл", "трпл"),
    "twin": ("twin", "twn"),
    "dbl":  ("dbl", "double", "дабл", "дбл"),
    "sgl":  ("sgl", "single", "single use", "одномест"),
}

INF_RX = re.compile(r'\binf\b', re.I)

_FAMILY_EQUIV = {
    frozenset(("4u", "amal")),  # IZI/4U == AMAL
}

HOTELS_TITLE_RE = re.compile(r'(?i)\b(hotel|hotels|отел[ьи]|размещени[ея]|accommod)\b')

STOP_HINTS = (
    "transfer","train","bus","guide","гид","трансфер","ow",  # <- без пробела
)


DATE_RANGE_RX = re.compile(
    r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s*[–—-]\s*(\d{1,2})/(\d{1,2})/(\d{4})\b"
)

SERVICE_HINTS = re.compile(r'(?i)\b(transfer|train|bus|yes\s*tour|комиссия|итог|таблица)\b')

HOTELS_NAME_HINTS = (
    "hotel", "hotels", "отель", "отели", "хотел", "хотели",
    "accommodation", "размещение"
)

# NEW: вверху файла рядом с import re
DATE_TOKEN_RX = re.compile(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}")
NOISE_TOKENS = {
    "makkah","madinah","перенос","авиа","stop sale","бронь","bus","train",
    "ow","rt","изменение","transfer"
}

CHILD_RX = re.compile(r'\b(inf(ant)?|chd|child|kid|реб(ён|ен)ок|дет(и|ск))\b', re.I)

