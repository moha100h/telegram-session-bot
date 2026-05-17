"""Force-join service — check channel membership."""
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from services.settings_service import get_setting
from db.database import AsyncSessionLocal


async def is_force_join_enabled() -> bool:
    async with AsyncSessionLocal() as session:
        val = await get_setting(session, "force_join_enabled", "0")
    return val == "1"


async def get_force_join_settings() -> dict:
    async with AsyncSessionLocal() as session:
        return {
            "enabled":    await get_setting(session, "force_join_enabled",    "0"),
            "channel":    await get_setting(session, "force_join_channel",    ""),
            "text":       await get_setting(session, "force_join_text",
                              "\u26a0\ufe0f \u0628\u0631\u0627\u06cc \u0627\u0633\u062a\u0641\u0627\u062f\u0647 \u0627\u0632 \u0631\u0628\u0627\u062a \u0627\u0628\u062a\u062f\u0627 \u062f\u0631 \u06a9\u0627\u0646\u0627\u0644 \u0645\u0627 \u0639\u0636\u0648 \u0634\u0648\u06cc\u062f."),
            "btn_join":   await get_setting(session, "force_join_btn_text",   "\U0001f4e2 \u0639\u0636\u0648\u06cc\u062a \u062f\u0631 \u06a9\u0627\u0646\u0627\u0644"),
            "btn_verify": await get_setting(session, "force_join_verify_text","\u2705 \u0639\u0636\u0648 \u0634\u062f\u0645\u060c \u062a\u0623\u06cc\u06cc\u062f \u06a9\u0646"),
        }


async def check_membership(bot: Bot, user_id: int, channel: str) -> bool:
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status not in ("left", "kicked", "banned")
    except (TelegramForbiddenError, TelegramBadRequest):
        return True
    except Exception:
        return True
