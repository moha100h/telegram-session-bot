"""
Instagram & YouTube section.
Downloader: yt-dlp with in-memory buffer — zero disk storage.
Live timeline progress shown to user.
"""
import asyncio
import io
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
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:p|reel|tv|reels)/([A-Za-z0-9_\-]+)"
)
IG_SHORT_RE = re.compile(r"https?://instagr\.am/p/([A-Za-z0-9_\-]+)")

SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]


# ─── FSM ──────────────────────────────────────────────────────────────────

class IGState(StatesGroup):
    waiting = State()


# ─── Timeline tracker ───────────────────────────────────────────────────────────

class Timeline:
    """
    Tracks steps with timestamps and renders a live Telegram message.
    Each step: (emoji, label, status: pending|active|done|error, ts)
    """
    STEPS = [
        ("1", "🔗", "دریافت لینک"),
        ("2", "🔍", "استخراج اطلاعات مدیا"),
        ("3", "📦", "دانلود فایل"),
        ("4", "🚀", "ارسال به تلگرام"),
    ]

    def __init__(self):
        self.started_at  = time.monotonic()
        self._spin_i     = 0
        # step_id -> {status, ts, detail}
        self._steps: dict = {
            s[0]: {"emoji": s[1], "label": s[2],
                   "status": "pending", "ts": None, "detail": ""}
            for s in self.STEPS
        }
        self._current = None

    def start(self, step_id: str, detail: str = ""):
        """Mark step as active."""
        if self._current and self._current != step_id:
            self._steps[self._current]["status"] = "done"
        self._steps[step_id]["status"] = "active"
        self._steps[step_id]["ts"]     = time.monotonic()
        self._steps[step_id]["detail"] = detail
        self._current = step_id

    def done(self, step_id: str, detail: str = ""):
        self._steps[step_id]["status"] = "done"
        if detail:
            self._steps[step_id]["detail"] = detail

    def error(self, step_id: str, detail: str = ""):
        self._steps[step_id]["status"] = "error"
        if detail:
            self._steps[step_id]["detail"] = detail
        self._current = None

    def _spin(self) -> str:
        self._spin_i = (self._spin_i + 1) % len(SPINNER)
        return SPINNER[self._spin_i]

    def _elapsed(self, ts) -> str:
        if ts is None:
            return ""
        s = time.monotonic() - ts
        return f" ({s:.1f}s)"

    def _total(self) -> str:
        s = time.monotonic() - self.started_at
        return f"{s:.1f}s"

    def render(self, extra: str = "") -> str:
        lines = ["📸 <b>دانلود اینستاگرام</b>\n"]

        for sid, step in self._steps.items():
            st     = step["status"]
            emoji  = step["emoji"]
            label  = step["label"]
            detail = step["detail"]

            if st == "pending":
                icon = "○"
                line = f"{icon} {emoji} {label}"
            elif st == "active":
                sp   = self._spin()
                ela  = self._elapsed(step["ts"])
                line = f"{sp} {emoji} <b>{label}</b>{ela}"
                if detail:
                    line += f"\n    └ {detail}"
            elif st == "done":
                ela  = self._elapsed(step["ts"])
                line = f"✅ {emoji} {label}"
                if detail:
                    line += f" — {detail}"
            elif st == "error":
                line = f"❌ {emoji} {label}"
                if detail:
                    line += f"\n    └ {detail}"
            else:
                line = f"○ {emoji} {label}"

            lines.append(line)

        if extra:
            lines.append(f"\n{extra}")

        lines.append(f"\n⏱ زمان کل: <b>{self._total()}</b>")
        return "\n".join(lines)


# ─── Menus ──────────────────────────────────────────────────────────────────

def social_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 خدمات اینستاگرام",  callback_data="social_instagram")],
        [InlineKeyboardButton(text="🎥 خدمات یوتیوب",      callback_data="social_youtube")],
        [InlineKeyboardButton(text="🔙 بازگشت",              callback_data="menu_main")],
    ])


