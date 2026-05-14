import asyncio, logging, json, random
import aiohttp
from redis.asyncio import Redis

logger = logging.getLogger("proxy_fetcher")
PROXY_KEY = "tsb:proxies"
REFRESH_INTERVAL = 3600

SOCKS5_SOURCES = [
    "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=socks5&timeout=5000&country=all&simplified=true",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
]

async def fetch_socks5() -> list:
    proxies = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        for url in SOCKS5_SOURCES:
            try:
                async with session.get(url) as r:
                    if r.status == 200:
                        text = await r.text()
                        for line in text.strip().splitlines():
                            line = line.strip()
                            if ":" in line and not line.startswith("#"):
                                parts = line.split(":")
                                if len(parts) >= 2:
                                    try:
                                        proxies.append({"type": "socks5", "host": parts[0], "port": int(parts[1])})
                                    except ValueError:
                                        pass
            except Exception as e:
                logger.warning(f"Proxy source failed: {e}")
    return proxies

class ProxyFetcher:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def refresh(self):
        proxies = await fetch_socks5()
        if proxies:
            await self.redis.delete(PROXY_KEY)
            pipe = self.redis.pipeline()
            for p in proxies:
                pipe.rpush(PROXY_KEY, json.dumps(p))
            await pipe.execute()
            logger.info(f"Proxy list updated: {len(proxies)}")

    async def get_random(self):
        data = await self.redis.lrange(PROXY_KEY, 0, -1)
        if not data:
            return None
        return json.loads(random.choice(data))

    async def get_all(self) -> list:
        data = await self.redis.lrange(PROXY_KEY, 0, -1)
        return [json.loads(d) for d in data]

    async def count(self) -> int:
        return await self.redis.llen(PROXY_KEY)

    async def run(self):
        while True:
            try:
                await self.refresh()
            except Exception as e:
                logger.error(f"ProxyFetcher error: {e}")
            await asyncio.sleep(REFRESH_INTERVAL)
