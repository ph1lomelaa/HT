import os
import uuid
import re
from PIL import Image, ImageDraw, ImageFont
from pligrim_bot.config.constants import BBOX, TMP_DIR, TTF_REGULAR, TTF_PATH
from pligrim_bot.core.parsers.transport_parser import need_train
from pligrim_bot.core.utils.validation import city_key

# Правильные пути к файлам
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
IMAGES_DIR = os.path.join(ASSETS_DIR, 'images')
TEMPLATES_DIR = os.path.join(ASSETS_DIR, 'templates')

# Пути к изображениям
UAE_MED_PATH = os.path.join(IMAGES_DIR, 'uae-med.png')
JED_MED_TRAIN_PATH = os.path.join(IMAGES_DIR, 'jed-med-train.png')
UAE_MEC_PATH = os.path.join(IMAGES_DIR, 'uae-mec.png')

# Пути к шаблонам
BG_PATH = os.path.join(TEMPLATES_DIR, 'v1.png')
TICKET_PATH = os.path.join(TEMPLATES_DIR, 'ticket.png')

# --- СПИСОК ФОНОВ (Для выбора 1, 2, 3) ---
AVAILABLE_BACKGROUNDS = [
    UAE_MED_PATH,       # Индекс 0
    JED_MED_TRAIN_PATH, # Индекс 1
    UAE_MEC_PATH        # Индекс 2
]

def page2_background(index: int, baggage: str = '8_23') -> str:
    """Resolve a program and its complete cabin/checked baggage allowance."""
    if baggage not in {'8_23', '5_20'}:
        raise ValueError('Выберите норму багажа: 8 + 23 кг или 5 + 20 кг')
    if index not in range(len(AVAILABLE_BACKGROUNDS)):
        raise ValueError('Неизвестная программа поездки')
    path = AVAILABLE_BACKGROUNDS[index]
    if index == 1 or baggage == '8_23':
        return path
    stem = 'uae-med' if index == 0 else 'uae-mec'
    candidates = [os.path.join(IMAGES_DIR, stem + ' 20.png')]
    if index == 0:
        candidates.append(os.path.join(IMAGES_DIR, 'use-med 20.png'))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    raise ValueError('Страница с ручной кладью 5 кг и багажом 20 кг ещё не загружена')


def pick_page2_bg(city1: str | None, transfer_raw: str | None) -> str:
    """Выбирает правильный фон для второй страницы (автоматически)"""
    c = (city1 or "").strip().lower()
    has_train = need_train(transfer_raw)

    if (city_key(c) == "madinah") and has_train:
        return JED_MED_TRAIN_PATH
    if city_key(c) == "madinah":
        return UAE_MED_PATH
    return UAE_MEC_PATH

