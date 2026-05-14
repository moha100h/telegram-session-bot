import os
import logging
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Awaitable, Any

logger = logging.getLogger("admin_middleware")

_raw = os.getenv("ADMIN_ID", "0").strip()
try:
    ADMIN_ID = int(_raw)
except ValueError:
    ADMIN_ID = 0
    logger.error(f"[AdminMiddleware] ADMIN_ID invalid: '{_raw}'")

logger.info(f"[AdminMiddleware] ADMIN_ID loaded as: {ADMIN_ID} (type={type(ADMIN_ID)})")


class AdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict], Awaitable[Any]],
        event: Any,
        data: dict
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is not None:
            uid = int(user.id)
            logger.debug(f"[AdminMiddleware] user.id={uid} ADMIN_ID={ADMIN_ID} match={uid == ADMIN_ID}")
            if uid != ADMIN_ID:
                if isinstance(event, Message):
                    await event.answer("⛔️ دسترسی ندارید")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔️ دسترسی ندارید", show_alert=True)
                return

        return await handler(event, data)
