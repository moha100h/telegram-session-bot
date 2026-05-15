import asyncio
import aiohttp
import random
import logging
import json
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Optional, List

logger = logging.getLogger("proxy_rotator")


@dataclass
class Proxy:
    host: str
    port: int
    type: str = "socks5"
    username: str = ""
    password: str = ""
    latency_ms: int = 9999
    fail_count: int = 0
    last_checked: float = 0.0
    is_alive: bool = False

    def to_telethon(self) -> dict:
        p = {
            "proxy_type": self.type,
            "addr": self.host,
            "port": self.port,
            "rdns": True
        }
        if self.username:
            p["username"] = self.username
            p["password"] = self.password
        return p


class ProxyRotator:
    def __init__(self, proxy_file="/app/data/proxies.json"):
        self.proxy_file = proxy_file
        self.proxies: List[Proxy] = []
        self.session_proxy_map: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.proxy_file):
            try:
                with open(self.proxy_file) as f:
                    data = json.load(f)
                    self.proxies = [Proxy(**p) for p in data]
            except Exception as e:
                logger.warning(f"Failed to load proxies: {e}")
        logger.info(f"Loaded {len(self.proxies)} proxies")

    def _save(self):
        os.makedirs(os.path.dirname(self.proxy_file), exist_ok=True)
        with open(self.proxy_file, "w") as f:
            json.dump([asdict(p) for p in self.proxies], f, indent=2)

    def add_proxies(self, proxy_list: list) -> int:
        added = 0
        for item in proxy_list:
            proxy = self._parse_proxy(item)
            if proxy and not self._exists(proxy):
                self.proxies.append(proxy)
                added += 1
        self._save()
        logger.info(f"Added {added} new proxies")
        return added

    def _parse_proxy(self, raw: str) -> Optional[Proxy]:
        try:
            raw = raw.strip()
            if not raw:
                return None
            if "://" in raw:
                ptype, rest = raw.split("://", 1)
                if "@" in rest:
                    auth, hostport = rest.rsplit("@", 1)
                    user, passwd = auth.split(":", 1)
                else:
                    hostport = rest
                    user = passwd = ""
                host, port = hostport.rsplit(":", 1)
                return Proxy(host=host, port=int(port), type=ptype,
                             username=user, password=passwd)
            else:
                parts = raw.split(":")
                if len(parts) >= 2:
                    return Proxy(
                        host=parts[0],
                        port=int(parts[1]),
                        type=parts[2] if len(parts) > 2 else "socks5"
                    )
        except Exception:
            pass
        return None

    def _exists(self, proxy: Proxy) -> bool:
        return any(p.host == proxy.host and p.port == proxy.port
                   for p in self.proxies)

    async def test_proxy(self, proxy: Proxy) -> bool:
        try:
            start = time.time()
            proxy_url = f"{proxy.type}://"
            if proxy.username:
                proxy_url += f"{proxy.username}:{proxy.password}@"
            proxy_url += f"{proxy.host}:{proxy.port}"

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.telegram.org",
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status in (200, 404):
                        proxy.latency_ms = int((time.time() - start) * 1000)
                        proxy.is_alive = True
                        proxy.fail_count = 0
                        proxy.last_checked = time.time()
                        return True
        except Exception:
            pass
        proxy.is_alive = False
        proxy.fail_count += 1
        proxy.last_checked = time.time()
        return False

    async def test_all(self, max_concurrent: int = 20) -> int:
        logger.info(f"Testing {len(self.proxies)} proxies...")
        sem = asyncio.Semaphore(max_concurrent)

        async def test_one(proxy):
            async with sem:
                return await self.test_proxy(proxy)

        results = await asyncio.gather(*[test_one(p) for p in self.proxies])
        alive = sum(results)
        self.proxies = [p for p in self.proxies if p.fail_count <= 3]
        self._save()
        logger.info(f"Proxy test done: {alive}/{len(results)} alive")
        return alive

    def get_best_proxy(self, exclude: list = None) -> Optional[Proxy]:
        exclude = exclude or []
        alive = [p for p in self.proxies
                 if p.is_alive and p.host not in exclude]
        if not alive:
            return None
        alive.sort(key=lambda p: p.latency_ms)
        top = alive[:5]
        return random.choice(top)

    def assign_proxy(self, session_name: str) -> Optional[Proxy]:
        if session_name in self.session_proxy_map:
            existing = self.session_proxy_map[session_name]
            if existing.is_alive:
                return existing
        used = [p.host for p in self.session_proxy_map.values()]
        proxy = self.get_best_proxy(exclude=used)
        if proxy:
            self.session_proxy_map[session_name] = proxy
            logger.info(f"Assigned {proxy.host}:{proxy.port} -> {session_name}")
        return proxy

    def rotate_proxy(self, session_name: str) -> Optional[Proxy]:
        old = self.session_proxy_map.get(session_name)
        exclude = [old.host] if old else []
        proxy = self.get_best_proxy(exclude=exclude)
        if proxy:
            self.session_proxy_map[session_name] = proxy
            logger.info(f"Rotated proxy for {session_name} -> {proxy.host}:{proxy.port}")
        return proxy

    def get_stats(self) -> dict:
        alive = [p for p in self.proxies if p.is_alive]
        avg_latency = (sum(p.latency_ms for p in alive) // len(alive)) if alive else 0
        return {
            "total": len(self.proxies),
            "alive": len(alive),
            "dead": len(self.proxies) - len(alive),
            "avg_latency_ms": avg_latency,
            "assigned": len(self.session_proxy_map)
        }
