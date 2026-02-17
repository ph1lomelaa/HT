from pligrim_bot.config.constants import *

def get_last(row, cols):   return _norm_spaces(row[cols["last"]])  if "last"  in cols and cols["last"]  < len(row) else ""
def get_first(row, cols):  return _norm_spaces(row[cols["first"]]) if "first" in cols and cols["first"] < len(row) else ""
def get_meal(row, cols):   return _norm_spaces(row[cols["meal"]])  if "meal"  in cols and cols["meal"]  < len(row) else ""
def get_room(row, cols):   return _norm_spaces(row[cols["room"]])  if "room"  in cols and cols["room"]  < len(row) else ""

def is_guest_row(row: list[str], cols: dict) -> bool:
    last  = get_last(row, cols)
    first = get_first(row, cols)
    if not last and not first:
        return False
    
    if DATE_TOKEN_RX.search(last) or DATE_TOKEN_RX.search(first):
        return False
    
    low_last, low_first = last.lower(), first.lower()
    if any(tok in low_last for tok in NOISE_TOKENS) or any(tok in low_first for tok in NOISE_TOKENS):
        return False
    return is_valid_name(last) or is_valid_name(first)


def detect_people_header(row: list[str]) -> dict | None:
    """Исправленный поиск заголовков для вашей структуры"""
    if not row:
        return None

    cols = {}
    print(f" Поиск заголовков в строке: {row}")

    for i, cell in enumerate(row):
        cell_text = norm_hdr(cell)
        if not cell_text:
            continue

        print(f"  Ячейка {i}: '{cell_text}'")

        # Тип комнаты - может быть ПЕРВОЙ колонкой!
        if any(keyword in cell_text for keyword in ["type of room", "room type", "тип номера", "room", "type"]):
            cols["room"] = i
            print(f"     Найден тип комнаты в колонке {i}")

        # Фамилия
        if any(keyword in cell_text for keyword in ["last name", "фамилия", "surname", "lastname"]):
            cols["last"] = i
            print(f"     Найдена фамилия в колонке {i}")

        # Имя
        if any(keyword in cell_text for keyword in ["first name", "имя", "firstname"]):
            cols["first"] = i
            print(f"     Найдено имя в колонке {i}")

        # Питание (может быть второй колонкой)
        if any(keyword in cell_text for keyword in ["meal", "meal a day", "питание", "hb", "ro"]):
            cols["meal"] = i
            print(f"     Найдено питание в колонке {i}")

    print(f" Итоговые колонки: {cols}")

    # Принимаем если есть либо фамилия/имя, либо оба
    if "last" in cols or "first" in cols:
        return cols

    return None

import re

# --- БАЗОВЫЕ КОНСТАНТЫ ТЫ УЖЕ ОБЪЯВИЛА ВЫШЕ ---
# CITY_ALIASES, CITY_ALIASES_HOTELS, CITY_PRIORITY
# PKG_KIND_ALIASES, HDR_ALIASES, ROOM_ALIASES
# STOP_HINTS, SERVICE_HINTS, HOTELS_NAME_HINTS
# DATE_RANGE_RX, DATE_TOKEN_RX, NOISE_TOKENS (базовый)


def _norm_token(s: str) -> str:
    return str(s or "").strip().upper()


def _build_bad_name_sets():
    bad_exact = set()
    bad_contains = set()

    def add_alias(alias: str):
        up = _norm_token(alias)
        if not up:
            return
        # очень короткое — обычно мусор, не добавляем
        if len(up) <= 2:
            return

        # если есть пробел/цифра/двоеточие — скорее шаблон / фраза → в CONTAINS
        if any(ch.isdigit() for ch in up) or " " in up or ":" in up or "\n" in up:
            bad_contains.add(up)
        else:
            bad_exact.add(up)

    # 1) Города (aliases + hotels)
    for aliases in CITY_ALIASES.values():
        for a in aliases:
            add_alias(a)

    for aliases in CITY_ALIASES_HOTELS.values():
        for a in aliases:
            add_alias(a)

    # 2) Типы пакетов (HIKMA, IZI, NIYET, 4U и т.п.)
    for aliases in PKG_KIND_ALIASES.values():
        for a in aliases:
            add_alias(a)

    # 3) Типы номеров (double, triple и т.п.) — чтобы не превращать их в «людей»
    for aliases in ROOM_ALIASES.values():
        for a in aliases:
            add_alias(a)

    # 4) Общие ключевые слова для отелей / размещения
    for word in HOTELS_NAME_HINTS:
        add_alias(word)

    # Можно руками добавить очевидные “мусорные имена”, которые уже видели в логах:
    manual_exact = {
        "ADDRESS",
    }
    manual_contains = {
        " HIKMA 7 DAYS",
        " AMAL 7 DAYS",
    }

    bad_exact |= manual_exact
    bad_contains |= manual_contains

    return bad_exact, bad_contains


