"""
Instagram account auto-creator.
Uses: HeroSMS (phone) + TempMail (email) + instagrapi + proxy.
"""
import asyncio
import logging
import os
import random
import string
import time

import httpx

logger = logging.getLogger("ig_creator")

DATA_DIR    = os.getenv("DATA_DIR", "/app/data")
SESSIONS_IG = os.path.join(DATA_DIR, "ig_sessions")

FIRST_NAMES = [
    "Alex","Sam","Jordan","Taylor","Morgan","Casey","Riley","Jamie",
    "Avery","Quinn","Blake","Drew","Skyler","Reese","Finley","Rowan",
    "Emery","Sage","River","Phoenix","Hayden","Dakota","Peyton","Kendall",
]
LAST_NAMES = [
    "Smith","Johnson","Brown","Davis","Wilson","Moore","Taylor",
    "Anderson","Thomas","Jackson","White","Harris","Martin","Garcia",
]
BIOS = [
    "🌟 Just living life",
    "📸 Photography lover",
    "☕ Coffee & vibes",
    "🌍 Exploring the world",
    "🎨 Creative soul",
    "📚 Book lover",
    "🎵 Music is life",
    "🏋️ Fitness enthusiast",
]


def _rand_username(first: str, last: str) -> str:
    suffix = random.randint(100, 9999)
    base   = f"{first.lower()}{last.lower()}{suffix}"
    return base[:30]


def _rand_password() -> str:
    chars = string.ascii_letters + string.digits + "!@#$"
    return "".join(random.choices(chars, k=14))


async def _get_temp_email() -> tuple[str, str]:
    """
    Get a temporary email address.
    Returns (email, token_for_reading)
    """
    async with httpx.AsyncClient(timeout=10) as c:
        # Use guerrillamail
        r = await c.get("https://api.guerrillamail.com/ajax.php",
                        params={"f": "get_email_address"})
        data = r.json()
        email = data["email_addr"]
        token = data["sid_token"]
        return email, token


async def _wait_email_code(token: str, timeout: int = 120) -> str | None:
    """
    Poll guerrillamail for verification code.
    """
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(timeout=10) as c:
        while time.monotonic() < deadline:
            await asyncio.sleep(5)
            try:
                r = await c.get("https://api.guerrillamail.com/ajax.php",
                                params={"f": "get_email_list", "offset": 0,
                                        "sid_token": token})
                emails = r.json().get("list", [])
                for em in emails:
                    if "instagram" in em.get("mail_from", "").lower() or \
                       "instagram" in em.get("mail_subject", "").lower():
                        # get full email
                        r2 = await c.get("https://api.guerrillamail.com/ajax.php",
                                         params={"f": "fetch_email",
                                                 "email_id": em["mail_id"],
                                                 "sid_token": token})
                        body = r2.json().get("mail_body", "")
                        import re
                        code = re.search(r"\b(\d{6})\b", body)
                        if code:
                            return code.group(1)
            except Exception as e:
                logger.warning("email poll: %s", e)
    return None


async def _get_proxy_for_ig() -> dict | None:
    """
    Get a working proxy from Redis proxy pool.
    """
    try:
        from redis.asyncio import Redis
        redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        proxies = await redis.lrange("proxies", 0, -1)
        await redis.aclose()
        if proxies:
            raw = random.choice(proxies).decode()
            # format: socks5://host:port or host:port:user:pass
            parts = raw.split(":")
            if len(parts) >= 2:
                return {"http://": f"socks5://{parts[0]}:{parts[1]}",
                        "https://": f"socks5://{parts[0]}:{parts[1]}"}
    except Exception as e:
        logger.warning("proxy fetch: %s", e)
    return None


