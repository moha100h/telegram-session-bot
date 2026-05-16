"""
SMMPass API client — https://smmpass.com/api/v1
Supports: Default, Package, Custom Comments, Mentions (all types),
          Comment Likes, Subscriptions, order status, balance.
"""
import logging
import os
import time

import httpx

logger = logging.getLogger("smmpass")

API_URL = "https://smmpass.com/api/v1"
API_KEY = os.getenv("SMMPASS_KEY", "J4C6s9TuoivmaY7I6X5Ad2euzXzRzy3v")
TIMEOUT = 20

_cache: dict = {}


# ─── Type helpers ────────────────────────────────────────────────────────────────
def _s(v) -> str:
    if v is None: return ""
    if isinstance(v, bool): return "true" if v else "false"
    return str(v)

def _i(v) -> int:
    try: return int(float(_s(v)))
    except: return 0

def _f(v) -> float:
    try: return float(_s(v))
    except: return 0.0


# ─── Core POST ──────────────────────────────────────────────────────────────────
async def _post(data: dict) -> object:
    payload = {"key": API_KEY, **data}
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0)",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
        r = await c.post(API_URL, data=payload, headers=headers)
        if r.status_code == 403:
            raise ValueError("API دسترسی ندارد (403). با سایت SMMPass تماس بگیرید.")
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            raise ValueError(f"Response not JSON: {r.text[:200]}")


# ─── Normalize service ───────────────────────────────────────────────────────────
def _norm(s) -> dict | None:
    if not isinstance(s, dict): return None
    sid = _i(s.get("service", 0))
    if sid == 0: return None
    return {
        "service":  sid,
        "name":     _s(s.get("name", "?"))[:60],
        "category": _s(s.get("category", "General")),
        "rate":     _s(s.get("rate", "0")),
        "min":      _s(s.get("min", "1")),
        "max":      _s(s.get("max", "10000")),
        "type":     _s(s.get("type", "default")).lower(),
        "desc":     _s(s.get("desc", "")),
        "dripfeed": bool(s.get("dripfeed", False)),
    }


# ─── Public API ─────────────────────────────────────────────────────────────────
async def get_balance() -> dict:
    raw = await _post({"action": "balance"})
    if not isinstance(raw, dict):
        raise ValueError(f"Bad response: {raw}")
    if raw.get("status") == "error":
        raise ValueError(_s(raw.get("message", raw)))
    return {
        "balance":  _s(raw.get("balance", "0")),
        "currency": _s(raw.get("currency", "USD")),
    }


async def get_services(force: bool = False) -> list:
    key = "services"
    now = time.time()
    if not force and key in _cache:
        ts, data = _cache[key]
        if now - ts < 300:
            return data
    raw = await _post({"action": "services"})
    items = raw if isinstance(raw, list) else raw.get("data", []) if isinstance(raw, dict) else []
    services = [n for s in items if (n := _norm(s))]
    _cache[key] = (now, services)
    logger.info("SMMPass: loaded %d services", len(services))
    return services


def _handle_order(raw) -> dict:
    if not isinstance(raw, dict): raise ValueError(f"Bad response: {raw}")
    if "error" in raw: raise ValueError(_s(raw["error"]))
    if raw.get("status") == "error": raise ValueError(_s(raw.get("message", str(raw))))
    oid = _i(raw.get("order", 0))
    if oid == 0: raise ValueError(f"No order ID: {raw}")
    return {"order": oid}


async def add_order_default(service_id: int, link: str, quantity: int,
                            runs: int = None, interval: int = None) -> dict:
    data = {"action": "add", "service": service_id, "link": link, "quantity": quantity}
    if runs:     data["runs"]     = runs
    if interval: data["interval"] = interval
    return _handle_order(await _post(data))


async def add_order_package(service_id: int, link: str) -> dict:
    return _handle_order(await _post(
        {"action": "add", "service": service_id, "link": link}))


async def add_order_custom_comments(service_id: int, link: str, comments: str) -> dict:
    return _handle_order(await _post(
        {"action": "add", "service": service_id, "link": link, "comments": comments}))


async def add_order_mentions_hashtags(service_id: int, link: str, quantity: int,
                                      usernames: str, hashtags: str) -> dict:
    return _handle_order(await _post({
        "action": "add", "service": service_id, "link": link,
        "quantity": quantity, "usernames": usernames, "hashtags": hashtags,
    }))


async def add_order_mentions_custom(service_id: int, link: str, usernames: str) -> dict:
    return _handle_order(await _post(
        {"action": "add", "service": service_id, "link": link, "usernames": usernames}))


async def add_order_mentions_hashtag(service_id: int, link: str, quantity: int,
                                     hashtag: str) -> dict:
    return _handle_order(await _post({
        "action": "add", "service": service_id, "link": link,
        "quantity": quantity, "hashtag": hashtag,
    }))


async def add_order_mentions_followers(service_id: int, link: str, quantity: int,
                                       username: str) -> dict:
    return _handle_order(await _post({
        "action": "add", "service": service_id, "link": link,
        "quantity": quantity, "username": username,
    }))


async def add_order_comment_likes(service_id: int, link: str, quantity: int,
                                  username: str) -> dict:
    return _handle_order(await _post({
        "action": "add", "service": service_id, "link": link,
        "quantity": quantity, "username": username,
    }))


async def add_order_subscription(service_id: int, username: str,
                                  min_qty: int, max_qty: int,
                                  delay: int = 0, expiry: str = None) -> dict:
    data = {
        "action": "add", "service": service_id,
        "username": username, "min": min_qty, "max": max_qty, "delay": delay,
    }
    if expiry: data["expiry"] = expiry
    return _handle_order(await _post(data))


async def get_order_status(order_id: int) -> dict:
    raw = await _post({"action": "status", "order": order_id})
    if not isinstance(raw, dict): raise ValueError(f"Bad response: {raw}")
    if "error" in raw: raise ValueError(_s(raw["error"]))
    if raw.get("status") == "error": raise ValueError(_s(raw.get("message", str(raw))))
    return {
        "order":       _s(raw.get("order", order_id)),
        "status":      _s(raw.get("status", "unknown")),
        "charge":      _s(raw.get("charge", "0")),
        "start_count": _s(raw.get("start_count", "0")),
        "remains":     _s(raw.get("remains", "0")),
    }


async def get_orders_status(order_ids: list[int]) -> dict:
    ids = ",".join(str(i) for i in order_ids)
    raw = await _post({"action": "status", "orders": ids})
    if not isinstance(raw, dict): raise ValueError(f"Bad response: {raw}")
    return raw


def clear_cache():
    _cache.clear()
