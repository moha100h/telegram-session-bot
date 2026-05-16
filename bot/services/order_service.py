"""
Order service - place and manage SMM orders.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Order, AdminSetting

logger = logging.getLogger("order_service")


async def get_markup(session: AsyncSession) -> float:
    result = await session.execute(
        select(AdminSetting).where(AdminSetting.key == "smm_markup_percent")
    )
    row = result.scalar_one_or_none()
    try:
        return float(row.value) if row and row.value else 20.0
    except Exception:
        return 20.0


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
