import asyncio
import logging
import os
import glob

from telethon import TelegramClient
from session_warmer import SessionWarmer
from proxy_rotator import ProxyRotator

logger = logging.getLogger("warming_scheduler")

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")

proxy_rotator = ProxyRotator()


async def warm_session(session_path: str):
    session_name = os.path.splitext(os.path.basename(session_path))[0]
    proxy = proxy_rotator.assign_proxy(session_name)

    try:
        client = TelegramClient(
            session_path,
            API_ID,
            API_HASH,
            proxy=proxy.to_telethon() if proxy else None
        )
        async with client:
            warmer = SessionWarmer(client, session_name)
            result = await warmer.run_warming_session()
            logger.info(
                f"[{session_name}] Warm done | "
                f"phase={result['phase']} score={result['score']}"
            )
    except Exception as e:
        logger.error(f"[{session_name}] Warm error: {e}")
        # اگه پروکسی مشکل داشت rotate کن
        if proxy and ("proxy" in str(e).lower() or "connect" in str(e).lower()):
            proxy_rotator.rotate_proxy(session_name)


async def warm_all_sessions():
    session_files = glob.glob(f"{SESSIONS_DIR}/*.session")
    logger.info(f"Warming {len(session_files)} sessions...")
    tasks = [warm_session(sf) for sf in session_files]
    # حداکثر ۵ سشن همزمان
    sem = asyncio.Semaphore(5)

    async def limited(coro):
        async with sem:
            await coro

    await asyncio.gather(*[limited(t) for t in tasks])


async def proxy_health_loop():
    """هر ۳۰ دقیقه پروکسی‌ها رو تست کن"""
    while True:
        try:
            alive = await proxy_rotator.test_all()
            logger.info(f"Proxy health check: {alive} alive")
            # سشن‌هایی که پروکسیشون مرده رو rotate کن
            for session_name, proxy in list(proxy_rotator.session_proxy_map.items()):
                if not proxy.is_alive:
                    new_proxy = proxy_rotator.rotate_proxy(session_name)
                    if new_proxy:
                        logger.info(f"Auto-rotated proxy for {session_name}")
        except Exception as e:
            logger.error(f"Proxy health loop error: {e}")
        await asyncio.sleep(30 * 60)


async def warming_loop():
    """هر ۶ ساعت سشن‌ها رو گرم کن"""
    while True:
        try:
            await warm_all_sessions()
        except Exception as e:
            logger.error(f"Warming loop error: {e}")
        await asyncio.sleep(6 * 3600)


async def start_schedulers():
    """شروع همه scheduler ها"""
    logger.info("Starting warming & proxy schedulers...")
    await asyncio.gather(
        warming_loop(),
        proxy_health_loop()
    )
