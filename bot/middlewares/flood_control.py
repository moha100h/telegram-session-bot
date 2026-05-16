"""
Global flood control middleware.
Catches TelegramRetryAfter and waits automatically.
"""
import asyncio
import logging
from typing import Any, Callable, Awaitable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import TelegramObject

logger = logging.getLogger("flood_mw")


class FloodControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        for attempt in range(3):
            try:
                return await handler(event, data)
            except TelegramRetryAfter as e:
                wait = e.retry_after + 2
                logger.warning("FloodControl: retry after %ds (attempt %d)", wait, attempt + 1)
                await asyncio.sleep(wait)
        # last attempt
        return await handler(event, data)
