"""
Instagram & YouTube section.
Downloader: yt-dlp.
Account Manager: auto-create, manage, follow/like.
Live timeline with instant edit on each step.
"""
import asyncio
import logging
import os
import re
import time

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramRetryAfter

logger   = logging.getLogger("social")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

IG_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv|reels)/([A-Za-z0-9_\-]+)"
)
IG_SHORT_RE = re.compile(r"https?://instagr\.am/p/([A-Za-z0-9_\-]+)")
SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")


# ─── FSM ──────────────────────────────────────────────────────────────────────
class IGState(StatesGroup):
    dl_waiting    = State()
    follow_target = State()
    follow_count  = State()
    like_url      = State()
    like_count    = State()


# ─── Timeline ─────────────────────────────────────────────────────────────────
class TL:
    def __init__(self, msg, title=""):
        self.msg   = msg
        self.t0    = time.monotonic()
        self._si   = 0
        self.steps = []
        self.title = title
        self._lock = asyncio.Lock()
        self._last_edit = 0.0
        self._min_interval = 1.0

    def add(self, icon, text):
        self.steps.append([icon, text, "wait", "", None])
        return len(self.steps) - 1

    async def run(self, i, detail=""):
        for s in self.steps:
            if s[2] == "run": s[2] = "ok"
        self.steps[i][2] = "run"
        self.steps[i][3] = detail
        self.steps[i][4] = time.monotonic()
        await self._edit()

    async def ok(self, i, detail=""):
        self.steps[i][2] = "ok"
        if detail: self.steps[i][3] = detail
        await self._edit()

    async def err(self, i, detail=""):
        self.steps[i][2] = "err"
        if detail: self.steps[i][3] = detail
        await self._edit()

    async def update(self, i, detail):
        self.steps[i][3] = detail
        await self._edit()

    async def done(self, note="", reply_markup=None):
        for s in self.steps:
            if s[2] == "run": s[2] = "ok"
        await self._edit(note=note, reply_markup=reply_markup, force=True)

    def _sp(self):
        self._si = (self._si + 1) % len(SPINNER)
        return SPINNER[self._si]

    def render(self, note=""):
        total = time.monotonic() - self.t0
        lines = [f"{self.title}  ⏱ <b>{total:.1f}s</b>\n"]
        for icon, text, st, detail, ts in self.steps:
            ela = f" <i>({time.monotonic()-ts:.1f}s)</i>" if ts and st == "run" else ""
            if   st == "wait": row = f"○ {icon} {text}"
            elif st == "run":  row = f"{self._sp()} {icon} <b>{text}</b>{ela}"
            elif st == "ok":   row = f"✅ {icon} {text}"
            else:              row = f"❌ {icon} {text}"
            if detail: row += f"\n    └ <i>{detail[:80]}</i>"
            lines.append(row)
        if note: lines.append(f"\n{note}")
        return "\n".join(lines)

    async def _edit(self, note="", reply_markup=None, force=False):
        async with self._lock:
            now = time.monotonic()
            if not force and (now - self._last_edit) < self._min_interval:
                await asyncio.sleep(self._min_interval - (now - self._last_edit))
            try:
                await self.msg.edit_text(
                    self.render(note), parse_mode="HTML", reply_markup=reply_markup)
                self._last_edit = time.monotonic()
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await self.msg.edit_text(
                        self.render(note), parse_mode="HTML", reply_markup=reply_markup)
                    self._last_edit = time.monotonic()
                except Exception: pass
            except Exception: pass


# ─── Menus ────────────────────────────────────────────────────────────────────
def social_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 اینستاگرام", callback_data="social_instagram")],
        [InlineKeyboardButton(text="🎥 یوتیوب",      callback_data="social_youtube")],
        [InlineKeyboardButton(text="🔙 بازگشت",    callback_data="menu_main")],
    ])

