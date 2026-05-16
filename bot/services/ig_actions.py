"""
Instagram actions: follow, like, unfollow.
Uses saved sessions from ig_account_store.
Each account uses its own proxy.
"""
import asyncio
import logging
import os
import random
import time
from typing import Optional

logger = logging.getLogger("ig_actions")


def _get_client(account: dict):
    """Build instagrapi Client from saved session."""
    from instagrapi import Client
    cl = Client()
    if account.get("proxy"):
        cl.set_proxy(account["proxy"])
    if account.get("session_json"):
        cl.set_settings(account["session_json"])
    return cl


async def follow_target(target_username: str, count: int,
                         on_progress=None) -> dict:
    """
    Follow target_username using `count` active accounts.
    Each account uses its own proxy.
    Returns {success, failed, results}
    """
    from services.ig_account_store import list_active, mark_banned
    loop    = asyncio.get_event_loop()
    active  = list_active()
    if not active:
        raise RuntimeError("هیچ اکانت فعالی وجود ندارد")

    workers = active[:count]
    results = []
    success = 0
    failed  = 0
    lock    = asyncio.Lock()
    sem     = asyncio.Semaphore(5)  # max 5 parallel

    async def _follow_one(acc: dict):
        nonlocal success, failed
        uname = acc["username"]
        async with sem:
            # human-like delay
            await asyncio.sleep(random.uniform(1, 4))
            try:
                def _do():
                    cl = _get_client(acc)
                    user_id = cl.user_id_from_username(target_username)
                    cl.user_follow(user_id)
                    return True
                await asyncio.wait_for(
                    loop.run_in_executor(None, _do), timeout=30)
                async with lock:
                    success += 1
                    results.append(f"✅ @{uname}")
                if on_progress:
                    await on_progress(success + failed, len(workers),
                                      success, failed)
            except Exception as e:
                err = str(e).lower()
                async with lock:
                    failed += 1
                    results.append(f"❌ @{uname}: {str(e)[:40]}")
                if "banned" in err or "challenge" in err or "block" in err:
                    await mark_banned(uname)
                if on_progress:
                    await on_progress(success + failed, len(workers),
                                      success, failed)

    await asyncio.gather(*[_follow_one(acc) for acc in workers])
    return {"success": success, "failed": failed, "results": results}


async def like_post(post_url: str, count: int,
                    on_progress=None) -> dict:
    """
    Like a post using `count` active accounts.
    """
    from services.ig_account_store import list_active, mark_banned
    loop   = asyncio.get_event_loop()
    active = list_active()
    if not active:
        raise RuntimeError("هیچ اکانت فعالی وجود ندارد")

    workers = active[:count]
    results = []
    success = 0
    failed  = 0
    lock    = asyncio.Lock()
    sem     = asyncio.Semaphore(5)

    # extract shortcode
    import re
    m = re.search(r"/p/([A-Za-z0-9_\-]+)", post_url)
    shortcode = m.group(1) if m else post_url

    async def _like_one(acc: dict):
        nonlocal success, failed
        uname = acc["username"]
        async with sem:
            await asyncio.sleep(random.uniform(1, 4))
            try:
                def _do():
                    cl = _get_client(acc)
                    media_id = cl.media_id(cl.media_pk_from_code(shortcode))
                    cl.media_like(media_id)
                    return True
                await asyncio.wait_for(
                    loop.run_in_executor(None, _do), timeout=30)
                async with lock:
                    success += 1
                    results.append(f"✅ @{uname}")
                if on_progress:
                    await on_progress(success + failed, len(workers),
                                      success, failed)
            except Exception as e:
                err = str(e).lower()
                async with lock:
                    failed += 1
                    results.append(f"❌ @{uname}: {str(e)[:40]}")
                if "banned" in err or "challenge" in err:
                    await mark_banned(uname)
                if on_progress:
                    await on_progress(success + failed, len(workers),
                                      success, failed)

    await asyncio.gather(*[_like_one(acc) for acc in workers])
    return {"success": success, "failed": failed, "results": results}


async def check_all_accounts() -> dict:
    """
    Check all accounts, mark banned ones.
    Returns {active, banned, checked}
    """
    from services.ig_account_store import list_all, mark_banned, update_field
    loop    = asyncio.get_event_loop()
    all_acc = list_all()
    active  = 0
    banned  = 0
    sem     = asyncio.Semaphore(5)
    lock    = asyncio.Lock()

    async def _check(acc: dict):
        nonlocal active, banned
        uname = acc["username"]
        async with sem:
            try:
                def _do():
                    cl = _get_client(acc)
                    cl.get_timeline_feed()
                    return True
                await asyncio.wait_for(
                    loop.run_in_executor(None, _do), timeout=20)
                async with lock:
                    active += 1
                    await update_field(uname, status="active")
            except Exception as e:
                err = str(e).lower()
                async with lock:
                    if "banned" in err or "challenge" in err or "login" in err:
                        banned += 1
                        await mark_banned(uname)
                    else:
                        active += 1  # temp error, keep active

    await asyncio.gather(*[_check(acc) for acc in all_acc])
    return {"checked": len(all_acc), "active": active, "banned": banned}
