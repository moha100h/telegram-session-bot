"""Notification Service — i18n v5.1"""
import logging
from aiogram import Bot
from i18n import t, status_label

logger = logging.getLogger("notification")
SEP = "━" * 24

async def _send(bot: Bot, tg_id: int, text: str) -> bool:
    try:
        await bot.send_message(tg_id, text, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"notify {tg_id}: {e}")
        return False

async def notify_order_placed(bot, tg_id, order_id, panel_name, cat_name, service_name, quantity, amount, balance, lang="en"):
    return await _send(bot, tg_id, t("notif_order_placed", lang, oid=order_id, sep=SEP, panel=panel_name, cat=cat_name, svc=service_name[:40], qty=quantity, amt=amount, bal=balance))

async def notify_order_status(bot, tg_id, order_id, status, service_name, completed_qty=0, refund=0.0, admin_note="", lang="en"):
    icon = {"pending":"⏳","processing":"🔄","in progress":"🔄","completed":"✅","partial":"⚠️","cancelled":"❌","failed":"💔","refunded":"↩️","rejected":"❌"}.get(status.lower(),"📌")
    text = t("notif_status_update", lang, icon=icon, oid=order_id, status=status_label(status, lang), sep=SEP, svc=service_name[:40])
    if completed_qty: text += f"\n{t('order_qty_done', lang)}: <b>{completed_qty:,}</b>"
    if refund:        text += f"\n{t('order_refund', lang)}: <b>${refund:.4f}</b>"
    if admin_note:    text += f"\n{t('order_admin_note', lang)}: {admin_note}"
    return await _send(bot, tg_id, text)

async def notify_refund(bot, tg_id, order_id, amount, balance, reason="", lang="en"):
    return await _send(bot, tg_id, t("notif_refund", lang, oid=order_id, sep=SEP, amt=amount, bal=balance, reason=reason))

async def notify_deposit_approved(bot, tg_id, amount, balance, lang="en"):
    return await _send(bot, tg_id, t("notif_deposit_ok", lang, sep=SEP, amt=amount, bal=balance))

async def notify_deposit_rejected(bot, tg_id, amount, reason="", lang="en"):
    r = f"\n📝 {reason}" if reason else ""
    return await _send(bot, tg_id, t("notif_deposit_rej", lang, sep=SEP, amt=amount, reason=r))

async def notify_manual_charge(bot, tg_id, amount, balance, lang="en"):
    return await _send(bot, tg_id, t("notif_manual_charge", lang, sep=SEP, amt=amount, bal=balance))

async def notify_group_new_order(bot, order_id, panel, cat_name, svc_name, user, link, qty, amount, note=""):
    from services.settings_service import get_setting
    from db.database import AsyncSessionLocal
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    async with AsyncSessionLocal() as s:
        gid_str = getattr(panel, "group_id", None) or await get_setting(s, f"panel_{panel.id}_group_id", "")
    if not gid_str: return False
    try: gid = int(gid_str)
    except (ValueError, TypeError): return False
    sep = "━" * 28
    uname = f"@{user.username}" if user.username else str(user.telegram_id)
    text = (f"🆕 <b>Order #{order_id}</b>\n{sep}\n" f"🏷 Panel: <b>{panel.name}</b>\n📂 Category: <b>{cat_name}</b>\n" f"📌 Service: <b>{svc_name[:50]}</b>\n{sep}\n" f"👤 <code>{user.telegram_id}</code> {uname}\n" f"🔗 <code>{link[:100]}</code>\n🔢 <b>{qty:,}</b>\n💰 <b>${amount:.4f}</b>\n" + (f"📝 <i>{note}</i>\n" if note else "") + f"{sep}\n⏳ <b>Pending</b>")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Processing", callback_data=f"adm_grp_porder_{order_id}_{panel.id}_processing"), InlineKeyboardButton(text="✅ Complete", callback_data=f"adm_grp_porder_{order_id}_{panel.id}_completed")],[InlineKeyboardButton(text="⚠️ Partial", callback_data=f"adm_grp_porder_{order_id}_{panel.id}_partial"), InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_grp_porder_{order_id}_{panel.id}_rejected")]])
    try:
        await bot.send_message(gid, text, reply_markup=kb, parse_mode="HTML")
        return True
    except Exception as e:
        logger.warning(f"group notify {gid}: {e}")
        return False