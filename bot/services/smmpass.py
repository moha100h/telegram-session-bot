"""SMMPass API client — raw prices, no markup."""
import logging, os, time
import httpx

logger  = logging.getLogger("smmpass")
API_URL = "https://smmpass.com/api/v1"
API_KEY = os.getenv("SMMPASS_KEY", "J4C6s9TuoivmaY7I6X5Ad2euzXzRzy3v")
TIMEOUT = 25
_cache: dict = {}
_cache_ts: float = 0
CACHE_TTL = 3600

async def _post(action: str, extra: dict = None) -> dict:
    payload = {"key": API_KEY, "action": action}
    if extra:
        payload.update(extra)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(API_URL, data=payload)
        r.raise_for_status()
        return r.json()

async def get_services(force: bool = False) -> list:
    global _cache, _cache_ts
    now = time.time()
    if not force and _cache and (now - _cache_ts) < CACHE_TTL:
        return _cache.get("services", [])
    try:
        data = await _post("services")
        svcs = data if isinstance(data, list) else []
        _cache = {"services": svcs}
        _cache_ts = now
        return svcs
    except Exception as e:
        logger.error(f"get_services: {e}")
        return _cache.get("services", [])

async def get_balance() -> dict:
    return await _post("balance")

async def add_order_default(service: int, link: str, quantity: int) -> dict:
    return await _post("add", {"service": service, "link": link, "quantity": quantity})

async def add_order_package(service: int, link: str) -> dict:
    return await _post("add", {"service": service, "link": link})

async def add_order_custom_comments(service: int, link: str, comments: str) -> dict:
    return await _post("add", {"service": service, "link": link, "comments": comments})

async def add_order_mentions_hashtag(service: int, link: str, quantity: int) -> dict:
    return await _post("add", {"service": service, "link": link, "quantity": quantity})

async def add_order_mentions_custom(service: int, link: str, usernames: str) -> dict:
    return await _post("add", {"service": service, "link": link, "usernames": usernames})

async def add_order_subscription(service: int, username: str, min_: int, max_: int) -> dict:
    return await _post("add", {"service": service, "username": username, "min": min_, "max": max_})

async def cancel_order(order_id: int) -> dict:
    """Cancel an order via SMMPass API."""
    return await _post("cancel", {"orders": str(order_id)})


async def get_order_status(order_id: int) -> dict:
    return await _post("status", {"order": order_id})

def clear_cache():
    global _cache, _cache_ts
    _cache = {}; _cache_ts = 0

def get_categories(services: list) -> dict:
    cats: dict = {}
    for s in services:
        cat = s.get("category", "Other")
        cats.setdefault(cat, []).append(s)
    return dict(sorted(cats.items(), key=lambda x: -len(x[1])))
