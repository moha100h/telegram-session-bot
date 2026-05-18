"""Backup Service v3.0"""
import asyncio, gzip, hashlib, io, json, logging, os, shutil, subprocess, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from aiogram import Bot
from aiogram.types import BufferedInputFile
from db.database import AsyncSessionLocal
from services.settings_service import get_setting, set_setting

logger = logging.getLogger("backup_service")
SESSIONS_DIR = os.getenv("SESSIONS_DIR",      "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR",          "/app/data")
BACKUP_DIR   = os.getenv("BACKUP_DIR",        "/app/data/backups")
DB_HOST      = os.getenv("POSTGRES_HOST",     "postgres")
DB_PORT      = os.getenv("POSTGRES_PORT",     "5432")
DB_NAME      = os.getenv("POSTGRES_DB",       "smmbot")
DB_USER      = os.getenv("POSTGRES_USER",     "smm")
DB_PASS      = os.getenv("POSTGRES_PASSWORD", "smm123")
REDIS_HOST   = os.getenv("REDIS_HOST",        "redis")
REDIS_PORT   = os.getenv("REDIS_PORT",        "6379")
VERSION      = "3.0"
ALL_TABLES   = ["users","orders","transactions","admin_users","admin_settings",
                "panels","panel_categories","panel_services","panel_orders","verification_codes"]
MAX_LOCAL_BACKUPS = 10

def _fmt_size(b):
    for u in ("B","KB","MB","GB"):
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def _dir_size(path):
    total = 0
    for p in Path(path).rglob("*"):
        if p.is_file():
            try: total += p.stat().st_size
            except: pass
    return total

def _sha256(data): return hashlib.sha256(data).hexdigest()
def _ensure_backup_dir(): Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)

def _cleanup_local_backups():
    _ensure_backup_dir()
    files = sorted(Path(BACKUP_DIR).glob("backup_*.zip"), key=lambda f: f.stat().st_mtime)
    while len(files) > MAX_LOCAL_BACKUPS:
        try:
            old = files.pop(0); old.unlink()
            s = Path(str(old)+".sha256")
            if s.exists(): s.unlink()
        except: pass

async def _get_db_stats():
    from sqlalchemy import text
    stats = {}
    async with AsyncSessionLocal() as s:
        for t in ALL_TABLES:
            try: r = await s.execute(text(f"SELECT COUNT(*) FROM {t}")); stats[t] = r.scalar()
            except: stats[t] = "N/A"
    return stats

def _pg_dump():
    env = os.environ.copy(); env["PGPASSWORD"] = DB_PASS
    p = subprocess.run(
        ["pg_dump","-h",DB_HOST,"-p",DB_PORT,"-U",DB_USER,"-d",DB_NAME,
         "--no-password","--format=plain","--encoding=UTF8","--no-owner","--no-acl","--clean","--if-exists"],
        capture_output=True, env=env, timeout=180)
    if p.returncode != 0: raise RuntimeError(f"pg_dump: {p.stderr.decode()[:300]}")
    return gzip.compress(p.stdout, compresslevel=9)

async def _json_export():
    from sqlalchemy import text
    exp = {"version":VERSION,"exported_at":datetime.now(timezone.utc).isoformat(),"tables":{}}
    async with AsyncSessionLocal() as s:
        for t in ALL_TABLES:
            try:
                r = await s.execute(text(f"SELECT * FROM {t}"))
                cols = list(r.keys())
                rows = [{k:(v.isoformat() if hasattr(v,"isoformat") else v) for k,v in zip(cols,row)} for row in r.fetchall()]
                exp["tables"][t] = {"columns":cols,"rows":rows,"count":len(rows)}
            except Exception as e: exp["tables"][t] = {"error":str(e)}
    return gzip.compress(json.dumps(exp,ensure_ascii=False,indent=2,default=str).encode(),compresslevel=9)

def _redis_dump():
    try:
        import redis as rs, time
        r = rs.Redis(host=REDIS_HOST,port=int(REDIS_PORT),decode_responses=False)
        r.bgsave()
        for _ in range(30):
            info = r.info("persistence")
            if not info.get("rdb_bgsave_in_progress",1): break
            time.sleep(0.5)
        p = info.get("rdb_filename","/data/dump.rdb")
        if not os.path.isabs(p): p = f"/data/{p}"
        if os.path.exists(p):
            with open(p,"rb") as f: return f.read()
    except Exception as e: logger.warning(f"Redis dump skipped: {e}")
    return None

