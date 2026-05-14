import asyncio, logging, os, zipfile, io
from datetime import datetime
from aiogram import Bot
from aiogram.types import BufferedInputFile
from redis.asyncio import Redis
from config import ADMIN_IDS, SESSIONS_DIR, DATA_DIR, BACKUPS_DIR

logger = logging.getLogger("backup")
BACKUP_INTERVAL = 3600

class BackupService:
    def __init__(self, bot: Bot, redis: Redis):
        self.bot = bot
        self.redis = redis

    async def create_backup(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fname in os.listdir(SESSIONS_DIR):
                zf.write(os.path.join(SESSIONS_DIR, fname), f"sessions/{fname}")
            for fname in os.listdir(DATA_DIR):
                fp = os.path.join(DATA_DIR, fname)
                if os.path.isfile(fp):
                    zf.write(fp, f"data/{fname}")
        buf.seek(0)
        return buf.read()

    async def send_backup(self):
        try:
            data = await self.create_backup()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"backup_{ts}.zip"
            os.makedirs(BACKUPS_DIR, exist_ok=True)
            with open(os.path.join(BACKUPS_DIR, fname), "wb") as f:
                f.write(data)
            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_document(
                        admin_id,
                        BufferedInputFile(data, filename=fname),
                        caption=f"🗄 بکاپ خودکار\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n📦 {len(data)//1024} KB",
                    )
                except Exception as e:
                    logger.error(f"Send backup to {admin_id}: {e}")
        except Exception as e:
            logger.error(f"Backup error: {e}")

    async def run(self):
        while True:
            await asyncio.sleep(BACKUP_INTERVAL)
            await self.send_backup()
