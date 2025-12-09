from pligrim_bot.config.constants import *

def normtxt(s: str) -> str:
    return re.sub(r"[\s\u00A0\u202F]+", " ", (s or "")).strip()

def row_has_table_header(row: list[str]) -> bool:
    joined = " ".join((row or [])[:12])
    return any(h in joined for h in HEADER_HINTS)

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()

def norm_title(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("\xa0", " ").replace("\u202f", " ")
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s+days\b", "days", s)

    # --- добавь это ---
    s = s.replace("/", "")                         # слэши не мешают поиску
    s = re.sub(r'(?<=\b4)\s*you\b', 'u', s)        # 4 YOU → 4U
    s = re.sub(r'\s+', "", s)                      # как было: убрать все пробелы

    return s.strip()

def norm_pkg(s: str) -> str:
    s = (s or "").lower()
    s = s.replace("\xa0", " ").replace("\u202f", " ")
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s+days\b", "days", s)
    s = re.sub(r"\s+", "", s)
    return s.strip()

def norm(s: str) -> str:
    # нижний регистр + убрать обычные/неразрывные/узкие пробелы и табы/переводы строк
    return re.sub(r"[\s\u00A0\u202F]+", "", (s or "").lower())

def n(s): return re.sub(r"[\s\u00A0\u202F]+", " ", ("" if s is None else str(s))).strip()
def lc(s): return n(s).lower()

def safe_cb_text(s: str) -> str:
    """Чтобы callback_data не ломалась из-за пробелов/двоеточий."""
    return re.sub(r'[:|]', '-', (s or '')).strip()

def row_text(row):
    return " ".join((cell or "").strip() for cell in row if cell).strip()
