import os
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from .settings import PALM_SHEETS
from ..core.google_sheets import get_palm_sheet_names
from ..core.utils.validation import city_key
from ..data.sessions import callback_ref


def markup(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def button(text,data):
    return InlineKeyboardButton(text=text,callback_data=data)


def main_scenario_kb():
    rows=[]
    url=os.getenv('WEBAPP_URL','')
    if url.startswith('https://'):
        rows.append([InlineKeyboardButton(text='Открыть Hickmet · Создать ваучер',web_app=WebAppInfo(url=url))])
    rows += [[button('Выбрать пакет в чате','get_month_buttons')],
             [button('Создать индивидуально в чате','indv_voucher_start')],
             [button('Ваучер на рейс','scenario:flight')]]
    return markup(rows)


def get_palm_month_buttons():
    return markup([[button(k,'palm_month:'+k)] for k in PALM_SHEETS]+[[button('Обновить таблицы','refresh_sheets')]])


def get_palm_sheet_buttons(month_key,show_all=False):
    names=get_palm_sheet_names(month_key,include_past=show_all)
    rows=[[button(n[:55],callback_ref('palm_sheet',month_key,n))] for n in (names if show_all else names[:8])]
    if not show_all:rows.append([button('Все листы, включая прошедшие','palm_show_all:'+month_key)])
    rows.append([button('Назад к месяцам','palm_back_to_months')])
    return markup(rows),names


def build_palm_packages_kb(month_key,ws_title,packages):
    return markup([[button(f"{p['title']} · строка {p['row']+1}"[:100],callback_ref('palm_pkg',month_key,ws_title,p['row'],p['title']))] for p in packages])


def preview_main_kb(cache_id):
    return markup([[button('Всё верно — отправить','pv_send:'+cache_id)],
                   [button('Изменить данные','pv_edit:'+cache_id)],
                   [button('Отмена','pv_cancel:'+cache_id)]])


def choose_background_kb(cache_id):
    return markup([[button(f'Вариант {i+1}',f'sel_bg:{cache_id}:{i}') for i in range(3)],
                   [button('Отмена','pv_cancel:'+cache_id)]])


def citykey_for_value(value,fallback):
    key=city_key(value)
    return key if key!='other' else fallback


def slot_for_city(v,citykey):
    if citykey in {'1','2'}:return int(citykey)
    return next((i for i in (1,2) if city_key(v.get(f'city{i}'))==citykey),None)


def get_month_buttons():
    return get_palm_month_buttons()
