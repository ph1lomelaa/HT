"""Shared validation for preview, editing and final delivery."""
import re
from pligrim_bot.core.utils.date_utils import normalize_date_range, parse_date_range
from pligrim_bot.core.voucher.builder import ensure_chronological_city_order
from pligrim_bot.core.parsers.people_parser import canon_room_kind
from pligrim_bot.core.utils.validation import city_key

FIELDS = {'hotel','dates','checkin','service','transfer','meal','guide','excursions','tech_guide','room_type'}


def apply_field(voucher, field, value):
    base, _, city = field.partition('@')
    if base not in FIELDS: raise ValueError('Неизвестное поле')
    value = str(value or '').strip()
    if not value: raise ValueError('Введите непустое значение')
    if len(value)>500: raise ValueError('Слишком длинное значение (не более 500 символов)')
    if base=='dates': value=normalize_date_range(value)
    if base=='checkin' and not re.fullmatch(r'(?:[01]?\d|2[0-3]):[0-5]\d',value):
        raise ValueError('Введите время в формате ЧЧ:ММ')
    if base=='room_type':
        kind=canon_room_kind(value)
        if not kind: raise ValueError('Укажите SGL, DBL, TWIN, TRPL или QUAD')
        for room in voucher.get('people',{}).get('rooms',[]): room['kind']=kind.upper()
        return
    if base in {'hotel','dates','checkin'}:
        slot = int(city) if city in {'1','2'} else next((i for i in (1,2) if city_key(voucher.get(f'city{i}'))==city),None)
        if slot is None: raise ValueError('Город не найден. Добавьте его в превью.')
        voucher[f'{base}{slot}']=value
    else: voucher[base]=value
    ensure_chronological_city_order(voucher)


def voucher_errors(voucher):
    errors=[]
    cities=[i for i in (1,2) if voucher.get(f'city{i}')]
    if not cities: errors.append('Добавьте город, отель и даты проживания')
    for i in cities:
        if not voucher.get(f'hotel{i}'): errors.append(f'Укажите отель для города {i}')
        try: parse_date_range(voucher.get(f'dates{i}'))
        except ValueError: errors.append(f'Укажите корректные даты для города {i}')
    rooms=voucher.get('people',{}).get('rooms',[])
    if not rooms or not any(r.get('people') for r in rooms): errors.append('Нет паломников')
    for room in rooms:
        capacities={'SGL':1,'DBL':2,'TWIN':2,'TRPL':3,'QUAD':4}
        if room.get('kind','').upper() not in capacities:
            errors.append('Укажите размещение для всех комнат'); break
        if room.get('adults',len(room.get('people',[]))) > capacities[room['kind'].upper()]:
            errors.append('Число взрослых превышает вместимость выбранного номера');break
    return errors


def require_valid_voucher(voucher):
    errors=voucher_errors(voucher)
    if errors: raise ValueError('Нельзя создать ваучер:\n• '+'\n• '.join(errors))
