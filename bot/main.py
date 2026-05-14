import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from handlers import start, sessions, tasks, stats, backup, proxy, virtual_number
from services.backup import BackupService
from services.proxy_fetcher import ProxyFetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

BOT_TOKEN  = os.getenv("BOT_TOKEN", "")
REDIS_URL  = os.getenv("REDIS_URL", "redis://redis:6379/0")
ADMIN_ID   = int(os.getenv("ADMIN_ID", "0"))


async def main():
    logger.info(f"Starting bot | ADMIN_ID={ADMIN_ID}")

    redis = Redis.from_url(REDIS_URL)
    storage = RedisStorage(redis)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=storage)

    # Inject redis & bot into handlers
    dp["redis"] = redis
    dp["bot"]   = bot

    # Register routers
    dp.include_router(start.router)
    dp.include_router(sessions.router)
    dp.include_router(tasks.router)
    dp.include_router(stats.router)
    dp.include_router(backup.router)
    dp.include_router(proxy.router)
    dp.include_router(virtual_number.router)

    # Background services
    asyncio.create_task(BackupService(bot, redis).run())
    asyncio.create_task(ProxyFetcher(redis).run())

    logger.info("Bot started, polling...")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
