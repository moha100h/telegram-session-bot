import asyncio
import json
import logging
import os
from typing import Optional
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import DeleteChatUserRequest
from redis.asyncio import Redis

logger = logging.getLogger("session_manager")

API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
SESSIONS_DIR  = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR      = os.getenv("DATA_DIR", "/app/data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

_login_clients: dict = {}


def _load_sessions() -> dict:
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_sessions(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SESSIONS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_proxy(proxy_dict: dict = None):
    if not proxy_dict:
        return None
    return (proxy_dict.get("type", "socks5"),
            proxy_dict.get("host"),
            int(proxy_dict.get("port", 1080)))


async def get_all_sessions() -> list:
    data = _load_sessions()
    file_names = set()
    if os.path.exists(SESSIONS_DIR):
        for f in os.listdir(SESSIONS_DIR):
            if f.endswith(".session"):
                file_names.add(f.replace(".session", ""))
    result = []
    all_names = set(data.keys()) | file_names
    for name in sorted(all_names):
        info = data.get(name, {})
        path = os.path.join(SESSIONS_DIR, name + ".session")
        result.append({
            "name":     name,
            "phone":    info.get("phone", "+" + name),
            "active":   os.path.exists(path),
            "verified": info.get("verified", False),
            "username": info.get("username", ""),
            "fullname": info.get("fullname", ""),
            **info
        })
    return result


async def get_active_sessions() -> list:
    return [s for s in await get_all_sessions() if s.get("active")]


async def get_session(name: str) -> Optional[dict]:
    data = _load_sessions()
    info = data.get(name, {})
    path = os.path.join(SESSIONS_DIR, name + ".session")
    if not os.path.exists(path) and name not in data:
        return None
    return {
        "name":     name,
        "phone":    info.get("phone", "+" + name),
        "active":   os.path.exists(path),
        "verified": info.get("verified", False),
        "username": info.get("username", ""),
        "fullname": info.get("fullname", ""),
        **info
    }


async def get_session_names() -> list:
    names = []
    if os.path.exists(SESSIONS_DIR):
        for f in os.listdir(SESSIONS_DIR):
            if f.endswith(".session"):
                names.append(f.replace(".session", ""))
    return names


async def verify_session(name: str, proxy: dict = None) -> dict:
    """Actually connect and check if session is valid."""
    path = os.path.join(SESSIONS_DIR, name)
    try:
        client = TelegramClient(path, API_ID, API_HASH, proxy=_get_proxy(proxy))
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            # Mark as invalid
            data = _load_sessions()
            if name in data:
                data[name]["verified"] = False
                data[name]["active"] = False
                _save_sessions(data)
            return {"ok": False, "error": "unauthorized"}
        me = await client.get_me()
        await client.disconnect()
        # Update meta
        data = _load_sessions()
        if name not in data:
            data[name] = {}
        data[name].update({
            "verified": True,
            "phone":    me.phone and "+" + me.phone or "+" + name,
            "username": me.username or "",
            "fullname": (me.first_name or "") + " " + (me.last_name or ""),
            "user_id":  me.id,
        })
        _save_sessions(data)
        return {"ok": True, "me": {
            "phone":    data[name]["phone"],
            "username": data[name]["username"],
            "fullname": data[name]["fullname"].strip(),
            "user_id":  me.id,
        }}
    except FloodWaitError as e:
        return {"ok": False, "error": f"FloodWait {e.seconds}s"}
    except Exception as e:
        logger.error(f"[verify_session] {name}: {e}")
        return {"ok": False, "error": str(e)}


async def verify_all_sessions() -> dict:
    """Verify all sessions and return summary."""
    names = await get_session_names()
    results = {"ok": [], "fail": []}
    for name in names:
        r = await verify_session(name)
        if r["ok"]:
            results["ok"].append(name)
        else:
            results["fail"].append({"name": name, "error": r.get("error")})
        await asyncio.sleep(0.5)
    return results


async def leave_channel(name: str, channel: str, proxy: dict = None) -> dict:
    """Leave a channel/group with a session."""
    path = os.path.join(SESSIONS_DIR, name)
    try:
        client = TelegramClient(path, API_ID, API_HASH, proxy=_get_proxy(proxy))
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return {"ok": False, "error": "unauthorized"}
        entity = await client.get_entity(channel)
        await client(LeaveChannelRequest(entity))
        await client.disconnect()
        return {"ok": True}
    except Exception as e:
        logger.error(f"[leave_channel] {name} -> {channel}: {e}")
        return {"ok": False, "error": str(e)}


async def add_session(redis: Redis, phone: str, step: str,
                      code: str = None,
                      phone_code_hash: str = None,
                      password: str = None) -> dict:
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
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            _login_clients[phone] = client
        try:
            await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            await client.disconnect()
            _login_clients.pop(phone, None)
            data = _load_sessions()
            data[session_name] = {
                "phone":    phone,
                "verified": True,
                "username": me.username or "",
                "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
                "user_id":  me.id,
            }
            _save_sessions(data)
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
            me = await client.get_me()
            await client.disconnect()
            _login_clients.pop(phone, None)
            data = _load_sessions()
            data[session_name] = {
                "phone":    phone,
                "verified": True,
                "username": me.username or "",
                "fullname": ((me.first_name or "") + " " + (me.last_name or "")).strip(),
                "user_id":  me.id,
            }
            _save_sessions(data)
            return {"ok": True}
        except Exception as e:
            logger.error(f"[add_session] 2fa {phone}: {e}")
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "unknown step"}


async def delete_session(name: str):
    data = _load_sessions()
    data.pop(name, None)
    _save_sessions(data)
    for ext in [".session", ".session-journal"]:
        path = os.path.join(SESSIONS_DIR, name + ext)
        if os.path.exists(path):
            os.remove(path)
    logger.info(f"[delete_session] {name} removed")