def instagram_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ دانلود پست / ریل / IGTV", callback_data="ig_download")],
        [InlineKeyboardButton(text="🔙 بازگشت",                       callback_data="menu_social")],
    ])


def youtube_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚧 بزودی — در دست ساخت",  callback_data="yt_coming_soon")],
        [InlineKeyboardButton(text="🔙 بازگشت",                    callback_data="menu_social")],
    ])


# ─── Menu handlers ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_social")
async def menu_social(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "📸 <b>اینستاگرام و یوتیوب</b>\nیک بخش را انتخاب کنید:",
        reply_markup=social_menu(), parse_mode="HTML",
    )


@router.callback_query(F.data == "social_instagram")
async def menu_instagram(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "📸 <b>خدمات اینستاگرام</b>\n\n"
        "• پست، ریل، IGTV و کاروسل\n"
        "• بدون ذخیره روی سرور\n"
        "⚠️ استوری پشتیبانی نمی‌شود",
        reply_markup=instagram_menu(), parse_mode="HTML",
    )


@router.callback_query(F.data == "social_youtube")
async def menu_youtube(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "🎥 <b>خدمات یوتیوب</b>\n\nبزودی — به زودی اضافه می‌شود.",
        reply_markup=youtube_menu(), parse_mode="HTML",
    )


@router.callback_query(F.data == "yt_coming_soon")
async def yt_soon(cb: CallbackQuery):
    await cb.answer("🚧 بزودی اضافه می‌شود!", show_alert=True)


# ─── Instagram download flow ───────────────────────────────────────────────────────

@router.callback_query(F.data == "ig_download")
async def ig_download_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(IGState.waiting)
    await cb.message.edit_text(
        "⬇️ <b>دانلود اینستاگرام</b>\n\n"
        "لینک پست، ریل یا IGTV بفرستید:\n"
        "<code>https://www.instagram.com/reel/ABC123/</code>\n"
        "<code>https://www.instagram.com/p/ABC123/</code>\n\n"
        "⚠️ فقط پست‌های عمومی پشتیبانی می‌شوند",
        parse_mode="HTML",
    )


@router.message(IGState.waiting)
async def ig_download_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return

    text = (msg.text or "").strip()
    await state.clear()

    # Step 1: validate URL
    tl  = Timeline()
    tl.start("1", text[:60])

    url = _normalize_url(text)
    if not url:
        tl.error("1", "لینک نامعتبر")
        await msg.answer(
            tl.render(),
            parse_mode="HTML", reply_markup=instagram_menu(),
        )
        return

    if "/stories/" in url:
        tl.error("1", "استوری پشتیبانی نمی‌شود")
        await msg.answer(
            tl.render("⚠️ فقط پست، ریل و IGTV قابل دانلود هستند."),
            parse_mode="HTML", reply_markup=instagram_menu(),
        )
        return

    tl.done("1", url.split("/")[-2] or "ok")

    # Send initial status message
    tl.start("2")
    status = await msg.answer(tl.render(), parse_mode="HTML")

    # Live updater task
    stop_live = asyncio.Event()

    async def live_update():
        while not stop_live.is_set():
            try:
                await status.edit_text(tl.render(), parse_mode="HTML")
            except Exception:
                pass
            await asyncio.sleep(2)

    live_task = asyncio.create_task(live_update())

    try:
        # Step 2: extract info with yt-dlp
        try:
            medias = await asyncio.wait_for(_extract_info(url), timeout=30)
            if not medias:
                raise ValueError("مدیایی پیدا نشد")
            tl.done("2", f"{len(medias)} فایل")
        except asyncio.TimeoutError:
            tl.error("2", "تایماوت")
            stop_live.set()
            await status.edit_text(
                tl.render("❌ تایماوت. دوباره امتحان کنید."),
                parse_mode="HTML", reply_markup=instagram_menu(),
            )
            return
        except Exception as e:
            tl.error("2", str(e)[:60])
            stop_live.set()
            await status.edit_text(
                tl.render(), parse_mode="HTML", reply_markup=instagram_menu()
            )
            return

        total = len(medias)

        # Step 3+4: download + send each file
        for i, media in enumerate(medias, 1):
            # Step 3: download
            tl.start("3", f"فایل {i}/{total}")
            try:
                data, filename = await asyncio.wait_for(
                    _download_to_ram(media["url"]), timeout=90
                )
                size_mb = len(data) / 1024 / 1024
                tl.done("3", f"{size_mb:.1f} MB")
            except asyncio.TimeoutError:
                tl.error("3", f"تایماوت — فایل {i}")
                continue
            except Exception as e:
                tl.error("3", str(e)[:50])
                continue

            # Step 4: send to Telegram
            tl.start("4", f"فایل {i}/{total}")
            try:
                caption  = f"📸 {i}/{total}" if total > 1 else "📸 Instagram"
                file_obj = BufferedInputFile(data, filename=filename)
                if media["type"] == "video":
                    await msg.answer_video(file_obj, caption=caption,
                                           supports_streaming=True)
                else:
                    await msg.answer_photo(file_obj, caption=caption)
                tl.done("4", f"فایل {i}/{total} ارسال شد")
            except Exception as e:
                tl.error("4", str(e)[:50])

            # Reset steps 3+4 for next file
            if i < total:
                tl._steps["3"]["status"] = "pending"
                tl._steps["3"]["detail"] = ""
                tl._steps["4"]["status"] = "pending"
                tl._steps["4"]["detail"] = ""

    finally:
        stop_live.set()
        await asyncio.sleep(0.1)

    await status.edit_text(
        tl.render(f"✅ تمام شد! {total} فایل ارسال شد."),
        parse_mode="HTML",
        reply_markup=instagram_menu(),
    )