async def create_instagram_account(tl, s0, s1, s2, s3, s4, s5) -> dict:
    """
    Full account creation flow:
    1. Temp email
    2. Buy phone (HeroSMS)
    3. Pick proxy
    4. Register on Instagram
    5. Set profile
    6. Save
    """
    os.makedirs(SESSIONS_IG, exist_ok=True)

    first = random.choice(FIRST_NAMES)
    last  = random.choice(LAST_NAMES)
    uname = _rand_username(first, last)
    pwd   = _rand_password()
    bday  = f"{random.randint(1990,2000)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"

    # Step 0: temp email
    tl.run(s0, "در حال ساخت...")
    try:
        email, email_token = await _get_temp_email()
        tl.ok(s0, email[:30])
    except Exception as e:
        tl.err(s0, str(e)[:50])
        return {"ok": False, "error": f"email: {e}"}

    # Step 1: buy phone
    tl.run(s1, "خرید شماره...")
    try:
        from services.herosms import get_number_smart, get_sms_code, confirm_number, cancel_number
        activation_id, phone, country_id, price = await get_number_smart("ig")
        phone_fmt = "+" + phone if not phone.startswith("+") else phone
        tl.ok(s1, phone_fmt)
    except Exception as e:
        tl.err(s1, str(e)[:50])
        return {"ok": False, "error": f"phone: {e}"}

    # Step 2: proxy
    tl.run(s2, "انتخاب پروکسی...")
    proxy = await _get_proxy_for_ig()
    tl.ok(s2, "پروکسی انتخاب شد" if proxy else "بدون پروکسی")

    # Step 3: register
    tl.run(s3, f"@{uname}")
    try:
        from instagrapi import Client
        cl = Client()
        if proxy:
            cl.set_proxy(list(proxy.values())[0])

        # Set device
        cl.set_device({
            "app_version": "269.0.0.18.75",
            "android_version": 26,
            "android_release": "8.0.0",
            "dpi": "480dpi",
            "resolution": "1080x1920",
            "manufacturer": "OnePlus",
            "device": "ONEPLUS A3003",
            "model": "OnePlus3",
            "cpu": "qcom",
            "version_code": "314665256",
        })
        cl.set_user_agent()

        # Register
        loop = asyncio.get_event_loop()
        registered = await loop.run_in_executor(
            None,
            lambda: cl.register_with_email(
                username=uname,
                password=pwd,
                email=email,
                first_name=first,
                birthday=bday,
            )
        )
        if not registered:
            raise RuntimeError("ثبت‌نام ناموفق")
        tl.ok(s3, f"@{uname} ساخته شد")
    except Exception as e:
        tl.err(s3, str(e)[:60])
        try: await cancel_number(activation_id)
        except Exception: pass
        return {"ok": False, "error": f"register: {e}"}

    # Wait for email verification if needed
    # (instagrapi handles this internally in most cases)

    # Step 4: set profile
    tl.run(s4, "تنظیم بیو و عکس...")
    try:
        bio = random.choice(BIOS)
        loop = asyncio.get_event_loop()

        # Set bio
        await loop.run_in_executor(None, lambda: cl.account_edit(
            biography=bio,
            full_name=f"{first} {last}",
        ))

        # Set random profile photo from UI Faces
        try:
            async with httpx.AsyncClient(timeout=10) as hc:
                r = await hc.get(
                    "https://randomuser.me/api/?inc=picture",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                pic_url = r.json()["results"][0]["picture"]["large"]
                pic_r   = await hc.get(pic_url)
                pic_data = pic_r.content

            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(pic_data)
                tmp_path = f.name

            await loop.run_in_executor(None, lambda: cl.account_change_picture(tmp_path))
            os.unlink(tmp_path)
        except Exception as pe:
            logger.warning("profile pic: %s", pe)

        tl.ok(s4, f"{first} {last} | {bio[:20]}")
    except Exception as e:
        tl.err(s4, str(e)[:50])
        # non-fatal

    # Step 5: save
    tl.run(s5, "ذخیره...")
    try:
        session_path = os.path.join(SESSIONS_IG, f"{uname}.json")
        cl.dump_settings(session_path)

        from services.ig_account_store import save_account
        account = {
            "username":  uname,
            "password":  pwd,
            "email":     email,
            "phone":     phone_fmt,
            "full_name": f"{first} {last}",
            "bio":       bio,
            "active":    True,
            "banned":    False,
            "followers": 0,
            "posts":     0,
            "session":   session_path,
            "proxy":     list(proxy.values())[0] if proxy else None,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_account(account)
        await confirm_number(activation_id)
        tl.ok(s5, "ذخیره شد")
        return {"ok": True, "account": account}
    except Exception as e:
        tl.err(s5, str(e)[:50])
        return {"ok": False, "error": f"save: {e}"}


async def check_account_status(account: dict) -> bool:
    """
    Check if account is still active (not banned).
    Returns True if active, False if banned/invalid.
    """
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
        return True  # network error - keep
