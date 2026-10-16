"""Shared flight-package discovery for the website and legacy chat callbacks."""
import hashlib
from datetime import datetime

from pligrim_bot.config.constants import PACKAGE_NAMES
from pligrim_bot.core.parsers.package_parser import FULL_DATE
from pligrim_bot.core.utils.date_utils import parse_date
from pligrim_bot.core.voucher.builder import build_maps_smart, assemble_voucher


def flight_pairs(rows):
    pairs=[];package='Все рейсы'
    for row in rows:
        label=next((str(c).strip() for c in row if any(p.lower() in str(c).lower() for p in PACKAGE_NAMES)),None)
        if label:package=label
        dates=[parse_date(t) for cell in row for t in FULL_DATE.findall(str(cell))]
        dates=[d for d in dates if d]
        if len(dates)>=2 and dates[1]>=dates[0]:
            value=(package,dates[0].strftime('%d.%m.%Y'),dates[1].strftime('%d.%m.%Y'))
            if value not in pairs:pairs.append(value)
    return pairs


def schedule_options(worksheet):
    schedules=[ws for ws in worksheet.spreadsheet.worksheets() if 'расписание' in ws.title.lower()]
    if not schedules:raise ValueError('В таблице нет листа «расписание рейсов». Введите рейсы вручную.')
    maps=build_maps_smart(schedules[0])
    routes={'AJJA':('ALA','JED','JED','ALA'),'AJMA':('ALA','JED','MED','ALA'),
            'AMJA':('ALA','MED','JED','ALA'),'AMMA':('ALA','MED','MED','ALA')}
    result=[]
    for package,dep,ret in flight_pairs(worksheet.get_all_values()):
        for token,(origin,destination,return_origin,return_destination) in routes.items():
            data=assemble_voucher(*maps,dep,ret,token)
            if not data:continue
            def segment(prefix,date,a,b):
                day=datetime.strptime(date,'%d.%m.%Y').date().isoformat()
                return {'airline':'Air Astana','number':data[f'{prefix}_flight'].removeprefix('Рейс ').strip(),
                        'origin':a,'destination':b,'departure_date':day,'arrival_date':day,
                        'departure_time':data[f'{prefix}_time1'],'arrival_time':data[f'{prefix}_time2']}
            result.append({'id':hashlib.sha256(f'{package}|{dep}|{ret}|{token}'.encode()).hexdigest()[:24],
                           'title':package,'label':f'{package} · {dep} → {ret} · {origin}–{destination} / {return_origin}–{return_destination}',
                           'flight':{'outbound':segment('depart',dep,origin,destination),
                                     'inbound':segment('return',ret,return_origin,return_destination)}})
    return result
