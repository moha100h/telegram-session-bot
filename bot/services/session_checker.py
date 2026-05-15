"""
SessionChecker — runs every 6h automatically.
Checks ALL sessions, auto-deletes truly invalid ones,
reports results to admin.
"""
import asyncio
import logging
import os

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from services import session_store
from services.session_validator import validate_session, INVALID_ERRORS

logger         = logging.getLogger("session_checker")
ADMIN_ID       = int(os.getenv("ADMIN_ID", "0"))
CHECK_INTERVAL = 6 * 3600   # every 6 hours
CONCURRENCY    = 8           # parallel checks


class SessionChecker:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def run(self):
        await asyncio.sleep(120)   # wait for bot to fully start
        while True:
            try:
                await self._run_once(auto=True)
            except Exception as e:
                logger.error("[checker] %s", e, exc_info=True)
            await asyncio.sleep(CHECK_INTERVAL)

    async def _run_once(self, auto: bool = True):
        keys   = session_store.list_session_files()
        total  = len(keys)
        if total == 0:
            logger.info("[checker] no sessions to check")
            return

        logger.info("[checker] checking %d sessions (auto=%s)", total, auto)

        valid   = []   # list of info dicts
        invalid = []   # list of (key, reason)
        sem     = asyncio.Semaphore(CONCURRENCY)
        lock    = asyncio.Lock()

        async def check_one(key: str):
            async with sem:
                result = await validate_session(key)
            async with lock:
                if result["ok"]:
                    valid.append(result["info"])
                else:
                    reason = result["reason"]
                    if reason in INVALID_ERRORS:
                        # Truly invalid — auto delete
                        session_store.remove_files(key)
                        invalid.append((key, reason))
                        logger.info("[checker] auto-deleted %s (%s)", key, reason)
                    else:
                        # Temporary error (FloodWait, network) — keep
                        valid.append({"phone": "+" + key, "username": "",
                                      "fullname": "", "user_id": "",
                                      "_temp_error": reason})
                        logger.info("[checker] kept %s (temp: %s)", key, reason)

        await asyncio.gather(*[check_one(k) for k in keys])

        # Rebuild sessions.json: only valid sessions
        clean = {}
        for info in valid:
            if "_temp_error" not in info:
                key = info.get("phone", "").lstrip("+")
                if key:
                    clean[key] = info
        await session_store.replace_all(clean)

        logger.info("[checker] done. valid=%d deleted=%d", len(clean), len(invalid))

        # Notify admin
        if auto and (invalid or len(clean) > 0):
            await self._notify(len(keys), clean, invalid)

    async def _notify(self, total: int, clean: dict, invalid: list):
        lines = [
            f"✅ <b>بررسی خودکار سشن‌ها</b>",
            f"📊 کل: <b>{total}</b> | "
            f"✅ سالم: <b>{len(clean)}</b> | "
            f"🗑 حذف شد: <b>{len(invalid)}</b>",
        ]
        if invalid:
            lines.append("")
            lines.append("🗑 <b>حذف شده:</b>")
            for key, reason in invalid[:20]:
                lines.append(f"  • <code>+{key}</code> — {reason}")
        try:
            await self.bot.send_message(
                ADMIN_ID, "\n".join(lines), parse_mode="HTML"
            )
        except Exception as e:
            logger.error("[checker] notify: %s", e)
