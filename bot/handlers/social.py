"""
Instagram & YouTube section.
Instagram downloader: streams media directly to Telegram — zero disk storage.
"""
import asyncio
import io
import logging
import os
import re
import httpx

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

# ─── Regex patterns ────────────────────────────────────────────────────────────

IG_URL_RE = re.compile(
    r"(https?://)?(www\.)?instagram\.com/"
    r"(p|reel|tv|stories|reels)/([A-Za-z0-9_\-]+)"
)
IG_SHORT_RE = re.compile(r"(https?://)?instagr\.am/p/([A-Za-z0-9_\-]+)")
IG_USER_RE  = re.compile(r"^@?([A-Za-z0-9_.]{1,30})$")

YT_URL_RE = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_\-]+)"
)


# ─── FSM ───────────────────────────────────────────────────────────────────────

class IGState(StatesGroup):
    waiting = State()


# ─── Menus ─────────────────────────────────────────────────────────────────────

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


# ─── Handlers: menus ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_social")
async def menu_social(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "📸 <b>اینستاگرام و یوتیوب</b>\n"
        "یک بخش را انتخاب کنید:",
        reply_markup=social_menu(), parse_mode="HTML",
    )


@router.callback_query(F.data == "social_instagram")
async def menu_instagram(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "📸 <b>خدمات اینستاگرام</b>\n\n"
        "• دانلود پست، ریل، IGTV\n"
        "• بدون ذخیره روی سرور\n"
        "• ارسال مستقیم به تلگرام",
        reply_markup=instagram_menu(), parse_mode="HTML",
    )


