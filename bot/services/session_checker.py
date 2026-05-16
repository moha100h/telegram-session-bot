"""
Session checker service.
Checks Telethon sessions every 6 hours.
Sends ONE summary message (not per-session) to avoid flood.
"""
import asyncio
import logging
import os

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

logger   = logging.getLogger("session_checker")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHECK_INTERVAL = 6 * 3600  # 6 hours


class SessionChecker:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def run(self):
        await asyncio.sleep(60)  # wait 1 min after startup
        while True:
            try:
                await self._check_all()
            except Exception as e:
                logger.error("session_checker error: %s", e)
            await asyncio.sleep(CHECK_INTERVAL)

    async def _check_all(self):
        from services.task_manager import get_all_tasks
        from telethon import TelegramClient
        from telethon.errors import AuthKeyUnregisteredError, UserDeactivatedBanError

        sessions_dir = os.getenv("SESSIONS_DIR", "/app/sessions")
        if not os.path.exists(sessions_dir):
            return

        session_files = [
            f[:-8] for f in os.listdir(sessions_dir)
            if f.endswith(".session")
        ]
        if not session_files:
            return

        total   = len(session_files)
        healthy = 0
        removed = []

        for name in session_files:
            path = os.path.join(sessions_dir, name)
            try:
                cl = TelegramClient(
                    path,
                    int(os.getenv("API_ID", "0")),
                    os.getenv("API_HASH", ""),
                )
                await cl.connect()
                if await cl.is_user_authorized():
                    healthy += 1
                else:
                    removed.append((name, "unauthorized"))
                    os.remove(path + ".session")
                await cl.disconnect()
            except (AuthKeyUnregisteredError, UserDeactivatedBanError) as e:
                removed.append((name, str(e)[:30]))
                try: os.remove(path + ".session")
                except Exception: pass
            except Exception as e:
                logger.warning("check %s: %s", name, e)
                healthy += 1  # assume ok on network error

        # Send ONE summary message
        if removed or total > 0:
            lines = [
                f"✅ بررسی خودکار سشن‌ها",
                f"📊 کل: {total} | سالم: {healthy} ✅ | حذف شد: {len(removed)} 🗑",
            ]
            if removed:
                lines.append("حذف شده:")
                for name, reason in removed[:10]:  # max 10 lines
                    lines.append(f"  • {name} — {reason}")

            try:
                await self.bot.send_message(ADMIN_ID, "\n".join(lines))
            except TelegramRetryAfter as e:
                logger.warning("flood: retry after %ds", e.retry_after)
                await asyncio.sleep(e.retry_after + 5)
                try:
                    await self.bot.send_message(ADMIN_ID, "\n".join(lines))
                except Exception:
                    pass
            except Exception as e:
                logger.error("send summary: %s", e)
