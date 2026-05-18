"""
Group/Channel ID Handler
- فقط سوپرادمین می‌تواند بات را به گروه/کانال اضافه کند
- اگر کس دیگری اضافه کرد → بات فوری leave می‌کند + نوتیف به ادمین
- وقتی بات به گروه/کانال اضافه شد → ID رو به ادمین می‌فرستد
- دستور /getid در گروه → ID رو نشون می‌دهد
"""
import logging, os
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION

logger   = logging.getLogger("group_id")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def _fa(t: str) -> str:
    return {"گروه": "گروه", "group": "گروه", "supergroup": "سوپرگروه", "channel": "کانال"}.get(t, t)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added(event: ChatMemberUpdated, bot: Bot):
    chat = event.chat
    by   = event.from_user
    if by and by.id != ADMIN_ID:
        logger.warning(f"SECURITY: unauthorized add by {by.id} to {chat.id}. Leaving...")
        try:
            await bot.send_message(
                ADMIN_ID,
                f"⚠️ <b>تلاش غیرمجاز برای اضافه کردن بات</b>\n\n"
                f"👤 توسط: <b>{by.full_name}</b> (<code>{by.id}</code>)\n"
                f"📛 گروه: <b>{chat.title or 'بدون نام'}</b>\n"
                f"🆔 آیدی: <code>{chat.id}</code>\n\n"
                f"🚫 بات خودکار خارج شد.",
                parse_mode="HTML"
            )
        except Exception: pass
        try: await bot.leave_chat(chat.id)
        except Exception as e: logger.error(f"leave failed {chat.id}: {e}")
        return

    ctype = _fa(chat.type)
    title = chat.title or "بدون نام"
    uname = f"@{chat.username}" if chat.username else "بدون یوزرنیم"
    try:
        await bot.send_message(
            ADMIN_ID,
            f"✅ <b>بات به {ctype} اضافه شد</b>\n\n"
            f"📛 نام: <b>{title}</b>\n"
            f"🔗 یوزرنیم: <b>{uname}</b>\n"
            f"🆔 آیدی عددی:\n<code>{chat.id}</code>\n\n"
            f"💡 این آیدی رو در تنظیمات پنل یا بکاپ استفاده کن.",
            parse_mode="HTML"
        )
    except Exception as e: logger.error(f"notify admin failed: {e}")
    logger.info(f"Bot added to {chat.type} {chat.id} ({title})")


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=LEAVE_TRANSITION))
async def bot_removed(event: ChatMemberUpdated, bot: Bot):
    chat  = event.chat
    by    = event.from_user
    ctype = _fa(chat.type)
    try:
        await bot.send_message(
            ADMIN_ID,
            f"🔴 <b>بات از {ctype} خارج شد</b>\n\n"
            f"📛 نام: <b>{chat.title or 'بدون نام'}</b>\n"
            f"🆔 آیدی: <code>{chat.id}</code>\n"
            f"👤 توسط: <b>{by.full_name if by else 'نامشخص'}</b>",
            parse_mode="HTML"
        )
    except Exception: pass


@router.message(F.text == "/getid")
async def cmd_getid(msg: Message):
    chat    = msg.chat
    user_id = msg.from_user.id if msg.from_user else None
    if chat.type == "private":
        if user_id != ADMIN_ID: return
        await msg.answer(f"🆔 آیدی شما: <code>{user_id}</code>", parse_mode="HTML")
        return
    if user_id != ADMIN_ID: return
    ctype = _fa(chat.type)
    await msg.answer(
        f"🆔 <b>آیدی این {ctype}:</b>\n"
        f"<code>{chat.id}</code>\n\n"
        f"📛 نام: <b>{chat.title or 'بدون نام'}</b>",
        parse_mode="HTML"
    )
    logger.info(f"/getid in {chat.type} {chat.id} by {user_id}")
