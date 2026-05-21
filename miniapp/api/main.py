"""MiniApp API — FastAPI backend for Telegram WebApp"""
import os, hmac, hashlib, json, logging
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, func, desc, update, text
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("miniapp")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))
DB_URL    = os.getenv("DATABASE_URL", "postgresql+asyncpg://smm:smm123@postgres:5432/smmbot")

engine = create_async_engine(DB_URL, pool_pre_ping=True, pool_size=5)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI(title="TSB MiniApp API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Telegram WebApp Auth ──────────────────────────────────────────────────────
def verify_telegram_webapp(init_data: str) -> dict:
    try:
        parsed = {}
        for part in init_data.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                from urllib.parse import unquote
                parsed[k] = unquote(v)
        hash_val = parsed.pop("hash", "")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, hash_val):
            raise ValueError("Invalid hash")
        return json.loads(parsed.get("user", "{}"))
    except Exception as ex:
        raise HTTPException(status_code=401, detail=f"Unauthorized: {ex}")

async def get_db():
    async with SessionLocal() as s:
        yield s

async def _get_user_by_tg(db, tg_id):
    r = await db.execute(text("SELECT * FROM users WHERE telegram_id=:tid"), {"tid": tg_id})
    row = r.mappings().first()
    return dict(row) if row else None

async def _get_admin_by_tg(db, tg_id):
    r = await db.execute(text("SELECT * FROM admin_users WHERE telegram_id=:tid"), {"tid": tg_id})
    row = r.mappings().first()
    return dict(row) if row else None

async def get_current_user(x_init_data: str = Header(..., alias="X-Init-Data"), db: AsyncSession = Depends(get_db)):
    tg = verify_telegram_webapp(x_init_data)
    user = await _get_user_by_tg(db, tg.get("id"))
    if not user: raise HTTPException(404, "User not found")
    return user

async def get_admin(x_init_data: str = Header(..., alias="X-Init-Data"), db: AsyncSession = Depends(get_db)):
    tg = verify_telegram_webapp(x_init_data)
    tg_id = tg.get("id")
    if tg_id != ADMIN_ID:
        adm = await _get_admin_by_tg(db, tg_id)
        if not adm: raise HTTPException(403, "Not admin")
    user = await _get_user_by_tg(db, tg_id)
    return user

# ── USER ──────────────────────────────────────────────────────────────────────
@app.get("/api/user/me")
async def user_me(user=Depends(get_current_user)):
    return {k: (str(v) if isinstance(v, datetime) else v) for k,v in user.items()}

