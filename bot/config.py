import os

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")

# پشتیبانی از هر دو ADMIN_IDS (جمع) و ADMIN_ID (مفرد)
_raw_ids    = os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", ""))
ADMIN_IDS   = [int(x.strip()) for x in _raw_ids.split(",") if x.strip().isdigit()]

API_ID      = int(os.getenv("API_ID",   "0") or "0")
API_HASH    = os.getenv("API_HASH",  "")
REDIS_URL   = os.getenv("REDIS_URL", "redis://redis:6379")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR",     "/app/data")
BACKUPS_DIR  = os.getenv("BACKUP_DIR",   "/app/data/backups")

for d in [SESSIONS_DIR, DATA_DIR, BACKUPS_DIR]:
    os.makedirs(d, exist_ok=True)