BAD_FIO_EXACT, BAD_FIO_CONTAINS = _build_bad_name_sets()


# --- Расширяем NOISE_TOKENS, используя все константы ---

BASE_NOISE_TOKENS = {
    "makkah","madinah","перенос","авиа","stop sale","бронь","bus","train",
    "ow","rt","изменение","transfer",
}

EXTRA_NOISE = set()

# Все алиасы городов
for aliases in CITY_ALIASES.values():
    for a in aliases:
        EXTRA_NOISE.add(str(a).lower())

for aliases in CITY_ALIASES_HOTELS.values():
    for a in aliases:
        EXTRA_NOISE.add(str(a).lower())

# Типы пакетов (ниет, хикма, izi и т.п.)
for aliases in PKG_KIND_ALIASES.values():
    for a in aliases:
        EXTRA_NOISE.add(str(a).lower())

# STOP_HINTS (transfer, train, bus и т.п.)
for w in STOP_HINTS:
    EXTRA_NOISE.add(str(w).lower())

# Общие слова по отелям
for w in HOTELS_NAME_HINTS:
    EXTRA_NOISE.add(str(w).lower())

NOISE_TOKENS = BASE_NOISE_TOKENS | EXTRA_NOISE


def collect_people_groups(
        data: list[list[str]],
        hdr_row: int,
        cols: dict,
        end_row: int,
        pkg_start_row: int = None
) -> dict:
    r_room = cols.get("room")
    rooms, flat = [], []

    # последняя открытая комната
    cur_kind: str | None = None
    bucket: list[str] = []
    adults_count = 0

    # последний ЯВНО заданный тип (тянем его, если ячейка пустая)
    last_explicit_kind: str | None = None

    # вместимость по типу комнаты
    CAP = {"quad": 4, "trpl": 3, "dbl": 2, "twin": 2, "sgl": 1}

    #  СЛОВАРЬ "НЕ ЛЮДЕЙ" (отели, города, служебный текст)
    BAD_FIO_EXACT = {
        "ADDRESS",
        "MAKKAH",
        "MAKKA",
        "MADINAH",
        "MEDINA",
        "JEDDAH",
        "RIYADH",
        "VALLY",
        "VALLEY",
        "HIKMA",
        "HIKMA 7 DAYS",
        "AMAL 7 DAYS",
        "SWISSOTEL",
        "FAIRMONT",
        "ROTANA",
        "WQF SFI",
        "Address"
    }

    BAD_FIO_CONTAINS = (
        " DAYS",
        "MAKKAH:",
        "MADINAH:",
        "MEDINAH:",
    )

    def flush():
        nonlocal cur_kind, bucket, adults_count
        if cur_kind and bucket:
            rooms.append({
                "kind": cur_kind.upper(),
                "count": len(bucket),
                "people": bucket.copy(),
                "adults": adults_count
            })
            print(f" ЗАКРЫВАЕМ КОМНАТУ: {cur_kind} с {len(bucket)} людьми ({adults_count} взр)")
        cur_kind = None
        bucket = []
        adults_count = 0

    for r in range(hdr_row + 1, min(end_row, len(data))):
        row = data[r]

        # пустые/служебные строки полностью пропускаем
        if not any(str(c or "").strip() for c in row):
            continue

        fio = _get_person_name(row, cols).strip()
        if not fio or len(fio) < 2:
            continue

        fio_up = fio.upper()

        #  ФИЛЬТР: если это не человек, а город/отель/текст — пропускаем
        if fio_up in BAD_FIO_EXACT or any(pat in fio_up for pat in BAD_FIO_CONTAINS):
            print(f"  ️ Служебная строка («{fio}»), пропускаем как не-паломника")
            continue

        print(f" Обрабатываем: {fio} (строка {r})")

        # ребёнок (INF / child) не увеличивает капасити по взрослым
        is_child = row_is_child(row, cols)

        # читаем тип комнаты из колонки
        raw_room = (row[r_room] if r_room is not None and r_room < len(row) else "")
        raw_room = (raw_room or "").strip()

        if raw_room:  # ЯВНЫЙ тип — ВСЕГДА новая комната
            kind = _norm_room_kind(raw_room, last_explicit_kind)
            last_explicit_kind = kind
            print(f"   Явный тип комнаты: {raw_room} -> {kind}")

            # закрываем то, что было открыто (даже если тип совпал)
            if bucket:
                print(" Явный тип — закрываем предыдущую комнату")
                flush()

            cur_kind = kind
            if not cur_kind:
                # если распознать не удалось — пропускаем строку
                print("  ️ Тип не распознан, строка пропущена")
                continue
        else:
            # ПУСТО — тянем предыдущий явный тип
            kind = _norm_room_kind("", last_explicit_kind)
            print(f"   Пустой тип, используем предыдущий: {kind}")

            # если нет открытой комнаты — открываем её на основании last_explicit_kind
            if cur_kind is None and kind is not None:
                cur_kind = kind

            # если и тут тип не ясен — пропускаем
            if cur_kind is None:
                print("  ️ Нет типа для продолжения — пропущено")
                continue

        # добавляем гостя
        bucket.append(fio)
        flat.append(fio)
        if not is_child:
            adults_count += 1

        # закрываем по капасити ТОЛЬКО по взрослым
        cap = CAP.get(cur_kind, 2)
        if adults_count >= cap:
            print(f" ДОСТИГНУТ ЛИМИТ по взрослым: {adults_count}/{cap}, закрываем комнату")
            flush()

    # хвост
    if bucket:
        flush()

    # удаляем комнаты без людей
    rooms = [g for g in rooms if g["people"]]

    #  МЕРДЖ: дети-комнаты (0 взрослых) к предыдущей комнате
    merged = []
    for room in rooms:
        if room["adults"] == 0 and merged:
            prev = merged[-1]
            prev["people"].extend(room["people"])
            prev["count"] = len(prev["people"])
            print(f" Перенесли {len(room['people'])} детей в предыдущую комнату {prev['kind']}")
        else:
            merged.append(room)

    rooms = merged

    print(f" РЕЗУЛЬТАТ: {len(rooms)} комнат")
    for i, room in enumerate(rooms, 1):
        print(f"  {i}. {room['kind']} ({room['adults']} взр): {', '.join(room['people'])}")

    #  ВАЖНО: возвращаем rooms/flat, а не create_default_payload()
    return {
        "rooms": rooms,
        "flat": flat,
    }




