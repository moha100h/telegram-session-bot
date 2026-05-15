"""
Central session store — single source of truth.
All reads/writes go through here to prevent duplicates and race conditions.
"""
import asyncio
import json
import logging
import os

logger = logging.getLogger("session_store")

DATA_DIR      = os.getenv("DATA_DIR", "/app/data")
SESSIONS_DIR  = os.getenv("SESSIONS_DIR", "/app/sessions")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")

_lock: asyncio.Lock | None = None


def get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def load() -> dict:
    """Load sessions.json. Always returns a clean dict keyed by phone (no +)."""
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE) as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                return {}
            # Normalize keys: strip leading +
            return {k.lstrip("+"): v for k, v in raw.items()}
    except Exception as e:
        logger.error("session_store.load: %s", e)
    return {}


def _write(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SESSIONS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SESSIONS_FILE)  # atomic


async def save_one(key: str, info: dict):
    """Atomically add/update one session."""
    key = key.lstrip("+")
    async with get_lock():
        data = load()
        data[key] = info
        _write(data)


async def remove_one(key: str):
    """Atomically remove one session from JSON."""
    key = key.lstrip("+")
    async with get_lock():
        data = load()
        data.pop(key, None)
        _write(data)


async def replace_all(data: dict):
    """Replace entire sessions.json atomically."""
    async with get_lock():
        _write({k.lstrip("+"): v for k, v in data.items()})


def list_session_files() -> list[str]:
    """
    Returns list of phone keys (no +, no extension)
    from actual .session files on disk. Deduped.
    """
    seen = set()
    result = []
    try:
        for fname in os.listdir(SESSIONS_DIR):
            if not fname.endswith(".session"):
                continue
            if fname.endswith("-shm") or fname.endswith("-wal"):
                continue
            key = fname[:-8]  # strip .session
            if key not in seen:
                seen.add(key)
                result.append(key)
    except Exception as e:
        logger.error("list_session_files: %s", e)
    return sorted(result)


def remove_files(key: str):
    """Remove all .session* files for a phone key."""
    key = key.lstrip("+")
    base = os.path.join(SESSIONS_DIR, key)
    for ext in [".session", ".session-shm", ".session-wal", ".session-journal"]:
        p = base + ext
        if os.path.exists(p):
            try:
                os.remove(p)
                logger.info("removed %s", p)
            except Exception as e:
                logger.warning("remove %s: %s", p, e)
