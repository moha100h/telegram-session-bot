"""Real-time crypto prices via CoinGecko. Cache: 60s."""
import time, aiohttp
from typing import Optional

_cache: dict = {}
CACHE_TTL = 60
COIN_IDS = {
    "ton":   "the-open-network", "trx": "tron", "bnb": "binancecoin",
    "eth":   "ethereum",         "btc": "bitcoin", "sol": "solana",
    "matic": "matic-network",    "ltc": "litecoin", "xrp": "ripple", "doge": "dogecoin",
}
STABLE = {"usdt","usdt_trc","usdt_bep","usdt_erc","usdc","busd","dai"}

async def get_price_usd(coin_key: str) -> Optional[float]:
    ck = coin_key.lower()
    if ck in STABLE: return 1.0
    cid = COIN_IDS.get(ck)
    if not cid: return None
    if ck in _cache:
        p, ts = _cache[ck]
        if time.time() - ts < CACHE_TTL: return p
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=usd"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(url) as r: data = await r.json()
        p = float(data[cid]["usd"])
        _cache[ck] = (p, time.time()); return p
    except Exception:
        return _cache[ck][0] if ck in _cache else None

async def usd_to_coin(usd: float, coin_key: str) -> Optional[float]:
    p = await get_price_usd(coin_key)
    return (usd / p) if p and p > 0 else None

def format_amount(amount: float, coin_key: str) -> str:
    ck = coin_key.lower()
    if ck in STABLE: return f"{amount:.2f}"
    if ck == "btc":  return f"{amount:.8f}"
    if ck in ("eth","bnb","sol"): return f"{amount:.6f}"
    return f"{amount:.4f}"
