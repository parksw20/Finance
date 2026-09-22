import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
INBOX_DIR = DATA_DIR / "inbox"
STATIC_DIR = ROOT / "static"


def _load_dotenv():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

DB_PATH = Path(os.environ.get("FINANCE_DB", str(DATA_DIR / "finance.db")))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
DART_API_KEY = os.environ.get("DART_API_KEY", "").strip()
REFRESH_SCHEDULE = os.environ.get("REFRESH_SCHEDULE", "0 6 * * *").strip()
REFRESH_ON_START = os.environ.get("REFRESH_ON_START", "false").lower() in ("1", "true", "yes")
