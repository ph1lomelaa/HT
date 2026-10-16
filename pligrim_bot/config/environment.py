"""Load local configuration without overwriting server environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.removeprefix('export ').split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


load_env()