@app.get("/api/user/orders")
async def user_orders(page:int=1, limit:int=20, status:Optional[str]=None,
                      user=Depends(get_current_user), db:AsyncSession=Depends(get_db)):
    where = "WHERE user_id=:uid" + (f" AND status=:st" if status else "")
    params = {"uid": user["id"]}
    if status: params["st"] = status
    total = (await db.execute(text(f"SELECT COUNT(*) FROM orders {where}"), params)).scalar()
    rows  = (await db.execute(text(f"SELECT * FROM orders {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
                              {**params,"lim":limit,"off":(page-1)*limit})).mappings().all()
    return {"total": total, "page": page, "items": [{k:(str(v) if isinstance(v,datetime) else v) for k,v in r.items()} for r in rows]}

@app.get("/api/user/panel-orders")
async def user_panel_orders(page:int=1, limit:int=20, status:Optional[str]=None,
                             user=Depends(get_current_user), db:AsyncSession=Depends(get_db)):
    where = "WHERE user_id=:uid" + (" AND status=:st" if status else "")
    params = {"uid": user["id"]}
    if status: params["st"] = status
    total = (await db.execute(text(f"SELECT COUNT(*) FROM panel_orders {where}"), params)).scalar()
    rows  = (await db.execute(text(f"SELECT * FROM panel_orders {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
                              {**params,"lim":limit,"off":(page-1)*limit})).mappings().all()
    return {"total": total, "page": page, "items": [{k:(str(v) if isinstance(v,datetime) else v) for k,v in r.items()} for r in rows]}

@app.get("/api/user/transactions")
async def user_transactions(page:int=1, limit:int=20,
                             user=Depends(get_current_user), db:AsyncSession=Depends(get_db)):
    params = {"uid": user["id"], "lim": limit, "off": (page-1)*limit}
    total = (await db.execute(text("SELECT COUNT(*) FROM transactions WHERE user_id=:uid"), {"uid":user["id"]})).scalar()
    rows  = (await db.execute(text("SELECT * FROM transactions WHERE user_id=:uid ORDER BY created_at DESC LIMIT :lim OFFSET :off"), params)).mappings().all()
    return {"total": total, "page": page, "items": [{k:(str(v) if isinstance(v,datetime) else v) for k,v in r.items()} for r in rows]}

# ── ADMIN ─────────────────────────────────────────────────────────────────────
@app.get("/api/admin/stats")
async def admin_stats(admin=Depends(get_admin), db:AsyncSession=Depends(get_db)):
    async def sc(q, p={}): return (await db.execute(text(q), p)).scalar() or 0
    return {
        "total_users":        await sc("SELECT COUNT(*) FROM users"),
        "banned_users":       await sc("SELECT COUNT(*) FROM users WHERE is_banned=true"),
        "active_users":       await sc("SELECT COUNT(*) FROM users WHERE is_banned=false"),
        "total_orders":       await sc("SELECT COUNT(*) FROM orders"),
        "pending_orders":     await sc("SELECT COUNT(*) FROM orders WHERE status='pending'"),
        "completed_orders":   await sc("SELECT COUNT(*) FROM orders WHERE status='completed'"),
        "total_revenue":      float(await sc("SELECT COALESCE(SUM(sell_price),0) FROM orders WHERE status='completed'")),
        "total_balance":      float(await sc("SELECT COALESCE(SUM(balance),0) FROM users")),
        "total_panel_orders": await sc("SELECT COUNT(*) FROM panel_orders"),
        "pending_panel_orders": await sc("SELECT COUNT(*) FROM panel_orders WHERE status='pending'"),
        "today_orders":       await sc("SELECT COUNT(*) FROM orders WHERE created_at >= CURRENT_DATE"),
        "today_revenue":      float(await sc("SELECT COALESCE(SUM(sell_price),0) FROM orders WHERE status='completed' AND created_at >= CURRENT_DATE")),
    }

@app.get("/api/admin/users")
async def admin_users(page:int=1, limit:int=20, search:Optional[str]=None,
                      admin=Depends(get_admin), db:AsyncSession=Depends(get_db)):
    where = ""
    params = {"lim": limit, "off": (page-1)*limit}
    if search:
        where = "WHERE username ILIKE :s OR first_name ILIKE :s OR last_name ILIKE :s"
        params["s"] = f"%{search}%"
        if search.isdigit():
            where += " OR telegram_id=:tid"
            params["tid"] = int(search)
    total = (await db.execute(text(f"SELECT COUNT(*) FROM users {where}"), params)).scalar()
    rows  = (await db.execute(text(f"SELECT * FROM users {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"), params)).mappings().all()
    return {"total": total, "page": page, "items": [{k:(str(v) if isinstance(v,datetime) else v) for k,v in r.items()} for r in rows]}

@app.post("/api/admin/users/{uid}/ban")
async def ban_user(uid:int, admin=Depends(get_admin), db:AsyncSession=Depends(get_db)):
    await db.execute(text("UPDATE users SET is_banned=true WHERE id=:uid"), {"uid":uid})
    await db.commit(); return {"ok": True}

@app.post("/api/admin/users/{uid}/unban")
async def unban_user(uid:int, admin=Depends(get_admin), db:AsyncSession=Depends(get_db)):
    await db.execute(text("UPDATE users SET is_banned=false WHERE id=:uid"), {"uid":uid})
    await db.commit(); return {"ok": True}

class ChargeBody(BaseModel):
    amount: float; note: Optional[str] = None

@app.post("/api/admin/users/{uid}/charge")
async def charge_user(uid:int, body:ChargeBody, admin=Depends(get_admin), db:AsyncSession=Depends(get_db)):
    r = (await db.execute(text("SELECT balance FROM users WHERE id=:uid"), {"uid":uid})).first()
    if not r: raise HTTPException(404)
    new_bal = float(r[0] or 0) + body.amount
    await db.execute(text("UPDATE users SET balance=:b WHERE id=:uid"), {"b":new_bal,"uid":uid})
    await db.execute(text("INSERT INTO transactions(user_id,type,amount,status,description,created_at) VALUES(:uid,:tp,:am,:st,:desc,NOW())"),
                     {"uid":uid,"tp":"admin_charge","am":body.amount,"st":"completed","desc":body.note or "Admin charge"})
    await db.commit()
    return {"ok": True, "new_balance": new_bal}

@app.get("/api/admin/panel-orders")
async def admin_panel_orders(page:int=1, limit:int=20, status:Optional[str]=None,
                              admin=Depends(get_admin), db:AsyncSession=Depends(get_db)):
    where = ("WHERE status=:st" if status else "")
    params = {"lim":limit,"off":(page-1)*limit}
    if status: params["st"] = status
    total = (await db.execute(text(f"SELECT COUNT(*) FROM panel_orders {where}"), params)).scalar()
    rows  = (await db.execute(text(f"SELECT * FROM panel_orders {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"), params)).mappings().all()
    return {"total": total, "page": page, "items": [{k:(str(v) if isinstance(v,datetime) else v) for k,v in r.items()} for r in rows]}

class UpdateOrderBody(BaseModel):
    status: str; admin_note: Optional[str] = None; completed_qty: Optional[int] = None

@app.patch("/api/admin/panel-orders/{oid}")
async def update_panel_order(oid:int, body:UpdateOrderBody, admin=Depends(get_admin), db:AsyncSession=Depends(get_db)):
    sets = ["status=:st", "updated_at=NOW()"]
    params = {"st": body.status, "oid": oid}
    if body.admin_note is not None: sets.append("admin_note=:note"); params["note"] = body.admin_note
    if body.completed_qty is not None: sets.append("completed_qty=:cq"); params["cq"] = body.completed_qty
    await db.execute(text(f"UPDATE panel_orders SET {', '.join(sets)} WHERE id=:oid"), params)
    await db.commit(); return {"ok": True}

@app.get("/api/admin/transactions")
async def admin_transactions(page:int=1, limit:int=20, status:Optional[str]=None,
                              admin=Depends(get_admin), db:AsyncSession=Depends(get_db)):
    where = ("WHERE status=:st" if status else "")
    params = {"lim":limit,"off":(page-1)*limit}
    if status: params["st"] = status
    total = (await db.execute(text(f"SELECT COUNT(*) FROM transactions {where}"), params)).scalar()
    rows  = (await db.execute(text(f"SELECT * FROM transactions {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"), params)).mappings().all()
    return {"total": total, "page": page, "items": [{k:(str(v) if isinstance(v,datetime) else v) for k,v in r.items()} for r in rows]}

@app.get("/api/health")
async def health(): return {"status": "ok"}
