import asyncio
import json
import logging
import os
import aiohttp
from typing import Optional

logger = logging.getLogger("herosms")

HEROSMS_API_KEY = os.getenv("HEROSMS_API_KEY", "")
HEROSMS_BASE    = "https://hero-sms.com/stubs/handler_api.php"


class HeroSMSError(Exception):
    pass


async def _get(session: aiohttp.ClientSession, params: dict) -> str:
    params["api_key"] = HEROSMS_API_KEY
    async with session.get(HEROSMS_BASE, params=params) as r:
        text = await r.text()
        return text.strip()


async def get_balance() -> float:
    """Get current account balance."""
    async with aiohttp.ClientSession() as session:
        result = await _get(session, {"action": "getBalance"})
        if result.startswith("ACCESS_BALANCE:"):
            return float(result.split(":")[1])
        raise HeroSMSError(f"getBalance failed: {result}")


async def get_cheapest_country(service: str = "tg") -> tuple:
    """
    Find cheapest country for given service.
    Returns (country_id, price_per_activation)
    """
    async with aiohttp.ClientSession() as session:
        result = await _get(session, {"action": "getPrices", "service": service})
        try:
            data = json.loads(result)
            best_country = None
            best_price   = 9999.0
            for country_id, services in data.items():
                if service in services:
                    info  = services[service]
                    cost  = float(info.get("cost", 9999))
                    count = int(info.get("count", 0))
                    if count > 0 and cost < best_price:
                        best_price   = cost
                        best_country = int(country_id)
            if best_country is None:
                raise HeroSMSError("No available numbers found")
            return best_country, best_price
        except json.JSONDecodeError:
            raise HeroSMSError(f"getPrices parse error: {result}")


async def get_number(country: int, service: str = "tg") -> tuple:
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
        # Response: ACCESS_NUMBER:12345678:79001234567
        if result.startswith("ACCESS_NUMBER:"):
            parts = result.split(":")
            return int(parts[1]), parts[2]
        raise HeroSMSError(f"getNumber failed: {result}")


async def get_sms_code(activation_id: int, timeout: int = 120) -> Optional[str]:
    """
    Poll for SMS code.
    Returns code string on success.
    Returns None on timeout or cancel — and auto-cancels to trigger refund.
    """
    async with aiohttp.ClientSession() as session:
        start = asyncio.get_event_loop().time()
        got_code = None
        while asyncio.get_event_loop().time() - start < timeout:
            result = await _get(session, {
                "action": "getStatus",
                "id":     activation_id,
            })
            if result.startswith("STATUS_OK:"):
                got_code = result.split(":")[1]
                break
            elif result in ("STATUS_WAIT_CODE", "STATUS_WAIT_RETRY"):
                await asyncio.sleep(5)
            elif result == "STATUS_CANCEL":
                # Already cancelled by provider
                logger.info("[herosms] activation %d cancelled by provider", activation_id)
                return None
            elif result == "STATUS_WAIT_RESEND":
                await asyncio.sleep(5)
            else:
                logger.warning("[herosms] unknown status for %d: %s", activation_id, result)
                await asyncio.sleep(5)

        if got_code is None:
            # Timeout — cancel to get refund
            logger.info("[herosms] timeout on %d — cancelling for refund", activation_id)
            try:
                cancel_result = await _get(session, {
                    "action": "setStatus",
                    "id":     activation_id,
                    "status": 6,
                })
                logger.info("[herosms] cancel result for %d: %s", activation_id, cancel_result)
            except Exception as e:
                logger.error("[herosms] cancel failed for %d: %s", activation_id, e)
            return None

        return got_code


async def set_status(activation_id: int, status: int) -> str:
    """
    Set activation status:
    1 = SMS received (notify provider)
    3 = Request another SMS
    6 = Cancel activation (refund)
    8 = Activation complete (confirm)
    """
    async with aiohttp.ClientSession() as session:
        return await _get(session, {
            "action": "setStatus",
            "id":     activation_id,
            "status": status,
        })


async def cancel_number(activation_id: int) -> str:
    """Cancel and refund the number. Returns API response."""
    result = await set_status(activation_id, 6)
    logger.info("[herosms] cancel %d -> %s", activation_id, result)
    return result


async def confirm_number(activation_id: int) -> str:
    """Mark activation as complete."""
    result = await set_status(activation_id, 8)
    logger.info("[herosms] confirm %d -> %s", activation_id, result)
    return result
