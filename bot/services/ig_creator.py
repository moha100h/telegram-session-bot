"""
Instagram account creator.
Flow:
  1. Get temp email via mail.tm
  2. Get phone via HeroSMS
  3. Register via Instagram private API
  4. Verify phone/email
  5. Set profile (name, bio, avatar)
  6. Save to ig_account_store

Uses instagrapi + rotating proxies.
"""
import asyncio
import logging
import os
import random
import string
import time
from typing import Optional

import httpx

from services.ig_account_store import save as store_save
from services.herosms import get_number_smart, get_sms_code, cancel_number, confirm_number, HeroSMSError

logger   = logging.getLogger("ig_creator")
API_ID   = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# ─── Random profile data ──────────────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Emma","Liam","Olivia","Noah","Ava","Ethan","Sophia","Mason",
    "Isabella","William","Mia","James","Charlotte","Oliver","Amelia",
    "Benjamin","Harper","Elijah","Evelyn","Lucas","Abigail","Henry",
    "Emily","Alexander","Elizabeth","Michael","Sofia","Daniel","Avery",
    "Logan","Ella","Jackson","Scarlett","Sebastian","Grace","Jack",
]
LAST_NAMES = [
    "Smith","Johnson","Williams","Brown","Jones","Garcia","Miller",
    "Davis","Wilson","Taylor","Anderson","Thomas","Jackson","White",
    "Harris","Martin","Thompson","Moore","Young","Allen","King",
    "Wright","Scott","Green","Baker","Adams","Nelson","Carter",
]
BIOS = [
    "🌟 Living my best life",
    "✨ Just vibing",
    "📸 Photography lover",
    "🌿 Nature & travel",
    "🎨 Creative soul",
    "📚 Book lover | Coffee addict",
    "🎵 Music is life",
    "🚀 Dream big, work hard",
    "🌍 Explorer | Dreamer",
    "☕ Coffee first, everything else later",
]
AVATAR_URLS = [
    "https://randomuser.me/api/portraits/women/{}.jpg",
    "https://randomuser.me/api/portraits/men/{}.jpg",
]


def _random_name() -> tuple[str, str]:
    return random.choice(FIRST_NAMES), random.choice(LAST_NAMES)


def _random_username(first: str, last: str) -> str:
    suffix = random.randint(100, 9999)
    styles = [
        f"{first.lower()}{last.lower()}{suffix}",
        f"{first.lower()}_{last.lower()}",
        f"{first.lower()}{suffix}",
        f"{last.lower()}{first.lower()[0]}{suffix}",
        f"{first.lower()}.{last.lower()}{random.randint(10,99)}",
    ]
    return random.choice(styles)


def _random_password() -> str:
    chars = string.ascii_letters + string.digits + "!@#$"
    return ''.join(random.choices(chars, k=14))


async def _get_avatar(gender: str = "women") -> Optional[bytes]:
    """Download random avatar from randomuser.me"""
    n = random.randint(1, 99)
    url = f"https://randomuser.me/api/portraits/{gender}/{n}.jpg"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url)
            if r.status_code == 200:
                return r.content
    except Exception as e:
        logger.warning("avatar download: %s", e)
    return None


# ─── mail.tm temp email ──────────────────────────────────────────────────────────────────

class TempEmail:
    def __init__(self, address: str, password: str, token: str):
        self.address  = address
        self.password = password
        self.token    = token

    async def wait_for_message(self, timeout: int = 120) -> Optional[str]:
        """Poll inbox until a message arrives. Returns full text body."""
        headers = {"Authorization": f"Bearer {self.token}"}
        deadline = time.monotonic() + timeout
        async with httpx.AsyncClient(timeout=10) as c:
            while time.monotonic() < deadline:
                try:
                    r = await c.get("https://api.mail.tm/messages",
                                    headers=headers)
                    msgs = r.json().get("hydra:member", [])
                    if msgs:
                        msg_id = msgs[0]["id"]
                        r2 = await c.get(f"https://api.mail.tm/messages/{msg_id}",
                                         headers=headers)
                        return r2.json().get("text", "") or r2.json().get("html", "")
                except Exception:
                    pass
                await asyncio.sleep(5)
        return None


async def create_temp_email() -> Optional[TempEmail]:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get("https://api.mail.tm/domains")
            domain = r.json()["hydra:member"][0]["domain"]
            user   = ''.join(random.choices(string.ascii_lowercase, k=10))
            pwd    = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            addr   = f"{user}@{domain}"
            r2 = await c.post("https://api.mail.tm/accounts",
                              json={"address": addr, "password": pwd},
                              headers={"Content-Type": "application/json"})
            if r2.status_code != 201:
                return None
            r3 = await c.post("https://api.mail.tm/token",
                              json={"address": addr, "password": pwd},
                              headers={"Content-Type": "application/json"})
            token = r3.json().get("token", "")
            if not token:
                return None
            return TempEmail(addr, pwd, token)
    except Exception as e:
        logger.error("create_temp_email: %s", e)
        return None


# ─── Instagram registration via instagrapi ──────────────────────────────────────────────────────────────────

