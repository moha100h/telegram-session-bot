"""
Auth middleware - auto register users, check ban status.
"""
import os
import logging
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from db.database import AsyncSessionLocal
from services.user_service import get_or_create_user, get_admin

logger = logging.getLogger("auth")
SUPERADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


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
                    await event.answer("⛔️ حساب شما مسدود شده است.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔️ حساب شما مسدود شده است.", show_alert=True)
                return

            # Check if admin
            admin = await get_admin(session, tg_user.id)
            is_superadmin = (tg_user.id == SUPERADMIN_ID)

            data["db_user"]      = user
            data["db_session"]   = session
            data["is_new_user"]  = is_new
            data["admin_record"] = admin
            data["is_superadmin"]= is_superadmin
            data["is_admin"]     = is_superadmin or (admin is not None)

            return await handler(event, data)