def get_person_name(row, cols):
    """Улучшенный парсинг имен"""
    if not row or not cols:
        return ""

    # ПРИОРИТЕТ 1: раздельные Last + First (даже если один из них пустой)
    if "last" in cols or "first" in cols:
        last_idx = cols.get("last", -1)
        first_idx = cols.get("first", -1)

        last = safe_get(row, last_idx, '')
        first = safe_get(row, first_idx, '')

        # Собираем имя из доступных частей
        name_parts = []
        if is_valid_name(last):
            name_parts.append(last.title())
        if is_valid_name(first):
            name_parts.append(first.title())

        if name_parts:
            return " ".join(name_parts)

    # ПРИОРИТЕТ 2: общая колонка Name
    if "name" in cols:
        name_idx = cols["name"]
        name = safe_get(row, name_idx, '')
        if is_valid_name(name):
            return name.title()

    return ""

def safe_get(row, index, default=''):
    """Безопасное получение значения из списка"""
    if not row or index < 0 or index >= len(row):
        return default

    value = str(row[index]) if row[index] is not None else ''
    return value.strip()

def is_valid_name(name: str) -> bool:
    if not name:
        return False
    s = name.strip()

    # 1) запрет дат/чисел/разделителей внутри
    if DATE_TOKEN_RX.search(s):
        return False
    if any(ch.isdigit() for ch in s):
        return False
    if any(ch in "/.-_|" for ch in s):
        return False

    # 2) служебные слова
    low = s.lower()
    if any(tok in low for tok in NOISE_TOKENS):
        return False

    # 3) отбрасываем одиночные маркеры
    invalid_words = {
        'hb','ro','bus','train','business','child','guide',
        'double','triple','quadro','single','yes','tour','own','visa',
        'f','m','inf','', '-', '–'
    }
    if low in invalid_words:
        return False

    # 4) должны быть буквы (лат/кир), допускаем пробел и дефис
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False

    return True


def _norm_hdr(s: str) -> str:
    import re
    return re.sub(r"[\s\u00A0\u202F]+", " ", (s or "").strip().lower())

def _norm_spaces(s: str) -> str:
    return re.sub(r'[\s\u00A0\u202F]+', ' ', (s or '')).strip()


def _get_person_name(row, cols):
    # единая колонка 'Name'
    if "name" in cols and cols["name"] < len(row):
        nm = _norm_spaces(row[cols["name"]])
        return nm if is_valid_name(nm) else ""

    # раздельно last/first
    last  = _norm_spaces(row[cols["last"]])  if "last"  in cols and cols["last"]  < len(row) else ""
    first = _norm_spaces(row[cols["first"]]) if "first" in cols and cols["first"] < len(row) else ""

    parts = []
    if is_valid_name(last):  parts.append(last)
    if is_valid_name(first): parts.append(first)
    return (" ".join(parts)).strip()