async def create_ig_account(proxy: Optional[str] = None,
                             on_step=None) -> dict:
    """
    Full Instagram account creation flow.
    on_step(step_name, detail) called for live progress.
    Returns account dict or raises exception.
    """
    loop = asyncio.get_event_loop()

    async def step(name, detail=""):
        if on_step:
            await on_step(name, detail)

    # 1. Generate profile
    await step("profile", "در حال ساخت پروفایل تصادفی...")
    first, last = _random_name()
    username    = _random_username(first, last)
    password    = _random_password()
    full_name   = f"{first} {last}"
    bio         = random.choice(BIOS)
    gender      = random.choice(["women", "men"])
    dob_year    = random.randint(1990, 2000)
    dob_month   = random.randint(1, 12)
    dob_day     = random.randint(1, 28)

    await step("profile", f"{full_name} / @{username}")

    # 2. Temp email
    await step("email", "در حال ساخت ایمیل موقت...")
    email_obj = await create_temp_email()
    if not email_obj:
        raise RuntimeError("ساخت ایمیل موقت شکست خورد")
    await step("email", email_obj.address)

    # 3. Phone number
    await step("phone", "در حال خرید شماره...")
    try:
        activation_id, phone, country_id, price = await get_number_smart("ig")
    except HeroSMSError:
        # fallback to any service
        activation_id, phone, country_id, price = await get_number_smart("tg")
    phone_fmt = "+" + phone if not phone.startswith("+") else phone
    await step("phone", phone_fmt)

    # 4. Register
    await step("register", f"در حال ثبت‌نام — @{username}")

    def _register():
        from instagrapi import Client
        cl = Client()
        if proxy:
            cl.set_proxy(proxy)
        cl.set_locale("en_US")
        cl.set_timezone_offset(0)
        # Randomize device
        cl.set_device({
            "app_version":        "269.0.0.18.75",
            "android_version":    26,
            "android_release":    "8.0.0",
            "dpi":                "480dpi",
            "resolution":         "1080x1920",
            "manufacturer":       random.choice(["Samsung","Xiaomi","OnePlus","Huawei"]),
            "device":             random.choice(["SM-G973F","Redmi Note 8","OnePlus 7"]),
            "model":              random.choice(["beyond1","ginkgo","guacamoleb"]),
            "cpu":                "qcom",
            "version_code":       "314665256",
        })
        result = cl.register(
            username=username,
            password=password,
            email=email_obj.address,
            phone_number=phone_fmt,
            full_name=full_name,
            year=dob_year,
            month=dob_month,
            day=dob_day,
        )
        return cl, result

    try:
        cl, reg_result = await loop.run_in_executor(None, _register)
    except Exception as e:
        await cancel_number(activation_id)
        raise RuntimeError(f"ثبت‌نام شکست: {str(e)[:80]}")

    await step("register", f"✅ @{username} ساخته شد")

    # 5. Phone verification
    await step("verify_phone", "منتظر کد SMS...")
    code = await get_sms_code(activation_id, timeout=90)
    if code:
        await step("verify_phone", f"کد: {code}")
        try:
            def _verify_phone():
                cl.verify_phone(phone_fmt, code)
            await loop.run_in_executor(None, _verify_phone)
            await confirm_number(activation_id)
            await step("verify_phone", "✅ تأیید شد")
        except Exception as e:
            logger.warning("phone verify: %s", e)
            await step("verify_phone", f"⚠️ {str(e)[:40]}")
    else:
        await cancel_number(activation_id)
        await step("verify_phone", "⚠️ SMS نرسید")

    # 6. Set profile
    await step("profile_set", "در حال تنظیم پروفایل...")
    try:
        def _set_profile():
            cl.account_edit(biography=bio)
        await loop.run_in_executor(None, _set_profile)
        await step("profile_set", "✅ بیو تنظیم شد")
    except Exception as e:
        logger.warning("set bio: %s", e)

    # 7. Upload avatar
    await step("avatar", "در حال دانلود عکس پروفایل...")
    avatar_data = await _get_avatar(gender)
    if avatar_data:
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
                f.write(avatar_data)
                tmp_path = f.name
            def _upload_avatar():
                cl.account_change_picture(tmp_path)
                os.unlink(tmp_path)
            await loop.run_in_executor(None, _upload_avatar)
            await step("avatar", "✅ عکس پروفایل آپلود شد")
        except Exception as e:
            logger.warning("avatar upload: %s", e)
            await step("avatar", f"⚠️ {str(e)[:40]}")
    else:
        await step("avatar", "⚠️ دانلود شکست")

    # 8. Get session info
    def _get_info():
        return cl.account_info()
    try:
        info = await loop.run_in_executor(None, _get_info)
        user_id = info.pk
    except Exception:
        user_id = ""

    # 9. Save
    account = {
        "username":      username,
        "password":      password,
        "email":         email_obj.address,
        "email_pass":    email_obj.password,
        "phone":         phone_fmt,
        "full_name":     full_name,
        "bio":           bio,
        "user_id":       str(user_id),
        "proxy":         proxy or "",
        "status":        "active",
        "created_at":    int(time.time()),
        "session_json":  cl.get_settings(),
    }
    await store_save(username, account)
    await step("done", f"✅ @{username} ذخیره شد")
    return account
