"""
Auth middleware - auto register users, check ban, force-join.
"""
import os
import logging
from aiogram import BaseMiddleware
from aiogram.types import (
    TelegramObject, Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from db.database import AsyncSessionLocal
from services.user_service import get_or_create_user, get_admin
from i18n import t  # noqa: F401

logger = logging.getLogger("auth")
SUPERADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

FORCE_JOIN_BYPASS = {"fj_verify", "lang_select_screen"}


class AuthMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if not tg_user:
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            user, is_new = await get_or_create_user(session, tg_user)
            await session.commit()

            if user.is_banned:
                if isinstance(event, Message):
                    await event.answer("\u26d4\ufe0f \u062d\u0633\u0627\u0628 \u0634\u0645\u0627 \u0645\u0633\u062f\u0648\u062f \u0634\u062f\u0647 \u0627\u0633\u062a.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("\u26d4\ufe0f \u062d\u0633\u0627\u0628 \u0634\u0645\u0627 \u0645\u0633\u062f\u0648\u062f \u0634\u062f\u0647 \u0627\u0633\u062a.", show_alert=True)
                return

            admin = await get_admin(session, tg_user.id)
            is_superadmin = (tg_user.id == SUPERADMIN_ID)
            is_admin_user = is_superadmin or (admin is not None)

            data["db_user"]      = user
            data["user_lang"]    = getattr(user, "language", "en") or "en"
            data["db_session"]   = session
            data["is_new_user"]  = is_new
            data["admin_record"] = admin
            data["is_superadmin"]= is_superadmin
            data["is_admin"]     = is_admin_user

        # ── Force-join check ────────────────────────────────────────────────
        if not is_admin_user:
            bypass = isinstance(event, CallbackQuery) and (event.data in FORCE_JOIN_BYPASS or event.data.startswith("set_lang_"))
            if not bypass:
                from services.force_join_service import (
                    is_force_join_enabled, get_force_join_settings, check_membership
                )
                if await is_force_join_enabled():
                    fj = await get_force_join_settings()
                    channel = fj["channel"].strip()
                    if channel:
                        bot = getattr(event, "bot", None) or data.get("bot")
                        if bot:
                            is_member = await check_membership(bot, tg_user.id, channel)
                            if not is_member:
                                ch_link = (
                                    f"https://t.me/{channel.lstrip('@')}"
                                    if channel.startswith("@") else channel
                                )
                                kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text=fj["btn_join"],   url=ch_link)],
                                    [InlineKeyboardButton(text=fj["btn_verify"], callback_data="fj_verify")],
                                ])
                                if isinstance(event, Message):
                                    await event.answer(fj["text"], reply_markup=kb)
                                elif isinstance(event, CallbackQuery):
                                    await event.answer(
                                        "\u26a0\ufe0f \u0627\u0628\u062a\u062f\u0627 \u062f\u0631 \u06a9\u0627\u0646\u0627\u0644 \u0639\u0636\u0648 \u0634\u0648\u06cc\u062f!",
                                        show_alert=True
                                    )
                                    try:
                                        await event.message.edit_text(fj["text"], reply_markup=kb)
                                    except Exception:
                                        await event.message.answer(fj["text"], reply_markup=kb)
                                return

        return await handler(event, data)
