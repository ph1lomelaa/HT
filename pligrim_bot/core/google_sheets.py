import difflib
import re
from datetime import datetime, date
from gspread import WorksheetNotFound

from pligrim_bot.config.settings import PALM_SHEETS, get_google_client
from pligrim_bot.core.utils.date_utils import norm_date_str
from pligrim_bot.core.utils.text_utils import norm_title

DDMM_RE = re.compile(r'(\d{1,2})\.(\d{1,2})')

def get_palm_sheet_names(month_key: str, *, include_past: bool = False) -> list[str]:
    """
    Возвращает отфильтрованные названия листов для выбранного месяца:
    - берём год из month_key (например, 2025);
    - оставляем только те листы, у которых dd.mm >= сегодня в этом году;
    - листы без даты считаем служебными — показываем всегда.
    """
    try:
        if month_key not in PALM_SHEETS:
            print(f"❌ Месяц {month_key} не найден в PALM_SHEETS")
            return []

        sheet_id = PALM_SHEETS[month_key]
        client = get_google_client()
        if not client:
            print("❌ Google Sheets клиент не доступен")
            return []

        ss = client.open_by_key(sheet_id)
        base_year = resolve_base_year(month_key, datetime.now().year)
        today = datetime.now().date()

        result = []
        for ws in ss.worksheets():
            ddmm = parse_first_ddmm(ws.title)
            if ddmm is None:
                # лист без даты — показываем (часто это инфо/шаблоны)
                result.append(ws.title)
                continue

            d, mth = ddmm
            try:
                sheet_date = date(base_year, mth, d)
                if include_past or sheet_date >= today:
                    result.append(ws.title)
            except ValueError:
                continue

        # Добавляем сортировку по дате
        def get_sort_key(title):
            ddmm = parse_first_ddmm(title)
            if ddmm is None:
                return (1, title)
            d, mth = ddmm
            try:
                sheet_date = date(base_year, mth, d)
                return (0, sheet_date)
            except ValueError:
                return (1, title)

        result.sort(key=get_sort_key)
        return result

    except Exception as e:
        print(f"❌ Ошибка в get_palm_sheet_names: {e}")
        return []

def get_sheet_titles_by_id(spreadsheet_id: str) -> list[str]:
    """Получает названия всех листов в документе по ID"""
    try:
        client = get_google_client()
        if not client:
            return []

        sheet = client.open_by_key(spreadsheet_id)
        worksheet_titles = [ws.title for ws in sheet.worksheets()]
        return worksheet_titles
    except Exception as e:
        print(f"❌ Ошибка получения листов для {spreadsheet_id}: {e}")
        return []

def parse_first_ddmm(title: str):
    """Возвращает (day, month) из названия листа или None, если не найдено."""
    m = DDMM_RE.search(title or "")
    if not m:
        return None
    d, mth = int(m.group(1)), int(m.group(2))
    if not (1 <= d <= 31 and 1 <= mth <= 12):
        return None
    return d, mth

def resolve_base_year(month_key: str, fallback_year: int | None = None) -> int:
    """Берёт год из строки 'OCTOBER 2025'. Если года нет — fallback на текущий."""
    m = re.search(r'(20\d{2})', month_key or "")
    if m:
        return int(m.group(1))
    return fallback_year or datetime.now().year

def find_worksheet_by_title(ss, wanted_title: str):
    """Ищет лист по названию, терпимо к пробелам/вариантам написания.
    Возвращает gspread.Worksheet или кидает WorksheetNotFound.
    """
    # 1) точное совпадение
    for ws in ss.worksheets():
        if ws.title == wanted_title:
            return ws

    # 2) нормализованное совпадение
    want = norm_title(wanted_title)
    candidates = ss.worksheets()
    for ws in candidates:
        if norm_title(ws.title) == want:
            return ws

    # 3) fuzzy fallback (на всякий случай)
    titles = [ws.title for ws in candidates]
    guess = difflib.get_close_matches(wanted_title, titles, n=1, cutoff=0.65)
    if guess:
        print(f"[WARN] Worksheet '{wanted_title}' not found, using close match '{guess[0]}'")
        return ss.worksheet(guess[0])

    raise WorksheetNotFound(wanted_title)

def token_from_schedule(dep: str, ret: str,
                        OUT_AJ: dict, OUT_AM: dict,
                        RET_JA: dict, RET_MA: dict) -> str | None:
    """Определяет тип маршрута по датам вылета и возврата"""
    d = norm_date_str(dep)
    r = norm_date_str(ret)

    depart_kind = "AJ" if d in OUT_AJ else ("AM" if d in OUT_AM else None)
    return_kind = "JA" if r in RET_JA else ("MA" if r in RET_MA else None)

    if depart_kind == "AJ" and return_kind == "JA": return "AJJA"
    if depart_kind == "AJ" and return_kind == "MA": return "AJMA"
    if depart_kind == "AM" and return_kind == "JA": return "AMJA"
    # "AMMA" у нас не используется для пакетов 7 дней
    return None

def match_city_any(cell: str) -> str | None:
    """Определяет город по тексту ячейки"""
    s = (cell or "").lower()

    # Мадина
    if any(a in s for a in ("madinah", "medina", "madina", "медин", "медина")):
        return "madinah"

    # Мекка
    if any(a in s for a in ("makkah", "mecca", "мекка", "макка")):
        return "makkah"

    # Джедда
    if any(a in s for a in ("jeddah", "jedda", "джедд", "джидд")):
        return "jeddah"

    # Аль-Ула
    if any(a in s for a in ("alula", "al-ula", "аль-ула", "алула")):
        return "alula"

    return None

def get_worksheet_data(worksheet, range_name: str = None):
    """Получает данные с листа"""
    try:
        if range_name:
            return worksheet.get(range_name)
        else:
            return worksheet.get_all_values()
    except Exception as e:
        print(f"❌ Ошибка получения данных с листа {worksheet.title}: {e}")
        return []

def find_column_index_by_header(worksheet, header_patterns: list, start_row: int = 1):
    """Находит индекс колонки по заголовку"""
    try:
        headers = worksheet.row_values(start_row)
        for i, header in enumerate(headers):
            header_lower = header.lower()
            for pattern in header_patterns:
                if pattern in header_lower:
                    return i
        return -1
    except Exception as e:
        print(f"❌ Ошибка поиска колонки: {e}")
        return -1

def extract_pilgrims_data(worksheet, date_range: str):
    """Основная функция для извлечения данных паломников"""
    try:
        all_data = get_worksheet_data(worksheet)
        if not all_data:
            return []

        # Здесь твоя логика парсинга данных паломников
        pilgrims = []

        # Пример поиска колонок
        name_col = find_column_index_by_header(worksheet, ["фио", "name", "guest"])
        room_col = find_column_index_by_header(worksheet, ["room", "тип номера"])

        for i, row in enumerate(all_data[1:], start=2):  # пропускаем заголовок
            if name_col < len(row) and row[name_col].strip():
                pilgrim_data = {
                    'name': row[name_col] if name_col < len(row) else '',
                    'room_type': row[room_col] if room_col < len(row) else '',
                    'row_number': i
                }
                pilgrims.append(pilgrim_data)

        return pilgrims

    except Exception as e:
        print(f"❌ Ошибка извлечения данных паломников: {e}")
        return []