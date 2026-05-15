import asyncio
import json
import logging
import os
import aiohttp
from typing import Optional, Tuple

logger = logging.getLogger("herosms")

HEROSMS_API_KEY = os.getenv("HEROSMS_API_KEY", "")
HEROSMS_BASE    = "https://hero-sms.com/stubs/handler_api.php"

# Preferred country IDs — used as a whitelist (only these are tried)
# All others are ignored to avoid low-quality numbers
PREFERRED_COUNTRIES = [106, 1, 14, 6, 22, 12, 31, 7, 0]
# 106=Kazakhstan, 1=Russia, 14=Ukraine, 6=Indonesia,
# 22=Philippines, 12=Bangladesh, 31=South Africa, 7=Vietnam


class HeroSMSError(Exception):
    pass


async def _get(session: aiohttp.ClientSession, params: dict) -> str:
    params["api_key"] = HEROSMS_API_KEY
    async with session.get(
        HEROSMS_BASE, params=params,
        timeout=aiohttp.ClientTimeout(total=15)
    ) as r:
        text = await r.text()
        return text.strip()


async def get_balance() -> float:
    async with aiohttp.ClientSession() as session:
        result = await _get(session, {"action": "getBalance"})
        if result.startswith("ACCESS_BALANCE:"):
            return float(result.split(":")[1])
        raise HeroSMSError(f"getBalance failed: {result}")


async def get_prices(service: str = "tg") -> dict:
    """
    Returns {country_id: {cost, count}} for available countries.
    Only includes countries in PREFERRED_COUNTRIES with count > 0.
    """
    async with aiohttp.ClientSession() as session:
        result = await _get(session, {"action": "getPrices", "service": service})
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


async def get_sorted_countries(service: str = "tg") -> list[tuple[int, float, int]]:
    """
    Returns list of (country_id, price, count) sorted by price ascending.
    Cheapest first.
    """
    prices = await get_prices(service)
    if not prices:
        raise HeroSMSError("No available numbers in any country")
    sorted_list = sorted(
        [(cid, info["cost"], info["count"]) for cid, info in prices.items()],
        key=lambda x: x[1]  # sort by price
    )
    return sorted_list


async def get_best_country(service: str = "tg") -> Tuple[int, float, int]:
    """
    Returns (country_id, price, count) — cheapest available.
    """
    sorted_list = await get_sorted_countries(service)
    return sorted_list[0]  # cheapest first


async def get_cheapest_country(service: str = "tg") -> Tuple[int, float]:
    cid, price, _ = await get_best_country(service)
    return cid, price


async def get_number(country: int, service: str = "tg") -> Tuple[int, str]:
    """
    Buy a virtual number.
    Returns (activation_id, phone_number)
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
    Smart number purchase: tries countries sorted by price (cheapest first).
    Falls back to next country on NO_NUMBERS.
    Returns (activation_id, phone, country_id, price)
    """
    try:
        sorted_countries = await get_sorted_countries(service)
    except HeroSMSError:
        raise

    last_error = None
    for cid, price, count in sorted_countries:
        if count < 1:
            continue
        try:
            act_id, phone = await get_number(cid, service)
            logger.info("[herosms] bought %s from country %d @ %.3f$", phone, cid, price)
            return act_id, phone, cid, price
        except HeroSMSError as e:
            last_error = e
            logger.warning("[herosms] country %d failed (%s), trying next...", cid, e)
            continue

    raise HeroSMSError(
        f"Could not purchase from any country. Last error: {last_error}"
    )


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
                logger.info("[herosms] code=%s for id=%d", code, activation_id)
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
            r = await _get(session, {
                "action": "setStatus",
                "id":     activation_id,
                "status": 6,
            })
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
