from datetime import datetime
import re
from datetime import datetime

from pligrim_bot.config.constants import DATE_ANY, DATE_ISO, DATE_RE


def extract_start_date(title):

    date_match = re.search(r'(\d{2}\.\d{2})-\d{2}\.\d{2}', title)
    if date_match:
        start_date_str = date_match.group(1) + f".{datetime.now().year}"
        try:
            return datetime.strptime(start_date_str, "%d.%m.%Y")
        except:
            return datetime.min
    return datetime.min

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

def _pick_ddmm_pair_from_title(title: str):
    m = re.search(r'(\d{1,2})[.\-/](\d{1,2}).*?[–—-].*?(\d{1,2})[.\-/](\d{1,2})', title or "")
    if not m:
        return None, None
    d1, m1, d2, m2 = m.groups()
    return (int(d1), int(m1)), (int(d2), int(m2))

def _row_has_ddmm(row_join: str, dd: str, mm: str) -> bool:
    """
    Проверяет, встречается ли в строке дата с этим днём и месяцем
    (любой разделитель, год опционален).
    """
    # варианты: 29/10, 29.10, 29-10, 29/10/2025 и т.п.
    pat = rf'(?<!\d){dd}[./-]{mm}(?:[./-]\d{{2,4}})?(?!\d)'
    return re.search(pat, row_join) is not None

def _year_from_sheet(ws) -> int:
    m = re.search(r'(20\d{2})', ws.spreadsheet.title + " " + ws.title)
    return int(m.group(1)) if m else datetime.now().year

def _anchors_from_title(title: str, ws):
    a1, a2 = _pick_ddmm_pair_from_title(title)
    if not a1 or not a2:
        return None, None
    Y = _year_from_sheet(ws)
    start = datetime(Y, a1[1], a1[0])
    end   = datetime(Y, a2[1], a2[0])
    if end < start:  # переход через Новый год
        end = end.replace(year=Y+1)
    return start, end

def _parse_start_end(when: str):
    try:
        a, b = [x.strip() for x in (when or "").split("–")]
        d1 = datetime.strptime(a, "%d/%m/%Y")
        d2 = datetime.strptime(b, "%d/%m/%Y")
        return d1, d2
    except Exception:
        return None, None

def to_ddmmyyyy(m):
    d, mth, y = m
    y = ("20" + y) if len(y) == 2 else y
    return f"{d.zfill(2)}.{mth.zfill(2)}.{y}"

def to_slash_fmt(ddmm):
    d, mth, y = ddmm.split(".")
    return f"{d}/{mth}/{y}"

def two_dates_in_row(cells):
    # возвращает ("dd/mm/yyyy", "dd/mm/yyyy") либо (None, None)
    txt = " ".join((c or "") for c in cells)
    found = DATE_ANY.findall(txt)
    if len(found) >= 2:
        a = to_ddmmyyyy(found[0]); b = to_ddmmyyyy(found[1])
        # на выход — формат, как у твоего сборщика (с / )
        return to_slash_fmt(a), to_slash_fmt(b)
    return None, None

def nights_ddmmyyyy_with_slash(d1, d2):
    from datetime import datetime
    try:
        a = datetime.strptime(d1, "%d/%m/%Y")
        b = datetime.strptime(d2, "%d/%m/%Y")
        return max(0, (b - a).days)
    except Exception:
        return None

def _parse_start_date(when: str):
    """Возвращает datetime начала периода DD/MM/YYYY – DD/MM/YYYY."""
    if not when:
        return None
    try:
        a = when.split("–")[0].strip()
        return datetime.strptime(a, "%d/%m/%Y")
    except Exception:
        return None

def norm_date_str(s: str) -> str | None:
    """Любую 5.11.25 / 05.11.2025 / 05/11/25 → 05.11.2025"""
    m = DATE_RE.search(s or "")
    if not m:
        return None
    d, mth, y = m.groups()
    y = ("20" + y) if len(y) == 2 else y
    return f"{d.zfill(2)}.{mth.zfill(2)}.{y}"

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

def year_from_title(title: str) -> int | None:
    m = re.search(r"(20\d{2})", title)
    return int(m.group(1)) if m else None
