"""
Main bot entry point - registers all handlers and middlewares.
"""
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from db.database import init_db
from middlewares.auth_middleware import AuthMiddleware
from handlers import (
    session_handler, join_handler, group_handler,
    view_handler, reaction_handler, proxy_handler,
    report_handler, task_manager
)
from handlers.user_handler     import router as user_router
from handlers.admin_handler    import router as admin_router
from handlers.user_smm_handler import router as user_smm_router
from handlers.smmpass_handler  import router as smmpass_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))


async def set_commands(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start",  description="🚀 \u0634\u0631\u0648\u0639 / \u0645\u0646\u0648 \u0627\u0635\u0644\u06cc"),
        BotCommand(command="admin",  description="🔑 \u067e\u0646\u0644 \u0627\u062f\u0645\u06cc\u0646"),
        BotCommand(command="balance",description="💰 \u0645\u0648\u062c\u0648\u062f\u06cc \u062d\u0633\u0627\u0628"),
        BotCommand(command="orders", description="📦 \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627\u06cc \u0645\u0646"),
    ])


async def main():
    logger.info(f"Starting bot | ADMIN_ID={ADMIN_ID}")

    # Init DB
    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = RedisStorage.from_url(REDIS_URL)
    dp = Dispatcher(storage=storage)

    # Middlewares
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Routers - order matters!
    dp.include_router(user_router)       # /start, user panel
    dp.include_router(admin_router)      # admin panel
    dp.include_router(user_smm_router)   # user SMM browsing
    dp.include_router(smmpass_router)    # admin SMM panel
    dp.include_router(session_handler.router)
    dp.include_router(join_handler.router)
    dp.include_router(group_handler.router)
    dp.include_router(view_handler.router)
    dp.include_router(reaction_handler.router)
    dp.include_router(proxy_handler.router)
    dp.include_router(report_handler.router)
    dp.include_router(task_manager.router)

    await set_commands(bot)

    # /admin shortcut
    @dp.message(lambda m: m.text == "/admin")
    async def admin_shortcut(msg):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        if msg.from_user.id != ADMIN_ID:
            async with __import__("db.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as session:
                from services.user_service import get_admin
                admin = await get_admin(session, msg.from_user.id)
                if not admin:
                    await msg.answer("⛔️ \u062f\u0633\u062a\u0631\u0633\u06cc \u0646\u062f\u0627\u0631\u06cc\u062f.")
                    return
        await msg.answer(
            "🔑 <b>\u067e\u0646\u0644 \u0645\u062f\u06cc\u0631\u06cc\u062a</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔑 \u0648\u0631\u0648\u062f \u0628\u0647 \u067e\u0646\u0644", callback_data="menu_admin")]
            ])
        )

    # /balance shortcut
    @dp.message(lambda m: m.text == "/balance")
    async def balance_shortcut(msg):
        from db.database import AsyncSessionLocal
        from services.user_service import get_user
        async with AsyncSessionLocal() as session:
            user = await get_user(session, msg.from_user.id)
            bal  = float(user.balance) if user else 0
        await msg.answer(f"💰 \u0645\u0648\u062c\u0648\u062f\u06cc: <b>${bal:.4f}</b>")

    # /orders shortcut
    @dp.message(lambda m: m.text == "/orders")
    async def orders_shortcut(msg):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        await msg.answer(
            "📦 \u0633\u0641\u0627\u0631\u0634\u200c\u0647\u0627\u06cc \u0634\u0645\u0627:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 \u0645\u0634\u0627\u0647\u062f\u0647", callback_data="u_my_orders")]
            ])
        )

    logger.info("Bot started, polling.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
