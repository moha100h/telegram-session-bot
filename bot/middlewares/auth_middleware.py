"""
Auth middleware - auto register users, check ban.
"""
import logging
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from db.database import AsyncSessionLocal
from services.user_service import get_or_create_user

logger = logging.getLogger("auth")


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if tg_user and not tg_user.is_bot:
            async with AsyncSessionLocal() as session:
                try:
                    user = await get_or_create_user(session, tg_user)
                    await session.commit()
                    data["db_user"] = user
                    if user.is_banned:
                        if isinstance(event, Message):
                            await event.answer("⛔️ \u062d\u0633\u0627\u0628 \u0634\u0645\u0627 \u0645\u0633\u062f\u0648\u062f \u0634\u062f\u0647 \u0627\u0633\u062a.")
                        elif isinstance(event, CallbackQuery):
                            await event.answer("⛔️ \u062d\u0633\u0627\u0628 \u0634\u0645\u0627 \u0645\u0633\u062f\u0648\u062f \u0634\u062f\u0647 \u0627\u0633\u062a.", show_alert=True)
                        return
                except Exception as e:
                    logger.error(f"AuthMiddleware error: {e}")

        return await handler(event, data)
