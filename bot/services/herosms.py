import asyncio
import json
import logging
import os
import aiohttp
from typing import Optional, Tuple

logger = logging.getLogger("herosms")

HEROSMS_API_KEY = os.getenv("HEROSMS_API_KEY", "")
HEROSMS_BASE    = "https://hero-sms.com/stubs/handler_api.php"

# Preferred country IDs (SMS-Activate / HeroSMS compatible)
# Ordered by Telegram success rate
PREFERRED_COUNTRIES = [106, 1, 14, 6, 22, 12, 31, 0]
# 106=Kazakhstan, 1=Russia, 14=Ukraine, 6=Indonesia,
# 22=Philippines, 12=Bangladesh, 31=South Africa, 0=auto


class HeroSMSError(Exception):
    pass


async def _get(session: aiohttp.ClientSession, params: dict) -> str:
    params["api_key"] = HEROSMS_API_KEY
    async with session.get(HEROSMS_BASE, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
        text = await r.text()
        return text.strip()


async def get_balance() -> float:
    async with aiohttp.ClientSession() as session:
        result = await _get(session, {"action": "getBalance"})
        if result.startswith("ACCESS_BALANCE:"):
            return float(result.split(":")[1])
        raise HeroSMSError(f"getBalance failed: {result}")


async def get_prices(service: str = "tg") -> dict:
    """Returns {country_id: {cost, count}} for available countries."""
    async with aiohttp.ClientSession() as session:
        result = await _get(session, {"action": "getPrices", "service": service})
        try:
            data = json.loads(result)
            out = {}
            for cid, services in data.items():
                if service in services:
                    info = services[service]
                    cost  = float(info.get("cost", 9999))
                    count = int(info.get("count", 0))
                    if count > 0:
                        out[int(cid)] = {"cost": cost, "count": count}
            return out
        except json.JSONDecodeError:
            raise HeroSMSError(f"getPrices parse error: {result}")


async def get_best_country(service: str = "tg") -> Tuple[int, float, int]:
    """
    Returns (country_id, price, available_count).
    Picks from PREFERRED_COUNTRIES first, falls back to cheapest.
    """
    prices = await get_prices(service)
    if not prices:
        raise HeroSMSError("No available numbers in any country")

    # Try preferred countries in order
    for cid in PREFERRED_COUNTRIES:
        if cid in prices and prices[cid]["count"] > 0:
            return cid, prices[cid]["cost"], prices[cid]["count"]

    # Fallback: cheapest available
    best = min(prices.items(), key=lambda x: x[1]["cost"])
    return best[0], best[1]["cost"], best[1]["count"]


async def get_cheapest_country(service: str = "tg") -> Tuple[int, float]:
    cid, price, _ = await get_best_country(service)
    return cid, price


async def get_number(country: int, service: str = "tg") -> Tuple[int, str]:
    """
    Buy a virtual number.
    Returns (activation_id, phone_number)
    Raises HeroSMSError if no numbers available.
    """
    async with aiohttp.ClientSession() as session:
        result = await _get(session, {
            "action":  "getNumber",
            "service": service,
            "country": country,
        })
        if result.startswith("ACCESS_NUMBER:"):
            parts = result.split(":")
            return int(parts[1]), parts[2]
        raise HeroSMSError(f"getNumber failed: {result}")


async def get_number_smart(service: str = "tg") -> Tuple[int, str, int, float]:
    """
    Smart number purchase: tries preferred countries in order.
    Returns (activation_id, phone, country_id, price)
    """
    prices = await get_prices(service)
    if not prices:
        raise HeroSMSError("No numbers available in any country")

    for cid in PREFERRED_COUNTRIES:
        if cid not in prices or prices[cid]["count"] < 1:
            continue
        try:
            act_id, phone = await get_number(cid, service)
            return act_id, phone, cid, prices[cid]["cost"]
        except HeroSMSError as e:
            logger.warning("[herosms] country %d failed: %s", cid, e)
            continue

    # Fallback: try all available sorted by cost
    for cid, info in sorted(prices.items(), key=lambda x: x[1]["cost"]):
        try:
            act_id, phone = await get_number(cid, service)
            return act_id, phone, cid, info["cost"]
        except HeroSMSError:
            continue

    raise HeroSMSError("Could not purchase number from any country")


async def get_sms_code(activation_id: int, timeout: int = 120) -> Optional[str]:
    """
    Poll for SMS code. Auto-cancels (refund) on timeout.
    Returns code string or None.
    """
    async with aiohttp.ClientSession() as session:
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            try:
                result = await _get(session, {
                    "action": "getStatus",
                    "id":     activation_id,
                })
            except Exception as e:
                logger.warning("[herosms] getStatus error: %s", e)
                await asyncio.sleep(5)
                continue

            if result.startswith("STATUS_OK:"):
                code = result.split(":", 1)[1]
                logger.info("[herosms] got code=%s for id=%d", code, activation_id)
                return code
            elif result in ("STATUS_WAIT_CODE", "STATUS_WAIT_RETRY", "STATUS_WAIT_RESEND"):
                await asyncio.sleep(5)
            elif result == "STATUS_CANCEL":
                logger.info("[herosms] id=%d cancelled by provider", activation_id)
                return None
            else:
                logger.warning("[herosms] unknown status id=%d: %s", activation_id, result)
                await asyncio.sleep(5)

        # Timeout — cancel for refund
        logger.info("[herosms] timeout id=%d — cancelling for refund", activation_id)
        try:
            r = await _get(session, {"action": "setStatus", "id": activation_id, "status": 6})
            logger.info("[herosms] cancel result: %s", r)
        except Exception as e:
            logger.error("[herosms] cancel failed: %s", e)
        return None


async def set_status(activation_id: int, status: int) -> str:
    async with aiohttp.ClientSession() as session:
        return await _get(session, {
            "action": "setStatus",
            "id":     activation_id,
            "status": status,
        })


async def cancel_number(activation_id: int) -> str:
    """Cancel and refund."""
    result = await set_status(activation_id, 6)
    logger.info("[herosms] cancel %d -> %s", activation_id, result)
    return result


async def confirm_number(activation_id: int) -> str:
    """Mark activation complete."""
    result = await set_status(activation_id, 8)
    logger.info("[herosms] confirm %d -> %s", activation_id, result)
    return result
