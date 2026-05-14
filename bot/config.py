import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "277236314").split(",") if x.strip()]
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
BACKUPS_DIR = os.getenv("BACKUPS_DIR", "/app/backups")

for d in [SESSIONS_DIR, DATA_DIR, BACKUPS_DIR]:
    os.makedirs(d, exist_ok=True)