async def create_backup(label="auto"):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fn = f"backup_{label}_{ts}.zip"
    stats = {"timestamp":ts,"label":label,"version":VERSION,"files":{},"errors":[]}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as zf:
        try:
            sg = _pg_dump(); zf.writestr(f"db/database_{ts}.sql.gz",sg)
            stats["files"]["postgresql"] = _fmt_size(len(sg))
        except Exception as e: stats["errors"].append(f"pg: {e}"); logger.error(e)
        try:
            jg = await _json_export(); zf.writestr(f"db/export_{ts}.json.gz",jg)
            stats["files"]["json_export"] = _fmt_size(len(jg))
        except Exception as e: stats["errors"].append(f"json: {e}"); logger.error(e)
        sp = Path(SESSIONS_DIR)
        if sp.exists():
            c = 0
            for fp in sp.rglob("*"):
                if fp.is_file():
                    try: zf.write(fp,f"sessions/{fp.relative_to(sp)}"); c+=1
                    except: pass
            stats["files"]["sessions"] = f"{c} files / {_fmt_size(_dir_size(SESSIONS_DIR))}"
        dp = Path(DATA_DIR)
        if dp.exists():
            c = 0
            for fp in dp.rglob("*"):
                if fp.is_file() and BACKUP_DIR not in str(fp):
                    try: zf.write(fp,f"data/{fp.relative_to(dp)}"); c+=1
                    except: pass
            stats["files"]["app_data"] = f"{c} files"
        rdb = _redis_dump()
        if rdb: zf.writestr("redis/dump.rdb",rdb); stats["files"]["redis"] = _fmt_size(len(rdb))
        else: stats["files"]["redis"] = "skipped"
        stats["db_tables"] = await _get_db_stats()
        stats["checksum_sha256"] = "pending"
        zf.writestr("metadata.json",json.dumps(stats,ensure_ascii=False,indent=2,default=str))
    zb = buf.getvalue(); ck = _sha256(zb)
    stats.update({"checksum_sha256":ck,"total_size":_fmt_size(len(zb)),"total_bytes":len(zb)})
    try:
        _ensure_backup_dir(); lp = Path(BACKUP_DIR)/fn
        lp.write_bytes(zb); Path(str(lp)+".sha256").write_text(ck)
        stats["local_path"] = str(lp); _cleanup_local_backups()
    except Exception as e: stats["errors"].append(f"local: {e}")
    logger.info(f"Backup: {fn} ({stats['total_size']}) sha256={ck[:16]}...")
    return zb, fn, stats

async def send_backup_to_group(bot, zip_bytes, filename, stats):
    async with AsyncSessionLocal() as s:
        gid_str = await get_setting(s,"backup_group_id","")
    if not gid_str: return False
    try: gid = int(gid_str)
    except: return False
    NL = "\n"
    db_r  = NL.join(f"  \u2022 {k}: <b>{v}</b>"       for k,v in stats.get("db_tables",{}).items())
    fi_r  = NL.join(f"  \u2022 {k}: <code>{v}</code>" for k,v in stats.get("files",{}).items())
    er_r  = ""
    if stats.get("errors"):
        er_r = NL+"\u26a0\ufe0f <b>Errors:</b>"+NL+NL.join(f"  \u2022 {e}" for e in stats["errors"])
    cap = (
        "\U0001f5c4 <b>Backup \u2014 "+stats["label"].upper()+"</b>"+NL
        +"\U0001f4c5 <code>"+stats["timestamp"].replace("_"," ")+" UTC</code>"+NL
        +"\U0001f4e6 Size: <code>"+stats.get("total_size","?")+"</code>"+NL
        +"\U0001f510 SHA-256: <code>"+stats.get("checksum_sha256","")[:32]+"...</code>"+NL+NL
        +"\U0001f4ca <b>DB:</b>"+NL+db_r+NL+NL
        +"\U0001f4c1 <b>Files:</b>"+NL+fi_r+er_r+NL+NL
        +"\U0001f516 v"+VERSION
    )
    try:
        await bot.send_document(chat_id=gid,document=BufferedInputFile(zip_bytes,filename=filename),caption=cap,parse_mode="HTML")
        return True
    except Exception as e: logger.error(f"Send failed: {e}"); return False