def slugify_filename_part(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")

def build_filename_from_payload(payload: dict) -> str:
    pilgrims = payload.get("pilgrims") or []
    if isinstance(pilgrims, str):
        parts = [p.strip() for p in pilgrims.split(",") if p.strip()]
        raw = ", ".join(parts) if len(parts) > 1 else pilgrims.strip()
    else:
        names = [str(p).strip() for p in pilgrims if str(p).strip()]
        raw = ", ".join(names)

    if not raw:
        return f"voucher_{uuid.uuid4().hex[:6]}"

    raw = raw.replace("/", "-")
    raw = re.sub(r'[\\:*?"<>|]+', "", raw)
    return raw[:80]

def render_voucher_page1_png(payload: dict) -> str:
    """Рендерит первую страницу ваучера"""
    img = Image.open(BG_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)
    FONT_MAIN = font(22)

    names = [str(n).strip() for n in payload.get('pilgrims', []) if str(n).strip()]
    if not names:
        raise ValueError('Не указаны паломники')
    draw_fitted(draw, '\n'.join(names), BBOX['pilgrims_box'], 26, align='right', wrap=False)

    # Остальные поля
    for k, box in BBOX.items():
        if k == "pilgrims_box":
            continue
        val = payload.get(k)
        if val not in ("", None):
            draw_value(draw, str(val), box, FONT_MAIN)

    file_stem = build_filename_from_payload(payload)
    out = os.path.join(TMP_DIR, f"{uuid.uuid4().hex}_p1.png")
    img.save(out, "PNG")
    return out

def draw_fitted(draw, text, box, size=22, align='left', *, wrap=True):
    x1, y1, x2, y2 = box
    width, height = x2-x1, y2-y1
    for sz in range(size, 7, -1):
        face = font(sz)
        lines = []
        for paragraph in str(text).split('\n'):
            if not wrap:
                lines.append(paragraph)
                continue
            line = ''
            for word in paragraph.split():
                candidate = f'{line} {word}' if line else word
                if line and draw.textlength(candidate, font=face)>width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        bounds = [draw.textbbox((0,0),line,font=face) for line in lines]
        ink_height = max(b[3]-b[1] for b in bounds)
        line_height = max(sz+4,ink_height+4)
        if (len(lines)-1)*line_height+ink_height <= height and all(max(draw.textlength(line,font=face),b[2]-b[0])<=width for line,b in zip(lines,bounds)):
            for i,(line,b) in enumerate(zip(lines,bounds)):
                w = max(draw.textlength(line,font=face),b[2]-b[0])
                x = x2-w if align=='right' else x1+(width-w)/2 if align=='center' else x1
                draw.text((x-b[0],y1+i*line_height-b[1]),line,font=face,fill=(20,20,20))
            return
    raise ValueError('Текст не помещается в ваучер: сократите значение или разделите группу')


def draw_value(draw, text, box, font, align='left'):
    draw_fitted(draw, str(text or ''), box, getattr(font,'size',22), align)


def plural_nights(n) -> str:
    if n is None or n == "":
        return ""
    try:
        n = int(n)
    except Exception:
        return str(n)
    x = abs(n) % 100
    y = x % 10
    if 11 <= x <= 14:
        word = "ночей"
    elif y == 1:
        word = "ночь"
    elif 2 <= y <= 4:
        word = "ночи"
    else:
        word = "ночей"
    return f"{n} {word}"

def font(sz):
    try:
        return ImageFont.truetype(TTF_REGULAR, sz)
    except Exception:
        return ImageFont.load_default()

def load_font(size):
    return font(size)

# --- ИСПРАВЛЕННАЯ ФУНКЦИЯ ---
def build_voucher_pdf(page1_png: str, city1: str | None, transfer_raw: str | None,
                      out_pdf_path: str, bg_index: int = -1, flight_data: dict | None = None,
                      baggage: str = '8_23') -> str:
    """
    Создает 2-страничный PDF ваучера.
    :param bg_index: Номер фона (0, 1, 2). Если -1, выбирает авто.
    """
    if 0 <= bg_index < len(AVAILABLE_BACKGROUNDS):
        # Берем фон по выбору пользователя
        page2_bg = page2_background(bg_index, baggage)
    else:
        # Автовыбор (старая логика)
        auto_bg = pick_page2_bg(city1, transfer_raw)
        page2_bg = page2_background(AVAILABLE_BACKGROUNDS.index(auto_bg), baggage)

    with Image.open(page1_png) as source1, Image.open(page2_bg) as source2:
        p1, p2 = source1.convert("RGB"), source2.convert("RGB")
        extra = render_flight_page(flight_data) if flight_data else None
        p1.save(out_pdf_path, "PDF", save_all=True, append_images=[p2]+([extra] if extra else []))
        p1.close(); p2.close()
        if extra: extra.close()
    return out_pdf_path

def generate_ticket(output_path, data):
    required=['depart_flight','depart_date1','depart_time1','depart_time2','return_flight','return_date1','return_time1','return_time2']
    if any(not data.get(k) for k in required):raise ValueError('Недостаточно данных для ваучера на рейс')
    with Image.open(TICKET_PATH) as source: img=source.convert('RGB')
    draw=ImageDraw.Draw(img)
    # Replace the variable part of the existing branded template.
    draw.rectangle((85,410,1010,700),fill='white')
    dep_city='Медина' if '263' in data['depart_flight'] else 'Джидда'
    ret_city='Медина' if '264' in data['return_flight'] else 'Джидда'
    for x,prefix,route in [(110,'depart',f'Алматы → {dep_city}'),(625,'return',f'{ret_city} → Алматы')]:
        draw_fitted(draw,route,(x,425,x+380,465),26)
        draw_fitted(draw,data[f'{prefix}_flight'],(x,485,x+380,525),24)
        draw_fitted(draw,data[f'{prefix}_date1'],(x,540,x+380,580),24)
        draw_fitted(draw,f"{data[f'{prefix}_time1']} → {data[f'{prefix}_time2']}",(x,600,x+380,645),30)
    img.save(output_path,'PNG');img.close()
    return output_path

def generate_pdf_from_png(png_path):
    pdf_path = os.path.splitext(png_path)[0] + ".pdf"
    img = Image.open(png_path).convert("RGB")
    img.save(pdf_path, "PDF", resolution=100.0)
    return pdf_path

def render_flight_page(flight):
    """A separate page with manually entered flights; all times are airport-local."""
    with Image.open(TICKET_PATH) as source: image=source.convert('RGB')
    draw=ImageDraw.Draw(image)
    draw.rectangle((85,410,1010,705),fill='white')
    for x,key in [(110,'outbound'),(625,'inbound')]:
        leg=flight.get(key)
        if not leg:
            draw_fitted(draw,'Обратный рейс\nне включён',(x,485,x+380,565),24)
            continue
        draw_fitted(draw,f"{leg['origin']} → {leg['destination']}",(x,420,x+380,470),25)
        draw_fitted(draw,f"{leg['airline']} · {leg['number']}",(x,485,x+380,530),22)
        draw_fitted(draw,f"{leg['departure_date']}  {leg['departure_time'][:5]}",(x,545,x+380,580),25)
        draw_fitted(draw,f"{leg['arrival_date']}  {leg['arrival_time'][:5]}",(x,590,x+380,625),25)
        draw_fitted(draw,'Вылет / прибытие · местное время',(x,645,x+380,675),15)
    return image
