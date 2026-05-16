"""
Admin settings service.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import AdminSetting


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(
        select(AdminSetting).where(AdminSetting.key == key)
    )
    s = result.scalar_one_or_none()
    return s.value if s else default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    result = await session.execute(
        select(AdminSetting).where(AdminSetting.key == key)
    )
    s = result.scalar_one_or_none()
    if s:
        s.value = value
    else:
        session.add(AdminSetting(key=key, value=value))
    await session.flush()


async def get_all_settings(session: AsyncSession) -> dict:
    result = await session.execute(select(AdminSetting))
    return {s.key: s.value for s in result.scalars().all()}


async def get_wallets(session: AsyncSession) -> dict:
    keys = ["usdt_wallet", "ton_wallet", "trx_wallet"]
    wallets = {}
    for key in keys:
        wallets[key] = await get_setting(session, key, "")
    return wallets
