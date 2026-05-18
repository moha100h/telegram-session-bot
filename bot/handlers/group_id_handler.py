"""
Group/Channel ID Handler
- وقتی بات به گروه/کانال اضافه میشه → ID رو به ادمین میفرسته
- دستور /getid در گروه → ID رو نشون میده
"""
import logging, os
from aiogram import Router, F, Bot
from aiogram.types import Message, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION

logger   = logging.getLogger("group_id")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=JOIN_TRANSITION))
async def bot_added_to_chat(event: ChatMemberUpdated, bot: Bot):
    chat = event.chat
    chat_type = {"group": "گروه", "supergroup": "سوپرگروه", "channel": "کانال"}.get(chat.type, chat.type)
    title    = chat.title or "بدون نام"
    username = f"@{chat.username}" if chat.username else "بدون یوزرنیم"
    text = (
        f"🔔 <b>بات به {chat_type} اضافه شد</b>\n\n"
        f"📛 نام: <b>{title}</b>\n"
        f"🔗 یوزرنیم: <b>{username}</b>\n"
        f"🆔 آیدی عددی:\n<code>{chat.id}</code>\n\n"
        f"💡 این آیدی رو در تنظیمات پنل یا بکاپ استفاده کن."
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Cannot notify admin: {e}")
    logger.info(f"Bot added to {chat_type}: {title} ({chat.id})")


@router.message(F.text == "/getid")
async def cmd_getid(msg: Message):
    chat    = msg.chat
    user_id = msg.from_user.id if msg.from_user else None

    if chat.type == "private":
        if user_id != ADMIN_ID:
            return
        await msg.answer(f"🆔 آیدی شما: <code>{user_id}</code>", parse_mode="HTML")
        return

    chat_type = {"group": "گروه", "supergroup": "سوپرگروه", "channel": "کانال"}.get(chat.type, chat.type)
    await msg.answer(
        f"🆔 <b>آیدی این {chat_type}:</b>\n"
        f"<code>{chat.id}</code>\n\n"
        f"📛 نام: <b>{chat.title or 'بدون نام'}</b>",
        parse_mode="HTML"
    )
    logger.info(f"/getid in {chat.type} {chat.id} by {user_id}")
