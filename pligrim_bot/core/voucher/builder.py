import re
from datetime import datetime

from pligrim_bot.config.constants import TIME_RE, FLIGHT_RE
from pligrim_bot.core.utils.date_utils import norm_date_str, norm_date
from pligrim_bot.core.utils.validation import *
from pligrim_bot.core.voucher.render import plural_nights


def base_payload_from(voucher: dict) -> dict:
    def _fmt_nights(val):
        # принимаем либо *_nights (число), либо 'stay1' (может быть числом)
        return plural_nights(val) if val not in (None, "") else ""

    n1 = voucher.get('stay1_nights', voucher.get('stay1'))
    n2 = voucher.get('stay2_nights', voucher.get('stay2'))

    return {
        "city1":    city_ru(voucher.get("city1")),
        "hotel1":   voucher.get("hotel1") or "",
        "stay1":    _fmt_nights(n1),
        "room1":    "",
        "dates1":   voucher.get("dates1") or "",
        "checkin1": voucher.get("checkin1") or "17:00",

        "city2":    city_ru(voucher.get("city2")),
        "hotel2":   voucher.get("hotel2") or "",
        "stay2":    _fmt_nights(n2),
        "room2":    "",
        "dates2":   voucher.get("dates2") or "",
        "checkin2": voucher.get("checkin2") or "17:00",

        "service":    voucher.get("service") or "Виза и страховка",
        "transfer":   voucher.get("transfer") or "—",
        "meal":       voucher.get("meal") or "Завтрак и ужин",
        "guide":      voucher.get("guide") or "Групповой гид",
        "excursions": voucher.get("excursions") or "Мекка, Медина",
        "tech_guide": voucher.get("tech_guide") or "+966 56 328 0325",
    }

def ensure_chronological_city_order(v: dict) -> None:
    """
    Улучшенная логика определения порядка городов.
    """
    def parse_date_range(date_str):
        if not date_str:
            return None
        try:
            parts = date_str.split('–')
            if len(parts) != 2:
                return None
            start_date = datetime.strptime(parts[0].strip(), "%d/%m/%Y")
            return start_date
        except Exception:
            return None

    date1 = parse_date_range(v.get("dates1", ""))
    date2 = parse_date_range(v.get("dates2", ""))

    # Если оба города есть и порядок неправильный - меняем местами
    if date1 and date2 and date2 < date1:
        print(f"🔁 Меняем порядок городов: {date2} -> {date1}")

        # Меняем все поля местами
        swap_fields = ["city", "hotel", "dates", "checkin", "stay", "stay_nights"]
        for fld in swap_fields:
            v[f"{fld}1"], v[f"{fld}2"] = v.get(f"{fld}2"), v.get(f"{fld}1")

        # Пересчитываем ночи
        v["stay1_nights"] = nights_from_dates(v.get("dates1", ""))
        v["stay2_nights"] = nights_from_dates(v.get("dates2", ""))
        v["stay1"] = plural_nights(v["stay1_nights"])
        v["stay2"] = plural_nights(v["stay2_nights"])

def nights_from_dates(dates_range: str) -> int | None:
    """Вычисляет количество ночей из строки с датами"""
    if not dates_range:
        return None

    try:
        parts = [p.strip() for p in dates_range.split("–")]
        if len(parts) != 2:
            return None

        d1 = datetime.strptime(parts[0], "%d/%m/%Y")
        d2 = datetime.strptime(parts[1], "%d/%m/%Y")
        return max(0, (d2 - d1).days)
    except Exception:
        return None

def _parse_from_date(dates_range: str) -> datetime | None:
    if not dates_range:
        return None

    # Пробуем разные форматы разделителей
    formats_to_try = [
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\s*[–—-]\s*(\d{1,2})/(\d{1,2})/(\d{4})\b",
        r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[–—-]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\b",
        r"\b(\d{1,2})-(\d{1,2})-(\d{4})\s*[–—-]\s*(\d{1,2})-(\d{1,2})-(\d{4})\b"
    ]

    for pattern in formats_to_try:
        m = re.search(pattern, dates_range)
        if m:
            d1, m1, y1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
            try:
                return datetime(y1, m1, d1)
            except Exception:
                continue

    return None

