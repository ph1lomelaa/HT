from pligrim_bot.core.utils.text_utils import *
from pligrim_bot.core.utils.validation import *


def scan_transfer_after_package(data: list[list[str]], pkg_row: int) -> dict:
    H = len(data)
    start = max(pkg_row + 1, 0)

    # найдём границу «следующего пакета»
    end = H - 1
    for r in range(start, H):
        txt = row_text(data[r]).lower()
        if not txt:
            continue
        if NEXT_PACKAGE_HINT.search(txt) and r > start + 1:
            end = r - 1
            break

    types_set = set()
    lines = []
    parsed = []

    for r in range(start, end + 1):
        txt = row_text(data[r])
        if not txt:
            continue

        found_type = None
        if BUS_RE.search(txt):
            types_set.add("автобус")
            found_type = "bus"
        if TRAIN_RE.search(txt):
            types_set.add("поезд")
            found_type = "train"  # если в строке и bus и train – последним останется "train" (редко, но ок)
        if TRANSFER_RE.search(txt):
            types_set.add("трансфер")
            # не перетираем found_type, это «общее» слово

        if found_type or TRANSFER_RE.search(txt):
            lines.append(txt)

            # разбираем детали (маршрут/время) если сможем
            route = None
            m_route = ROUTE_RE.search(txt)
            if m_route:
                route = f"{m_route.group(1).upper()}-{m_route.group(2).upper()}"
            time = None
            m_time = TIME_RE.search(txt)
            if m_time:
                time = m_time.group(0)

            parsed.append({
                "type": (found_type or "transfer"),
                "route": route,
                "time": time,
                "raw": txt
            })

    return {
        "types": sorted(types_set, key=lambda x: ["автобус","поезд","трансфер"].index(x) if x in ["автобус","поезд","трансфер"] else 99),
        "lines": lines,
        "parsed": parsed
    }

def collect_transport(data: list[list[str]], from_row: int, to_row: int) -> dict:
    """
    Сканирует строки [from_row; to_row) и собирает типы транспорта.
    В display выводим ТОЛЬКО «Поезд»/«Автобус» (слово «трансфер» игнорируем).
    """
    types, lines, details = set(), [], []
    H = len(data)
    a = max(0, from_row)
    b = min(H, to_row)

    for r in range(a, b):
        txt = " ".join((c or "").strip() for c in data[r] if c).strip()
        if not txt:
            continue

        found = False
        if TRAIN_RE.search(txt):
            types.add("поезд"); found = True
        if BUS_RE.search(txt):
            types.add("автобус"); found = True
        # TRANSFER_RE — только как маркер блока, в types не добавляем

        if found or TRANSFER_RE.search(txt):
            lines.append(txt)
            m_route = ROUTE_RE.search(txt)
            m_time  = TIME_RE.search(txt)
            details.append({
                "raw": txt,
                "route": f"{m_route.group(1).upper()}–{m_route.group(2).upper()}" if m_route else None,
                "time": m_time.group(0) if m_time else None,
                "has_train": bool(TRAIN_RE.search(txt)),
                "has_bus": bool(BUS_RE.search(txt)),
            })

    # В display выводим только поезд/автобус (без «трансфер»)
    order = [("поезд","Поезд"), ("автобус","Автобус")]
    present = [pretty for low, pretty in order if low in types]
    display = ", ".join(present) if present else "—"

    return {
        "types": [low for low, _ in order if low in types],
        "display": display,
        "lines": lines,
        "details": details
    }

def summarize_transfer(details: list[dict]) -> str:
    has_train = any(d.get("has_train") or TRAIN_RE.search(d.get("raw","") or "") for d in (details or []))
    has_bus   = any(d.get("has_bus")   or BUS_RE.search(d.get("raw","")   or "") for d in (details or []))

    if has_train and has_bus: return "Поезд, Автобус"
    if has_train:             return "Поезд"
    if has_bus:               return "Автобус"
    return "—"

def transfer_display(raw: str | None) -> str:
    s = (raw or "").lower()
    has_train = any(k in s for k in ("train", "поезд", "жд"))
    has_bus   = any(k in s for k in ("bus", "автобус"))
    has_word_transfer = "трансфер" in s or "transfer" in s

    # если явно поезда нет, но встречается слово «трансфер» — считаем автобусом
    if not has_train and not has_bus and has_word_transfer:
        has_bus = True

    parts = []
    if has_train: parts.append("Поезд")
    if has_bus:   parts.append("Автобус")
    return ", ".join(parts) if parts else "Автобус"

def need_train(raw: str | None) -> bool:
    return bool(TRAIN_RE.search(raw or ""))

def prettify_transfer_ru(s: str | None) -> str:
    t = (s or "").lower()
    has_train = any(w in t for w in ("train", "поезд", "жд"))
    has_bus   = any(w in t for w in ("bus", "автобус"))
    parts = []
    if has_train: parts.append("Поезд")
    if has_bus:   parts.append("Автобус")
    return ", ".join(parts) if parts else "—"
# -----------------------------------------------------------------------------

def has_train(transfer_details: list[dict]|None) -> bool:
    """
    true, если в деталях транспорта есть поезд.
    поддерживает два вида данных:
      - наш detail.has_train = True
      - или raw-строка, в которой встречается 'поезд/train/жд'
    """
    details = transfer_details or []
    for d in details:
        if d.get("has_train"):
            return True
        if TRAIN_RE.search((d.get("raw") or "")):
            return True
    return False

def choose_second_page(voucher: dict) -> str:
    c1 = voucher.get("city1")
    train = has_train(voucher.get("_transfer_details"))
    if is_madinah(c1) and train: return SECOND_ASSETS["JEDMED_TRAIN"]
    if is_madinah(c1):           return SECOND_ASSETS["UAEmed"]
    if is_makkah(c1):            return SECOND_ASSETS["UAEmec"]
    return SECOND_ASSETS["UAEmed"]
