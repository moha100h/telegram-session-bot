"""
Instagram & YouTube section menu.
Downloader + Account Manager.
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

logger   = logging.getLogger("social")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

IG_URL_RE   = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv|reels)/([A-Za-z0-9_\-]+)"
)
IG_SHORT_RE = re.compile(r"https?://instagr\.am/p/([A-Za-z0-9_\-]+)")
SPINNER     = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]


class IGState(StatesGroup):
    waiting = State()


# ─── Menus ──────────────────────────────────────────────────────────────────

def social_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 خدمات اینستاگرام", callback_data="social_instagram")],
        [InlineKeyboardButton(text="🎥 خدمات یوتیوب",     callback_data="social_youtube")],
        [InlineKeyboardButton(text="🔙 بازگشت",             callback_data="menu_main")],
    ])


def instagram_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ دانلود پست / ریل",    callback_data="ig_download")],
        [InlineKeyboardButton(text="🤖 مدیریت اکانت‌ها",    callback_data="igm_menu")],
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
    await cb.message.edit_text(
        "📸 <b>خدمات اینستاگرام</b>\n"
        "• دانلود پست و ریل\n"
        "• ساخت و مدیریت اکانت\n"
        "• فالو و لایک خودکار",
        reply_markup=instagram_menu(), parse_mode="HTML")


@router.callback_query(F.data == "social_youtube")
async def menu_youtube(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "🎥 <b>یوتیوب</b> — بزودی اضافه می‌شود.",
        reply_markup=youtube_menu(), parse_mode="HTML")


@router.callback_query(F.data == "yt_coming_soon")
async def yt_soon(cb: CallbackQuery):
    await cb.answer("🚧 بزودی!", show_alert=True)


# ─── Instagram downloader ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "ig_download")
async def ig_download_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(IGState.waiting)
    await cb.message.edit_text(
        "⬇️ <b>دانلود اینستاگرام</b>\n\n"
        "لینک پست، ریل یا IGTV بفرستید:\n"
        "<code>https://www.instagram.com/reel/ABC123/</code>",
        parse_mode="HTML")


@router.message(IGState.waiting)
async def ig_download_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    text = (msg.text or "").strip()
    await state.clear()

    tl = TL()
    s0 = tl.add("🔗", "دریافت لینک")
    s1 = tl.add("🔍", "استخراج مدیا")
    s2 = tl.add("📥", "دانلود به RAM")
    s3 = tl.add("🚀", "ارسال به تلگرام")

    tl.run(s0, text[:50])
    url = _normalize_url(text)
    if not url:
        tl.err(s0, "لینک نامعتبر")
        await msg.answer(tl.render(), parse_mode="HTML", reply_markup=instagram_menu())
        return
    if "/stories/" in url:
        tl.err(s0, "استوری پشتیبانی نمی‌شود")
        await msg.answer(tl.render(), parse_mode="HTML", reply_markup=instagram_menu())
        return
    tl.ok(s0, url)

    status   = await msg.answer(tl.render(), parse_mode="HTML")
    stop_evt = asyncio.Event()

    async def _live():
        while not stop_evt.is_set():
            try: await status.edit_text(tl.render(), parse_mode="HTML")
            except Exception: pass
            await asyncio.sleep(2)
    live = asyncio.create_task(_live())

    try:
        tl.run(s1, "تلاش با چند API...")
        try:
            medias = await asyncio.wait_for(_extract(url, tl, s1), timeout=40)
        except asyncio.TimeoutError:
            tl.err(s1, "تایماوت")
            stop_evt.set()
            await status.edit_text(tl.render("❌ تایماوت."),
                                   parse_mode="HTML", reply_markup=instagram_menu())
            return
        except Exception as e:
            tl.err(s1, str(e)[:60])
            stop_evt.set()
            await status.edit_text(tl.render(), parse_mode="HTML", reply_markup=instagram_menu())
            return

        if not medias:
            tl.err(s1, "مدیایی پیدا نشد")
            stop_evt.set()
            await status.edit_text(tl.render("⚠️ پست خصوصی یا لینک نامعتبر."),
                                   parse_mode="HTML", reply_markup=instagram_menu())
            return

        total = len(medias)
        tl.ok(s1, f"{total} فایل")

        for i, media in enumerate(medias, 1):
            lbl = f"{i}/{total}"
            tl.run(s2, f"فایل {lbl}")
            try:
                data, fname = await asyncio.wait_for(_download_ram(media["url"]), timeout=90)
                tl.ok(s2, f"{len(data)/1024/1024:.1f} MB")
            except Exception as e:
                tl.err(s2, str(e)[:50]); continue

            tl.run(s3, f"فایل {lbl}")
            try:
                cap  = f"📸 {lbl}" if total > 1 else "📸 Instagram"
                fobj = BufferedInputFile(data, filename=fname)
                if media["type"] == "video":
                    await msg.answer_video(fobj, caption=cap, supports_streaming=True)
                else:
                    await msg.answer_photo(fobj, caption=cap)
                tl.ok(s3, f"فایل {lbl} ارسال شد")
            except Exception as e:
                tl.err(s3, str(e)[:50])

            if i < total:
                for si in (s2, s3):
                    tl.steps[si][2] = "wait"
                    tl.steps[si][3] = ""
                    tl.steps[si][4] = None
    finally:
        stop_evt.set()
        await asyncio.sleep(0.1)
        try: await live
        except Exception: pass

    await status.edit_text(
        tl.render(f"✅ تمام! {total} فایل."),
        parse_mode="HTML", reply_markup=instagram_menu())


# ─── Timeline ──────────────────────────────────────────────────────────────────

class TL:
    def __init__(self):
        self.t0    = time.monotonic()
        self._si   = 0
        self.steps = []
    def add(self, icon, text):
        self.steps.append([icon, text, "wait", "", None])
        return len(self.steps) - 1
    def run(self, i, detail=""):
        for s in self.steps:
            if s[2] == "run": s[2] = "ok"
        self.steps[i][2] = "run"
        self.steps[i][3] = detail
        self.steps[i][4] = time.monotonic()
    def ok(self, i, detail=""):
        self.steps[i][2] = "ok"
        if detail: self.steps[i][3] = detail
    def err(self, i, detail=""):
        self.steps[i][2] = "err"
        if detail: self.steps[i][3] = detail
    def _sp(self):
        self._si = (self._si + 1) % len(SPINNER)
        return SPINNER[self._si]
    def render(self, note="") -> str:
        total = time.monotonic() - self.t0
        lines = [f"📸 <b>Instagram</b>  ⏱ {total:.1f}s\n"]
        for icon, text, st, detail, ts in self.steps:
            ela = f" ({time.monotonic()-ts:.1f}s)" if ts and st == "run" else ""
            if   st == "wait": row = f"○ {icon} {text}"
            elif st == "run":  row = f"{self._sp()} {icon} <b>{text}</b>{ela}"
            elif st == "ok":   row = f"✅ {icon} {text}"
            else:              row = f"❌ {icon} {text}"
            if detail: row += f"\n    └ <i>{detail}</i>"
            lines.append(row)
        if note: lines.append(f"\n{note}")
        return "\n".join(lines)


# ─── Multi-API extractor ─────────────────────────────────────────────────────────────────

async def _extract(url: str, tl: TL, si: int) -> list[dict]:
    shortcode = _shortcode(url)
    apis = [
        ("sssinstagram", _api_sss),
        ("reelsaver",    _api_reelsaver),
        ("yt-dlp",       _api_ytdlp),
    ]
    last_err = ""
    for name, fn in apis:
        tl.steps[si][3] = f"تلاش: {name}..."
        try:
            result = await asyncio.wait_for(fn(url, shortcode), timeout=15)
            if result:
                tl.steps[si][3] = f"✅ {name}"
                return result
        except asyncio.TimeoutError:
            last_err = f"{name}: timeout"
        except Exception as e:
            last_err = f"{name}: {str(e)[:40]}"
    raise RuntimeError(f"هیچ API کار نکرد. {last_err}")


async def _api_sss(url: str, shortcode: str) -> list[dict]:
    import httpx
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
        r = await c.get("https://sssinstagram.com/", headers={"User-Agent": _ua()})
        tok = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', r.text)
        if not tok:
            tok = re.search(r'name="_token"\s+value="([^"]+)"', r.text)
        if not tok:
            return []
        r2 = await c.post(
            "https://sssinstagram.com/request",
            data={"url": url, "_token": tok.group(1)},
            headers={"Referer": "https://sssinstagram.com/",
                     "User-Agent": _ua(),
                     "X-Requested-With": "XMLHttpRequest"},
        )
        data = r2.json()
    items = data.get("data", {}).get("items", []) or data.get("items", [])
    results = []
    for item in items:
        u = item.get("url") or item.get("video") or item.get("src")
        if u:
            is_v = ".mp4" in u or item.get("type") == "video"
            results.append({"type": "video" if is_v else "photo", "url": u})
    return results


async def _api_reelsaver(url: str, shortcode: str) -> list[dict]:
    import httpx
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
        r = await c.get("https://reelsaver.net/", headers={"User-Agent": _ua()})
        tok = re.search(r'name="_token"\s+value="([^"]+)"', r.text)
        if not tok:
            return []
        r2 = await c.post(
            "https://reelsaver.net/",
            data={"url": url, "_token": tok.group(1)},
            headers={"Referer": "https://reelsaver.net/",
                     "User-Agent": _ua()},
        )
    # parse video/image from response HTML
    return _parse_html_links(r2.text)


async def _api_ytdlp(url: str, shortcode: str) -> list[dict]:
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "http_headers": {"User-Agent": _ua_mob()}}
    loop = asyncio.get_event_loop()
    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    info = await loop.run_in_executor(None, _run)
    if not info: return []
    entries = info.get("entries") or [info]
    results = []
    for e in entries:
        if not e: continue
        fmts = [f for f in (e.get("formats") or [])
                if f.get("vcodec") != "none" and f.get("url")]
        if fmts:
            best = max(fmts, key=lambda f: f.get("height") or 0)
            results.append({"type": "video", "url": best["url"]})
        elif e.get("thumbnail"):
            results.append({"type": "photo", "url": e["thumbnail"]})
    return results


def _parse_html_links(html: str) -> list[dict]:
    results = []
    for m in re.finditer(r'href="(https://[^"]+\.mp4[^"]*?)"', html):
        u = m.group(1)
        if u not in [r["url"] for r in results]:
            results.append({"type": "video", "url": u})
    if not results:
        for m in re.finditer(r'href="(https://[^"]+\.jpg[^"]*?)"', html):
            u = m.group(1)
            if u not in [r["url"] for r in results]:
                results.append({"type": "photo", "url": u})
    if not results:
        for m in re.finditer(r'src="(https://[^"]+(?:cdninstagram|fbcdn)[^"]+)"', html):
            u = m.group(1)
            if u not in [r["url"] for r in results]:
                results.append({"type": "photo", "url": u})
    return results


async def _download_ram(url: str) -> tuple[bytes, str]:
    import httpx
    async with httpx.AsyncClient(
        headers={"User-Agent": _ua(), "Referer": "https://www.instagram.com/"},
        timeout=90, follow_redirects=True
    ) as c:
        r = await c.get(url)
        r.raise_for_status()
    ct  = r.headers.get("content-type", "")
    ext = "mp4" if "video" in ct else "jpg"
    return r.content, f"ig_media.{ext}"


def _shortcode(url):
    m = IG_URL_RE.search(url)
    return m.group(1) if m else ""

def _normalize_url(text):
    m = IG_URL_RE.search(text)
    if m: return f"https://www.instagram.com/p/{m.group(1)}/"
    m = IG_SHORT_RE.search(text)
    if m: return f"https://www.instagram.com/p/{m.group(1)}/"
    if "instagram.com/stories/" in text: return text.split("?")[0]
    return None

def _ua():
    return ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
def _ua_mob():
    return ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