def assemble_voucher(OUT_AJ, OUT_AM, RET_JA, RET_MA, dep, ret, token):
    dep = norm_date_str(dep); ret = norm_date_str(ret)

    if token == "AJJA":      # ALA→JED / JED→ALA
        o, b = OUT_AJ.get(dep), RET_JA.get(ret)
    elif token == "AJMA":    # ALA→JED / MED→ALA
        o, b = OUT_AJ.get(dep), RET_MA.get(ret)
    elif token == "AMJA":    # ALA→MED / JED→ALA (на будущее)
        o, b = OUT_AM.get(dep), RET_JA.get(ret)
    else:
        o = b = None

    if not o or not b:
        return None

    return {
        "depart_date": dep,
        "depart_flight": f"Рейс {o['flight']}",
        "depart_time1": o["t1"],
        "depart_date1": dep,
        "depart_time2": o["t2"],
        "depart_date2": dep,
        "return_date": ret,
        "return_flight": f"Рейс {b['flight']}",
        "return_time1": b["t1"],
        "return_date1": ret,
        "return_time2": b["t2"],
        "return_date2": ret,
    }

def assemble_voucher_from_one_row_style(ws, dep_date, ret_date, token):
    """
    Идём по каждой строке: если в строке есть искомые даты, собираем ваучер.
    token:
      'AJMA' — ALA→JED  /  MED→ALA  (KC265/KC8201, KC264)
      'AMJA' — ALA→MED  /  JED→ALA  (KC263, KC266/KC8202)
      'AJJA' — ALA→JED  /  JED→ALA  (KC265/KC8201, KC266/KC8202)
    """
    dep_date = norm_date_str(dep_date)
    ret_date = norm_date_str(ret_date)
    rows = ws.get_all_values()

    # какие коды подходят под направление
    want = {
        "AJMA": (("KC265","KC8201"), ("KC264",)),          # out AJ, back MA
        "AMJA": (("KC263",),         ("KC266","KC8202")),  # out AM, back JA
        "AJJA": (("KC265","KC8201"), ("KC266","KC8202")),  # out AJ, back JA
    }.get(token, ((),()))

    for row in rows:
        segs = extract_segments_from_row(row)
        if not segs:
            continue
        # сгруппируем по коду рейса (в строке каждый код встречается обычно 0/1 раз)
        by_code = {s["flight"]: s for s in segs}

        # подберём нужные сегменты с учётом нескольких возможных кодов
        dep_seg = None
        for code in want[0]:
            s = by_code.get(code)
            if s and s["date"] == dep_date:
                dep_seg = s
                break

        ret_seg = None
        for code in want[1]:
            s = by_code.get(code)
            if s and s["date"] == ret_date:
                ret_seg = s
                break

        # если обе части нашлись в ОДНОЙ строке — это то, что тебе нужно
        if dep_seg and ret_seg:
            return {
                "depart_date": dep_date,
                "depart_flight": f"Рейс {dep_seg['flight']}",
                "depart_time1": dep_seg["dep"],
                "depart_date1": dep_date,
                "depart_time2": dep_seg["arr"],
                "depart_date2": dep_date,

                "return_date": ret_date,
                "return_flight": f"Рейс {ret_seg['flight']}",
                "return_time1": ret_seg["dep"],
                "return_date1": ret_date,
                "return_time2": ret_seg["arr"],
                "return_date2": ret_date,
            }

    return None  # в одной строке не нашли — можно падать в резервную логику

