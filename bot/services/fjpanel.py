"""
FJPanel API client.
https://fjpanel.com/api/v2
"""
import logging
import os

import httpx

logger = logging.getLogger("fjpanel")

API_URL = "https://fjpanel.com/api/v2"
API_KEY = os.getenv("FJPANEL_KEY", "656AEGDB99092971778949517YVWUZ734LMKIH9909STPRQ774")
TIMEOUT = 15


async def _post(data: dict) -> dict:
    data["key"] = API_KEY
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(API_URL, data=data)
        r.raise_for_status()
        return r.json()


async def get_balance() -> dict:
    """Returns {balance, currency}"""
    return await _post({"action": "balance"})


async def get_services() -> list:
    """Returns list of all services."""
    result = await _post({"action": "services"})
    return result if isinstance(result, list) else []


async def add_order(service_id: int, link: str, quantity: int) -> dict:
    """Returns {order: ID}"""
    return await _post({
        "action":   "add",
        "service":  service_id,
        "link":     link,
        "quantity": quantity,
    })


async def get_order_status(order_id: int) -> dict:
    """Returns {charge, status, currency}"""
    return await _post({"action": "status", "order": order_id})
