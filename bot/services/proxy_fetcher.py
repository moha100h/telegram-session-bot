import asyncio
import logging
import json
import aiohttp
from redis.asyncio import Redis

logger = logging.getLogger("proxy_fetcher")

PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
]
PROXY_KEY      = "tsb:proxies"
FETCH_INTERVAL = 3600


class ProxyFetcher:
    def __init__(self, redis: Redis):
        self.redis = redis

    async def fetch(self):
        proxies = []
        async with aiohttp.ClientSession() as session:
            for url in PROXY_SOURCES:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                        text = await r.text()
                        for line in text.strip().splitlines():
                            line = line.strip()
                            if ":" in line:
                                host, port = line.split(":", 1)
                                proxies.append(json.dumps({"type": "socks5", "host": host, "port": port}))
                except Exception as e:
                    logger.warning(f"Proxy fetch error {url}: {e}")
        if proxies:
            await self.redis.delete(PROXY_KEY)
            await self.redis.rpush(PROXY_KEY, *proxies)
            logger.info(f"Fetched {len(proxies)} proxies")

    async def run(self):
        while True:
            await self.fetch()
            await asyncio.sleep(FETCH_INTERVAL)
