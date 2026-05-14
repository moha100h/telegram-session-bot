import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from handlers import start, sessions, tasks, stats, backup, proxy, virtual_number
from services.backup import BackupService
from services.proxy_fetcher import ProxyFetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

async def main():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    storage = RedisStorage(redis=redis)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)

    dp.include_router(start.router)
    dp.include_router(sessions.router)
    dp.include_router(tasks.router)
    dp.include_router(stats.router)
    dp.include_router(backup.router)
    dp.include_router(proxy.router)
    dp.include_router(virtual_number.router)

    backup_svc = BackupService(bot, redis)
    proxy_svc = ProxyFetcher(redis)
    asyncio.create_task(backup_svc.run())
    asyncio.create_task(proxy_svc.run())

    logger.info("Bot started successfully")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
