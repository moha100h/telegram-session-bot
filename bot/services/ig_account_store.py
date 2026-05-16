"""
Instagram account storage.
Saves accounts to /app/data/ig_accounts.json
"""
import json
import logging
import os

logger    = logging.getLogger("ig_store")
DATA_DIR  = os.getenv("DATA_DIR", "/app/data")
STORE_FILE = os.path.join(DATA_DIR, "ig_accounts.json")


def _load() -> list:
    try:
        if os.path.exists(STORE_FILE):
            with open(STORE_FILE) as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error("ig_store load: %s", e)
    return []


def _save(accounts: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STORE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STORE_FILE)


def load_accounts() -> list:
    return _load()


def count_accounts(active_only=False) -> int:
    accounts = _load()
    if active_only:
        return sum(1 for a in accounts if a.get("active"))
    return len(accounts)


def save_account(account: dict):
    accounts = _load()
    # update if exists
    for i, a in enumerate(accounts):
        if a.get("username") == account.get("username"):
            accounts[i] = account
            _save(accounts)
            return
    accounts.append(account)
    _save(accounts)


def remove_account(username: str):
    accounts = _load()
    accounts = [a for a in accounts if a.get("username") != username]
    _save(accounts)


def get_active_accounts(limit: int = None) -> list:
    accounts = [a for a in _load() if a.get("active")]
    if limit:
        return accounts[:limit]
    return accounts


def mark_banned(username: str):
    accounts = _load()
    for a in accounts:
        if a.get("username") == username:
            a["active"] = False
            a["banned"] = True
    _save(accounts)
