"""
Instagram account manager handler.
Menu: create, list, follow, like, check/clean banned.
"""
import asyncio
import logging
import os
import time

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services import ig_account_store

logger   = logging.getLogger("ig_manager")
router   = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]


class IGMgrState(StatesGroup):
    follow_target  = State()
    follow_count   = State()
    like_url       = State()
    like_count     = State()
    create_count   = State()


# ─── Menus ──────────────────────────────────────────────────────────────────

def ig_manager_menu() -> InlineKeyboardMarkup:
    cnt = ig_account_store.count()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🤖 ساخت اکانت جدید",
            callback_data="igm_create")]],
        [[InlineKeyboardButton(
            text=f"📊 اکانت‌ها: ✅{cnt['active']} 🗑{cnt['banned']} کل:{cnt['total']}",
            callback_data="igm_list")]],
        [[InlineKeyboardButton(text="👥 فالو بزن",  callback_data="igm_follow"),
          InlineKeyboardButton(text="❤️ لایک بزن", callback_data="igm_like")]],
        [[InlineKeyboardButton(text="🧹 حذف بن شده‌ها", callback_data="igm_clean")]],
        [[InlineKeyboardButton(text="🔄 بررسی وضعیت اکانت‌ها", callback_data="igm_check")]],
        [[InlineKeyboardButton(text="🔙 بازگشت", callback_data="social_instagram")]],
    ])


# ─── Entry ──────────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "igm_menu")
async def igm_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear(); await cb.answer()
    await cb.message.edit_text(
        "📸 <b>مدیریت اکانت اینستاگرام</b>",
        reply_markup=ig_manager_menu(), parse_mode="HTML")


