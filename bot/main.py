import asyncio, logging, os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from db.database import init_db
from middlewares.auth_middleware import AuthMiddleware
from handlers.user_handler         import router as user_router
from handlers.admin_handler        import router as admin_router
from handlers.smmpass_handler      import router as smmpass_router
from handlers.force_join_handler   import router as force_join_router
from handlers.backup_handler       import router as backup_router
from handlers.panel_admin_handler  import router as panel_admin_router
from handlers.panel_user_handler   import router as panel_user_router
from handlers.group_id_handler     import router as group_id_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger    = logging.getLogger("main")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))

async def set_commands(bot: Bot):
    base = [BotCommand(command="start", description="\u0634\u0631\u0648\u0639"),
            BotCommand(command="cancel", description="\u0644\u063a\u0648")]
    await bot.set_my_commands(base, scope=BotCommandScopeDefault())
    if ADMIN_ID:
        try:
            await bot.set_my_commands(base + [BotCommand(command="admin", description="\u067e\u0646\u0644 \u0627\u062f\u0645\u06cc\u0646")],
                                      scope=BotCommandScopeChat(chat_id=ADMIN_ID))
        except Exception: pass

async def main():
    storage = RedisStorage.from_url(REDIS_URL)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher(storage=storage)
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(group_id_router)
    dp.include_router(force_join_router)
    dp.include_router(backup_router)
    dp.include_router(panel_admin_router)
    dp.include_router(panel_user_router)
    dp.include_router(user_router)
    dp.include_router(admin_router)
    dp.include_router(smmpass_router)
    await init_db()
    await set_commands(bot)

    # ── Backup scheduler ──────────────────────────────────────────────
    try:
        from services.backup_service import start_scheduler as _sb
        from db.database import AsyncSessionLocal as _ASL
        from services.settings_service import get_setting as _gs
        async with _ASL() as _s:
            _auto = await _gs(_s, "backup_auto_enabled", "1")
        if _auto == "1":
            _sb(bot); logger.info("Backup scheduler started.")
    except Exception as _e:
        logger.warning(f"Backup scheduler not started: {_e}")

    # ── Order polling (SmmPass auto status update) ────────────────────
    try:
        from services.order_polling_service import start_order_polling
        asyncio.create_task(start_order_polling(bot))
        logger.info("Order polling service started.")
    except Exception as _e:
        logger.warning(f"Order polling not started: {_e}")

    logger.info("Bot started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
