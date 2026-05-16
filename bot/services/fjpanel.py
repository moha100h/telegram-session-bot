"""
FJPanel API client — robust version.
Handles all type mismatches from API responses.
"""
import logging
import os
import time

import httpx

logger = logging.getLogger("fjpanel")

API_URL = os.getenv("FJPANEL_URL", "https://fjpanel.com/api/v2")
API_KEY = os.getenv("FJPANEL_KEY", "")
TIMEOUT = 20

# In-memory cache
_cache: dict = {}


def _str(val) -> str:
    """Safe string conversion — handles bool, None, int, etc."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def _float(val) -> float:
    """Safe float conversion."""
    try:
        return float(_str(val))
    except (ValueError, TypeError):
        return 0.0


def _int(val) -> int:
    """Safe int conversion."""
    try:
        return int(float(_str(val)))
    except (ValueError, TypeError):
        return 0


def _normalize_service(s) -> dict | None:
    """Normalize a raw service dict — returns None if invalid."""
    if not isinstance(s, dict):
        return None
    svc_id = _int(s.get("service", 0))
    if svc_id == 0:
        return None
    return {
        "service":  svc_id,
        "name":     _str(s.get("name", "?"))[:60],
        "type":     _str(s.get("type", "Default")),
        "category": _str(s.get("category", "General")),
        "rate":     _str(s.get("rate", "0")),
        "min":      _str(s.get("min", "1")),
        "max":      _str(s.get("max", "10000")),
    }


async def _post(data: dict) -> object:
    """POST to API, returns parsed JSON."""
    payload = dict(data)
    payload["key"] = API_KEY
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(API_URL, data=payload)
        r.raise_for_status()
        return r.json()


async def get_balance() -> dict:
    """Returns {balance: str, currency: str}"""
    raw = await _post({"action": "balance"})
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected response: {raw}")
    return {
        "balance":  _str(raw.get("balance", "0")),
        "currency": _str(raw.get("currency", "Rial")),
    }


async def get_services(force: bool = False) -> list:
    """
    Returns normalized list of services.
    Cached for 5 minutes unless force=True.
    """
    cache_key = "services"
    now = time.time()
    if not force and cache_key in _cache:
        ts, data = _cache[cache_key]
        if now - ts < 300:
            return data

    raw = await _post({"action": "services"})

    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        # Some panels wrap in {"data": [...]}
        items = raw.get("data", [])
        if not isinstance(items, list):
            items = []
    else:
        items = []

    services = []
    for s in items:
        normalized = _normalize_service(s)
        if normalized:
            services.append(normalized)

    _cache[cache_key] = (now, services)
    logger.info("FJPanel: loaded %d services", len(services))
    return services


async def add_order(service_id: int, link: str, quantity: int) -> dict:
    """Returns {order: int}"""
    raw = await _post({
        "action":   "add",
        "service":  service_id,
        "link":     link,
        "quantity": quantity,
    })
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected response: {raw}")
    if "error" in raw:
        raise ValueError(_str(raw["error"]))
    order_id = _int(raw.get("order", 0))
    if order_id == 0:
        raise ValueError(f"No order ID in response: {raw}")
    return {"order": order_id}


async def get_order_status(order_id: int) -> dict:
    """Returns {charge: str, status: str, currency: str}"""
    raw = await _post({"action": "status", "order": order_id})
    if not isinstance(raw, dict):
        raise ValueError(f"Unexpected response: {raw}")
    if "error" in raw:
        raise ValueError(_str(raw["error"]))
    return {
        "charge":   _str(raw.get("charge", "0")),
        "status":   _str(raw.get("status", "unknown")),
        "currency": _str(raw.get("currency", "Rial")),
    }


def clear_cache():
    """Clear all cached data."""
    _cache.clear()