def instagram_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ دانلود پست/ریل/IGTV",    callback_data="ig_download")],
        [InlineKeyboardButton(text="🤖 ساخت خودکار اکانت",    callback_data="ig_create_account")],
        [InlineKeyboardButton(text="📊 مدیریت اکانت‌ها",       callback_data="ig_accounts_list")],
        [InlineKeyboardButton(text="👥 فالو خودکار",           callback_data="ig_follow")],
        [InlineKeyboardButton(text="❤️ لایک خودکار",            callback_data="ig_like")],
        [InlineKeyboardButton(text="🔙 بازگشت",                  callback_data="menu_social")],
    ])

def youtube_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚧 بزودی", callback_data="yt_coming_soon")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu_social")],
    ])


# ─── Menu handlers ───────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu_social")
async def menu_social(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "📸 <b>اینستاگرام و یوتیوب</b>",
        reply_markup=social_menu(), parse_mode="HTML")

@router.callback_query(F.data == "social_instagram")
async def menu_instagram(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    from services.ig_account_store import count_accounts
    cnt = count_accounts()
    await cb.message.edit_text(
        f"📸 <b>خدمات اینستاگرام</b>\n📊 اکانت‌ها: <b>{cnt}</b>",
        reply_markup=instagram_menu(), parse_mode="HTML")

@router.callback_query(F.data == "social_youtube")
async def menu_youtube(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "🎥 <b>یوتیوب</b> — بزودی.",
        reply_markup=youtube_menu(), parse_mode="HTML")

@router.callback_query(F.data == "yt_coming_soon")
async def yt_soon(cb: CallbackQuery):
    await cb.answer("🚧 بزودی!", show_alert=True)


# ═══ DOWNLOADER ═════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "ig_download")
async def ig_download_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(IGState.dl_waiting)
    await cb.message.edit_text(
        "⬇️ <b>دانلود اینستاگرام</b>\n\n"
        "لینک پست، ریل یا IGTV بفرستید:\n"
        "<code>https://www.instagram.com/reel/ABC123/</code>\n\n"
        "⚠️ فقط پست‌های عمومی",
        parse_mode="HTML")


@router.message(IGState.dl_waiting)
async def ig_download_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    text = (msg.text or "").strip()
    await state.clear()

    status = await msg.answer("⏳ در حال بررسی...", parse_mode="HTML")
    tl = TL(status, "📸 <b>Instagram Downloader</b>")
    s0 = tl.add("🔗", "دریافت لینک")
    s1 = tl.add("🔍", "استخراج مدیا")
    s2 = tl.add("📥", "دانلود")
    s3 = tl.add("🚀", "ارسال")

    await tl.run(s0, text[:60])
    url = _normalize_url(text)
    if not url:
        await tl.err(s0, "لینک نامعتبر")
        await tl.done(reply_markup=instagram_menu())
        return
    await tl.ok(s0)

    await tl.run(s1, "در حال استخراج...")
    try:
        medias = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, lambda: _ytdlp_extract(url)),
            timeout=45)
        if not medias: raise ValueError("مدیایی پیدا نشد")
        await tl.ok(s1, f"{len(medias)} فایل — {medias[0].get('height',0)}p")
    except Exception as e:
        err_msg = str(e)
        if "not available" in err_msg or "Private" in err_msg:
            err_msg = "پست پریویت یا دسترس ندارد"
        await tl.err(s1, err_msg[:60])
        await tl.done(reply_markup=instagram_menu())
        return

    total = len(medias)
    for i, media in enumerate(medias, 1):
        lbl = f"{i}/{total}"
        await tl.run(s2, f"فایل {lbl}")
        try:
            data, fname = await asyncio.wait_for(_download_ram(media["url"]), timeout=120)
            await tl.ok(s2, f"{len(data)/1024/1024:.1f} MB")
        except Exception as e:
            await tl.err(s2, str(e)[:50]); continue

        await tl.run(s3, f"فایل {lbl}")
        try:
            cap  = f"📸 {lbl}" if total > 1 else "📸 Instagram"
            fobj = BufferedInputFile(data, filename=fname)
            if media["type"] == "video":
                await msg.answer_video(fobj, caption=cap, supports_streaming=True)
            else:
                await msg.answer_photo(fobj, caption=cap)
            await tl.ok(s3, f"فایل {lbl} ارسال شد")
        except Exception as e:
            await tl.err(s3, str(e)[:50])

    await tl.done(f"✅ تمام! {total} فایل.", reply_markup=instagram_menu())


