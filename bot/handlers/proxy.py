from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from middlewares.admin import AdminMiddleware
from services.proxy_fetcher import ProxyFetcher
from redis.asyncio import Redis

router = Router()
router.callback_query.middleware(AdminMiddleware())


@router.callback_query(F.data == "menu_proxy")
async def proxy_menu(cb: CallbackQuery, redis: Redis):
    pf = ProxyFetcher(redis)
    count = await pf.count()
    sample = await pf.get_random()
    if sample:
        sample_text = f"🔹 نمونه: <code>{sample['host']}:{sample['port']}</code> ({sample.get('type','socks5')})"
    else:
        sample_text = "⚠️ هیچ پروکسی موجود نیست"
    await cb.message.edit_text(
        f"🌐 <b>مدیریت پروکسی</b>\n\n"
        f"📊 تعداد پروکسی: <b>{count}</b>\n"
        f"{sample_text}\n\n"
        f"🔄 به‌روزرسانی خودکار هر ۱ ساعت",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 به‌روزرسانی الان", callback_data="proxy_refresh")],
            [InlineKeyboardButton(text="📋 نمایش لیست", callback_data="proxy_list")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_main")],
        ]))


@router.callback_query(F.data == "proxy_refresh")
async def proxy_refresh(cb: CallbackQuery, redis: Redis):
    msg = await cb.message.edit_text("🔄 در حال دریافت پروکسی از اینترنت...\nحدود ۳۰ ثانیه صبر کنید")
    pf = ProxyFetcher(redis)
    await pf.refresh()
    count = await pf.count()
    await msg.edit_text(
        f"✅ لیست پروکسی به‌روز شد\n📊 تعداد: <b>{count}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_proxy")],
        ]))


@router.callback_query(F.data == "proxy_list")
async def proxy_list(cb: CallbackQuery, redis: Redis):
    pf = ProxyFetcher(redis)
    proxies = await pf.get_all()
    if not proxies:
        await cb.message.edit_text("📭 هیچ پروکسی وجود ندارد\nابتدا به‌روزرسانی کنید",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 به‌روزرسانی", callback_data="proxy_refresh")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_proxy")],
            ]))
        return
    text = f"🌐 <b>لیست پروکسی ({len(proxies)} عدد)</b>\n\n"
    for p in proxies[:20]:
        text += f"🔹 <code>{p['host']}:{p['port']}</code>\n"
    if len(proxies) > 20:
        text += f"\n... و {len(proxies)-20} مورد دیگر"
    await cb.message.edit_text(text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_proxy")],
        ]))