def build_maps_smart(ws):
    """
    Заполняет карты OUT_AJ / OUT_AM / RET_JA / RET_MA, проходя по всей таблице.
    Работает и с KC 264/8201 (с пробелом), и с обычными KC264/8201.
    """
    data = ws.get_all_values()
    OUT_AJ, OUT_AM, RET_JA, RET_MA = {}, {}, {}, {}

    def put(map_, date, flight, dep, arr):
        d = norm_date_str(date)
        if d and dep and arr:
            map_[d] = {"flight": flight, "t1": dep, "t2": arr}

    for row in data[1:]:
        segs = extract_segments_from_row(row)
        for s in segs:
            f = s["flight"]
            if   f in ("KC265", "KC8201"): put(OUT_AJ, s["date"], f, s["dep"], s["arr"])
            elif f == "KC263":            put(OUT_AM, s["date"], f, s["dep"], s["arr"])
            elif f in ("KC266", "KC8202"):put(RET_JA, s["date"], f, s["dep"], s["arr"])
            elif f == "KC264":            put(RET_MA, s["date"], f, s["dep"], s["arr"])

    print(f"✅ build_maps(): ALA→JED={len(OUT_AJ)}, JED→ALA={len(RET_JA)}, ALA→MED={len(OUT_AM)}, MED→ALA={len(RET_MA)}")
    return OUT_AJ, OUT_AM, RET_JA, RET_MA

def build_maps(ws):
    """
    Сканирует лист 'расписание рейсов' и извлекает ВСЕ направления:
      KC265 — ALA→JED
      KC266 — JED→ALA
      KC263 — ALA→MED
      KC264 — MED→ALA
      KC8201 / KC8202 — чартеры
    """
    data = ws.get_all_values()

    OUT_AJ, OUT_AM, RET_JA, RET_MA = {}, {}, {}, {}

    def put(map_, date, flight, t1, t2):
        d = norm_date_str(date)
        if d and flight and t1 and t2:
            map_[d] = {"flight": flight.strip(), "t1": t1.strip(), "t2": t2.strip()}

    for row in data[1:]:
        if not any(row):
            continue

        # --- Блок 1: ALA→JED и JED→ALA
        if len(row) > 5 and "KC265" in row[2]:
            put(OUT_AJ, row[1], row[2], row[3], row[4])
        if len(row) > 12 and "KC266" in row[9]:
            put(RET_JA, row[8], row[9], row[10], row[11])

        if len(row) > 20 and "KC263" in row[17]:
            put(OUT_AM, row[16], row[17], row[18], row[19])
        if len(row) > 25 and "KC264" in row[22]:
            put(RET_MA, row[21], row[22], row[23], row[24])

        if "KC 8201" in " ".join(row):
            idx = row.index("KC 8201")
            if idx >= 2:
                put(OUT_AJ, row[idx - 1], "KC8201", row[idx + 1], row[idx + 2])
        if "KC 8202" in " ".join(row):
            idx = row.index("KC 8202")
            if idx >= 2:
                put(RET_JA, row[idx - 1], "KC8202", row[idx + 1], row[idx + 2])

    print(f"✅ build_maps(): "
          f"ALA→JED={len(OUT_AJ)}, JED→ALA={len(RET_JA)}, "
          f"ALA→MED={len(OUT_AM)}, MED→ALA={len(RET_MA)}")

    return OUT_AJ, OUT_AM, RET_JA, RET_MA

def cell(row, i):
    return (row[i] if 0 <= i < len(row) else "") or ""

def find_left_date_in_row(row, i, lookback=3):
    # дата обычно в i-1, но надёжнее проверить несколько ячеек влево
    for k in range(1, lookback+1):
        d = norm_date(cell(row, i-k))
        if d:
            return d
    return None

def safe_time(s):
    s = (s or "").strip()
    return s if TIME_RE.match(s) else ""

def extract_segments_from_row(row):
    """
    Возвращает список сегментов из строки:
    [{flight:'KC265', date:'dd.mm.yyyy', dep:'hh:mm', arr:'hh:mm', route:'ALA JED'}, ...]
    """
    segs = []
    for i, raw in enumerate(row):
        s = (raw or "").replace("\xa0", " ")
        m = FLIGHT_RE.search(s)
        if not m:
            continue
        flight = ("KC" + m.group(1)).upper()  # нормализуем KC 264 -> KC264

        date = find_left_date_in_row(row, i, lookback=3)
        dep  = safe_time(cell(row, i+1))
        arr  = safe_time(cell(row, i+2))
        route = (cell(row, i+3) or "").strip().upper()

        # базовая валидация
        if date and dep and arr:
            segs.append({
                "flight": flight,
                "date": date,
                "dep": dep,
                "arr": arr,
                "route": route
            })
    return segs