def _ytdlp_extract(url: str) -> list[dict]:
    import yt_dlp
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "http_headers": {"User-Agent": UA},
        # Try without login first - works for public posts
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info: return []
    entries = info.get("entries") or [info]
    results = []
    for e in entries:
        if not e: continue
        fmts = [f for f in (e.get("formats") or [])
                if f.get("vcodec") != "none" and f.get("url")]
        if fmts:
            best = max(fmts, key=lambda f: f.get("height") or 0)
            results.append({"type": "video", "url": best["url"],
                            "height": best.get("height", 0)})
        elif e.get("thumbnail"):
            results.append({"type": "photo", "url": e["thumbnail"], "height": 0})
    return results


async def _download_ram(url: str) -> tuple[bytes, str]:
    import httpx
    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Referer": "https://www.instagram.com/"},
        timeout=120, follow_redirects=True
    ) as c:
        r = await c.get(url)
        r.raise_for_status()
    ct  = r.headers.get("content-type", "")
    ext = "mp4" if "video" in ct else "jpg"
    return r.content, f"ig_media.{ext}"


# ═══ ACCOUNT MANAGER ═══════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "ig_create_account")
async def ig_create_account(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("⛔️", show_alert=True); return
    await cb.answer()

    status = await cb.message.edit_text("⏳ در حال آماده‌سازی...", parse_mode="HTML")
    tl = TL(status, "🤖 <b>ساخت اکانت اینستاگرام</b>")
    s0 = tl.add("📧", "ساخت ایمیل موقت")
    s1 = tl.add("🛍", "خرید شماره مجازی")
    s2 = tl.add("🌐", "انتخاب پروکسی")
    s3 = tl.add("📝", "ثبت‌نام در اینستاگرام")
    s4 = tl.add("📸", "تنظیم پروفایل")
    s5 = tl.add("💾", "ذخیره در سرور")

    try:
        from services.ig_account_creator import create_instagram_account
        result = await create_instagram_account(tl, s0, s1, s2, s3, s4, s5)
    except Exception as e:
        logger.error("[ig_create] %s", e, exc_info=True)
        result = {"ok": False, "error": str(e)}

    note = (
        f"✅ ساخته شد!\n"
        f"👤 <code>{result['account']['username']}</code>\n"
        f"📞 <code>{result['account']['phone']}</code>\n"
        f"📧 <code>{result['account']['email']}</code>"
    ) if result["ok"] else f"❌ {result.get('error','?')[:80]}"

    await tl.done(note, reply_markup=instagram_menu())


@router.callback_query(F.data == "ig_accounts_list")
async def ig_accounts_list(cb: CallbackQuery):
    await cb.answer()
    from services.ig_account_store import load_accounts
    accounts = load_accounts()
    if not accounts:
        await cb.message.edit_text(
            "📊 هیچ اکانتی وجود ندارد.",
            reply_markup=instagram_menu(), parse_mode="HTML"); return
    lines = [f"📊 <b>اکانت‌ها ({len(accounts)})</b>\n"]
    for a in accounts[:30]:
        icon = "✅" if a.get("active") else "🚫"
        lines.append(f"{icon} <code>{a['username']}</code> | 📞 {a.get('phone','?')}")
    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧹 حذف بن‌شده‌ها", callback_data="ig_clean_banned")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="social_instagram")],
        ]),
        parse_mode="HTML")


@router.callback_query(F.data == "ig_clean_banned")
async def ig_clean_banned(cb: CallbackQuery):
    await cb.answer()
    from services.ig_account_store import load_accounts, remove_account
    accounts = load_accounts()
    removed  = sum(1 for a in accounts if not a.get("active"))
    for a in [x for x in accounts if not x.get("active")]:
        remove_account(a["username"])
    await cb.message.edit_text(
        f"✅ {removed} اکانت غیرفعال حذف شد.",
        reply_markup=instagram_menu(), parse_mode="HTML")


