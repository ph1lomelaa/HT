import os
import uuid
import re
from PIL import Image, ImageDraw, ImageFont

from pligrim_bot.config.constants import BBOX, TMP_DIR, TTF_PATH
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


def pick_page2_bg(city1: str | None, transfer_raw: str | None) -> str:
    """Выбирает правильный фон для второй страницы"""
    c = (city1 or "").strip().lower()
    has_train = need_train(transfer_raw)

    if ("madinah" in c or "медин" in c) and has_train:
        return JED_MED_TRAIN_PATH
    if "madinah" in c or "медин" in c:
        return UAE_MED_PATH
    return UAE_MEC_PATH

def slugify_filename_part(s: str) -> str:
    """
    Превращает строку в безопасную часть имени файла:
    убирает лишние символы, пробелы заменяет на _
    и оставляет только буквы (латиница/кириллица) и цифры.
    """
    s = s.strip()
    s = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def build_filename_from_payload(payload: dict) -> str:
    """
    Имя файла = список паломников, например:
    ["MARYPOV FARKHAD", "MARYPOV MURAT"] ->
        "MARYPOV FARKHAD, MARYPOV MURAT"
    """
    pilgrims = payload.get("pilgrims") or []

    # если в payload пришла одна строка
    if isinstance(pilgrims, str):
        # "MARYPOV FARKHAD , MARYPOV MURAT" -> две фамилии
        parts = [p.strip() for p in pilgrims.split(",") if p.strip()]
        raw = ", ".join(parts) if len(parts) > 1 else pilgrims.strip()
    else:
        names = [str(p).strip() for p in pilgrims if str(p).strip()]
        raw = ", ".join(names)

    if not raw:
        return f"voucher_{uuid.uuid4().hex[:6]}"

    # минимальная очистка: убираем совсем запрещённые символы
    raw = raw.replace("/", "-")
    raw = re.sub(r'[\\:*?"<>|]+', "", raw)

    # ограничим длину
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


def generate_voucher(output_path, data):
    """Генерирует ваучер (альтернативная версия)"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    img = Image.open(BG_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    GRAY = "#000000"
    FONT_PEOPLE = load_font(17.5)
    FONT_MAIN = load_font(21)

    # Список паломников
    x1, y1, x2, y2 = BBOX["pilgrims_box"]
    y = y1
    line_step = 30
    for nm in data.get("pilgrims", []):
        txt = str(nm)
        w = draw.textlength(txt, font=FONT_PEOPLE)
        draw.text((x2 - w, y), txt, font=FONT_PEOPLE, fill=(20, 20, 20))
        y += line_step

    # Остальные поля
    for key, box in BBOX.items():
        if key == "pilgrims_box":
            continue
        if key in data and data[key] not in ("", None):
            val = str(data[key])
            draw.text((box[0], box[1]), val,
                      font=FONT_MAIN,
                      fill=(20, 20, 20) if key not in {"service", "transfer", "meal", "guide", "excursions"} else GRAY)

    img.save(output_path, "PNG")
    return output_path


def draw_value(draw, text, box, font, align="left"):
    """Рисует текст в заданной области с выравниванием"""
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
    """Склонение слова 'ночь'"""
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
    """Загружает шрифт"""
    try:
        return ImageFont.truetype(TTF_PATH, sz)
    except:
        return ImageFont.load_default()


def load_font(size):
    """Загружает шрифт (альтернативная версия)"""
    try:
        return ImageFont.truetype(TTF_PATH, size)
    except Exception:
        return ImageFont.load_default()


def build_voucher_pdf(page1_png: str, city1: str | None, transfer_raw: str | None,
                      out_pdf_path: str) -> str:
    """Создает 2-страничный PDF ваучера"""
    page2_bg = pick_page2_bg(city1, transfer_raw)

    p1 = Image.open(page1_png).convert("RGB")
    p2 = Image.open(page2_bg).convert("RGB")

    p1.save(out_pdf_path, "PDF", save_all=True, append_images=[p2])
    return out_pdf_path


def generate_ticket(output_path, data):
    """Создает PNG билета"""
    img = Image.open(TICKET_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    GRAY = "#939393"

    # Загружаем шрифты
    try:
        font_main = ImageFont.truetype(TTF_PATH, 19)
        font_small = ImageFont.truetype(TTF_PATH, 16)
    except:
        font_main = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Вылет
    draw.text((228.5, 456.2), data["depart_date"], font=font_main, fill="black")
    draw.text((281.2, 531.9), data["depart_flight"], font=font_main, fill=GRAY)

    draw.text((160.4, 567.8), data["depart_time1"], font=font_main, fill="black")
    draw.text((161.9, 594.4), data["depart_date1"], font=font_small, fill=GRAY)

    draw.text((161.9, 631.6), data["depart_time2"], font=font_main, fill="black")
    draw.text((161.9, 658.5), data["depart_date2"], font=font_small, fill=GRAY)

    # Прилет
    draw.text((743.3, 453), data["return_date"], font=font_main, fill="black")
    draw.text((791.2, 531), data["return_flight"], font=font_main, fill=GRAY)

    draw.text((671.8, 571.8), data["return_time1"], font=font_main, fill="black")
    draw.text((671.8, 594.3), data["return_date1"], font=font_small, fill=GRAY)

    draw.text((671.8, 631.6), data["return_time2"], font=font_main, fill="black")
    draw.text((671.8, 658.5), data["return_date2"], font=font_small, fill=GRAY)

    img.save(output_path, "PNG")
    return output_path


def generate_pdf_from_png(png_path):
    """Конвертирует PNG в PDF"""
    pdf_path = os.path.splitext(png_path)[0] + ".pdf"
    img = Image.open(png_path).convert("RGB")
    img.save(pdf_path, "PDF", resolution=100.0)
    return pdf_path