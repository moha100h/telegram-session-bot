"""
Core session validation logic.
Used by both SessionChecker (auto) and cleanup handler (manual).
"""
import asyncio
import logging
import os

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    AuthKeyDuplicatedError,
    UserDeactivatedBanError,
    UserDeactivatedError,
    SessionRevokedError,
    SessionExpiredError,
    UnauthorizedError,
    FloodWaitError,
    PhoneNumberBannedError,
)

logger   = logging.getLogger("session_validator")
API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# These errors = session is permanently dead — safe to auto-delete
INVALID_ERRORS = {
    "unauthorized",
    "auth_key_unregistered",
    "auth_key_duplicated",
    "user_deactivated_ban",
    "user_deactivated",
    "session_revoked",
    "session_expired",
    "phone_number_banned",
    "session_file_missing",
}

# These errors = temporary, don't delete
TEMP_ERRORS = {
    "flood_wait",
    "network_error",
    "timeout",
    "connection_error",
}


async def validate_session(key: str) -> dict:
    """
    Fully validate a session.
    Returns:
      {"ok": True,  "info": {...}}           — valid
      {"ok": False, "reason": str}           — invalid
    reason is one of INVALID_ERRORS or TEMP_ERRORS.
    """
    from services import session_store

    session_path = os.path.join(session_store.SESSIONS_DIR, key)

    # Check file exists
    if not os.path.exists(session_path + ".session"):
        return {"ok": False, "reason": "session_file_missing"}

    client = TelegramClient(
        session_path, API_ID, API_HASH,
        connection_retries=2, retry_delay=1,
    )
    try:
        await asyncio.wait_for(client.connect(), timeout=12)

        # WAL mode
        try:
            s = client.session
            if hasattr(s, "_conn") and s._conn:
                s._conn.execute("PRAGMA busy_timeout=5000")
                s._conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass

        # Check auth
        try:
            authorized = await asyncio.wait_for(
                client.is_user_authorized(), timeout=8
            )
        except (AuthKeyUnregisteredError, AuthKeyDuplicatedError):
            return {"ok": False, "reason": "auth_key_unregistered"}
        except SessionRevokedError:
            return {"ok": False, "reason": "session_revoked"}
        except SessionExpiredError:
            return {"ok": False, "reason": "session_expired"}
        except UnauthorizedError:
            return {"ok": False, "reason": "unauthorized"}

        if not authorized:
            return {"ok": False, "reason": "unauthorized"}

        # Get user info
        try:
            me = await asyncio.wait_for(client.get_me(), timeout=8)
        except FloodWaitError as e:
            return {"ok": False, "reason": f"flood_wait_{e.seconds}s"}
        except Exception:
            return {"ok": False, "reason": "timeout"}

        if not me:
            return {"ok": False, "reason": "unauthorized"}

        phone_fmt = "+" + key if not key.startswith("+") else key
        return {
            "ok": True,
            "info": {
                "phone":    phone_fmt,
                "verified": True,
                "username": me.username or "",
                "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
                "user_id":  me.id,
                "dc_id":    getattr(getattr(me, "photo", None), "dc_id", None),
            }
        }

    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}
    except (UserDeactivatedBanError, PhoneNumberBannedError):
        return {"ok": False, "reason": "user_deactivated_ban"}
    except UserDeactivatedError:
        return {"ok": False, "reason": "user_deactivated"}
    except OSError:
        return {"ok": False, "reason": "network_error"}
    except Exception as e:
        err = str(e).lower()
        if "unauthorized" in err or "auth" in err:
            return {"ok": False, "reason": "unauthorized"}
        logger.warning("[validator] %s: %s", key, e)
        return {"ok": False, "reason": "network_error"}
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
