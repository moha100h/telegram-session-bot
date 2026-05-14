import asyncio
import json
import logging
import os
from typing import Optional
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from redis.asyncio import Redis

logger = logging.getLogger("session_manager")

API_ID       = int(os.getenv("API_ID", "0"))
API_HASH     = os.getenv("API_HASH", "")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR", "/app/data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# In-memory temp store for login flows
_login_clients: dict = {}


# ----------------------------------------------------------------
# Persistence helpers
# ----------------------------------------------------------------
def _load_sessions() -> dict:
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_sessions(data: dict):
    with open(SESSIONS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------
# Public read API
# ----------------------------------------------------------------
async def get_all_sessions() -> list:
    """Return list of all session dicts."""
    data = _load_sessions()
    result = []
    for name, info in data.items():
        # Check if session file exists
        path = os.path.join(SESSIONS_DIR, name + ".session")
        active = os.path.exists(path)
        result.append({
            "name":   name,
            "phone":  info.get("phone", name),
            "active": active,
            **info
        })
    return result


async def get_active_sessions() -> list:
    sessions = await get_all_sessions()
    return [s for s in sessions if s.get("active")]


async def get_session(name: str) -> Optional[dict]:
    data = _load_sessions()
    if name not in data:
        return None
    info = data[name]
    path = os.path.join(SESSIONS_DIR, name + ".session")
    return {
        "name":   name,
        "phone":  info.get("phone", name),
        "active": os.path.exists(path),
        **info
    }


async def get_session_names() -> list:
    """Return list of session file names (without .session)."""
    names = []
    if os.path.exists(SESSIONS_DIR):
        for f in os.listdir(SESSIONS_DIR):
            if f.endswith(".session"):
                names.append(f.replace(".session", ""))
    return names


# ----------------------------------------------------------------
# Add session (multi-step login flow)
# ----------------------------------------------------------------
async def add_session(redis: Redis, phone: str, step: str,
                      code: str = None,
                      phone_code_hash: str = None,
                      password: str = None) -> dict:
    """
    Multi-step login:
      step="send_code"  -> sends code, returns {ok, phone_code_hash}
      step="sign_in"    -> signs in with code, returns {ok} or {need_password}
      step="2fa"        -> completes 2FA, returns {ok}
    """
    # Normalize phone
    phone = phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    session_name = phone.replace("+", "").replace(" ", "")
    session_path = os.path.join(SESSIONS_DIR, session_name)

    if step == "send_code":
        try:
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            result = await client.send_code_request(phone)
            _login_clients[phone] = client
            return {"ok": True, "phone_code_hash": result.phone_code_hash}
        except Exception as e:
            logger.error(f"[add_session] send_code {phone}: {e}")
            return {"ok": False, "error": str(e)}

    elif step == "sign_in":
        client = _login_clients.get(phone)
        if client is None:
            # Reconnect
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            _login_clients[phone] = client
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            await client.disconnect()
            _login_clients.pop(phone, None)
            # Save to sessions file
            data = _load_sessions()
            data[session_name] = {"phone": phone}
            _save_sessions(data)
            logger.info(f"[add_session] {phone} signed in OK")
            return {"ok": True}
        except SessionPasswordNeededError:
            return {"ok": False, "need_password": True}
        except Exception as e:
            logger.error(f"[add_session] sign_in {phone}: {e}")
            return {"ok": False, "error": str(e)}

    elif step == "2fa":
        client = _login_clients.get(phone)
        if client is None:
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            _login_clients[phone] = client
        try:
            await client.sign_in(password=password)
            await client.disconnect()
            _login_clients.pop(phone, None)
            data = _load_sessions()
            data[session_name] = {"phone": phone}
            _save_sessions(data)
            logger.info(f"[add_session] {phone} 2FA OK")
            return {"ok": True}
        except Exception as e:
            logger.error(f"[add_session] 2fa {phone}: {e}")
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "unknown step"}


# ----------------------------------------------------------------
# Delete session
# ----------------------------------------------------------------
async def delete_session(name: str):
    # Remove from JSON
    data = _load_sessions()
    data.pop(name, None)
    _save_sessions(data)
    # Remove session file
    path = os.path.join(SESSIONS_DIR, name + ".session")
    if os.path.exists(path):
        os.remove(path)
    logger.info(f"[delete_session] {name} removed")
