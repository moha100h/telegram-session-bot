"""MiniApp API — FastAPI backend for Telegram WebApp"""
import os, hmac, hashlib, json, logging
from datetime import datetime
from typing import Optional
from urllib.parse import unquote
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("miniapp")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))
DB_URL    = os.getenv("DATABASE_URL", "postgresql+asyncpg://smm:smm123@postgres:5432/smmbot")

engine = create_async_engine(DB_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI(title="TSB MiniApp API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# serve static miniapp
import os as _os
_static = _os.path.join(_os.path.dirname(__file__), "..", "miniapp")
if _os.path.isdir(_static):
    app.mount("/static", StaticFiles(directory=_static), name="static")

@app.get("/")
async def root():
    idx = _os.path.join(_static, "index.html")
    if _os.path.exists(idx):
        return FileResponse(idx)
    return {"status": "ok"}

# ── Auth ──────────────────────────────────────────────────────────────────────
def verify_tg(init_data: str) -> dict:
    try:
        parsed = {}
        for part in init_data.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                parsed[k] = unquote(v)
        hash_val = parsed.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, hash_val):
            raise ValueError("bad hash")
        return json.loads(parsed.get("user", "{}"))
    except Exception as ex:
        raise HTTPException(401, f"Unauthorized: {ex}")

async def get_db():
    async with SessionLocal() as s:
        yield s

def row2dict(row):
    if row is None: return None
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, datetime): d[k] = v.isoformat()
    return d

async def get_user_by_tg(db, tg_id):
    r = await db.execute(text("SELECT * FROM users WHERE telegram_id=:t"), {"t": tg_id})
    return r.mappings().first()

async def require_user(x: str = Header(..., alias="X-Init-Data"), db: AsyncSession = Depends(get_db)):
    tg = verify_tg(x)
    u = await get_user_by_tg(db, tg.get("id"))
    if not u: raise HTTPException(404, "User not found")
    return dict(u)

async def require_admin(x: str = Header(..., alias="X-Init-Data"), db: AsyncSession = Depends(get_db)):
    tg = verify_tg(x)
    tg_id = tg.get("id")
    if tg_id != ADMIN_ID:
        r = await db.execute(text("SELECT id FROM admin_users WHERE telegram_id=:t"), {"t": tg_id})
        if not r.first(): raise HTTPException(403, "Not admin")
    u = await get_user_by_tg(db, tg_id)
    return dict(u) if u else {"telegram_id": tg_id}

# ══════════════════════════════════════════════════════════════════════════════
# USER — پروفایل
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/user/me")
async def user_me(user=Depends(require_user)):
    return user

# ══════════════════════════════════════════════════════════════════════════════
# USER — پنل‌ها
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/user/panels")
async def user_panels(user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT id, name, button_label, description, order_index "
        "FROM panels WHERE is_active=true ORDER BY order_index, id"
    ))).mappings().all()
    return [dict(r) for r in rows]

# ══════════════════════════════════════════════════════════════════════════════
# USER — دسته‌بندی‌های پنل
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/user/panels/{panel_id}/categories")
async def user_panel_cats(panel_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    p = (await db.execute(text("SELECT id FROM panels WHERE id=:pid AND is_active=true"), {"pid": panel_id})).first()
    if not p: raise HTTPException(404, "Panel not found")
    rows = (await db.execute(text(
        "SELECT pc.id, pc.name, pc.icon, pc.order_index, "
        "COUNT(ps.id) FILTER (WHERE ps.is_active=true) as service_count "
        "FROM panel_categories pc "
        "LEFT JOIN panel_services ps ON ps.category_id=pc.id "
        "WHERE pc.panel_id=:pid AND pc.is_active=true "
        "GROUP BY pc.id ORDER BY pc.order_index, pc.id"
    ), {"pid": panel_id})).mappings().all()
    return [dict(r) for r in rows]

# ══════════════════════════════════════════════════════════════════════════════
# USER — خدمات دسته
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/user/panels/{panel_id}/categories/{cat_id}/services")
async def user_panel_svcs(panel_id: int, cat_id: int, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT id, name, description, price, min_qty, max_qty, order_index "
        "FROM panel_services WHERE category_id=:cid AND is_active=true ORDER BY order_index, id"
    ), {"cid": cat_id})).mappings().all()
    return [dict(r) for r in rows]

