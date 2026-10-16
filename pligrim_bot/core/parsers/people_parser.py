"""Header-driven guest parsing. Never silently discard a guest without a room."""
import os
import re
from pligrim_bot.config.constants import ROOM_ALIASES, ROOM_HUMAN_RU, TMP_DIR


def norm_hdr(value):
    return re.sub(r'\s+', ' ', str(value or '').replace('\xa0', ' ')).strip().lower()


def detect_people_header(row):
    aliases = {
        'last': {'last name', 'lastname', 'surname', 'фамилия'},
        'first': {'first name', 'firstname', 'имя'},
        'name': {'name', 'names', 'guest name', 'guestname', 'full name', 'first/last name', 'first / last name', 'last/first name', 'last / first name', 'фио', 'ф.и.о.', 'имя и фамилия'},
        'room': {'type of room', 'room type', 'тип номера', 'тип размещения', 'room', 'размещение'},
        'meal': {'meal', 'meal a day', 'питание', 'meal plan'},
        'room_id': {'room number', 'room no', 'номер комнаты', '№ комнаты'},
        'category': {'pax type','passenger type','категория'},
        'age': {'age','возраст'},
    }
    cols = {}
    for i, cell in enumerate(row):
        text = norm_hdr(cell).strip(':')
        if text in aliases['name']:
            cols['name']=i;continue
        for kind, names in aliases.items():
            if text in names or any(norm_hdr(part).strip(':') in names for part in re.split(r'[/\n]',str(cell))):
                cols[kind] = i
                break
    return cols if any(k in cols for k in ('name', 'last', 'first')) else None


def safe_get(row, index, default=''):
    return str(row[index] or '').strip() if index is not None and 0 <= index < len(row) else default


def is_valid_name(value):
    s = str(value or '').strip()
    if not s or any(c.isdigit() for c in s):
        return False
    # Cities can also be real names (e.g. MEDINA); context comes from the name column.
    if norm_hdr(s) in {'hb', 'ro', 'bus', 'train', 'child', 'inf', 'chd', 'guide', 'transfer',
                       'double', 'triple', 'quad', 'single', 'yes', 'no', 'итог', 'total',
                       'last name', 'first name', 'name', 'фамилия', 'имя', 'фио', 'address'}:
        return False
    return len([c for c in s if c.isalpha()]) >= 2 and all(c.isalpha() or c in " -–’'`" for c in s)


def _get_person_name(row, cols):
    if 'name' in cols:
        name = safe_get(row, cols['name'])
        return name if is_valid_name(name) else ''
    parts = [safe_get(row, cols.get(k)) for k in ('last', 'first')]
    return ' '.join(p for p in parts if is_valid_name(p))


get_person_name = _get_person_name
CHILD_RX = re.compile(r'\b(inf(ant)?|chd|child|kid|реб[её]нок|дети)\b', re.I)


def row_is_child(row, cols):
    # Search designated meal/room cells, not names or arbitrary agency notes.
    return (any(CHILD_RX.search(safe_get(row, cols.get(k))) for k in ('meal', 'room', 'age', 'category'))
            or any(CHILD_RX.fullmatch(str(cell).strip()) for i,cell in enumerate(row) if i not in {cols.get('first'),cols.get('last'),cols.get('name')}))


def canon_room_kind(value):
    s = norm_hdr(value)
    for code, aliases in ROOM_ALIASES.items():
        if any(re.search(r'(?<!\w)' + re.escape(a) + r'(?!\w)', s) for a in aliases):
            return code
    match = re.fullmatch(r'([1-4])(?:\s*[- ]?\s*мест\w*|\s*pax)?', s)
    return {'1':'sgl','2':'dbl','3':'trpl','4':'quad'}.get(match.group(1)) if match else None


def _norm_room_kind(value, prev=None):
    return canon_room_kind(value) or (prev if not norm_hdr(value) or CHILD_RX.search(str(value)) else None)


def collect_people_groups(data, hdr_row, cols, end_row, pkg_start_row=None):
    rooms, flat = [], []
    current = None
    previous_kind = None
    capacities = {'sgl':1, 'dbl':2, 'twin':2, 'trpl':3, 'quad':4}
    for row in data[hdr_row+1:min(end_row, len(data))]:
        if detect_people_header(row):
            continue
        name = _get_person_name(row, cols)
        if not name:
            continue
        raw = safe_get(row, cols.get('room'))
        kind = _norm_room_kind(raw, previous_kind) or previous_kind
        if kind: previous_kind = kind
        child = row_is_child(row, cols)
        room_id = safe_get(row, cols.get('room_id'))
        if (current is None or (canon_room_kind(raw) and not child and current['people'])
                or (kind and current['kind'] != kind.upper())
                or (room_id and room_id != current.get('_room_id'))
                or (not child and current['adults'] >= capacities.get(kind, 99))):
            current = {'kind':(kind or '').upper(), 'count':0, 'people':[], 'adults':0, '_room_id':room_id}
            rooms.append(current)
        current['people'].append(name)
        current['count'] += 1
        current['adults'] += not child
        flat.append(name)
    for room in rooms: room.pop('_room_id', None)
    return {'rooms':rooms, 'flat':flat}


def find_people_header_in_range(data, a, b):
    for r in range(max(0, a), min(b, len(data))):
        cols = detect_people_header(data[r])
        if cols:
            return r, cols
    return None, None


def human_room(kind):
    return ROOM_HUMAN_RU.get(str(kind or '').upper(), 'Номер')


def ensure_tmp():
    os.makedirs(TMP_DIR, exist_ok=True)


def format_caption(idx, kind_code, names):
    return f'{idx}) {human_room(kind_code)} — {", ".join(names)}'
