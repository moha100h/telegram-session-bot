from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from config import ADMIN_IDS

class AdminMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and user.id not in ADMIN_IDS:
            if isinstance(event, Message):
                await event.answer("⛔ دسترسی ندارید.")
            return
        return await handler(event, data)
