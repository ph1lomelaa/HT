
from datetime import datetime

from pligrim_bot.config.constants import *
from pligrim_bot.core.utils.date_utils import _parse_start_end
from pligrim_bot.core.utils.text_utils import norm_pkg, norm_title, n, lc
from pligrim_bot.core.utils.validation import canon_family
import re

_HOTELS_HINTS = ("hotel","hotels","отель","отели","размещение","accommodation")

def extract_hotels_block_for_package(data, pkg_title, start_row):
    """
    data – get_all_values() с листа
    pkg_title – название пакета ("15.11-22.11 NIYET/7d")
    start_row – индекс строки, где нашли пакет
    """
    pkg_fam = canon_family(pkg_title)

    H = len(data)
    blocks = []
    city_order = []

    # собираем два города: сначала Makkah, потом Madinah
    for rr in range(start_row + 1, min(start_row + 15, H)):
        row = data[rr]
        text = " ".join(x or "" for x in row).lower()

        if not text.strip():
            continue

        city = None
        if "makkah" in text or "макка" in text or "mekka" in text:
            city = "Makkah"
        elif "madinah" in text or "медина" in text or "medina" in text:
            city = "Madinah"

        if not city:
            continue

        # индекс города
        city_col = next((i for i, c in enumerate(row) if c and city.lower() in str(c).lower()), None)
        if city_col is None:
            continue

        hotel = _extract_hotel_near(row, city_col)
        d1, d2 = as_ddmmYYYY_pair(" ".join(row))

        if hotel and d1 and d2 and city not in city_order:
            blocks.append({
                "city": city,
                "hotel": hotel,
                "when": f"{d1} – {d2}",
                "checkin": "16:00"
            })
            city_order.append(city)

            if len(blocks) == 2:
                break

    return blocks if blocks else None



def extract_hotels_rows_for_package(ws_hotels, package_title: str):
    """
    Ищем на листе ОТЕЛЕЙ два блока (Медина/Мекка) для конкретного пакета.
    """
    data = ws_hotels.get_all_values()
    if not data:
        print("❌ Лист отелей пустой")
        return []

    print(f"🔍 Поиск отелей для пакета: {package_title}")

    # Извлекаем даты из названия пакета
    pkg_dates = _extract_dates_from_package_title(package_title)
    if not pkg_dates:
        print(f"❌ Не удалось извлечь даты из названия пакета: {package_title}")
        return []

    print(f"📅 Даты пакета: {pkg_dates}")

    H = len(data)
    all_candidates = []

    for rr in range(H):
        row = data[rr]
        row_text = " ".join(str(cell) for cell in row).lower()

        # --- город ---
        city_key = None
        city_col = None

        for c, cell in enumerate(row[:18]):
            cell_text = str(cell or "").lower()
            if any(name in cell_text for name in ["madinah", "medina", "madina", "медин", "медина"]):
                city_key = "madinah"
                city_col = c
                break
            elif any(name in cell_text for name in ["makkah", "makka", "mecca", "mekka", "макк", "мекка"]):
                city_key = "makkah"
                city_col = c
                break

        if not city_key:
            continue

        # --- отель ---
        hotel = ""
        for c in range(city_col + 1, min(city_col + 6, len(row))):
            val = (row[c] or "").strip()
            if val and not any(keyword in val.lower() for keyword in ["madinah", "makkah", "medina", "mecca", "медин", "мекка"]):
                hotel = val
                break

        # --- даты ---
        raw_text = " ".join(str(cell) for cell in row)
        d1, d2 = as_ddmmYYYY_pair(raw_text)

        # ПРОВЕРЯЕМ СОВПАДЕНИЕ ДАТ С ПАКЕТОМ
        if not (d1 and d2):
            continue

        # Сравниваем даты отеля с датами пакета
        if not _dates_match_package(d1, d2, pkg_dates):
            continue

        if not (hotel and d1 and d2):
            continue

        s, e = _parse_start_end(f"{d1} – {d2}")
        if not s:
            continue

        nights = (e - s).days if e else None

        all_candidates.append({
            "city": city_key,
            "hotel": hotel,
            "when": f"{d1} – {d2}",
            "nights": nights,
            "row": rr,
            "start_date": s,
        })

        print(f"✅ Найден подходящий отель: {city_key} - {hotel} - {d1} – {d2}")

    if not all_candidates:
        print("❌ Не найдено подходящих отелей для пакета")
        return []

    # --- Берем по одному лучшему блоку на город ---
    best_by_city = {}
    for c in sorted(all_candidates, key=lambda x: (x["city"], x["row"])):
        if c["city"] not in best_by_city:
            best_by_city[c["city"]] = c
            print(f"🏆 Выбран лучший для {c['city']}: {c['hotel']}")

    blocks = list(best_by_city.values())
    blocks.sort(key=lambda x: x["start_date"])

    print(f"📦 Итоговые блоки: {len(blocks)}")
    for block in blocks:
        print(f"  - {block['city']}: {block['hotel']} ({block['when']})")

    return blocks

