"""
Instagram actions: follow, like.
All TL calls are async.
"""
import asyncio
import logging
import random

logger = logging.getLogger("ig_actions")

MAX_CONCURRENT = 3
DELAY_MIN      = 4
DELAY_MAX      = 9


async def _get_client(account: dict):
    import os
    from instagrapi import Client
    cl = Client()
    if account.get("proxy"):
        cl.set_proxy(account["proxy"])
    session_path = account.get("session")
    if session_path and os.path.exists(session_path):
        cl.load_settings(session_path)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: cl.login(
        account["username"], account["password"]))
    return cl


async def follow_target(target: str, count: int, tl, s0, s1) -> dict:
    from services.ig_account_store import get_active_accounts, mark_banned
    accounts = get_active_accounts(limit=count)
    await tl.ok(s0, f"{len(accounts)} اکانت")
    await tl.run(s1, f"0/{len(accounts)}")

    ok = 0; fail = 0
    lock = asyncio.Lock()
    sem  = asyncio.Semaphore(MAX_CONCURRENT)

    async def do_follow(acc):
        nonlocal ok, fail
        async with sem:
            try:
                cl   = await _get_client(acc)
                loop = asyncio.get_event_loop()
                uid  = await loop.run_in_executor(None, lambda: cl.user_id_from_username(target))
                await loop.run_in_executor(None, lambda: cl.user_follow(uid))
                async with lock:
                    ok += 1
                    await tl.update(s1, f"{ok}/{len(accounts)} فالو شد")
                await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            except Exception as e:
                if any(x in str(e).lower() for x in ["banned","challenge","disabled"]):
                    mark_banned(acc["username"])
                async with lock:
                    fail += 1
                logger.warning("follow %s via %s: %s", target, acc["username"], e)

    await asyncio.gather(*[do_follow(a) for a in accounts])
    return {"ok": ok, "fail": fail}


async def like_post(url: str, count: int, tl, s0, s1) -> dict:
    import re
    from services.ig_account_store import get_active_accounts, mark_banned
    m = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_\-]+)", url)
    if not m: return {"ok": 0, "fail": count}
    shortcode = m.group(1)

    accounts = get_active_accounts(limit=count)
    await tl.ok(s0, f"{len(accounts)} اکانت")
    await tl.run(s1, f"0/{len(accounts)}")

    ok = 0; fail = 0
    lock = asyncio.Lock()
    sem  = asyncio.Semaphore(MAX_CONCURRENT)

    async def do_like(acc):
        nonlocal ok, fail
        async with sem:
            try:
                cl   = await _get_client(acc)
                loop = asyncio.get_event_loop()
                mid  = await loop.run_in_executor(
                    None, lambda: cl.media_id(cl.media_pk_from_code(shortcode)))
                await loop.run_in_executor(None, lambda: cl.media_like(mid))
                async with lock:
                    ok += 1
                    await tl.update(s1, f"{ok}/{len(accounts)} لایک شد")
                await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            except Exception as e:
                if any(x in str(e).lower() for x in ["banned","challenge","disabled"]):
                    mark_banned(acc["username"])
                async with lock:
                    fail += 1
                logger.warning("like %s via %s: %s", shortcode, acc["username"], e)

    await asyncio.gather(*[do_like(a) for a in accounts])
    return {"ok": ok, "fail": fail}