def _norm_room_kind(s: str, prev: str | None) -> str | None:
    """Нормализация типа комнаты. Если пусто — возвращаем prev (тянем)."""
    t = _norm_hdr(s)
    if not t:
        return prev  # <-- тянем прошлый

    for k, als in ROOM_ALIASES.items():
        if any(a in t for a in als):
            return k

    # Числовые подсказки
    if "4" in t: return "quad"
    if "3" in t: return "trpl"
    if "2" in t: return "dbl"
    if "1" in t: return "sgl"
    return prev


def pick_nearest_header(candidates: list[tuple[int, dict]], cfg_row: int) -> tuple[int|None, dict]:
    if not candidates:
        return None, {}
    r, cols = min(candidates, key=lambda x: abs(x[0] - cfg_row))
    return r, cols

CHILD_RX = re.compile(r'\b(inf(ant)?|chd|child|kid|реб(ён|ен)ок|дет(и|ск))\b', re.I)

def row_is_child(row: list[str], cols: dict) -> bool:
    """Ребёнок, если в Meal a day явно есть INF/CHILD/CHD и т.п.
       Если колонки нет — fallback: ищем маркеры по всей строке."""
    # 1) приоритет: колонка Meal a day
    meal_idx = cols.get("meal")
    if meal_idx is not None and meal_idx < len(row):
        meal_val = str(row[meal_idx] or "")
        if CHILD_RX.search(meal_val):
            return True

    # 2) запасной путь: ищем по всей строке
    joined = " ".join(str(c or "") for c in row)
    if CHILD_RX.search(joined):
        return True

    return False

def row_has_inf(row: list[str]) -> bool:
    return any(INF_RX.search((c or "")) for c in row)

def canon_room_kind(value: str | None) -> str | None:
    s = norm_hdr(value)
    if not s:
        return None
    for canon, variants in ROOM_ALIASES.items():
        if any(v in s for v in variants):
            return canon
    # иногда пишут «2-мест», «3-мест»
    if "2" in s: return "dbl"
    if "3" in s: return "trpl"
    if "4" in s: return "quad"
    if "1" in s: return "sgl"
    return None

def canon_room(value: str) -> tuple[str|None, int|None]:
    s = (value or "").strip()
    if not s:
        return None, None
    for code, cap, pat in ROOM_PATTERNS:
        if pat.search(s):
            return code, cap
    return None, None

def find_people_header_in_range(data, a, b):
    """Поиск заголовков с расширенным диапазоном"""
    # Сначала ищем вблизи начала пакета
    for r in range(a, min(b, len(data))):
        cols = detect_people_header(data[r])
        if cols:
            print(f"[DEBUG] Найден заголовок в строке {r}: {cols}")
            return r, cols

    # Если не нашли - ищем в первых 30 строках после начала пакета
    for r in range(a, min(a + 30, len(data))):
        cols = detect_people_header(data[r])
        if cols:
            print(f"[DEBUG] Найден заголовок в расширенном поиске (строка {r}): {cols}")
            return r, cols

    return None, None

def _norm_room_kind(s: str, prev: str|None) -> str|None:
    """Определяет тип комнаты, с поддержкой предыдущего значения"""
    t = _norm_hdr(s)

    # Если есть явный тип - возвращаем его
    if t:
        for k, als in ROOM_ALIASES.items():
            if any(a in t for a in als):
                return k
        # Цифровые указания
        if "2" in t: return "dbl"
        if "3" in t: return "trpl"
        if "4" in t: return "quad"
        if "1" in t: return "sgl"

    # Если тип пустой - возвращаем предыдущий
    return prev

def norm_hdr(s: str) -> str:
    """Мягкая нормализация для поиска заголовков"""
    if s is None:
        return ""
    # Базовая очистка, сохраняем пробелы для точного поиска
    s = str(s).replace("\xa0", " ").replace("\u202f", " ").lower().strip()
    s = re.sub(r"\s+", " ", s)  # заменяем множественные пробелы на один
    return s

def ensure_tmp():
    os.makedirs(TMP_DIR, exist_ok=True)

def human_room(kind: str | None) -> str:
    return ROOM_HUMAN_RU.get((kind or "").upper(), "Номер")


def format_caption(idx: int, kind_code: str, names: list[str]) -> str:
    return f" Ваш ваучер: {idx}) {human_room(kind_code)} — {', '.join(names)}"

