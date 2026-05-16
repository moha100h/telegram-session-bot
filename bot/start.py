"""
Main bot entry point — registers all handlers and middlewares.
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton

from db.database import init_db
from middlewares.auth_middleware import AuthMiddleware
from handlers import (
    session_handler, join_handler, group_handler,
    view_handler, reaction_handler, proxy_handler,
    report_handler, task_manager,
)
from handlers.user_handler    import router as user_router
from handlers.admin_handler   import router as admin_router
from handlers.smmpass_handler import router as smmpass_router

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
        BotCommand(command="start",   description="\U0001f680 شروع / منو اصلی"),
        BotCommand(command="admin",   description="\U0001f511 پنل ادمین"),
        BotCommand(command="balance", description="\U0001f4b0 موجودی حساب"),
        BotCommand(command="orders",  description="\U0001f4e6 سفارش‌های من"),
    ])


async def main():
    logger.info(f"Starting bot | ADMIN_ID={ADMIN_ID}")

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

    # Routers — order matters!
    dp.include_router(user_router)        # /start, user panel, deposit, orders
    dp.include_router(admin_router)       # admin panel
    dp.include_router(smmpass_router)     # SMM ordering flow
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
        from db.database import AsyncSessionLocal
        from services.user_service import is_admin as _is_admin
        async with AsyncSessionLocal() as session:
            ok = await _is_admin(session, msg.from_user.id)
        if msg.from_user.id != ADMIN_ID and not ok:
            await msg.answer("⛔️ دسترسی ندارید.")
            return
        await msg.answer(
            "🔧 <b>پنل مدیریت</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔧 ورود به پنل", callback_data="menu_admin")]
            ])
        )

    # /balance shortcut
    @dp.message(lambda m: m.text == "/balance")
    async def balance_shortcut(msg):
        from db.database import AsyncSessionLocal
        from services.user_service import get_user
        async with AsyncSessionLocal() as session:
            u = await get_user(session, msg.from_user.id)
        bal = float(u.balance or 0) if u else 0
        await msg.answer(f"💰 موجودی: <b>${bal:.2f}</b>")

    # /orders shortcut
    @dp.message(lambda m: m.text == "/orders")
    async def orders_shortcut(msg):
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        await msg.answer(
            "📦 سفارش‌های شما:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 سفارش‌های من", callback_data="user_orders")]
            ])
        )

    logger.info("Bot started, polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
