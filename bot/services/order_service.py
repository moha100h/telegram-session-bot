"""
Order service - place and manage SMM orders.
"""
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Order, AdminSetting

logger = logging.getLogger("order_service")


async def get_markup(session: AsyncSession) -> float:
    """Return markup percent from settings (default 20)."""
    result = await session.execute(
        select(AdminSetting).where(AdminSetting.key == "smm_markup_percent")
    )
    row = result.scalar_one_or_none()
    try:
        return float(row.value) if row and row.value else 20.0
    except Exception:
        return 20.0


def apply_markup(price: float, markup_percent: float) -> float:
    """Apply markup percent to a price."""
    return round(price * (1 + markup_percent / 100), 4)


def calc_order_price(rate: float, quantity: int, markup_percent: float) -> float:
    """Calculate final order price: rate per 1000 * quantity + markup."""
    base = rate * quantity / 1000
    return round(base * (1 + markup_percent / 100), 4)


async def create_order(
    session: AsyncSession,
    user_id: int,
    service_id: int,
    service_name: str,
    link: str,
    quantity: int,
    cost_price: float,
    sell_price: float,
) -> Order:
    """Create and persist a new order."""
    order = Order(
        user_id=user_id,
        service_id=service_id,
        service_name=service_name,
        link=link,
        quantity=quantity,
        cost_price=cost_price,
        sell_price=sell_price,
        status="pending",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def place_order(
    session: AsyncSession,
    user_id: int,
    service_id: int,
    service_name: str,
    link: str,
    quantity: int,
    cost_price: float,
    sell_price: float,
) -> Order:
    """Alias for create_order."""
    return await create_order(
        session, user_id, service_id, service_name,
        link, quantity, cost_price, sell_price
    )


async def get_user_orders(session: AsyncSession, user_id: int) -> list:
    result = await session.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
    )
    return result.scalars().all()


async def get_all_orders(session: AsyncSession) -> list:
    result = await session.execute(
        select(Order).order_by(Order.created_at.desc())
    )
    return result.scalars().all()
