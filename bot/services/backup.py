import asyncio
import logging
import os
import zipfile
import tempfile
from datetime import datetime
from aiogram import Bot
from redis.asyncio import Redis

logger = logging.getLogger("backup")

ADMIN_ID     = int(os.getenv("ADMIN_ID", "0"))
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR", "/app/data")
BACKUP_INTERVAL = 3600  # 1 hour


class BackupService:
    def __init__(self, bot: Bot, redis: Redis):
        self.bot   = bot
        self.redis = redis

    async def do_backup(self):
        try:
            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp = tempfile.mktemp(suffix=f"_backup_{ts}.zip")
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                # Sessions
                if os.path.exists(SESSIONS_DIR):
                    for f in os.listdir(SESSIONS_DIR):
                        zf.write(os.path.join(SESSIONS_DIR, f), f"sessions/{f}")
                # Data
                if os.path.exists(DATA_DIR):
                    for f in os.listdir(DATA_DIR):
                        if f.endswith(".json"):
                            zf.write(os.path.join(DATA_DIR, f), f"data/{f}")
            from aiogram.types import FSInputFile
            doc = FSInputFile(tmp, filename=f"backup_{ts}.zip")
            await self.bot.send_document(
                ADMIN_ID, doc,
                caption=f"💾 بکاپ خودکار | {ts}"
            )
            os.remove(tmp)
            logger.info(f"Backup sent: {ts}")
        except Exception as e:
            logger.error(f"Backup error: {e}")

    async def run(self):
        while True:
            await asyncio.sleep(BACKUP_INTERVAL)
            await self.do_backup()
