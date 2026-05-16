"""
Instagram account store.
Saves/loads IG accounts from /app/data/ig_accounts.json
"""
import json
import os
import asyncio
import logging

logger    = logging.getLogger("ig_store")
DATA_DIR  = os.getenv("DATA_DIR", "/app/data")
IG_FILE   = os.path.join(DATA_DIR, "ig_accounts.json")
_lock     = asyncio.Lock()


def load() -> dict:
    """Returns dict keyed by username."""
    try:
        if os.path.exists(IG_FILE):
            with open(IG_FILE) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.error("ig_store.load: %s", e)
    return {}


def _write(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = IG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, IG_FILE)


async def save(username: str, info: dict):
    async with _lock:
        data = load()
        data[username] = info
        _write(data)


async def remove(username: str):
    async with _lock:
        data = load()
        data.pop(username, None)
        _write(data)


async def mark_banned(username: str):
    async with _lock:
        data = load()
        if username in data:
            data[username]["status"] = "banned"
            _write(data)


async def update_field(username: str, **kwargs):
    async with _lock:
        data = load()
        if username in data:
            data[username].update(kwargs)
            _write(data)


def list_active() -> list:
    return [v for v in load().values() if v.get("status") == "active"]


def list_all() -> list:
    return list(load().values())


def count() -> dict:
    all_accs = load()
    active  = sum(1 for v in all_accs.values() if v.get("status") == "active")
    banned  = sum(1 for v in all_accs.values() if v.get("status") == "banned")
    pending = sum(1 for v in all_accs.values() if v.get("status") == "pending")
    return {"total": len(all_accs), "active": active,
            "banned": banned, "pending": pending}