def _extract_dates_from_package_title(package_title: str) -> tuple:
    """
    Извлекает даты из названия пакета в формате '05.11-12.11 NIYET/7d'
    Возвращает (start_date, end_date) или None
    """
    # Ищем паттерн дат в начале названия
    date_match = re.search(r'(\d{1,2})\.(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})', package_title)
    if not date_match:
        return None

    d1, m1, d2, m2 = date_match.groups()
    current_year = datetime.now().year

    try:
        start_date = datetime(current_year, int(m1), int(d1))
        end_date = datetime(current_year, int(m2), int(d2))
        return (start_date, end_date)
    except ValueError:
        return None

def _dates_match_package(hotel_start: str, hotel_end: str, pkg_dates: tuple) -> bool:
    """
    Проверяет, совпадают ли даты отеля с датами пакета
    """
    if not pkg_dates:
        return False

    pkg_start, pkg_end = pkg_dates

    try:
        # Парсим даты отеля
        hotel_start_dt = datetime.strptime(hotel_start, "%d/%m/%Y")
        hotel_end_dt = datetime.strptime(hotel_end, "%d/%m/%Y")

        # Проверяем пересечение дат
        return (hotel_start_dt >= pkg_start and hotel_end_dt <= pkg_end) or \
            (abs((hotel_start_dt - pkg_start).days) <= 2)  # допуск +/- 2 дня
    except Exception:
        return False

def payload_from_hotels_sheet(ss, package_title: str):
    """
    1) Собираем кандидатов-OTELI листов.
    2) На каждом пытаемся вытащить 2 блока (Медина/Мекка) ИМЕННО для нужного пакета,
       учитывая эквивалентность IZI <-> AMAL.
    3) Если на явных 'Hotels' не нашли — проверяем 'похожие' листы.
    """
    pkg_fam = canon_family(package_title)
    hotel_ws_list = find_hotels_sheets(ss)
    tried = []

    def _try(ws) -> dict | None:
        tried.append(ws.title)
        blocks = extract_hotels_rows_for_package(ws, package_title)  # см. п.4 — там теперь same_family
        if not blocks:
            return None
        p = []
        for blk in blocks[:2]:
            p.append({
                "city": "Madinah" if blk["city"] == "madinah" else "Makkah",
                "hotel": blk["hotel"],
                "when": blk["when"],
                "nights": blk["nights"],
                "checkin": "16:00",
            })
        if not p:
            return None
        p1 = p[0]
        p2 = p[1] if len(p) > 1 else None
        return {
            "city1": p1["city"], "hotel1": p1["hotel"], "dates1": p1["when"], "checkin1": p1["checkin"], "stay1": p1["nights"], "stay1_nights": p1["nights"],
            "city2": (p2["city"] if p2 else None), "hotel2": (p2["hotel"] if p2 else None), "dates2": (p2["when"] if p2 else None),
            "checkin2": (p2["checkin"] if p2 else "16:00"), "stay2": (p2["nights"] if p2 else None), "stay2_nights": (p2["nights"] if p2 else None),
            "service": "Виза и страховка",
            "meal": "Завтрак и ужин",
            "guide": "Групповой гид",
            "excursions": "Мекка, Медина",
            "tech_guide": "+966 56 328 0325",
            "transfer": "—",
            "_source": {"from": "hotels_sheet", "sheet": ws.title}
        }

    # 1) Явные HOTELS-листы
    for ws in hotel_ws_list:
        out = _try(ws)
        if out: return out

    # 2) Похожие листы
    for ws in similar_hotels_sheets(ss):
        if ws.title in tried:
            continue
        out = _try(ws)
        if out: return out

    return None

