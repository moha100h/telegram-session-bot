"""
Backup Service — PostgreSQL dump + sessions + data → zip → Telegram group.
"""
import asyncio, gzip, io, json, logging, os, shutil, subprocess, tempfile, zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.types import BufferedInputFile

from db.database import AsyncSessionLocal
from services.settings_service import get_setting, set_setting

logger = logging.getLogger("backup_service")

SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR",     "/app/data")
DB_HOST      = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT      = os.getenv("POSTGRES_PORT", "5432")
DB_NAME      = os.getenv("POSTGRES_DB",   "smmbot")
DB_USER      = os.getenv("POSTGRES_USER", "smm")
DB_PASS      = os.getenv("POSTGRES_PASSWORD", "smm123")
REDIS_HOST   = os.getenv("REDIS_HOST", "redis")
REDIS_PORT   = os.getenv("REDIS_PORT", "6379")
VERSION      = "2.0"


def _fmt_size(b: int) -> str:
    for unit in ("B","KB","MB","GB"):
        if b < 1024: return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def _dir_size(path: str) -> int:
    total = 0
    for p in Path(path).rglob("*"):
        if p.is_file():
            try: total += p.stat().st_size
            except OSError: pass
    return total

async def _get_db_stats() -> dict:
    try:
        from sqlalchemy import text
        async with AsyncSessionLocal() as session:
            tables = {}
            for tbl in ("users","orders","transactions","admin_users","admin_settings"):
                try:
                    r = await session.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
                    tables[tbl] = r.scalar()
                except Exception: tables[tbl] = -1
        return tables
    except Exception as e: return {"error": str(e)}

