from pligrim_bot.core.utils.text_utils import norm_title

def is_madinah(s: str|None) -> bool:
    s = (s or "").lower()
    return any(x in s for x in ("madinah","medina","madina","медин"))

def is_makkah(s: str|None) -> bool:
    s = (s or "").lower()
    return any(x in s for x in ("makkah","mecca","mekka","макк"))

def city_key(s: str | None) -> str:
    s = (s or "").lower()
    if any(x in s for x in ("madinah","medina","madina","медин","медина")): return "madinah"
    if any(x in s for x in ("makkah","mecca","mekka","макк","мекка")):      return "makkah"
    return "other"

def city_ru(name: str | None) -> str:
    s = (name or "").strip().lower()
    if any(x in s for x in ("madinah","medina","madina","медин")):
        return "Медина"
    if any(x in s for x in ("makkah","mecca","mekka","макк")):
        return "Мекка"
    return (name or "").strip()

def canon_family(s: str | None) -> str | None:
    t = norm_title(s or "")
    # 4 YOU / 4U / IZI
    if any(k in t for k in ("4you", "4u", "izi")): return "4u"
    if "niyet" in t:  return "niyet"
    if "hikma" in t:  return "hikma"
    if "amal"  in t:  return "amal"
    return None

_FAMILY_EQUIV = {
    frozenset(("4u", "amal")),  # IZI/4U == AMAL
}

def same_family(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    pair = frozenset((a, b))
    return pair in _FAMILY_EQUIV
