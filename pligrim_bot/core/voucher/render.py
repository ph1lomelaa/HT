import os
import uuid
import re
from PIL import Image, ImageDraw, ImageFont
from pligrim_bot.config.constants import BBOX, TMP_DIR, TTF_REGULAR, TTF_PATH
from pligrim_bot.core.parsers.transport_parser import need_train

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

def pick_page2_bg(city1: str | None, transfer_raw: str | None) -> str:
    """Выбирает правильный фон для второй страницы (автоматически)"""
    c = (city1 or "").strip().lower()
    has_train = need_train(transfer_raw)

    if ("madinah" in c or "медин" in c) and has_train:
        return JED_MED_TRAIN_PATH
    if "madinah" in c or "медин" in c:
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
    FONT_PEOPLE = font(26)
    FONT_MAIN = font(22)

    # Имена (правый столбец)
    x1, y1, x2, y2 = BBOX["pilgrims_box"]
    y = y1
    line_h = 32
    for nm in payload.get("pilgrims", []):
        nm = str(nm).strip()
        if not nm:
            continue
        if y + line_h > y2:
            break
        draw.text(
            (x2 - draw.textlength(nm, font=FONT_PEOPLE), y),
            nm, font=FONT_PEOPLE, fill=(20, 20, 20)
        )
        y += line_h

    # Остальные поля
    for k, box in BBOX.items():
        if k == "pilgrims_box":
            continue
        val = payload.get(k)
        if val not in ("", None):
            draw_value(draw, str(val), box, FONT_MAIN)

    file_stem = build_filename_from_payload(payload)
    out = os.path.join(TMP_DIR, f"{file_stem}_p1.png")
    img.save(out, "PNG")
    return out

def draw_value(draw, text, box, font, align="left"):
    x1, y1, x2, y2 = box
    s = "" if text is None else str(text)
    w = draw.textlength(s, font=font)
    if align == "right":
        x = x2 - w
    elif align == "center":
        x = x1 + (x2 - x1 - w) // 2
    else:
        x = x1
    draw.text((x, y1), s, font=font, fill=(20, 20, 20))

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
                      out_pdf_path: str, bg_index: int = -1) -> str:
    """
    Создает 2-страничный PDF ваучера.
    :param bg_index: Номер фона (0, 1, 2). Если -1, выбирает авто.
    """
    if 0 <= bg_index < len(AVAILABLE_BACKGROUNDS):
        # Берем фон по выбору пользователя
        page2_bg = AVAILABLE_BACKGROUNDS[bg_index]
    else:
        # Автовыбор (старая логика)
        page2_bg = pick_page2_bg(city1, transfer_raw)

    p1 = Image.open(page1_png).convert("RGB")
    p2 = Image.open(page2_bg).convert("RGB")

    p1.save(out_pdf_path, "PDF", save_all=True, append_images=[p2])
    return out_pdf_path

def generate_ticket(output_path, data):
    # (Оставляем заглушку или ваш старый код билета, он не влияет на ошибку)
    pass

def generate_pdf_from_png(png_path):
    pdf_path = os.path.splitext(png_path)[0] + ".pdf"
    img = Image.open(png_path).convert("RGB")
    img.save(pdf_path, "PDF", resolution=100.0)
    return pdf_path