def _pg_dump() -> bytes:
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS
    proc = subprocess.run(
        ["pg_dump","-h",DB_HOST,"-p",DB_PORT,"-U",DB_USER,"-d",DB_NAME,
         "--no-password","--format=plain","--encoding=UTF8"],
        capture_output=True, env=env, timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {proc.stderr.decode()[:300]}")
    return gzip.compress(proc.stdout)

def _redis_dump() -> Optional[bytes]:
    try:
        import redis as redis_sync
        r = redis_sync.Redis(host=REDIS_HOST, port=int(REDIS_PORT), decode_responses=False)
        r.bgsave()
        import time
        for _ in range(20):
            info = r.info("persistence")
            if info.get("rdb_bgsave_in_progress", 1) == 0: break
            time.sleep(0.5)
        rdb_path = info.get("rdb_filename", "/data/dump.rdb")
        if not os.path.isabs(rdb_path): rdb_path = f"/data/{rdb_path}"
        if os.path.exists(rdb_path):
            with open(rdb_path,"rb") as f: return f.read()
    except Exception as e: logger.warning(f"Redis dump skipped: {e}")
    return None

async def create_backup(label: str = "auto") -> tuple:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{label}_{ts}.zip"
    stats = {"timestamp": ts, "label": label, "version": VERSION, "files": {}}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        # 1. PostgreSQL
        try:
            sql_gz = _pg_dump()
            zf.writestr(f"db/database_{ts}.sql.gz", sql_gz)
            stats["files"]["database"] = _fmt_size(len(sql_gz))
        except Exception as e:
            stats["files"]["database"] = f"ERROR: {e}"
            logger.error(f"DB dump error: {e}")
        # 2. Sessions
        sess_path = Path(SESSIONS_DIR)
        if sess_path.exists():
            count = 0
            for fp in sess_path.rglob("*"):
                if fp.is_file():
                    try: zf.write(fp, f"sessions/{fp.relative_to(sess_path)}"); count += 1
                    except Exception: pass
            stats["files"]["sessions"] = f"{count} files ({_fmt_size(_dir_size(SESSIONS_DIR))})"
        # 3. Data
        data_path = Path(DATA_DIR)
        if data_path.exists():
            count = 0
            for fp in data_path.rglob("*"):
                if fp.is_file():
                    try: zf.write(fp, f"data/{fp.relative_to(data_path)}"); count += 1
                    except Exception: pass
            stats["files"]["data"] = f"{count} files ({_fmt_size(_dir_size(DATA_DIR))})"
        # 4. Redis
        rdb = _redis_dump()
        if rdb:
            zf.writestr("redis/dump.rdb", rdb)
            stats["files"]["redis"] = _fmt_size(len(rdb))
        # 5. Metadata
        stats["db_tables"] = await _get_db_stats()
        zf.writestr("metadata.json", json.dumps(stats, ensure_ascii=False, indent=2))
    zip_bytes = buf.getvalue()
    stats["total_size"] = _fmt_size(len(zip_bytes))
    logger.info(f"Backup created: {filename} ({stats['total_size']})")
    return zip_bytes, filename, stats

async def send_backup_to_group(bot: Bot, zip_bytes: bytes, filename: str, stats: dict) -> bool:
    async with AsyncSessionLocal() as session:
        group_id_str = await get_setting(session, "backup_group_id", "")
    if not group_id_str: return False
    try:
        group_id = int(group_id_str)
    except ValueError: return False
    db_info = "\n".join(f"  \u2022 {k}: <b>{v}</b>" for k,v in stats.get("db_tables",{}).items() if k!="error")
    files_info = "\n".join(f"  \u2022 {k}: <code>{v}</code>" for k,v in stats.get("files",{}).items())
    caption = (
        f"\U0001f5c4 <b>Backup \u2014 {stats['label'].upper()}</b>\n"
        f"\U0001f4c5 <code>{stats['timestamp'].replace('_',' ')}</code>\n"
        f"\U0001f4e6 \u062d\u062c\u0645 \u06a9\u0644: <code>{stats.get('total_size','?')}</code>\n\n"
        f"\U0001f4ca <b>\u062c\u062f\u0627\u0648\u0644 DB:</b>\n{db_info}\n\n"
        f"\U0001f4c1 <b>\u0641\u0627\u06cc\u0644\u200c\u0647\u0627:</b>\n{files_info}\n\n"
        f"\U0001f516 \u0646\u0633\u062e\u0647: <code>v{VERSION}</code>"
    )
    doc = BufferedInputFile(zip_bytes, filename=filename)
    await bot.send_document(chat_id=group_id, document=doc, caption=caption, parse_mode="HTML")
    logger.info(f"Backup sent to group {group_id}")
    return True

async def restore_from_zip(zip_bytes: bytes) -> dict:
    result = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(tmpdir)
        meta_path = os.path.join(tmpdir, "metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f: result["metadata"] = json.load(f)
        else: result["metadata"] = "not found"
        # DB restore
        db_dir = os.path.join(tmpdir, "db")
        if os.path.exists(db_dir):
            sql_files = list(Path(db_dir).glob("*.sql.gz"))
            if sql_files:
                try:
                    with gzip.open(sql_files[0],"rb") as f: sql_data = f.read()
                    env = os.environ.copy(); env["PGPASSWORD"] = DB_PASS
                    subprocess.run(
                        ["psql","-h",DB_HOST,"-p",DB_PORT,"-U",DB_USER,"-d","postgres","-c",
                         f"DROP DATABASE IF EXISTS {DB_NAME}; CREATE DATABASE {DB_NAME};"],
                        env=env, capture_output=True, timeout=30
                    )
                    proc = subprocess.run(
                        ["psql","-h",DB_HOST,"-p",DB_PORT,"-U",DB_USER,"-d",DB_NAME],
                        input=sql_data, env=env, capture_output=True, timeout=300
                    )
                    result["database"] = "\u2705 \u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc \u0634\u062f" if proc.returncode==0 else f"\u26a0\ufe0f {proc.stderr.decode()[:200]}"
                except Exception as e: result["database"] = f"\u274c {e}"
            else: result["database"] = "\u0641\u0627\u06cc\u0644 SQL \u06cc\u0627\u0641\u062a \u0646\u0634\u062f"
        # Sessions
        sess_src = os.path.join(tmpdir,"sessions")
        if os.path.exists(sess_src):
            try:
                if os.path.exists(SESSIONS_DIR): shutil.rmtree(SESSIONS_DIR)
                shutil.copytree(sess_src, SESSIONS_DIR)
                count = sum(1 for _ in Path(SESSIONS_DIR).rglob("*") if _.is_file())
                result["sessions"] = f"\u2705 {count} \u0641\u0627\u06cc\u0644 \u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc \u0634\u062f"
            except Exception as e: result["sessions"] = f"\u274c {e}"
        # Data
        data_src = os.path.join(tmpdir,"data")
        if os.path.exists(data_src):
            try:
                if os.path.exists(DATA_DIR): shutil.rmtree(DATA_DIR)
                shutil.copytree(data_src, DATA_DIR)
                count = sum(1 for _ in Path(DATA_DIR).rglob("*") if _.is_file())
                result["data"] = f"\u2705 {count} \u0641\u0627\u06cc\u0644 \u0628\u0627\u0632\u06af\u0631\u062f\u0627\u0646\u06cc \u0634\u062f"
            except Exception as e: result["data"] = f"\u274c {e}"
    return result

_scheduler_task: Optional[asyncio.Task] = None

async def _scheduler_loop(bot: Bot):
    logger.info("Backup scheduler started")
    while True:
        try:
            async with AsyncSessionLocal() as session:
                interval_str = await get_setting(session, "backup_interval_hours", "1")
                enabled      = await get_setting(session, "backup_auto_enabled",   "1")
            if enabled != "1":
                await asyncio.sleep(300); continue
            await asyncio.sleep(max(1, int(interval_str)) * 3600)
            zip_bytes, filename, stats = await create_backup("auto")
            await send_backup_to_group(bot, zip_bytes, filename, stats)
            async with AsyncSessionLocal() as session:
                await set_setting(session, "backup_last_at",
                                  datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
                await session.commit()
        except asyncio.CancelledError: break
        except Exception as e:
            logger.error(f"Backup scheduler error: {e}")
            await asyncio.sleep(60)

def start_scheduler(bot: Bot):
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done(): return
    _scheduler_task = asyncio.create_task(_scheduler_loop(bot))

def stop_scheduler():
    global _scheduler_task
    if _scheduler_task: _scheduler_task.cancel(); _scheduler_task = None