@router.callback_query(F.data == "ig_follow")
async def ig_follow_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    from services.ig_account_store import count_accounts
    if count_accounts(active_only=True) == 0:
        await cb.answer("⚠️ هیچ اکانت فعالی ندارید.", show_alert=True); return
    await state.set_state(IGState.follow_target)
    await cb.message.edit_text(
        "👥 <b>فالو خودکار</b>\n\nایدی پیج هدف را بفرستید:",
        parse_mode="HTML")

@router.message(IGState.follow_target)
async def ig_follow_target(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    target = re.sub(r"https?://(?:www\.)?instagram\.com/", "",
                    (msg.text or "").strip().lstrip("@")).strip("/")
    await state.update_data(target=target)
    await state.set_state(IGState.follow_count)
    from services.ig_account_store import count_accounts
    await msg.answer(
        f"👥 هدف: <code>@{target}</code>\nچند فالو بزنیم؟ (1–{count_accounts(active_only=True)})",
        parse_mode="HTML")

@router.message(IGState.follow_count)
async def ig_follow_count(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        count = int((msg.text or "").strip())
        if count < 1: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح."); return
    data = await state.get_data(); await state.clear()
    status = await msg.answer("⏳", parse_mode="HTML")
    tl = TL(status, f"👥 <b>فالو @{data['target']}</b>")
    s0 = tl.add("📊", "انتخاب اکانت‌ها")
    s1 = tl.add("👥", f"فالو با {count} اکانت")
    try:
        from services.ig_actions import follow_target
        result = await follow_target(data["target"], count, tl, s0, s1)
    except Exception:
        result = {"ok": 0, "fail": count}
    await tl.done(f"✅ موفق: {result.get('ok',0)} | ناموفق: {result.get('fail',0)}",
                  reply_markup=instagram_menu())


@router.callback_query(F.data == "ig_like")
async def ig_like_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    from services.ig_account_store import count_accounts
    if count_accounts(active_only=True) == 0:
        await cb.answer("⚠️ هیچ اکانت فعالی ندارید.", show_alert=True); return
    await state.set_state(IGState.like_url)
    await cb.message.edit_text(
        "❤️ <b>لایک خودکار</b>\n\nلینک پست را بفرستید:",
        parse_mode="HTML")

@router.message(IGState.like_url)
async def ig_like_url(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    url = _normalize_url((msg.text or "").strip())
    if not url:
        await msg.answer("❌ لینک نامعتبر."); return
    await state.update_data(like_url=url)
    await state.set_state(IGState.like_count)
    from services.ig_account_store import count_accounts
    await msg.answer(f"چند لایک بزنیم؟ (1–{count_accounts(active_only=True)})")

@router.message(IGState.like_count)
async def ig_like_count(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        count = int((msg.text or "").strip())
        if count < 1: raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح."); return
    data = await state.get_data(); await state.clear()
    status = await msg.answer("⏳", parse_mode="HTML")
    tl = TL(status, "❤️ <b>لایک خودکار</b>")
    s0 = tl.add("📊", "انتخاب اکانت‌ها")
    s1 = tl.add("❤️", f"لایک با {count} اکانت")
    try:
        from services.ig_actions import like_post
        result = await like_post(data["like_url"], count, tl, s0, s1)
    except Exception:
        result = {"ok": 0, "fail": count}
    await tl.done(f"✅ موفق: {result.get('ok',0)} | ناموفق: {result.get('fail',0)}",
                  reply_markup=instagram_menu())


# ─── URL helpers ─────────────────────────────────────────────────────────────────────────────────
def _normalize_url(text: str) -> str | None:
    m = IG_URL_RE.search(text)
    if m: return f"https://www.instagram.com/p/{m.group(1)}/"
    m = IG_SHORT_RE.search(text)
    if m: return f"https://www.instagram.com/p/{m.group(1)}/"
    if "instagram.com/stories/" in text: return text.split("?")[0]
    return None