# ─── Create account ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "igm_create")
async def igm_create(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(IGMgrState.create_count)
    await cb.message.edit_text(
        "🤖 <b>ساخت اکانت اینستاگرام</b>\n\n"
        "چند اکانت می‌خواید بسازید? (1-10)",
        parse_mode="HTML")


@router.message(IGMgrState.create_count)
async def igm_create_count(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    try:
        count = int(msg.text.strip())
        if not 1 <= count <= 10:
            await msg.answer("❌ عدد بین ۱ تا ۱۰ باشد."); return
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کن."); return
    await state.clear()

    status_msg = await msg.answer(
        f"⏳ در حال ساخت <b>{count}</b> اکانت...",
        parse_mode="HTML")

    asyncio.create_task(_create_accounts_task(count, status_msg, msg))


async def _create_accounts_task(count: int, status_msg, msg: Message):
    from services.ig_creator import create_ig_account
    from services.proxy_fetcher import ProxyFetcher
    from redis.asyncio import Redis

    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis = Redis.from_url(REDIS_URL)

    # Get proxies
    proxies = []
    try:
        raw = await redis.lrange("proxies", 0, count * 2)
        proxies = [p.decode() if isinstance(p, bytes) else p for p in raw]
    except Exception:
        pass

    results  = []
    success  = 0
    failed   = 0
    spin_i   = 0
    t0       = time.monotonic()

    # Timeline state per account
    timelines = {}

    async def update_msg():
        elapsed = time.monotonic() - t0
        spin_i_local = (int(elapsed * 3)) % len(SPINNER)
        sp = SPINNER[spin_i_local]
        lines = [
            f"{sp} <b>ساخت اکانت اینستاگرام</b>  ⏱ {elapsed:.0f}s",
            f"✅ موفق: <b>{success}</b>  ❌ شکست: <b>{failed}</b>  کل: {count}\n",
        ]
        for slot, tl in timelines.items():
            lines.append(f"<b>سلات {slot}:</b>")
            for step_name, detail in tl.items():
                lines.append(f"  {detail}")
        if results:
            lines.append("")
            lines.extend(results[-5:])
        try:
            await status_msg.edit_text("\n".join(lines), parse_mode="HTML")
        except Exception:
            pass

    stop_evt = asyncio.Event()

    async def live_loop():
        while not stop_evt.is_set():
            await update_msg()
            await asyncio.sleep(2)

    live = asyncio.create_task(live_loop())

    sem = asyncio.Semaphore(3)  # max 3 parallel creations

    async def create_one(slot: int):
        nonlocal success, failed
        proxy = proxies[slot % len(proxies)] if proxies else None
        timelines[slot] = {}

        async def on_step(step, detail):
            STEP_ICONS = {
                "profile":      "👤",
                "email":        "📧",
                "phone":        "📱",
                "register":     "📝",
                "verify_phone": "🔐",
                "profile_set":  "🎨",
                "avatar":       "🖼",
                "done":         "🏁",
            }
            icon = STEP_ICONS.get(step, "○")
            timelines[slot][step] = f"{icon} {detail}"

        async with sem:
            try:
                acc = await create_ig_account(proxy=proxy, on_step=on_step)
                success += 1
                results.append(f"✅ @{acc['username']} — {acc['phone']}")
            except Exception as e:
                failed += 1
                results.append(f"❌ سلات {slot}: {str(e)[:60]}")

    await asyncio.gather(*[create_one(i + 1) for i in range(count)])
    stop_evt.set()
    await asyncio.sleep(0.1)
    try: await live
    except Exception: pass

    cnt = ig_account_store.count()
    final = [
        f"🏁 <b>ساخت تمام شد!</b>",
        f"✅ موفق: <b>{success}</b>  ❌ شکست: <b>{failed}</b>",
        f"📊 کل اکانت‌ها: <b>{cnt['total']}</b> (✅{cnt['active']} 🗑{cnt['banned']})",
        "",
    ] + results
    try:
        await msg.answer("\n".join(final),
                         reply_markup=ig_manager_menu(), parse_mode="HTML")
    except Exception: pass


# ─── List accounts ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "igm_list")
async def igm_list(cb: CallbackQuery):
    await cb.answer()
    all_acc = ig_account_store.list_all()
    if not all_acc:
        await cb.message.edit_text(
            "📢 هیچ اکانتی وجود ندارد.\nابتدا اکانت بسازید.",
            reply_markup=ig_manager_menu(), parse_mode="HTML")
        return

    lines = [f"📊 <b>لیست اکانت‌ها ({len(all_acc)})</b>\n"]
    for acc in all_acc[:30]:
        st   = "✅" if acc.get("status") == "active" else "🗑"
        uname = acc.get("username", "?")
        phone = acc.get("phone", "")
        lines.append(f"{st} <code>@{uname}</code> — {phone}")
    if len(all_acc) > 30:
        lines.append(f"\n... و {len(all_acc)-30} اکانت دیگر")

    await cb.message.edit_text(
        "\n".join(lines),
        reply_markup=ig_manager_menu(), parse_mode="HTML")


# ─── Follow ──────────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "igm_follow")
async def igm_follow(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    active = ig_account_store.list_active()
    if not active:
        await cb.answer("❌ هیچ اکانت فعالی ندارید.", show_alert=True); return
    await state.set_state(IGMgrState.follow_target)
    await cb.message.edit_text(
        f"👥 <b>فالو</b>\nاکانت فعال: <b>{len(active)}</b>\n\n"
        "یوزرنیم تارگت را بفرستید:\n"
        "<code>username</code> یا <code>@username</code>",
        parse_mode="HTML")


@router.message(IGMgrState.follow_target)
async def igm_follow_target(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    target = msg.text.strip().lstrip("@")
    await state.update_data(target=target)
    await state.set_state(IGMgrState.follow_count)
    active = ig_account_store.list_active()
    await msg.answer(
        f"👥 تارگت: <b>@{target}</b>\n"
        f"اکانت فعال: <b>{len(active)}</b>\n\n"
        f"چند فالو بزنیم? (1–{len(active)})",
        parse_mode="HTML")


@router.message(IGMgrState.follow_count)
async def igm_follow_count(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    target = data.get("target", "")
    try:
        count = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کن."); return
    await state.clear()

    status_msg = await msg.answer(
        f"⏳ در حال فالو — تارگت: <b>@{target}</b> — تعداد: <b>{count}</b>",
        parse_mode="HTML")
    asyncio.create_task(_follow_task(target, count, status_msg, msg))


async def _follow_task(target: str, count: int, status_msg, msg: Message):
    from services.ig_actions import follow_target
    t0   = time.monotonic()
    done = 0
    ok   = 0
    fail = 0
    stop = asyncio.Event()

    async def on_prog(d, total, s, f):
        nonlocal done, ok, fail
        done, ok, fail = d, s, f

    async def live():
        spin_i = 0
        while not stop.is_set():
            sp = SPINNER[spin_i % len(SPINNER)]; spin_i += 1
            ela = time.monotonic() - t0
            try:
                await status_msg.edit_text(
                    f"{sp} <b>فالو</b> — @{target}  ⏱ {ela:.0f}s\n"
                    f"✅ موفق: <b>{ok}</b>  ❌ شکست: <b>{fail}</b>  کل: {count}",
                    parse_mode="HTML")
            except Exception: pass
            await asyncio.sleep(2)

    live_t = asyncio.create_task(live())
    try:
        result = await follow_target(target, count, on_progress=on_prog)
    except Exception as e:
        result = {"success": 0, "failed": count, "results": [str(e)]}
    finally:
        stop.set()
        try: await live_t
        except Exception: pass

    lines = [
        f"🏁 <b>فالو تمام شد!</b>",
        f"✅ موفق: <b>{result['success']}</b>  ❌ شکست: <b>{result['failed']}</b>",
        f"⏱ {time.monotonic()-t0:.0f}s\n",
    ] + result["results"][:20]
    await msg.answer("\n".join(lines),
                     reply_markup=ig_manager_menu(), parse_mode="HTML")


# ─── Like ──────────────────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "igm_like")
async def igm_like(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    active = ig_account_store.list_active()
    if not active:
        await cb.answer("❌ هیچ اکانت فعالی ندارید.", show_alert=True); return
    await state.set_state(IGMgrState.like_url)
    await cb.message.edit_text(
        f"❤️ <b>لایک</b>\nاکانت فعال: <b>{len(active)}</b>\n\n"
        "لینک پست را بفرستید:\n"
        "<code>https://www.instagram.com/p/ABC123/</code>",
        parse_mode="HTML")


@router.message(IGMgrState.like_url)
async def igm_like_url(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    await state.update_data(url=msg.text.strip())
    await state.set_state(IGMgrState.like_count)
    active = ig_account_store.list_active()
    await msg.answer(
        f"❤️ لینک: <code>{msg.text.strip()[:60]}</code>\n"
        f"اکانت فعال: <b>{len(active)}</b>\n\n"
        f"چند لایک بزنیم? (1–{len(active)})",
        parse_mode="HTML")


@router.message(IGMgrState.like_count)
async def igm_like_count(msg: Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    url  = data.get("url", "")
    try:
        count = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کن."); return
    await state.clear()

    status_msg = await msg.answer(
        f"⏳ در حال لایک — تعداد: <b>{count}</b>",
        parse_mode="HTML")
    asyncio.create_task(_like_task(url, count, status_msg, msg))


async def _like_task(url: str, count: int, status_msg, msg: Message):
    from services.ig_actions import like_post
    t0   = time.monotonic()
    ok   = 0; fail = 0
    stop = asyncio.Event()

    async def on_prog(d, total, s, f):
        nonlocal ok, fail
        ok, fail = s, f

    async def live():
        spin_i = 0
        while not stop.is_set():
            sp = SPINNER[spin_i % len(SPINNER)]; spin_i += 1
            ela = time.monotonic() - t0
            try:
                await status_msg.edit_text(
                    f"{sp} <b>لایک</b>  ⏱ {ela:.0f}s\n"
                    f"✅ موفق: <b>{ok}</b>  ❌ شکست: <b>{fail}</b>  کل: {count}",
                    parse_mode="HTML")
            except Exception: pass
            await asyncio.sleep(2)

    live_t = asyncio.create_task(live())
    try:
        result = await like_post(url, count, on_progress=on_prog)
    except Exception as e:
        result = {"success": 0, "failed": count, "results": [str(e)]}
    finally:
        stop.set()
        try: await live_t
        except Exception: pass

    lines = [
        f"🏁 <b>لایک تمام شد!</b>",
        f"✅ موفق: <b>{result['success']}</b>  ❌ شکست: <b>{result['failed']}</b>",
        f"⏱ {time.monotonic()-t0:.0f}s\n",
    ] + result["results"][:20]
    await msg.answer("\n".join(lines),
                     reply_markup=ig_manager_menu(), parse_mode="HTML")


# ─── Check & Clean ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "igm_check")
async def igm_check(cb: CallbackQuery):
    await cb.answer()
    status_msg = await cb.message.edit_text(
        "⏳ در حال بررسی وضعیت اکانت‌ها...",
        parse_mode="HTML")
    asyncio.create_task(_check_task(status_msg))


async def _check_task(status_msg):
    from services.ig_actions import check_all_accounts
    try:
        result = await check_all_accounts()
        await status_msg.edit_text(
            f"✅ <b>بررسی تمام شد</b>\n"
            f"📊 بررسی شده: <b>{result['checked']}</b>\n"
            f"✅ فعال: <b>{result['active']}</b>\n"
            f"🗑 بن: <b>{result['banned']}</b>",
            reply_markup=ig_manager_menu(), parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(f"❌ {e}",
                                   reply_markup=ig_manager_menu(), parse_mode="HTML")


@router.callback_query(F.data == "igm_clean")
async def igm_clean(cb: CallbackQuery):
    await cb.answer()
    all_acc = ig_account_store.list_all()
    banned  = [a for a in all_acc if a.get("status") == "banned"]
    if not banned:
        await cb.answer("✅ هیچ اکانت بنی وجود ندارد.", show_alert=True); return

    for acc in banned:
        await ig_account_store.remove(acc["username"])

    await cb.message.edit_text(
        f"🧹 <b>{len(banned)} اکانت بن حذف شد.</b>",
        reply_markup=ig_manager_menu(), parse_mode="HTML")
