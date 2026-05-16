"""
Instagram account auto-creator.
All TL calls are async (await tl.run / tl.ok / tl.err).
"""
import asyncio
import logging
import os
import random
import re
import string
import time

import httpx

logger = logging.getLogger("ig_creator")

DATA_DIR    = os.getenv("DATA_DIR", "/app/data")
SESSIONS_IG = os.path.join(DATA_DIR, "ig_sessions")

FIRST_NAMES = [
    "Alex","Sam","Jordan","Taylor","Morgan","Casey","Riley","Jamie",
    "Avery","Quinn","Blake","Drew","Skyler","Reese","Finley","Rowan",
]
LAST_NAMES = [
    "Smith","Johnson","Brown","Davis","Wilson","Moore","Taylor",
    "Anderson","Thomas","Jackson","White","Harris",
]
BIOS = [
    "🌟 Just living life",
    "📸 Photography lover",
    "☕ Coffee & vibes",
    "🌍 Exploring the world",
    "🎨 Creative soul",
    "📚 Book lover",
]


def _rand_username(first: str, last: str) -> str:
    return f"{first.lower()}{last.lower()}{random.randint(100,9999)}"[:30]

def _rand_password() -> str:
    chars = string.ascii_letters + string.digits + "!@#$"
    return "".join(random.choices(chars, k=14))


async def _get_temp_email() -> tuple[str, str]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get("https://api.guerrillamail.com/ajax.php",
                        params={"f": "get_email_address"})
        data = r.json()
        return data["email_addr"], data["sid_token"]


async def _get_proxy_for_ig() -> dict | None:
    try:
        from redis.asyncio import Redis
        redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        proxies = await redis.lrange("proxies", 0, -1)
        await redis.aclose()
        if proxies:
            raw = random.choice(proxies).decode()
            parts = raw.split(":")
            if len(parts) >= 2:
                return {"http://": f"socks5://{parts[0]}:{parts[1]}",
                        "https://": f"socks5://{parts[0]}:{parts[1]}"}
    except Exception as e:
        logger.warning("proxy fetch: %s", e)
    return None


async def create_instagram_account(tl, s0, s1, s2, s3, s4, s5) -> dict:
    os.makedirs(SESSIONS_IG, exist_ok=True)

    first = random.choice(FIRST_NAMES)
    last  = random.choice(LAST_NAMES)
    uname = _rand_username(first, last)
    pwd   = _rand_password()
    bday  = f"{random.randint(1990,2000)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

    # Step 0: temp email
    await tl.run(s0, "در حال ساخت...")
    try:
        email, email_token = await _get_temp_email()
        await tl.ok(s0, email[:30])
    except Exception as e:
        await tl.err(s0, str(e)[:50])
        return {"ok": False, "error": f"email: {e}"}

    # Step 1: phone (skip if no HeroSMS configured)
    await tl.run(s1, "در حال دریافت...")
    phone_fmt = "+10000000000"  # placeholder
    activation_id = None
    try:
        from services.herosms import get_number_smart, confirm_number
        activation_id, phone, country_id, price = await get_number_smart("ig")
        phone_fmt = "+" + phone if not phone.startswith("+") else phone
        await tl.ok(s1, phone_fmt)
    except Exception as e:
        await tl.err(s1, f"نیاز به HeroSMS API: {str(e)[:40]}")
        return {"ok": False, "error": f"phone: {e}"}

    # Step 2: proxy
    await tl.run(s2, "انتخاب...")
    proxy = await _get_proxy_for_ig()
    await tl.ok(s2, "پروکسی انتخاب شد" if proxy else "بدون پروکسی")

    # Step 3: register
    await tl.run(s3, f"@{uname}")
    try:
        from instagrapi import Client
        cl = Client()
        if proxy:
            cl.set_proxy(list(proxy.values())[0])
        loop = asyncio.get_event_loop()
        registered = await loop.run_in_executor(
            None,
            lambda: cl.register_with_email(
                username=uname, password=pwd,
                email=email, first_name=first, birthday=bday,
            )
        )
        if not registered:
            raise RuntimeError("ثبت‌نام ناموفق")
        await tl.ok(s3, f"@{uname} ساخته شد")
    except Exception as e:
        await tl.err(s3, str(e)[:60])
        return {"ok": False, "error": f"register: {e}"}

    # Step 4: profile
    await tl.run(s4, "تنظیم...")
    bio = random.choice(BIOS)
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: cl.account_edit(
            biography=bio, full_name=f"{first} {last}"))
        await tl.ok(s4, f"{first} {last}")
    except Exception as e:
        await tl.err(s4, str(e)[:50])

    # Step 5: save
    await tl.run(s5, "ذخیره...")
    try:
        session_path = os.path.join(SESSIONS_IG, f"{uname}.json")
        cl.dump_settings(session_path)
        from services.ig_account_store import save_account
        account = {
            "username":   uname,
            "password":   pwd,
            "email":      email,
            "phone":      phone_fmt,
            "full_name":  f"{first} {last}",
            "bio":        bio,
            "active":     True,
            "banned":     False,
            "followers":  0,
            "posts":      0,
            "session":    session_path,
            "proxy":      list(proxy.values())[0] if proxy else None,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_account(account)
        if activation_id:
            try:
                from services.herosms import confirm_number
                await confirm_number(activation_id)
            except Exception: pass
        await tl.ok(s5, "ذخیره شد")
        return {"ok": True, "account": account}
    except Exception as e:
        await tl.err(s5, str(e)[:50])
        return {"ok": False, "error": f"save: {e}"}


async def check_account_status(account: dict) -> bool:
    try:
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
        return True
    except Exception as e:
        err = str(e).lower()
        if any(x in err for x in ["banned", "challenge", "disabled", "invalid"]):
            return False
        return True
