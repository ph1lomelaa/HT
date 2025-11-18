
from typing import Dict

PREVIEW_CACHE: Dict[str, dict] = {}  # cache_id -> {"voucher":..., "pkg_title":..., "page2_png":...}
EDIT_STATE: Dict[int, dict] = {}     # user_id -> {"cache_id":..., "field":...}