# ─── yt-dlp: extract info only (no download) ─────────────────────────────────────────

async def _extract_info(url: str) -> list[dict]:
    import yt_dlp

    opts = {
        "quiet":       True,
        "no_warnings": True,
        "skip_download": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/16.0 Mobile/15E148 Safari/604.1"
            ),
        },
    }

    loop = asyncio.get_event_loop()

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    info = await loop.run_in_executor(None, _run)
    if not info:
        return []

    entries = info.get("entries") or [info]
    medias  = []

    for entry in entries:
        if not entry:
            continue
        formats = entry.get("formats") or []
        # Best video under 50 MB
        vformats = [
            f for f in formats
            if f.get("vcodec") != "none" and f.get("url")
            and (f.get("filesize") or 0) < 50 * 1024 * 1024
        ]
        if not vformats:
            vformats = [f for f in formats
                        if f.get("vcodec") != "none" and f.get("url")]

        if vformats:
            best = max(vformats,
                       key=lambda f: f.get("height") or f.get("quality") or 0)
            medias.append({"type": "video", "url": best["url"],
                           "title": entry.get("title", "")})
        elif entry.get("thumbnail"):
            medias.append({"type": "photo", "url": entry["thumbnail"],
                           "title": entry.get("title", "")})

    return medias


# ─── Download to RAM ───────────────────────────────────────────────────────────────────────

async def _download_to_ram(url: str) -> tuple[bytes, str]:
    """Download URL into RAM. Returns (bytes, filename). Zero disk."""
    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/16.0 Mobile/15E148 Safari/604.1"
        ),
        "Referer": "https://www.instagram.com/",
    }

    async with httpx.AsyncClient(headers=headers, timeout=90,
                                 follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.content

    ct       = r.headers.get("content-type", "")
    filename = "ig_media.mp4" if "video" in ct else "ig_media.jpg"
    return data, filename


# ─── URL helpers ─────────────────────────────────────────────────────────────────────────────

def _normalize_url(text: str) -> str | None:
    m = IG_URL_RE.search(text)
    if m:
        return "https://www.instagram.com/p/" + m.group(1) + "/"
    m = IG_SHORT_RE.search(text)
    if m:
        return f"https://www.instagram.com/p/{m.group(1)}/"
    if "instagram.com/stories/" in text:
        return text.split("?")[0]
    return None