# ══════════════════════════════════════════════════════════════════════════════
# USER — ثبت سفارش پنل
# ══════════════════════════════════════════════════════════════════════════════
class PanelOrderBody(BaseModel):
    service_id: int
    panel_id: int
    link: str
    quantity: int
    note: Optional[str] = None

@app.post("/api/user/orders/panel")
async def create_panel_order(body: PanelOrderBody, user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    svc = (await db.execute(text(
        "SELECT ps.*, pc.panel_id, p.button_label, p.is_active as panel_active "
        "FROM panel_services ps "
        "JOIN panel_categories pc ON pc.id=ps.category_id "
        "JOIN panels p ON p.id=pc.panel_id "
        "WHERE ps.id=:sid AND ps.is_active=true AND pc.is_active=true AND p.is_active=true"
    ), {"sid": body.service_id})).mappings().first()
    if not svc: raise HTTPException(404, "Service not found or inactive")
    if svc["panel_id"] != body.panel_id: raise HTTPException(400, "Panel mismatch")
    if body.quantity < svc["min_qty"] or body.quantity > svc["max_qty"]:
        raise HTTPException(400, f"Quantity must be between {svc['min_qty']} and {svc['max_qty']}")
    total = round(float(svc["price"]) * body.quantity, 6)
    bal = float(user.get("balance") or 0)
    if bal < total - 1e-9:
        raise HTTPException(400, f"Insufficient balance. Need ${total:.4f}, have ${bal:.2f}")
    new_bal = round(bal - total, 6)
    await db.execute(text("UPDATE users SET balance=:b WHERE id=:uid"), {"b": new_bal, "uid": user["id"]})
    r = await db.execute(text(
        "INSERT INTO panel_orders(user_id,panel_id,service_id,service_name,panel_name,"
        "quantity,unit_price,total_price,link,note,status,refund_amount,created_at,updated_at) "
        "VALUES(:uid,:pid,:sid,:sname,:pname,:qty,:up,:tp,:link,:note,'pending',0,NOW(),NOW()) "
        "RETURNING id,total_price,status,created_at"
    ), {
        "uid": user["id"], "pid": body.panel_id, "sid": body.service_id,
        "sname": svc["name"], "pname": svc["button_label"],
        "qty": body.quantity, "up": float(svc["price"]), "tp": total,
        "link": body.link, "note": body.note or ""
    })
    order = r.mappings().first()
    await db.execute(text(
        "INSERT INTO transactions(user_id,type,amount,status,description,created_at) "
        "VALUES(:uid,'panel_order_charge',:amt,'completed',:desc,NOW())"
    ), {"uid": user["id"], "amt": -total, "desc": f"سفارش #{order['id']} — {svc['name'][:40]}"})
    await db.commit()
    return {"id": order["id"], "total_price": total, "status": "pending",
            "created_at": order["created_at"].isoformat() if order["created_at"] else None}

# ══════════════════════════════════════════════════════════════════════════════
# USER — سفارشات پنل
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/user/panel-orders")
async def user_panel_orders(page: int = 1, limit: int = 20, status: Optional[str] = None,
                             user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    where = "WHERE user_id=:uid" + (" AND status=:st" if status else "")
    params = {"uid": user["id"]}
    if status: params["st"] = status
    total = (await db.execute(text(f"SELECT COUNT(*) FROM panel_orders {where}"), params)).scalar()
    rows = (await db.execute(text(
        f"SELECT id,panel_id,service_id,service_name,panel_name,quantity,unit_price,total_price,"
        f"link,note,status,completed_qty,refund_amount,admin_note,created_at,updated_at "
        f"FROM panel_orders {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"
    ), {**params, "lim": limit, "off": (page - 1) * limit})).mappings().all()
    return {"total": total, "page": page, "items": [row2dict(r) for r in rows]}

# ══════════════════════════════════════════════════════════════════════════════
# USER — تراکنش‌ها
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/user/transactions")
async def user_transactions(page: int = 1, limit: int = 20,
                             user=Depends(require_user), db: AsyncSession = Depends(get_db)):
    params = {"uid": user["id"], "lim": limit, "off": (page - 1) * limit}
    total = (await db.execute(text("SELECT COUNT(*) FROM transactions WHERE user_id=:uid"), {"uid": user["id"]})).scalar()
    rows = (await db.execute(text(
        "SELECT * FROM transactions WHERE user_id=:uid ORDER BY created_at DESC LIMIT :lim OFFSET :off"
    ), params)).mappings().all()
    return {"total": total, "page": page, "items": [row2dict(r) for r in rows]}

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — آمار
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/stats")
async def admin_stats(admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    async def sc(q, p={}): return (await db.execute(text(q), p)).scalar() or 0
    return {
        "total_users":          await sc("SELECT COUNT(*) FROM users"),
        "banned_users":         await sc("SELECT COUNT(*) FROM users WHERE is_banned=true"),
        "active_users":         await sc("SELECT COUNT(*) FROM users WHERE is_banned=false"),
        "total_panel_orders":   await sc("SELECT COUNT(*) FROM panel_orders"),
        "pending_panel_orders": await sc("SELECT COUNT(*) FROM panel_orders WHERE status='pending'"),
        "processing_orders":    await sc("SELECT COUNT(*) FROM panel_orders WHERE status='processing'"),
        "completed_orders":     await sc("SELECT COUNT(*) FROM panel_orders WHERE status='completed'"),
        "partial_orders":       await sc("SELECT COUNT(*) FROM panel_orders WHERE status='partial'"),
        "rejected_orders":      await sc("SELECT COUNT(*) FROM panel_orders WHERE status='rejected'"),
        "total_revenue":        float(await sc("SELECT COALESCE(SUM(total_price),0) FROM panel_orders WHERE status IN ('completed','partial')")),
        "total_balance":        float(await sc("SELECT COALESCE(SUM(balance),0) FROM users")),
        "today_orders":         await sc("SELECT COUNT(*) FROM panel_orders WHERE created_at>=CURRENT_DATE"),
        "today_revenue":        float(await sc("SELECT COALESCE(SUM(total_price),0) FROM panel_orders WHERE status IN ('completed','partial') AND created_at>=CURRENT_DATE")),
    }

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — کاربران
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/users")
async def admin_users(page: int = 1, limit: int = 20, search: Optional[str] = None,
                      admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    where, params = "", {"lim": limit, "off": (page - 1) * limit}
    if search:
        where = "WHERE username ILIKE :s OR first_name ILIKE :s OR last_name ILIKE :s"
        params["s"] = f"%{search}%"
        if search.isdigit():
            where += " OR telegram_id=:tid"
            params["tid"] = int(search)
    total = (await db.execute(text(f"SELECT COUNT(*) FROM users {where}"), params)).scalar()
    rows = (await db.execute(text(
        f"SELECT id,telegram_id,username,first_name,last_name,balance,is_banned,referral_count,created_at "
        f"FROM users {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"
    ), params)).mappings().all()
    return {"total": total, "page": page, "items": [row2dict(r) for r in rows]}

@app.post("/api/admin/users/{uid}/ban")
async def ban_user(uid: int, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await db.execute(text("UPDATE users SET is_banned=true WHERE id=:uid"), {"uid": uid})
    await db.commit()
    return {"ok": True}

@app.post("/api/admin/users/{uid}/unban")
async def unban_user(uid: int, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    await db.execute(text("UPDATE users SET is_banned=false WHERE id=:uid"), {"uid": uid})
    await db.commit()
    return {"ok": True}

class ChargeBody(BaseModel):
    amount: float
    note: Optional[str] = None

@app.post("/api/admin/users/{uid}/charge")
async def charge_user(uid: int, body: ChargeBody, admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = (await db.execute(text("SELECT balance FROM users WHERE id=:uid"), {"uid": uid})).first()
    if not r: raise HTTPException(404)
    new_bal = round(float(r[0] or 0) + body.amount, 6)
    await db.execute(text("UPDATE users SET balance=:b WHERE id=:uid"), {"b": new_bal, "uid": uid})
    await db.execute(text(
        "INSERT INTO transactions(user_id,type,amount,status,description,created_at) "
        "VALUES(:uid,'admin_charge',:amt,'completed',:desc,NOW())"
    ), {"uid": uid, "amt": body.amount, "desc": body.note or "Admin charge"})
    await db.commit()
    return {"ok": True, "new_balance": new_bal}

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — سفارشات پنل
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/admin/panel-orders")
async def admin_panel_orders(page: int = 1, limit: int = 20, status: Optional[str] = None,
                              admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    where = ("WHERE status=:st" if status else "")
    params = {"lim": limit, "off": (page - 1) * limit}
    if status: params["st"] = status
    total = (await db.execute(text(f"SELECT COUNT(*) FROM panel_orders {where}"), params)).scalar()
    rows = (await db.execute(text(
        f"SELECT id,user_id,panel_id,service_id,service_name,panel_name,quantity,unit_price,total_price,"
        f"link,note,status,completed_qty,refund_amount,admin_note,group_message_id,created_at,updated_at "
        f"FROM panel_orders {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"
    ), params)).mappings().all()
    return {"total": total, "page": page, "items": [row2dict(r) for r in rows]}

class UpdateOrderBody(BaseModel):
    status: str
    admin_note: Optional[str] = None
    completed_qty: Optional[int] = None

@app.patch("/api/admin/panel-orders/{oid}")
async def update_panel_order(oid: int, body: UpdateOrderBody,
                              admin=Depends(require_admin), db: AsyncSession = Depends(get_db)):
    r = (await db.execute(text(
        "SELECT po.*, u.balance as user_balance, u.id as user_db_id "
        "FROM panel_orders po JOIN users u ON u.id=po.user_id WHERE po.id=:oid"
    ), {"oid": oid})).mappings().first()
    if not r: raise HTTPException(404)
    order = dict(r)
    if order["status"] in ("completed", "rejected", "partial"):
        raise HTTPException(400, "Order already finalized")

    refund = 0.0
    if body.status == "rejected":
        refund = float(order["total_price"] or 0)
    elif body.status == "partial" and body.completed_qty is not None:
        done = min(body.completed_qty, order["quantity"])
        paid = float(order["unit_price"] or 0) * done
        refund = round(float(order["total_price"] or 0) - paid, 6)

    sets = ["status=:st", "updated_at=NOW()"]
    params = {"st": body.status, "oid": oid}
    if body.admin_note is not None:
        sets.append("admin_note=:note"); params["note"] = body.admin_note
    if body.completed_qty is not None:
        sets.append("completed_qty=:cq"); params["cq"] = body.completed_qty
    if refund > 0:
        sets.append("refund_amount=:ref"); params["ref"] = refund

    await db.execute(text(f"UPDATE panel_orders SET {', '.join(sets)} WHERE id=:oid"), params)

    if refund > 0:
        new_bal = round(float(order["user_balance"] or 0) + refund, 6)
        await db.execute(text("UPDATE users SET balance=:b WHERE id=:uid"),
                         {"b": new_bal, "uid": order["user_db_id"]})
        await db.execute(text(
            "INSERT INTO transactions(user_id,type,amount,status,description,created_at) "
            "VALUES(:uid,'refund',:amt,'completed',:desc,NOW())"
        ), {"uid": order["user_db_id"], "amt": refund,
            "desc": f"بازگشت وجه سفارش #{oid} — {body.status}"})

    await db.commit()
    return {"ok": True, "refund": refund}

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
