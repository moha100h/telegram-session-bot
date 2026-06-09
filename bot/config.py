import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Check your .env file.")

# ADMIN_ID (single) و ADMIN_IDS (comma-separated) هر دو پشتیبانی میشن
_admin_id  = os.getenv("ADMIN_ID", "")
_admin_ids = os.getenv("ADMIN_IDS", "")
_raw = _admin_ids if _admin_ids else _admin_id
ADMIN_IDS: list[int] = [int(x.strip()) for x in _raw.split(",") if x.strip().isdigit()]
ADMIN_ID:  int       = ADMIN_IDS[0] if ADMIN_IDS else 0

API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

REDIS_URL    = os.getenv("REDIS_URL", "redis://redis:6379/0")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR", "/app/data")
BACKUPS_DIR  = os.getenv("BACKUPS_DIR", "/app/data/backups")

for d in [SESSIONS_DIR, DATA_DIR, BACKUPS_DIR]:
    os.makedirs(d, exist_ok=True)
