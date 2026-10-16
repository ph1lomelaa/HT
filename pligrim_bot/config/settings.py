"""Lazy Google client; refresh dictionaries in place to preserve imports."""
import json
import os
import re
import threading
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from .constants import SCOPES, CREDENTIALS_FILE

_client = None
client = None
ALL_SHEETS = {}
PALM_SHEETS = {}
_lock = threading.RLock()
EXCLUDED_PILGRIM_MONTHS = {
    value.strip() for value in os.getenv('EXCLUDED_PILGRIM_MONTHS', '').split(',') if value.strip()
}

def get_google_client():
    global _client, client
    with _lock:
        if _client is None:
            raw = os.getenv('GOOGLE_CREDS') or os.getenv('GOOGLE_CREDS_JSON')
            creds = (Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
                     if raw else Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES))
            _client = gspread.authorize(creds)
            _client.set_timeout(30)
            client = _client
        return _client

def get_all_accessible_sheets():
    return {s.title: s.id for s in get_google_client().openall()}

def detect_pilgrim_months(sheets):
    months = 'january february march april may june july august september october november december'.split()
    found = {}
    for title, key in sheets.items():
        month = next((m for m in months if re.search(r'\b'+m+r'\b', title.lower())), None)
        if month:
            year = re.search(r'20\d{2}', title)
            label = f"{month.title()} {year.group() if year else datetime.now().year}"
            if label in EXCLUDED_PILGRIM_MONTHS:
                continue
            if label in found:
                raise ValueError(f'Несколько таблиц для {label}; уточните их названия')
            found[label] = key
    return found

def refresh_sheets():
    with _lock:
        sheets = get_all_accessible_sheets()
        months = detect_pilgrim_months(sheets)
        ALL_SHEETS.clear(); ALL_SHEETS.update(sheets)
        PALM_SHEETS.clear(); PALM_SHEETS.update(months)

def get_worksheet(month_key, sheet_name):
    from pligrim_bot.core.google_sheets import find_worksheet_by_title
    return find_worksheet_by_title(get_google_client().open_by_key(PALM_SHEETS[month_key]), sheet_name)