def find_hotels_sheets(ss) -> list[gspread.Worksheet]:
    """Вернёт все листы, которые похожи на 'отели/размещение'."""
    out = []
    for ws in ss.worksheets():
        t = (ws.title or "").strip()
        if HOTELS_TITLE_RE.search(t):
            out.append(ws)
    return out

def similar_hotels_sheets(ss) -> list[gspread.Worksheet]:
    """
    Если точных 'Hotels' нет или пакет не найден, берём верхние листы,
    где в первых строках встречаются города/даты — как 'похожие'.
    """
    cands = []
    for ws in ss.worksheets()[:6]:
        try:
            vals = ws.get_all_values()[:12]
        except Exception:
            continue
        blob = " ".join(" ".join(r[:6]) for r in vals).lower()
        if (any(k in blob for k in ("madinah","medina","madina","медин","медина","makkah","mecca","мекк","макк"))
                and re.search(r"\d{1,2}[./-]\d{1,2}([./-]\d{2,4})?", blob)):
            cands.append(ws)
    return cands

def find_hotels_worksheet(ss) -> gspread.Worksheet | None:
    # 1) точные/частичные совпадения
    for ws in ss.worksheets():
        t = (ws.title or "").strip().lower().replace("\xa0", " ").replace("\u202f", " ")
        if any(h in t for h in HOTELS_NAME_HINTS):
            return ws

    # 2) самый верхний лист, у которого в первых двух колонках встречаются города/даты
    for ws in ss.worksheets()[:5]:
        try:
            vals = ws.get_all_values()[:10]
        except Exception:
            continue
        text = " ".join(" ".join(r[:3]) for r in vals).lower()
        if any(c in text for c in ("madinah","medina","makkah","mecca","медин","макк")) and re.search(r"\d{1,2}[./-]\d{1,2}", text):
            return ws
    return None

def norm_spaces(s: str) -> str:
    return re.sub(r'[\s\u00A0\u202F]+', ' ', (s or '')).strip()


# ---- извлекаем из листа ОТЕЛЕЙ одну “конфигурацию” по имени пакета ----
def extract_hotels_config(ws_hotels: gspread.Worksheet, package_title: str, city_col=None) -> dict | None:
    """
    Ищет строку(и) для пакета в листе отелей.
    Ожидаемый формат: в колонке B ('packages') названия пакетов,
    в соседних колонках — City / Hotel / Dates (могут быть в разных местах).
    Возвращает dict:
      {
        "city1": "Madinah", "hotel1": "...", "dates1": "dd/mm/yyyy – dd/mm/yyyy", "stay1_nights": 3,
        "city2": "Makkah",  "hotel2": "...", "dates2": "dd/mm/yyyy – dd/mm/yyyy", "stay2_nights": 7,
      }
    либо None, если пакет не найден.
    """
    data = ws_hotels.get_all_values()
    if not data:
        return None

    # найдём колонку с пакетами (часто это 'B', но лучше по заголовку)
    hdr = [x.strip().lower() for x in (data[0] if data else [])]
    col_pkg = None
    for i, cell in enumerate(hdr):
        if any(k in cell for k in ("package", "пакет")):
            col_pkg = i
            break
    if col_pkg is None:
        # если нет заголовков — считаем пакеты во 2-й колонке
        col_pkg = 1 if len(data[0]) > 1 else 0

    want = norm_pkg(package_title)
    picks = []
    for r, row in enumerate(data[1:], start=1):
        pkg = norm_pkg(row[col_pkg] if col_pkg < len(row) else "")
        if pkg and (want in pkg or pkg in want):
            picks.append((r, row))

    if not picks:
        return None

    def _extract_hotel_near(row: list[str], city_col: int | None) -> str | None:
        """
        Ищет название отеля в строке row рядом с колонкой города.
        Игнорирует города, даты и служебные пометки типа Gr.10.
        """
    if not row:
        return None

    # область поиска вокруг city_col
    if city_col is None:
        start_c, end_c = 0, len(row)
    else:
        start_c = max(0, city_col - 3)
        end_c   = min(len(row), city_col + 8)

    for c in range(start_c, end_c):
        val = norm_spaces(row[c])
        if not val:
            continue

        low = val.lower()

        # пропускаем города
        if any(name in low for name in (
                "madinah","medina","madina","медин","медина",
                "makkah","makka","mecca","mekka","макк","мекка"
        )):
            continue

        # пропускаем даты
        if DATE_ANY.search(val):
            continue

        # пропускаем явные групповые пометки
        if re.search(r"\bgr\.\s*\d+", low):
            continue

        return val  # первая нормальная текстовая ячейка — это отель

    return None



