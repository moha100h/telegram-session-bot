"""Settings service."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import AdminSetting

async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(AdminSetting).where(AdminSetting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row and row.value is not None else default

async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    result = await session.execute(select(AdminSetting).where(AdminSetting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(AdminSetting(key=key, value=value))
    await session.flush()

async def get_wallets(session: AsyncSession) -> dict:
    out = {}
    for key in ["wallet_usdt", "wallet_ton", "wallet_trx"]:
        out[key.replace("wallet_", "")] = await get_setting(session, key, "")
    return out
