"""Parse a worksheet snapshot; resolve hotels without crossing passenger blocks."""
import re
from datetime import datetime
from pligrim_bot.core.parsers.people_parser import detect_people_header, collect_people_groups, find_people_header_in_range
from pligrim_bot.core.parsers.transport_parser import collect_transport
from pligrim_bot.core.utils.date_utils import parse_date, normalize_date_range, parse_date_range

DATE_RANGE = re.compile(r'(?<!\d)(\d{1,2})[./-](\d{1,2})(?:[./-](\d{4}|\d{2}))?\s*[–—-]\s*(\d{1,2})[./-](\d{1,2})(?:[./-](\d{4}|\d{2}))?(?!\d)')
FULL_DATE = re.compile(r'(?<!\d)(?:20\d{2}-\d{1,2}-\d{1,2}|\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2}))(?!\d)')
CITY_ALIASES = {'Madinah':{'madinah','medinah','medina','madina','медина','мадина'},
                'Makkah':{'makkah','makka','mecca','mekka','мекка','макка'}}


def normtxt(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def kind_from_title(title):
    text = normtxt(title).lower()
    for kind, pattern in [('niyet',r'niyet|ниет'), ('hikma',r'hikma|хикма'),
                          ('izi',r'izi|4\s*(?:you|u)|amal|амал'),('aroya',r'aroya|ароя'),
                          ('aa',r'aa'),('standard',r'standard')]:
        if re.search(r'(?<!\w)(?:'+pattern+r')(?![a-zа-я])',text):
            return kind
    return ''


def _variant(title):
    text = str(title).lower()
    if 'standard' in text or 'standart' in text:return 'standard'
    if 'econom' in text or 'эконом' in text:return 'econom'
    return next((v for v in ('fairmont','swiss','shohada') if v in text), '')


def find_palm_packages(ws):
    data = ws.get_all_values()
    found = []
    last_header = -1
    for h, row in enumerate(data):
        if not detect_people_header(row): continue
        candidates = []
        for r in range(max(last_header+1, h-8), h):
            cells = [normtxt(c) for c in data[r] if normtxt(c)]
            if not cells: continue
            text = ' '.join(cells)
            # A package title is separate from passenger rows and hotel configurations.
            if any(_city_cell(c) for c in cells): continue
            if DATE_RANGE.search(text) or (kind_from_title(text) and len(cells) <= 3 and not re.search(r'guide|гид',text,re.I)):
                candidates.append((r,text))
        if candidates:
            r, title = candidates[-1]
        else:
            r, title = h, normtxt(getattr(ws,'title','Паломники'))
        if not candidates and found:
            last_header=h
            continue
        found.append({'title':title,'row':r,'col':0,'header_row':h})
        last_header = h
    return found


def _city_cell(value):
    head = normtxt(value).lower().rstrip(':')
    for city, aliases in CITY_ALIASES.items():
        if head in aliases or any(head.startswith(a+':') for a in aliases): return city
    return None


def _city_row(row):
    # Passenger rows contain birth/passport dates, not accommodation dates.
    if row and re.fullmatch(r'\d+', normtxt(row[0])): return None
    for c, cell in enumerate(row):
        city = _city_cell(cell)
        if not city: continue
        dates = [parse_date(t) for value in row[c+1:] for t in FULL_DATE.findall(str(value))]
        dates = [d for d in dates if d]
        if len(dates)<2 or dates[1]<dates[0]: continue
        inline = str(cell).split(':',1)[1].strip() if ':' in str(cell) else ''
        hotel = inline or next((normtxt(x) for x in row[c+1:] if normtxt(x) and not FULL_DATE.search(str(x))), '')
        if not hotel: continue
        return {'city':city,'hotel':hotel,'start':dates[0],'end':dates[1],
                'kind':kind_from_title(' '.join(str(x) for x in row[:c])),
                'label':' '.join(str(x) for x in row[:c]),'raw':row}
    return None


def _config_blocks(data):
    blocks=[];current=None;pending_label=''
    for r,row in enumerate(data):
        if detect_people_header(row):
            pending_label=''
            continue
        item=_city_row(row)
        if not item:
            cells=[normtxt(c) for c in row if normtxt(c)]
            text=' '.join(cells)
            if len(cells)<=3 and kind_from_title(text) and not re.search(r'guide|гид',text,re.I):pending_label=text
            continue
        if not item['kind'] and pending_label:
            item['kind']=kind_from_title(pending_label);item['label']=pending_label
        pending_label=''
        if (current is None
                or (item['kind'] and current['kind'] and item['kind']!=current['kind'])
                or (_variant(item['label']) and _variant(current['label']) and _variant(item['label'])!=_variant(current['label']))
                or any(c['city']==item['city'] for c in current['cities'])):
            current={'row':r,'end_row':r,'kind':item['kind'],'label':item['label'],'cities':[]}
            blocks.append(current)
        if not current['kind'] and item['kind']:current['kind']=item['kind'];current['label']=item['label']
        current['cities'].append(item);current['end_row']=r
    return blocks


def _resolve_config(data, a, b, title, packages, year=None):
    blocks=_config_blocks(data)
    kind=kind_from_title(title);variant=_variant(title)
    anchor=DATE_RANGE.search(title)
    matching=[]
    for block in blocks:
        if kind and block['kind'] and block['kind']!=kind: continue
        if variant and not any(_variant(part)==variant for part in [block['label']]+[c['hotel'] for c in block['cities']]):continue
        duration=re.search(r'(?<!\d)(\d+)\s*(?:days|d|дн)',title,re.I)
        block_duration=re.search(r'(?<!\d)(\d+)\s*(?:days|d|дн)',block['label'],re.I)
        if duration and block_duration and duration.group(1)!=block_duration.group(1):continue
        local=a<=block['row']<b
        # Shared footer configurations must explicitly match the family, unless there is only one candidate.
        if not local and kind and not block['kind']: continue
        tour_start=min(c['start'] for c in block['cities'])
        tour_end=max(c['end'] for c in block['cities'])
        if anchor:
            d,m,_,rd,rm,_=anchor.groups()
            expected_start=(int(d),int(m));expected_end=(int(rd),int(rm))
            if (tour_end.day,tour_end.month)!=expected_end: continue
            if year or anchor.group(3):
                try:
                    start_year=int(anchor.group(3) or year)
                    if start_year<100:start_year+=2000
                    end_year=int(anchor.group(6) or (start_year+(int(rm)<int(m))))
                    if end_year<100:end_year+=2000
                    expected_begin=datetime(start_year,int(m),int(d))
                    expected_finish=datetime(end_year,int(rm),int(rd))
                except ValueError:continue
                if tour_end!=expected_finish or (expected_begin-tour_start).days not in (0,1):continue
            # Overnight arrivals may begin the hotel stay one day before the tour.
            from datetime import timedelta
            if not any(((tour_start+timedelta(days=delta)).day,(tour_start+timedelta(days=delta)).month)==expected_start for delta in (0,1)):continue
        matching.append((block,local))
    local=[v for v,l in matching if l]
    candidates=local or [v for v,l in matching]
    if len(candidates)!=1:
        return None, ('Не найдена конфигурация отелей' if not candidates else 'Найдено несколько конфигураций отелей; уточните даты или вариант пакета')
    return candidates[0],None


def collect_voucher_by_package(ws, pkg_row, pkg_title=None, *, look_through_next_packages=0):
    data=ws.get_all_values()
    class Snapshot:
        title=getattr(ws,'title','Паломники')
        def get_all_values(self): return data
    packages=find_palm_packages(Snapshot())
    selected=next((p for p in packages if p['row']==pkg_row),None)
    if selected is None: raise ValueError('Пакет больше не найден на листе. Обновите список.')
    a=selected['row'];b=next((p['row'] for p in packages if p['row']>a),len(data))
    title=selected['title']
    hdr,cols=find_people_header_in_range(data,a,b)
    # Stop guests before the footer hotel configuration.
    configs=_config_blocks(data)
    people_end=min([c['row'] for c in configs if a<c['row']<b] or [b])
    people=collect_people_groups(data,hdr,cols,people_end) if hdr is not None else {'rooms':[],'flat':[]}
    v={'city1':None,'hotel1':None,'dates1':None,'stay1':None,'checkin1':'16:00',
       'city2':None,'hotel2':None,'dates2':None,'stay2':None,'checkin2':'16:00',
       'service':'Виза и страховка','meal':'Завтрак и ужин','guide':'Групповой гид',
       'excursions':'Мекка, Медина','tech_guide':'+966 56 328 0325','transfer':'Автобус',
       'people':people,'room_groups':people['rooms'],'_people_flat':people['flat'],
       'kind':kind_from_title(title),'source':{'search_range':[a,b],'people_from':{'hdr_row':hdr,'cols':cols}},'warnings':[]}
    year_match=re.search(r'20\d{2}',str(getattr(getattr(ws,'spreadsheet',None),'title','')))
    block,warning=_resolve_config(data,a,b,title,packages,int(year_match.group()) if year_match else None)
    if warning:v['warnings'].append(warning)
    if block:
        for i,c in enumerate(sorted(block['cities'],key=lambda c:c['start']),1):
            v.update({f'city{i}':c['city'],f'hotel{i}':c['hotel'],f'dates{i}':f"{c['start']:%d/%m/%Y} – {c['end']:%d/%m/%Y}",f'stay{i}_nights':(c['end']-c['start']).days})
        v['source']['config_row']=block['row']
        next_config=min([c['row'] for c in configs if c['row']>block['row']] or [len(data)])
        transport=collect_transport(data,block['row'],next_config)
    else:
        transport=collect_transport(data,a,people_end)
    if transport['types']:v['transfer']=transport['display']
    v['_transfer_details']=transport['details']
    if not people['flat']:v['warnings'].append('В пакете пока нет паломников')
    from pligrim_bot.core.voucher.builder import ensure_chronological_city_order
    ensure_chronological_city_order(v)
    return v


def package_bounds(ws,pkg_row):
    data=ws.get_all_values();packages=find_palm_packages(ws)
    return pkg_row,next((p['row'] for p in packages if p['row']>pkg_row),len(data)),packages


def find_config_block(data,start_r,end_r,want_kind):
    blocks=[b for b in _config_blocks(data[start_r:end_r]) if b['kind']==kind_from_title(want_kind)]
    if len(blocks)!=1:return None,{}
    block=blocks[0];payload={}
    for i,c in enumerate(sorted(block['cities'],key=lambda c:c['start']),1):
        payload.update({f'city{i}':c['city'],f'hotel{i}':c['hotel'],f'dates{i}':f"{c['start']:%d/%m/%Y} – {c['end']:%d/%m/%Y}"})
    return block['row']+start_r,payload
