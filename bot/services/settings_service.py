"""Settings service."""
import json
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
    if row: row.value = value
    else: session.add(AdminSetting(key=key, value=value))
    await session.flush()

_DEFAULT_COINS = [
    {"key":"usdt_trc","label":"USDT (TRC20)","icon":"🟢","network":"TRC20","address":"","enabled":True},
    {"key":"ton",     "label":"TON",          "icon":"💎","network":"TON",  "address":"","enabled":True},
    {"key":"trx",     "label":"TRX",          "icon":"⚡","network":"TRON", "address":"","enabled":True},
]

async def get_coins(session: AsyncSession) -> list:
    raw = await get_setting(session, "coins_config", "")
    if raw:
        try: return json.loads(raw)
        except Exception: pass
    coins = []
    for c in _DEFAULT_COINS:
        base = c["key"].split("_")[0]
        addr    = await get_setting(session, f"wallet_{base}", "")
        enabled = await get_setting(session, f"wallet_{base}_enabled", "1")
        coins.append({**c, "address": addr, "enabled": enabled == "1"})
    return coins

async def save_coins(session: AsyncSession, coins: list) -> None:
    await set_setting(session, "coins_config", json.dumps(coins, ensure_ascii=False))

async def get_active_coins(session: AsyncSession) -> list:
    return [c for c in await get_coins(session) if c.get("enabled") and c.get("address","").strip()]

async def get_wallets(session: AsyncSession) -> dict:
    return {c["key"]: c.get("address","") for c in await get_coins(session)}