@router.callback_query(F.data == "social_youtube")
async def menu_youtube(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(
        "🎥 <b>خدمات یوتیوب</b>\n\n"
        "بزودی — به زودی اضافه می‌شود.",
        reply_markup=youtube_menu(), parse_mode="HTML",
    )


@router.callback_query(F.data == "yt_coming_soon")
async def yt_soon(cb: CallbackQuery):
    await cb.answer("🚧 بزودی اضافه می‌شود!", show_alert=True)


# ─── Instagram downloader ──────────────────────────────────────────────────────

@router.callback_query(F.data == "ig_download")
async def ig_download_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(IGState.waiting)
    await cb.message.edit_text(
        "⬇️ <b>دانلود اینستاگرام</b>\n\n"
        "لینک پست، ریل یا IGTV را بفرستید:\n"
        "<code>https://www.instagram.com/reel/ABC123/</code>\n\n"
        "یا شورتکاد:\n"
        "<code>https://instagr.am/p/ABC123/</code>",
        parse_mode="HTML",
    )


@router.message(IGState.waiting)
async def ig_download_handle(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return

    text = (msg.text or "").strip()
    await state.clear()

    # Extract shortcode
    shortcode = _extract_shortcode(text)
    if not shortcode:
        await msg.answer(
            "❌ لینک معتبر نیست.\n"
            "مثال: <code>https://www.instagram.com/reel/ABC123/</code>",
            parse_mode="HTML",
            reply_markup=instagram_menu(),
        )
        return

    status = await msg.answer("⏳ در حال دریافت اطلاعات...", parse_mode="HTML")

    try:
        medias = await _fetch_instagram(shortcode)
    except Exception as e:
        logger.error("[ig] fetch error: %s", e)
        await status.edit_text(
            f"❌ خطا در دریافت: {str(e)[:100]}",
            reply_markup=instagram_menu(),
        )
        return

    if not medias:
        await status.edit_text(
            "❌ مدیایی پیدا نشد. شاید پست خصوصی است.",
            reply_markup=instagram_menu(),
        )
        return

    total = len(medias)
    await status.edit_text(f"⏳ در حال ارسال {total} فایل... (0‌سرور ذخیره نمی‌شود)")

    sent = 0
    for i, media in enumerate(medias, 1):
        try:
            await _send_media_stream(msg, media, i, total)
            sent += 1
        except Exception as e:
            logger.error("[ig] send error item %d: %s", i, e)
            await msg.answer(f"⚠️ فایل {i} ارسال نشد: {str(e)[:80]}")

    await status.edit_text(
        f"✅ تمام شد! {sent}/{total} فایل ارسال شد.",
        reply_markup=instagram_menu(),
    )


# ─── Core: extract shortcode ───────────────────────────────────────────────────

def _extract_shortcode(text: str) -> str | None:
    """Extract Instagram shortcode from URL or raw shortcode."""
    m = IG_URL_RE.search(text)
    if m:
        return m.group(4)
    m = IG_SHORT_RE.search(text)
    if m:
        return m.group(2)
    # Raw shortcode (11 chars, alphanumeric)
    if re.match(r"^[A-Za-z0-9_\-]{10,15}$", text):
        return text
    return None


# ─── Core: fetch media info via instaloader API (no login needed for public) ───

async def _fetch_instagram(shortcode: str) -> list[dict]:
    """
    Fetch media URLs using Instagram's public GraphQL endpoint.
    No login, no cookies, no disk storage.
    Returns list of {type, url, filename}
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.instagram.com/",
        "X-IG-App-ID": "936619743392459",
    }

    # Try multiple endpoints
    results = await _try_graphql(shortcode, headers)
    if not results:
        results = await _try_oembed(shortcode, headers)
    return results


async def _try_graphql(shortcode: str, headers: dict) -> list[dict]:
    url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"
    try:
        async with httpx.AsyncClient(headers=headers, timeout=20,
                                     follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return []
            data = r.json()
    except Exception as e:
        logger.warning("[ig] graphql err: %s", e)
        return []

    try:
        media = data["graphql"]["shortcode_media"]
    except (KeyError, TypeError):
        try:
            media = data["items"][0]
        except (KeyError, TypeError, IndexError):
            return []

    return _parse_media_node(media, shortcode)


async def _try_oembed(shortcode: str, headers: dict) -> list[dict]:
    """Fallback: use a public Instagram downloader API."""
    apis = [
        f"https://api.snapinsta.app/v1?url=https://www.instagram.com/p/{shortcode}/",
        f"https://instagram-downloader-download-instagram-videos-stories.p.rapidapi.com/index?url=https://www.instagram.com/p/{shortcode}/",
    ]
    # Try snapinsta-style API (no key needed)
    try:
        api_url = f"https://api.instagramdl.io/download?url=https://www.instagram.com/p/{shortcode}/"
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(api_url)
            if r.status_code == 200:
                data = r.json()
                items = data.get("data", {}).get("items", []) or data.get("items", [])
                results = []
                for item in items:
                    media_url = item.get("url") or item.get("video_url") or item.get("image_url")
                    if media_url:
                        is_video = "video" in item.get("type", "") or ".mp4" in media_url
                        results.append({
                            "type": "video" if is_video else "photo",
                            "url": media_url,
                            "filename": f"{shortcode}_{len(results)+1}.{'mp4' if is_video else 'jpg'}",
                        })
                if results:
                    return results
    except Exception as e:
        logger.warning("[ig] oembed err: %s", e)

    return []


def _parse_media_node(media: dict, shortcode: str) -> list[dict]:
    """Parse Instagram GraphQL media node into list of {type, url, filename}."""
    results = []

    media_type = media.get("__typename", "") or media.get("media_type", "")

    # Carousel / sidecar
    edges = (media.get("edge_sidecar_to_children", {}).get("edges", [])
             or media.get("carousel_media", []))
    if edges:
        for i, edge in enumerate(edges):
            node = edge.get("node", edge)  # graphql vs v1
            results.extend(_parse_single_node(node, shortcode, i + 1))
        return results

    # Single
    results.extend(_parse_single_node(media, shortcode, 1))
    return results


def _parse_single_node(node: dict, shortcode: str, idx: int) -> list[dict]:
    # Video
    video_url = node.get("video_url")
    if video_url:
        return [{"type": "video", "url": video_url,
                 "filename": f"{shortcode}_{idx}.mp4"}]
    # Image
    img = (node.get("display_url")
           or _best_image(node.get("display_resources", []))
           or _best_image(node.get("image_versions2", {}).get("candidates", [])))
    if img:
        return [{"type": "photo", "url": img,
                 "filename": f"{shortcode}_{idx}.jpg"}]
    return []


def _best_image(resources: list) -> str | None:
    if not resources:
        return None
    best = max(resources, key=lambda r: r.get("width", 0) or r.get("config_width", 0))
    return best.get("src") or best.get("url")


# ─── Core: stream media to Telegram (no disk) ──────────────────────────────────

async def _send_media_stream(msg: Message, media: dict, idx: int, total: int):
    """
    Download media into RAM buffer and send directly to Telegram.
    No temp files, no disk writes.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.instagram.com/",
    }

    async with httpx.AsyncClient(headers=headers, timeout=60,
                                 follow_redirects=True) as client:
        r = await client.get(media["url"])
        r.raise_for_status()
        data = r.content  # in-memory bytes, no disk

    buf      = io.BytesIO(data)
    filename = media["filename"]
    caption  = f"📸 {idx}/{total}" if total > 1 else "📸 Instagram"
    file_obj = BufferedInputFile(buf.read(), filename=filename)

    if media["type"] == "video":
        await msg.answer_video(file_obj, caption=caption)
    else:
        await msg.answer_photo(file_obj, caption=caption)
