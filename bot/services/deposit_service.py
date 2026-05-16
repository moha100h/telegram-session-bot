"""
Deposit service - create and manage deposit requests.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Transaction
from services.user_service import get_user_by_id, add_balance


async def create_deposit_request(
    session: AsyncSession,
    user_id: int,
    amount: float,
    method: str,
    tx_hash: str = "",
    wallet_address: str = "",
) -> Transaction:
    tx = Transaction(
        user_id        = user_id,
        type           = "deposit",
        amount         = amount,
        status         = "pending",
        method         = method,
        tx_hash        = tx_hash,
        wallet_address = wallet_address,
        description    = f"Deposit via {method}",
    )
    session.add(tx)
    await session.flush()
    return tx


async def approve_deposit(session: AsyncSession, tx_id: int) -> tuple[bool, str]:
    result = await session.execute(
        select(Transaction).where(Transaction.id == tx_id)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        return False, "تراکنش یافت نشد"
    if tx.status != "pending":
        return False, f"وضعیت قبلی: {tx.status}"
    tx.status = "approved"
    await add_balance(session, tx.user_id, float(tx.amount))
    return True, "تایید شد"


async def reject_deposit(session: AsyncSession, tx_id: int) -> tuple[bool, str]:
    result = await session.execute(
        select(Transaction).where(Transaction.id == tx_id)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        return False, "تراکنش یافت نشد"
    if tx.status != "pending":
        return False, f"وضعیت قبلی: {tx.status}"
    tx.status = "rejected"
    return True, "رد شد"


async def get_pending_deposits(session: AsyncSession) -> list[Transaction]:
    result = await session.execute(
        select(Transaction).where(
            Transaction.type == "deposit",
            Transaction.status == "pending",
        ).order_by(Transaction.created_at)
    )
    return list(result.scalars().all())


async def get_user_transactions(session: AsyncSession, user_id: int,
                                 page: int = 0, page_size: int = 10) -> list[Transaction]:
    result = await session.execute(
        select(Transaction).where(Transaction.user_id == user_id)
        .order_by(Transaction.created_at.desc())
        .offset(page * page_size).limit(page_size)
    )
    return list(result.scalars().all())


async def manual_credit(
    session: AsyncSession,
    user_id: int,
    amount: float,
    description: str = "Manual credit by admin",
) -> Transaction:
    await add_balance(session, user_id, amount)
    tx = Transaction(
        user_id     = user_id,
        type        = "manual",
        amount      = amount,
        status      = "approved",
        method      = "manual",
        description = description,
    )
    session.add(tx)
    await session.flush()
    return tx
