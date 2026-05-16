"""
Main bot entry point — SMM Panel + Session Manager.
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    BotCommand, BotCommandScopeDefault,
    BotCommandScopeChat, InlineKeyboardMarkup, InlineKeyboardButton,
)

from db.database import init_db
from middlewares.auth_middleware import AuthMiddleware
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

# دستورات پنل کاربری
USER_COMMANDS = [
    BotCommand(command="start",   description="\U0001f680 منو اصلی"),
    BotCommand(command="balance", description="\U0001f4b0 موجودی حساب"),
    BotCommand(command="orders",  description="\U0001f4e6 سفارش‌های من"),
    BotCommand(command="deposit", description="\U0001f4b3 واریز موجودی"),
    BotCommand(command="support", description="\U0001f4de پشتیبانی"),
]

# دستورات پنل ادمین (اضافه بر دستورات کاربری)
ADMIN_COMMANDS = [
    BotCommand(command="start",   description="\U0001f680 منو اصلی"),
    BotCommand(command="admin",   description="\U0001f527 پنل مدیریت"),
    BotCommand(command="balance", description="\U0001f4b0 موجودی حساب"),
    BotCommand(command="orders",  description="\U0001f4e6 سفارش‌های من"),
    BotCommand(command="deposit", description="\U0001f4b3 واریز موجودی"),
    BotCommand(command="users",   description="\U0001f465 مدیریت کاربران"),
    BotCommand(command="stats",   description="\U0001f4ca آمار سیستم"),
]


async def set_commands(bot: Bot):
    # دستورات پیش‌فرض برای همه کاربران
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    # دستورات اختصاصی ادمین
    try:
        await bot.set_my_commands(
            ADMIN_COMMANDS,
            scope=BotCommandScopeChat(chat_id=ADMIN_ID)
        )
    except Exception as e:
        logger.warning(f"Could not set admin commands: {e}")


async def main():
    logger.info(f"Starting SMM Panel Bot | ADMIN_ID={ADMIN_ID}")

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

    # Session manager routers (optional — wrapped in try/except)
    try:
        from handlers import (
            session_handler, join_handler, group_handler,
            view_handler, reaction_handler, proxy_handler,
            report_handler, task_manager,
        )
        dp.include_router(session_handler.router)
        dp.include_router(join_handler.router)
        dp.include_router(group_handler.router)
        dp.include_router(view_handler.router)
        dp.include_router(reaction_handler.router)
        dp.include_router(proxy_handler.router)
        dp.include_router(report_handler.router)
        dp.include_router(task_manager.router)
        logger.info("Session manager routers loaded.")
    except ImportError as e:
        logger.warning(f"Session manager routers not loaded: {e}")

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
        await msg.answer(
            f"💰 موجودی: <b>${bal:.2f}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 واریز", callback_data="user_deposit"),
                 InlineKeyboardButton(text="📋 تراکنش‌ها", callback_data="user_transactions")]
            ])
        )

    # /deposit shortcut
    @dp.message(lambda m: m.text == "/deposit")
    async def deposit_shortcut(msg):
        await msg.answer(
            "💳 <b>واریز موجودی</b>\n\nروش پرداخت را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🟢 USDT", callback_data="dep_usdt")],
                [InlineKeyboardButton(text="💎 TON",  callback_data="dep_ton")],
                [InlineKeyboardButton(text="⚡ TRX",  callback_data="dep_trx")],
            ])
        )

    # /orders shortcut
    @dp.message(lambda m: m.text == "/orders")
    async def orders_shortcut(msg):
        await msg.answer(
            "📦 سفارش‌های شما:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 سفارش‌های من", callback_data="user_orders"),
                 InlineKeyboardButton(text="🛒 سفارش جدید",   callback_data="menu_smmpass")]
            ])
        )

    # /support shortcut
    @dp.message(lambda m: m.text == "/support")
    async def support_shortcut(msg):
        await msg.answer(
            "📞 پشتیبانی:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📞 پشتیبانی", callback_data="user_support")]
            ])
        )

    # /stats shortcut (admin only)
    @dp.message(lambda m: m.text == "/stats")
    async def stats_shortcut(msg):
        from db.database import AsyncSessionLocal
        from services.user_service import is_admin as _is_admin
        async with AsyncSessionLocal() as session:
            ok = await _is_admin(session, msg.from_user.id)
        if msg.from_user.id != ADMIN_ID and not ok:
            await msg.answer("⛔️ دسترسی ندارید.")
            return
        await msg.answer(
            "📊 آمار:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 مشاهده آمار", callback_data="adm_stats")]
            ])
        )

    # /users shortcut (admin only)
    @dp.message(lambda m: m.text == "/users")
    async def users_shortcut(msg):
        from db.database import AsyncSessionLocal
        from services.user_service import is_admin as _is_admin
        async with AsyncSessionLocal() as session:
            ok = await _is_admin(session, msg.from_user.id)
        if msg.from_user.id != ADMIN_ID and not ok:
            await msg.answer("⛔️ دسترسی ندارید.")
            return
        await msg.answer(
            "👥 مدیریت کاربران:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 کاربران", callback_data="adm_users")]
            ])
        )

    logger.info("Bot started, polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
