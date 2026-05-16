"""
Order service - place orders with markup, track status.
"""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Order, Transaction
from services.user_service import get_setting, deduct_balance


async def get_markup(session: AsyncSession) -> float:
    val = await get_setting(session, "smm_markup_percent", "20")
    try:
        return float(val)
    except Exception:
        return 20.0


def apply_markup(price: float, markup_pct: float) -> float:
    return round(price * (1 + markup_pct / 100), 4)


async def place_order(
    session: AsyncSession,
    user_id: int,
    service: dict,
    link: str,
    quantity: int,
    extra: dict = None
) -> dict:
    markup = await get_markup(session)
    rate   = float(service["rate"])
    cost   = round(rate * quantity / 1000, 4)          # actual SMMPass cost
    charge = round(apply_markup(rate, markup) * quantity / 1000, 4)  # user pays

    # Deduct balance
    ok = await deduct_balance(session, user_id, charge)
    if not ok:
        raise ValueError("insufficient_balance")

    # Place order on SMMPass
    from services import smmpass as sp
    t = service["type"].lower()
    if t == "package":
        result = await sp.add_order_package(service["service"], link)
    elif t in ("custom comments", "custom comments package"):
        result = await sp.add_order_custom_comments(service["service"], link, extra.get("comments", ""))
    elif t == "subscriptions":
        result = await sp.add_order_subscription(
            service["service"], extra.get("username", ""),
            extra.get("min", 1), extra.get("max", 100)
        )
    else:
        result = await sp.add_order_default(service["service"], link, quantity)

    smm_order_id = result.get("order")

    # Save order
    order = Order(
        user_id=user_id,
        service_id=service["service"],
        service_name=service["name"],
        link=link,
        quantity=quantity,
        charge=charge,
        cost=cost,
        status="processing",
    )
    session.add(order)

    # Save transaction
    tx = Transaction(
        user_id=user_id,
        type="order",
        amount=-charge,
        status="approved",
        description=f"Order #{smm_order_id} - {service['name'][:50]}"
    )
    session.add(tx)
    await session.flush()

    return {"order_id": order.id, "smm_order_id": smm_order_id, "charge": charge}


async def get_user_orders(session: AsyncSession, user_id: int) -> list[Order]:
    r = await session.execute(
        select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(20)
    )
    return r.scalars().all()