def _extract_hotel_near(row: list[str], city_col: int | None) -> str | None:
    """
    Ищет название отеля в строке row рядом с колонкой города.
    Игнорирует города, даты и служебные пометки типа Gr.10.
    """
    if not row:
        return None

    # область поиска вокруг city_col
    if city_col is None:
        start_c, end_c = 0, len(row)
    else:
        start_c = max(0, city_col - 3)
        end_c   = min(len(row), city_col + 8)

    for c in range(start_c, end_c):
        val = norm_spaces(row[c])
        if not val:
            continue

        low = val.lower()

        # пропускаем города
        if any(name in low for name in (
                "madinah","medina","madina","медин","медина",
                "makkah","makka","mecca","mekka","макк","мекка"
        )):
            continue

        # пропускаем даты
        if DATE_ANY.search(val):
            continue

        # пропускаем явные групповые пометки
        if re.search(r"\bgr\.\s*\d+", low):
            continue

        return val  # первая нормальная текстовая ячейка — это отель

    return None



def extract_city_block_from_hotels(ws_hotels, package_title: str):
    """
    На листе отелей:
      - в кол. B указаны названия пакетов (как на листах паломников);
      - рядом по строкам встречаются строки с городом, отелем и двумя датами.
    Возвращает dict с hotel/when по двум городам или None, если не нашли.
    """
    data = ws_hotels.get_all_values()
    if not data:
        return None

    # Нормализатор названия пакета
    want = norm_title(package_title)

    # Ищем все строки, где в любом столбце есть наш пакет (надёжнее, чем жесткая 'кол. B')
    pkg_rows = []
    for r, row in enumerate(data):
        row_join = " ".join((x or "") for x in row)
        if norm_title(row_join) and want in norm_title(row_join):
            pkg_rows.append(r)

    if not pkg_rows:
        return None

    # Возьмем ближайший блок ниже первого вхождения пакета
    start_r = pkg_rows[0]
    end_r = min(len(data), start_r + 60)  # «окно» на всякий случай

    mad = {"hotel": None, "when": None}
    mak = {"hotel": None, "when": None}

    for rr in range(start_r, end_r):
        row = data[rr]

        # Пробуем для Медины
        h, w = extract_city_line(row, "madinah")
        if h and not mad["hotel"]: mad["hotel"] = h
        if w and not mad["when"]:  mad["when"]  = w

        # Пробуем для Мекки
        h, w = extract_city_line(row, "makkah")
        if h and not mak["hotel"]: mak["hotel"] = h
        if w and not mak["when"]:  mak["when"]  = w

        if mad["hotel"] and mad["when"] and mak["hotel"] and mak["when"]:
            return {"mad": mad, "mak": mak}

    return None

