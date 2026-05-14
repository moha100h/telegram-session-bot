import os
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Awaitable, Any

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


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
        if user and user.id != ADMIN_ID:
            if isinstance(event, Message):
                await event.answer("⛔️ دسترسی ندارید")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔️ دسترسی ندارید", show_alert=True)
            return
        return await handler(event, data)