async def restore_from_zip(zip_bytes, verify_checksum=""):
    result = {"steps":{},"errors":[],"success":False}
    actual = _sha256(zip_bytes)
    if verify_checksum:
        if actual != verify_checksum: result["errors"].append(f"checksum mismatch"); return result
        result["steps"]["checksum"] = "\u2705 verified"
    else: result["steps"]["checksum"] = f"\u26a0\ufe0f not verified ({actual[:16]}...)"
    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf: zf.extractall(tmp)
        except Exception as e: result["errors"].append(f"zip: {e}"); return result
        mp = os.path.join(tmp,"metadata.json")
        result["metadata"] = json.load(open(mp)) if os.path.exists(mp) else {}
        dd = os.path.join(tmp,"db")
        sqls = sorted(Path(dd).glob("*.sql.gz")) if os.path.exists(dd) else []
        if sqls:
            try:
                sql = gzip.open(sqls[0],"rb").read()
                env = os.environ.copy(); env["PGPASSWORD"] = DB_PASS
                p = subprocess.run(["psql","-h",DB_HOST,"-p",DB_PORT,"-U",DB_USER,"-d",DB_NAME,"--set","ON_ERROR_STOP=0"],
                                   input=sql,env=env,capture_output=True,timeout=300)
                se = p.stderr.decode()
                result["steps"]["database"] = "\u2705 restored" if p.returncode==0 or "ERROR" not in se else f"\u26a0\ufe0f {se[:200]}"
            except Exception as e: result["steps"]["database"] = f"\u274c {e}"; result["errors"].append(str(e))
        ss = os.path.join(tmp,"sessions")
        if os.path.exists(ss):
            try:
                if os.path.exists(SESSIONS_DIR):
                    bk = SESSIONS_DIR+"_pre_restore"
                    if os.path.exists(bk): shutil.rmtree(bk)
                    shutil.copytree(SESSIONS_DIR,bk); shutil.rmtree(SESSIONS_DIR)
                shutil.copytree(ss,SESSIONS_DIR)
                c = sum(1 for _ in Path(SESSIONS_DIR).rglob("*") if _.is_file())
                result["steps"]["sessions"] = f"\u2705 {c} files"
            except Exception as e: result["steps"]["sessions"] = f"\u274c {e}"; result["errors"].append(str(e))
        ds = os.path.join(tmp,"data")
        if os.path.exists(ds):
            try:
                dest = Path(DATA_DIR); dest.mkdir(parents=True,exist_ok=True); c=0
                for fp in Path(ds).rglob("*"):
                    if fp.is_file():
                        d = dest/fp.relative_to(ds); d.parent.mkdir(parents=True,exist_ok=True)
                        shutil.copy2(fp,d); c+=1
                result["steps"]["app_data"] = f"\u2705 {c} files"
            except Exception as e: result["steps"]["app_data"] = f"\u274c {e}"; result["errors"].append(str(e))
        rs = os.path.join(tmp,"redis","dump.rdb")
        if os.path.exists(rs):
            try: shutil.copy2(rs,"/data/dump.rdb"); result["steps"]["redis"] = "\u2705 restored"
            except Exception as e: result["steps"]["redis"] = f"\u26a0\ufe0f {e}"
    result["success"] = not result["errors"]
    return result

def list_local_backups():
    _ensure_backup_dir()
    files = sorted(Path(BACKUP_DIR).glob("backup_*.zip"),key=lambda f:f.stat().st_mtime,reverse=True)
    out = []
    for f in files:
        sf = Path(str(f)+".sha256"); ck = sf.read_text().strip() if sf.exists() else ""
        out.append({"filename":f.name,"path":str(f),"size":_fmt_size(f.stat().st_size),
                    "mtime":datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "checksum":ck[:16]+"..." if ck else "unknown"})
    return out

_scheduler_task: Optional[asyncio.Task] = None

async def _scheduler_loop(bot):
    logger.info("Backup scheduler started")
    while True:
        try:
            async with AsyncSessionLocal() as s:
                iv  = await get_setting(s,"backup_interval_hours","1")
                ena = await get_setting(s,"backup_auto_enabled","1")
            if ena != "1": await asyncio.sleep(300); continue
            await asyncio.sleep(max(1,int(iv))*3600)
            zb,fn,st = await create_backup("auto")
            sent = await send_backup_to_group(bot,zb,fn,st)
            async with AsyncSessionLocal() as s:
                await set_setting(s,"last_backup_time",datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
                await set_setting(s,"last_backup_size",st.get("total_size","?"))
                await set_setting(s,"last_backup_status","\u2705 OK" if sent else "\u26a0\ufe0f saved locally")
                await s.commit()
        except asyncio.CancelledError: break
        except Exception as e: logger.error(f"Scheduler error: {e}"); await asyncio.sleep(600)

def start_scheduler(bot):
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done(): return
    _scheduler_task = asyncio.create_task(_scheduler_loop(bot))

def stop_scheduler():
    global _scheduler_task
    if _scheduler_task: _scheduler_task.cancel(); _scheduler_task = None
