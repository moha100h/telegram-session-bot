import asyncio
import json
import logging
import os
import aiohttp
from typing import Optional, Tuple

logger = logging.getLogger("herosms")

HEROSMS_API_KEY = os.getenv("HEROSMS_API_KEY", "")
HEROSMS_BASE    = "https://hero-sms.com/stubs/handler_api.php"

# Whitelist of quality countries for Telegram
PREFERRED_COUNTRIES = [106, 1, 14, 6, 22, 12, 31, 7]
# 106=Kazakhstan, 1=Russia, 14=Ukraine, 6=Indonesia,
# 22=Philippines, 12=Bangladesh, 31=South Africa, 7=Vietnam


class HeroSMSError(Exception):
    pass


# Shared aiohttp session for performance
_http_session: Optional[aiohttp.ClientSession] = None


async def _get_http() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=50),
            timeout=aiohttp.ClientTimeout(total=15),
        )
    return _http_session


async def _get(params: dict) -> str:
    params = dict(params)
    params["api_key"] = HEROSMS_API_KEY
    session = await _get_http()
    async with session.get(HEROSMS_BASE, params=params) as r:
        return (await r.text()).strip()


async def get_balance() -> float:
    result = await _get({"action": "getBalance"})
    if result.startswith("ACCESS_BALANCE:"):
        return float(result.split(":")[1])
    raise HeroSMSError(f"getBalance failed: {result}")


async def get_prices(service: str = "tg") -> dict:
    """
    Returns {country_id: {cost, count}} sorted by price.
    Only PREFERRED_COUNTRIES with count > 0.
    """
    result = await _get({"action": "getPrices", "service": service})
    try:
        data = json.loads(result)
        out  = {}
        for cid_str, services in data.items():
            cid = int(cid_str)
            if cid not in PREFERRED_COUNTRIES:
                continue
            if service not in services:
                continue
            info  = services[service]
            cost  = float(info.get("cost", 9999))
            count = int(info.get("count", 0))
            if count > 0:
                out[cid] = {"cost": cost, "count": count}
        return out
    except json.JSONDecodeError:
        raise HeroSMSError(f"getPrices parse error: {result}")


async def get_sorted_countries(service: str = "tg") -> list:
    """Returns [(country_id, price, count)] sorted cheapest first."""
    prices = await get_prices(service)
    if not prices:
        raise HeroSMSError("No available numbers in any country")
    return sorted(
        [(cid, info["cost"], info["count"]) for cid, info in prices.items()],
        key=lambda x: x[1]
    )


async def get_best_country(service: str = "tg") -> Tuple[int, float, int]:
    lst = await get_sorted_countries(service)
    return lst[0]


async def get_cheapest_country(service: str = "tg") -> Tuple[int, float]:
    cid, price, _ = await get_best_country(service)
    return cid, price


async def get_number(country: int, service: str = "tg") -> Tuple[int, str]:
    result = await _get({"action": "getNumber", "service": service, "country": country})
    if result.startswith("ACCESS_NUMBER:"):
        parts = result.split(":")
        return int(parts[1]), parts[2]
    raise HeroSMSError(f"getNumber failed: {result}")


async def get_number_smart(service: str = "tg") -> Tuple[int, str, int, float]:
    """
    Buy number from cheapest available country.
    Falls back to next country on failure.
    Returns (activation_id, phone, country_id, price)
    """
    sorted_countries = await get_sorted_countries(service)
    last_error = None
    for cid, price, count in sorted_countries:
        if count < 1:
            continue
        try:
            act_id, phone = await get_number(cid, service)
            logger.info("[herosms] bought %s country=%d price=%.3f$", phone, cid, price)
            return act_id, phone, cid, price
        except HeroSMSError as e:
            last_error = e
            logger.warning("[herosms] country %d -> %s, next...", cid, e)
    raise HeroSMSError(f"No country worked. Last: {last_error}")


async def get_sms_code(activation_id: int, timeout: int = 90) -> Optional[str]:
    """
    Poll for SMS. Fast polling: every 3s first 30s, then every 5s.
    Auto-cancels on timeout for refund.
    """
    start    = asyncio.get_event_loop().time()
    elapsed  = 0.0

    while elapsed < timeout:
        await asyncio.sleep(3 if elapsed < 30 else 5)
        elapsed = asyncio.get_event_loop().time() - start

        try:
            result = await _get({"action": "getStatus", "id": activation_id})
        except Exception as e:
            logger.warning("[herosms] getStatus err: %s", e)
            continue

        if result.startswith("STATUS_OK:"):
            code = result.split(":", 1)[1]
            logger.info("[herosms] ✅ code=%s id=%d (%.0fs)", code, activation_id, elapsed)
            return code
        elif result == "STATUS_CANCEL":
            logger.info("[herosms] id=%d cancelled by provider", activation_id)
            return None
        elif result not in ("STATUS_WAIT_CODE", "STATUS_WAIT_RETRY", "STATUS_WAIT_RESEND"):
            logger.warning("[herosms] unknown status id=%d: %s", activation_id, result)

    # Timeout — cancel for refund
    logger.info("[herosms] timeout id=%d — refunding", activation_id)
    try:
        r = await _get({"action": "setStatus", "id": activation_id, "status": 6})
        logger.info("[herosms] refund result: %s", r)
    except Exception as e:
        logger.error("[herosms] refund failed: %s", e)
    return None


async def set_status(activation_id: int, status: int) -> str:
    return await _get({"action": "setStatus", "id": activation_id, "status": status})


async def cancel_number(activation_id: int) -> str:
    result = await set_status(activation_id, 6)
    logger.info("[herosms] cancel %d -> %s", activation_id, result)
    return result


async def confirm_number(activation_id: int) -> str:
    result = await set_status(activation_id, 8)
    logger.info("[herosms] confirm %d -> %s", activation_id, result)
    return result
