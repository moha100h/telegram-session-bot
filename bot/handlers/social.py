"""
Instagram & YouTube section.
Downloader: yt-dlp with in-memory buffer — zero disk storage.
Supports: Reels, Posts, IGTV, Carousels
"""
import asyncio
import io
import logging
import os
import re
import tempfile
import shutil

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
    URLInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger   = logging.getLogger("social")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

IG_URL_RE = re.compile(
    r"https?://(?:www\.)?instagram\.com/"
    r"(?:p|reel|tv|reels)/([A-Za-z0-9_\-]+)"
)
IG_SHORT_RE = re.compile(r"https?://instagr\.am/p/([A-Za-z0-9_\-]+)")


# ─── FSM ──────────────────────────────────────────────────────────────────

class IGState(StatesGroup):
    waiting = State()


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
        "⚠️ استوری پشتیبانی نمی‌شود (نیاز به لاگین دارد)",
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

    # Normalize URL
    url = _normalize_url(text)
    if not url:
        await msg.answer(
            "❌ لینک معتبر نیست.\n"
            "مثال: <code>https://www.instagram.com/reel/ABC123/</code>",
            parse_mode="HTML", reply_markup=instagram_menu(),
        )
        return

    # Check if story
    if "/stories/" in url:
        await msg.answer(
            "⚠️ استوری پشتیبانی نمی‌شود.\n"
            "فقط پست، ریل و IGTV قابل دانلود هستند.",
            reply_markup=instagram_menu(),
        )
        return

    status = await msg.answer("⏳ در حال دانلود...")

    try:
        medias = await asyncio.wait_for(
            _download_with_ytdlp(url),
            timeout=120,
        )
    except asyncio.TimeoutError:
        await status.edit_text("❌ تایماوت — لینک را دوباره امتحان کنید.",
                               reply_markup=instagram_menu())
        return
    except Exception as e:
        logger.error("[ig] download error: %s", e)
        await status.edit_text(
            f"❌ خطا: {str(e)[:120]}",
            reply_markup=instagram_menu(),
        )
        return

    if not medias:
        await status.edit_text(
            "❌ مدیایی پیدا نشد.\n"
            "شاید پست خصوصی است یا لینک نامعتبر.",
            reply_markup=instagram_menu(),
        )
        return

    total = len(medias)
    await status.edit_text(f"⏳ در حال ارسال {total} فایل...")

    sent = 0
    for i, media in enumerate(medias, 1):
        try:
            await _send_from_buffer(msg, media, i, total)
            sent += 1
        except Exception as e:
            logger.error("[ig] send %d: %s", i, e)
            await msg.answer(f"⚠️ فایل {i} ارسال نشد: {str(e)[:80]}")

    await status.edit_text(
        f"✅ {sent}/{total} فایل ارسال شد.",
        reply_markup=instagram_menu(),
    )


# ─── yt-dlp downloader (no disk) ─────────────────────────────────────────────────────

async def _download_with_ytdlp(url: str) -> list[dict]:
    """
    Use yt-dlp to extract media URLs, then download into RAM.
    No temp files on disk.
    """
    import yt_dlp

    ydl_opts = {
        "quiet":           True,
        "no_warnings":     True,
        "extract_flat":    False,
        "skip_download":   True,   # just get info first
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                          "Mobile/15E148 Safari/604.1",
        },
    }

    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    info = await loop.run_in_executor(None, _extract)
    if not info:
        return []

    medias = []

    # Carousel / playlist
    entries = info.get("entries") or [info]

    for entry in entries:
        if not entry:
            continue

        # Pick best video format under 50MB
        video_url = None
        thumb_url  = entry.get("thumbnail")

        formats = entry.get("formats") or []
        # Sort by filesize asc, pick largest under 50MB
        video_formats = [
            f for f in formats
            if f.get("vcodec") != "none"
            and f.get("url")
            and (f.get("filesize") or 0) < 50 * 1024 * 1024
        ]
        if not video_formats:
            # No size info — just pick best quality
            video_formats = [
                f for f in formats
                if f.get("vcodec") != "none" and f.get("url")
            ]

        if video_formats:
            best = max(video_formats,
                       key=lambda f: f.get("height") or f.get("quality") or 0)
            video_url = best.get("url")

        if video_url:
            medias.append({"type": "video", "url": video_url,
                           "thumb": thumb_url, "title": entry.get("title", "")})
        elif thumb_url:
            medias.append({"type": "photo", "url": thumb_url,
                           "title": entry.get("title", "")})

    return medias


async def _send_from_buffer(msg: Message, media: dict, idx: int, total: int):
    """
    Download into RAM buffer, send to Telegram. Zero disk usage.
    """
    import httpx

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                      "Mobile/15E148 Safari/604.1",
        "Referer": "https://www.instagram.com/",
    }

    caption = f"📸 {idx}/{total}" if total > 1 else "📸 Instagram"
    if media.get("title"):
        caption += f"\n{media['title'][:100]}"

    async with httpx.AsyncClient(headers=headers, timeout=60,
                                 follow_redirects=True) as client:
        r = await client.get(media["url"])
        r.raise_for_status()
        data = r.content

    file_obj = BufferedInputFile(data, filename=f"ig_{idx}.mp4"
                                 if media["type"] == "video" else f"ig_{idx}.jpg")

    if media["type"] == "video":
        await msg.answer_video(file_obj, caption=caption,
                               supports_streaming=True)
    else:
        await msg.answer_photo(file_obj, caption=caption)


# ─── helpers ──────────────────────────────────────────────────────────────────────────────────

def _normalize_url(text: str) -> str | None:
    """Extract and normalize Instagram URL."""
    m = IG_URL_RE.search(text)
    if m:
        return m.group(0).split("?")[0].rstrip("/") + "/"
    m = IG_SHORT_RE.search(text)
    if m:
        return f"https://www.instagram.com/p/{m.group(1)}/"
    # stories
    if "instagram.com/stories/" in text:
        return text.split("?")[0]
    return None