def norm_date(val: str) -> str | None:
    if not isinstance(val, str):
        val = str(val or "")
    s = val.strip()
    m = DATE_RE.search(s)
    if not m:
        return None
    d, mth, y = m.groups()
    y = f"20{y}" if len(y) == 2 else y
    return f"{d.zfill(2)}.{mth.zfill(2)}.{y}"

def extract_city_line(row):
    """
    Строка вида:
        Makkah   [hotel?]  15/11/2025   20/11/2025
    или:
        Madinah  Vally     20/11/2025   22/11/2025

    Возвращает:
        (city, hotel_or_none, d1, d2)
    """
    clean = lambda x: norm_spaces(x or "")
    parts = [clean(x) for x in row if clean(x)]

    if not parts:
        return None, None, None, None

    # Определяем город (может быть в любой части строки)
    city = None
    for part in parts:
        low_part = part.lower()
        if any(name in low_part for name in ["madinah", "medina", "madina", "медина"]):
            city = "Madinah"
            break
        elif any(name in low_part for name in ["makkah", "makka", "mecca", "мекка"]):
            city = "Makkah"
            break

    if not city:
        return None, None, None, None

    # Ищем даты (любые два подряд)
    dates = []
    for part in parts:
        d = norm_date(part)
        if d:
            dates.append(d)

    if len(dates) >= 2:
        d1, d2 = dates[:2]
    else:
        return city, None, None, None

    # hotel = текст между городом и первой датой
    hotel = None
    city_index = parts.index(next(p for p in parts if city.lower() in p.lower()))
    date_index = parts.index(next(p for p in parts if norm_date(p) == d1))

    if date_index > city_index + 1:
        hotel_parts = parts[city_index + 1:date_index]
        hotel = " ".join(hotel_parts) if hotel_parts else None

    return city, hotel, d1, d2

def as_ddmmYYYY_pair(text: str) -> tuple[str|None, str|None]:
    m = DATE_ANY.findall(text or "")
    if len(m) >= 2:
        def mk_dmY(t):
            d,m,y = t
            y = ("20"+y) if len(y)==2 else y
            return f"{d.zfill(2)}/{m.zfill(2)}/{y}"
        return mk_dmY(m[0]), mk_dmY(m[1])

    m2 = DATE_ISO.findall(text or "")
    if len(m2) >= 2:
        def mk_iso(t):
            y,m,d = t
            return f"{d}/{m}/{y}"
        return mk_iso(m2[0]), mk_iso(m2[1])
    return None, None

def find_hotels_sheet_name(wb):
    for ws in wb.worksheets:
        if any(h in lc(ws.title) for h in _HOTELS_HINTS):
            return ws.title
    city_hints = ("madinah","medina","makkah","mecca","медин","медина","макка","мекка")
    date_rx = re.compile(r"\b\d{1,2}[./-]\d{1,2}([./-]\d{2,4})?\b")
    for ws in wb.worksheets[:6]:
        rows = ws.iter_rows(min_row=1, max_row=20, min_col=1, max_col=20, values_only=True)
        blob = " ".join(n(v) for row in rows for v in row)
        bl = blob.lower()
        if any(c in bl for c in city_hints) and date_rx.search(bl):
            return ws.title
    return None

def dump_sheet(ws, max_rows=100, max_cols=24):
    width = 0
    rows_cache = []
    for row in ws.iter_rows(min_row=1, max_row=max_rows, min_col=1, max_col=max_cols, values_only=True):
        rowv = [n(v) for v in row]
        rows_cache.append(rowv)
        width = max(width, len(rowv))
    width = min(width, max_cols)

    header = " | ".join([f"col{i+1}" for i in range(width)])
    print("\n📄 HOTELS — лист:", ws.title)
    print("    | " + header)
    print("----+" + "-" * len(header))
    for i, rowv in enumerate(rows_cache, start=1):
        rowv = [(c if c else "·") for c in rowv[:width]]
        print(f"{i:>3} | " + " | ".join(rowv))
    print("\n✅ Готово.\n")