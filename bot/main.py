"""
Main bot entry point - SMM Panel + Session Manager.
Replaces old main.py with new unified entry point.
"""
import asyncio
import logging
import os
import sys

# Fix encoding for Docker
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, Message, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))


async def set_commands(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start",   description="🚀 منو اصلی"),
        BotCommand(command="admin",   description="🔑 پنل ادمین"),
        BotCommand(command="balance", description="💰 موجودی حساب"),
        BotCommand(command="orders",  description="📦 سفارش‌های من"),
    ])


async def main():
    logger.info(f"Starting SMM Panel Bot | ADMIN_ID={ADMIN_ID}")

    # Init DB
    from db.database import init_db
    await init_db()
    logger.info("Database initialized.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    storage = RedisStorage.from_url(REDIS_URL)
    dp = Dispatcher(storage=storage)

    # ─── Middlewares ───────────────────────────────────────────────────────────────────────────────
    from middlewares.auth_middleware import AuthMiddleware
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # ─── New SMM Panel Routers ────────────────────────────────────────────────────────────────────
    from handlers.user_handler     import router as user_router
    from handlers.admin_handler    import router as admin_router
    from handlers.smmpass_handler  import router as smmpass_router

    dp.include_router(user_router)
    dp.include_router(admin_router)
    dp.include_router(smmpass_router)

    # ─── Old Session Manager Routers ────────────────────────────────────────────────────────────────
    try:
        from handlers import (
            session_handler, join_handler, group_handler,
            view_handler, reaction_handler, proxy_handler,
            report_handler, task_manager
        )
        dp.include_router(session_handler.router)
        dp.include_router(join_handler.router)
        dp.include_router(group_handler.router)
        dp.include_router(view_handler.router)
        dp.include_router(reaction_handler.router)
        dp.include_router(proxy_handler.router)
        dp.include_router(report_handler.router)
        dp.include_router(task_manager.router)
        logger.info("Session manager handlers loaded.")
    except Exception as e:
        logger.warning(f"Session manager handlers not loaded: {e}")

    # ─── Shortcuts ───────────────────────────────────────────────────────────────────────────────
    @dp.message(F.text == "/admin")
    async def cmd_admin(msg: Message):
        from db.database import AsyncSessionLocal
        from services.user_service import get_admin
        is_super = (msg.from_user.id == ADMIN_ID)
        if not is_super:
            async with AsyncSessionLocal() as session:
                admin = await get_admin(session, msg.from_user.id)
                if not admin:
                    await msg.answer("⛔️ دسترسی ندارید.")
                    return
        await msg.answer(
            "🔑 <b>پنل مدیریت</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔑 ورود به پنل", callback_data="menu_admin")]
            ])
        )

    @dp.message(F.text == "/balance")
    async def cmd_balance(msg: Message):
        from db.database import AsyncSessionLocal
        from services.user_service import get_user
        async with AsyncSessionLocal() as session:
            user = await get_user(session, msg.from_user.id)
            bal  = float(user.balance or 0) if user else 0
        await msg.answer(f"💰 موجودی: <b>${bal:.2f}</b>")

    @dp.message(F.text == "/orders")
    async def cmd_orders(msg: Message):
        await msg.answer(
            "📦 سفارش‌های شما:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 مشاهده", callback_data="user_orders")]
            ])
        )

    await set_commands(bot)
    logger.info("Bot polling started.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
