from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Any


class AdminMiddleware(BaseMiddleware):
    """Pass-through - admin check is done inline in each handler."""
    async def __call__(
        self,
        handler: Callable[[Any, dict], Awaitable[Any]],
        event: Any,
        data: dict
    ) -> Any:
        return await handler(event, data)
