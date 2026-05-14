from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from middlewares.admin import AdminMiddleware
from services.proxy_fetcher import ProxyFetcher
from redis.asyncio import Redis

router = Router()
router.callback_query.middleware(AdminMiddleware())


@router.callback_query(F.data == "menu_proxy")
async def proxy_menu(cb: CallbackQuery, redis: Redis):
    count = await redis.llen("tsb:proxies")
    await cb.message.edit_text(
        f"🌐 <b>مدیریت پروکسی</b>\n\n"
        f"• پروکسی فعال: <b>{count}</b> عدد\n"
        f"• به‌روزرسانی خودکار هر ۱ ساعت",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 به‌روزرسانی الان", callback_data="proxy_refresh")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ])
    )


@router.callback_query(F.data == "proxy_refresh")
async def proxy_refresh(cb: CallbackQuery, redis: Redis):
    await cb.message.edit_text("⏳ در حال دریافت پروکسی...")
    svc = ProxyFetcher(redis)
    await svc.fetch()
    count = await redis.llen("tsb:proxies")
    await cb.message.edit_text(
        f"✅ پروکسی به‌روز شد | تعداد: <b>{count}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_proxy")],
        ])
    )
