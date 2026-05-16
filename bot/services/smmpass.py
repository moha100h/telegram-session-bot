"""
SMMPass API client.
Endpoint: POST https://smmpass.com/api/v2
Features: services, add order (+ drip-feed), status, batch status, refill, balance
"""
import logging
import os
import time

import httpx

logger = logging.getLogger("smmpass")

API_URL = os.getenv("SMMPASS_URL", "https://smmpass.com/api/v2")
API_KEY = os.getenv("SMMPASS_KEY", "")
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


# ─── Core POST ───────────────────────────────────────────────────────────────────
async def _post(data: dict) -> object:
    payload = dict(data)
    payload["key"] = API_KEY
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(API_URL, data=payload)
        r.raise_for_status()
        return r.json()


# ─── Normalize service ─────────────────────────────────────────────────────────────
def _norm(s) -> dict | None:
    if not isinstance(s, dict): return None
    sid = _i(s.get("service", 0))
    if sid == 0: return None
    return {
        "service":   sid,
        "name":      _s(s.get("name", "?"))[:60],
        "category":  _s(s.get("category", "General")),
        "rate":      _s(s.get("rate", "0")),
        "min":       _s(s.get("min", "1")),
        "max":       _s(s.get("max", "10000")),
        "type":      _s(s.get("type", "default")),
        "desc":      _s(s.get("desc", "")),
        "dripfeed":  bool(_i(s.get("dripfeed", 0))),
    }


# ─── Public API ───────────────────────────────────────────────────────────────────
async def get_balance() -> dict:
    raw = await _post({"action": "balance"})
    if not isinstance(raw, dict):
        raise ValueError(f"Bad response: {raw}")
    if "error" in raw:
        raise ValueError(_s(raw["error"]))
    return {
        "balance":  _s(raw.get("balance", "0")),
        "currency": _s(raw.get("currency", "USD")),
    }


async def get_services(force: bool = False) -> list:
    """Cached 5 min. force=True bypasses cache."""
    key = "smmpass_services"
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


async def add_order(
    service_id: int,
    link: str,
    quantity: int,
    runs: int = 0,
    interval: int = 0,
) -> dict:
    """Returns {order: int}"""
    payload = {
        "action":   "add",
        "service":  service_id,
        "link":     link,
        "quantity": quantity,
    }
    if runs > 0:     payload["runs"]     = runs
    if interval > 0: payload["interval"] = interval
    raw = await _post(payload)
    if not isinstance(raw, dict):
        raise ValueError(f"Bad response: {raw}")
    if "error" in raw:
        raise ValueError(_s(raw["error"]))
    oid = _i(raw.get("order", 0))
    if oid == 0:
        raise ValueError(f"No order ID: {raw}")
    return {"order": oid}


async def get_order_status(order_id: int) -> dict:
    """Returns {order, status, charge, start_count, remains}"""
    raw = await _post({"action": "status", "order": order_id})
    if not isinstance(raw, dict):
        raise ValueError(f"Bad response: {raw}")
    if "error" in raw:
        raise ValueError(_s(raw["error"]))
    return {
        "order":       _s(raw.get("order", order_id)),
        "status":      _s(raw.get("status", "unknown")),
        "charge":      _s(raw.get("charge", "0")),
        "start_count": _s(raw.get("start_count", "0")),
        "remains":     _s(raw.get("remains", "0")),
    }


async def get_orders_status(order_ids: list[int]) -> dict:
    """Batch status. Returns {order_id: dict|str}"""
    ids_str = ",".join(str(i) for i in order_ids)
    raw = await _post({"action": "status", "orders": ids_str})
    if not isinstance(raw, dict):
        raise ValueError(f"Bad response: {raw}")
    result = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            result[k] = {
                "order":       _s(v.get("order", k)),
                "status":      _s(v.get("status", "?")),
                "charge":      _s(v.get("charge", "0")),
                "start_count": _s(v.get("start_count", "0")),
                "remains":     _s(v.get("remains", "0")),
            }
        else:
            result[k] = _s(v)
    return result


async def create_refill(order_id: int) -> dict:
    """Returns {refill: int}"""
    raw = await _post({"action": "refill", "order": order_id})
    if not isinstance(raw, dict):
        raise ValueError(f"Bad response: {raw}")
    if "error" in raw:
        raise ValueError(_s(raw["error"]))
    return {"refill": _i(raw.get("refill", 0))}


def clear_cache():
    _cache.clear()
