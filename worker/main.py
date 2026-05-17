import asyncio
import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from redis.asyncio import Redis
from telethon import TelegramClient
from telethon.tl.functions.channels import (
    JoinChannelRequest, InviteToChannelRequest, LeaveChannelRequest
)
from telethon.tl.functions.messages import GetMessagesViewsRequest, SendReactionRequest
from telethon.tl.types import ReactionEmoji, InputPeerUser
from telethon.errors import (
    FloodWaitError, UserPrivacyRestrictedError,
    UserAlreadyParticipantError, PeerFloodError,
    ChatWriteForbiddenError, UserBannedInChannelError,
    ChatAdminRequiredError, UserNotMutualContactError,
    InputUserDeactivatedError
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("worker")

API_ID        = int(os.getenv("API_ID", "0"))
API_HASH      = os.getenv("API_HASH", "")
DATABASE_URL  = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")  # sync-style for worker
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))
REDIS_URL    = os.getenv("REDIS_URL", "redis://redis:6379")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR", "/app/data")
TASK_QUEUE   = "tsb:task_queue"
TASK_FILE    = os.path.join(DATA_DIR, "tasks.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

PEER_FLOOD_COOLDOWN = 300
ADD_DELAY_MIN = 15
ADD_DELAY_MAX = 30

WARM_CHANNELS = [
    "@telegram", "@durov", "@TelegramTips",
    "@cryptocurrency", "@python", "@linux",
]
WARM_ACTIONS_PER_DAY = [3, 5, 8, 12, 18, 25]
WARM_DAYS_TO_FULL    = 6


# ================================================================
# PROXY MANAGEMENT
# ================================================================

async def ping_proxy(host: str, port: int, timeout: float = 3.0) -> float:
    try:
        t0 = time.monotonic()
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        latency = (time.monotonic() - t0) * 1000
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return round(latency, 1)
    except Exception:
        return 9999.0


async def get_best_proxy(redis: Redis, exclude_hosts: set = None, top_n: int = 20) -> dict | None:
    try:
        total = await redis.llen("tsb:proxies")
        if total == 0:
            return None
        sample_size = min(top_n * 3, total)
        indices = random.sample(range(total), sample_size)
        raws = await asyncio.gather(*[redis.lindex("tsb:proxies", i) for i in indices])
        candidates = []
        for raw in raws:
            if not raw:
                continue
            try:
                p = json.loads(raw)
                if exclude_hosts and p.get("host") in exclude_hosts:
                    continue
                candidates.append(p)
            except Exception:
                pass
        if not candidates:
            for raw in raws:
                if not raw:
                    continue
                try:
                    candidates.append(json.loads(raw))
                except Exception:
                    pass
        if not candidates:
            return None
        to_ping = candidates[:top_n]
        pings = await asyncio.gather(*[
            ping_proxy(p["host"], int(p["port"])) for p in to_ping
        ])
        best_proxy = None
        best_ping  = 9999.0
        for proxy, ping in zip(to_ping, pings):
            if ping < best_ping:
                best_ping  = ping
                best_proxy = proxy
        if best_proxy and best_ping < 5000:
            best_proxy["_ping_ms"] = best_ping
            return best_proxy
        return None
    except Exception as e:
        logger.warning("[get_best_proxy] %s", e)
        return None


async def get_proxy(redis: Redis) -> dict | None:
    try:
        total = await redis.llen("tsb:proxies")
        if not total:
            return None
        raw = await redis.lindex("tsb:proxies", random.randint(0, total - 1))
        return json.loads(raw) if raw else None
    except Exception:
        return None


# ================================================================
# SESSION HELPERS
# ================================================================

def get_session_files() -> list:
    names = []
    if os.path.exists(SESSIONS_DIR):
        for fn in os.listdir(SESSIONS_DIR):
            if fn.endswith(".session"):
                names.append(fn.replace(".session", ""))
    return sorted(names)


def load_sessions_meta() -> dict:
    path = os.path.join(DATA_DIR, "sessions.json")
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def parse_target(target: str):
    target = target.strip().rstrip("/")
    if target.startswith("https://t.me/") or target.startswith("http://t.me/"):
        path = target.split("t.me/", 1)[1]
        if path.startswith("+") or path.startswith("joinchat/"):
            return target
        username = path.split("/")[0]
        return "@" + username if not username.startswith("@") else username
    if target.lstrip("-").isdigit():
        return int(target)
    if not target.startswith("@"):
        return "@" + target
    return target


# ================================================================
# SQLITE FIX — WAL mode + busy_timeout
# ================================================================

def _patch_sqlite(client, timeout_ms: int = 10000):
    """
    Enable WAL journal mode and set busy_timeout on the SQLite session.
    Prevents 'database is locked' when bot and worker access same .session file.
    """
    try:
        session = client.session
        if hasattr(session, "_conn") and session._conn:
            session._conn.execute(f"PRAGMA busy_timeout = {timeout_ms}")
            session._conn.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass


async def make_client(session_name: str, proxy: dict = None) -> TelegramClient:
    path = os.path.join(SESSIONS_DIR, session_name)
    kwargs = {
        "connection_retries": 3,
        "retry_delay": 2,
        "request_retries": 3,
    }
    if proxy and proxy.get("type") in ("socks5", "socks4", "http"):
        try:
            kwargs["proxy"] = (proxy["type"], proxy["host"], int(proxy["port"]))
        except Exception:
            pass
    return TelegramClient(path, API_ID, API_HASH, **kwargs)


# Per-session lock — prevents concurrent SQLite access ("database is locked")
_session_locks: dict = {}

def _get_session_lock(name: str) -> asyncio.Lock:
    if name not in _session_locks:
        _session_locks[name] = asyncio.Lock()
    return _session_locks[name]


async def connect_client(session_name: str, proxy: dict = None) -> TelegramClient | None:
    if proxy:
        try:
            client = await make_client(session_name, proxy)
            await asyncio.wait_for(client.connect(), timeout=10)
            _patch_sqlite(client)
            if await client.is_user_authorized():
                return client
            await client.disconnect()
        except Exception as e:
            logger.warning("[connect] proxy failed %s: %s -> direct", session_name, e)
            try:
                await client.disconnect()
            except Exception:
                pass
    try:
        client = await make_client(session_name, proxy=None)
        await asyncio.wait_for(client.connect(), timeout=15)
        _patch_sqlite(client)
        if await client.is_user_authorized():
            return client
        await client.disconnect()
        return None
    except Exception as e:
        logger.error("[connect] %s failed: %s", session_name, e)
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


async def safe_disconnect(client):
    try:
        if client and client.is_connected():
            await client.disconnect()
    except Exception:
        pass


# ================================================================
# TASK FILE HELPERS
# ================================================================

async def load_task(tid: str) -> dict | None:
    try:
        import aiofiles
        if not os.path.exists(TASK_FILE):
            return None
        async with aiofiles.open(TASK_FILE, "r") as f:
            raw = json.loads(await f.read())
        if isinstance(raw, list):
            for t in raw:
                if t.get("id") == tid:
                    return t
            return None
        return raw.get(tid)
    except Exception:
        return None


async def update_task(tid: str, data: dict):
    import aiofiles
    for _ in range(3):
        try:
            raw = []
            if os.path.exists(TASK_FILE):
                async with aiofiles.open(TASK_FILE, "r") as f:
                    raw = json.loads(await f.read())
            if isinstance(raw, list):
                for t in raw:
                    if t.get("id") == tid:
                        t.update(data)
                        break
                async with aiofiles.open(TASK_FILE, "w") as f:
                    await f.write(json.dumps(raw, ensure_ascii=False, indent=2))
            else:
                if tid in raw:
                    raw[tid].update(data)
                async with aiofiles.open(TASK_FILE, "w") as f:
                    await f.write(json.dumps(raw, ensure_ascii=False, indent=2))
            return
        except Exception:
            await asyncio.sleep(0.1)


async def is_cancelled(tid: str) -> bool:
    t = await load_task(tid)
    return t is not None and t.get("status") == "cancelled"


# ================================================================
# WARMING ENGINE
# ================================================================

async def get_warm_state(redis: Redis, name: str) -> dict:
    raw = await redis.get("warm:session:" + name)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {
        "phase": "new",
        "day": 0,
        "score": 0,
        "total_actions": 0,
        "last_active": None,
        "proxy_host": None,
    }


async def save_warm_state(redis: Redis, name: str, state: dict):
    await redis.set("warm:session:" + name, json.dumps(state))


async def warm_one_session(redis: Redis, name: str, proxy: dict | None):
    state = await get_warm_state(redis, name)
    day   = state.get("day", 0)
    idx   = min(day, len(WARM_ACTIONS_PER_DAY) - 1)
    target_actions = WARM_ACTIONS_PER_DAY[idx]

    logger.info("[warm] %s day=%d target=%d proxy=%s",
                name, day, target_actions,
                proxy.get("host") + ":" + str(proxy.get("port")) if proxy else "direct")

    state["phase"]      = "warming"
    state["proxy_host"] = proxy.get("host") if proxy else None
    await save_warm_state(redis, name, state)

    client = await connect_client(name, proxy)
    if client is None:
        logger.warning("[warm] %s could not connect", name)
        state["phase"] = "new"
        await save_warm_state(redis, name, state)
        return

    actions_done = 0
    channels = random.sample(WARM_CHANNELS, min(len(WARM_CHANNELS), target_actions))

    try:
        for ch in channels:
            try:
                entity = await client.get_entity(ch)
                try:
                    await client(JoinChannelRequest(entity))
                    await asyncio.sleep(random.uniform(2, 5))
                except UserAlreadyParticipantError:
                    pass
                except Exception:
                    pass
                msgs = await client.get_messages(entity, limit=3)
                if msgs:
                    try:
                        await client(GetMessagesViewsRequest(
                            peer=entity,
                            id=[m.id for m in msgs],
                            increment=True
                        ))
                    except Exception:
                        pass
                    await asyncio.sleep(random.uniform(3, 8))
                    try:
                        react_emojis = ["\U0001f44d", "\u2764", "\U0001f525", "\U0001f44f"]
                        await client(SendReactionRequest(
                            peer=entity,
                            msg_id=msgs[0].id,
                            reaction=[ReactionEmoji(emoticon=random.choice(react_emojis))]
                        ))
                    except Exception:
                        pass
                actions_done += 1
                await asyncio.sleep(random.uniform(5, 15))
            except FloodWaitError as e:
                logger.warning("[warm] %s FloodWait %ds", name, e.seconds)
                await asyncio.sleep(min(e.seconds, 60))
            except Exception as e:
                logger.warning("[warm] %s action error: %s", name, e)
            if actions_done >= target_actions:
                break
    finally:
        await safe_disconnect(client)

    state["day"]           = day + 1
    state["total_actions"] = state.get("total_actions", 0) + actions_done
    state["last_active"]   = datetime.now(timezone.utc).isoformat()
    state["score"]         = min(20, state.get("score", 0) + actions_done)
    state["phase"]         = "warm" if state["day"] >= WARM_DAYS_TO_FULL else "warming"
    await save_warm_state(redis, name, state)
    logger.info("[warm] %s done: day=%d score=%d phase=%s",
                name, state["day"], state["score"], state["phase"])


async def run_warming(redis: Redis, sessions: list = None):
    if sessions is None:
        sessions = get_session_files()
    if not sessions:
        logger.info("[warm] No sessions to warm")
        return
    logger.info("[warm] Starting warming cycle for %d sessions", len(sessions))
    used_hosts: set = set()
    for name in sessions:
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts, top_n=30)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
            logger.info("[warm] %s -> proxy %s:%s ping=%.1fms",
                        name, proxy["host"], proxy["port"], proxy.get("_ping_ms", 0))
        else:
            logger.warning("[warm] %s no proxy available, using direct", name)
        await warm_one_session(redis, name, proxy)
        await asyncio.sleep(random.uniform(10, 30))
    logger.info("[warm] Warming cycle complete")


async def auto_warmer(redis: Redis):
    logger.info("[auto_warmer] Started - first cycle in 60s")
    await asyncio.sleep(60)
    while True:
        try:
            sessions = get_session_files()
            if sessions:
                logger.info("[auto_warmer] Daily cycle for %d sessions", len(sessions))
                await run_warming(redis, sessions)
            else:
                logger.info("[auto_warmer] No sessions found, skipping")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[auto_warmer] error: %s", e)
        await asyncio.sleep(24 * 3600)


# ================================================================
# JOIN
# ================================================================
async def run_join(task: dict, redis: Redis):
    tid      = task["id"]
    target   = parse_target(task["target"])
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    used_hosts: set = set()
    logger.info("[join] task=%s target=%s sessions=%d", tid, target, len(sessions))
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(target)
            await client(JoinChannelRequest(entity))
            done += 1
        except UserAlreadyParticipantError:
            done += 1
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error("[join] %s: %s: %s", session_name, type(e).__name__, e)
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(2, 5))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ================================================================
# GROUP TO GROUP
# ================================================================
async def run_group2group(task: dict, redis: Redis):
    tid         = task["id"]
    source      = parse_target(task["source"])
    dest        = parse_target(task.get("target", task.get("dest", "")))
    total       = int(task["count"])
    per_session = int(task.get("per_session", 10))
    sessions    = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    used_hosts: set = set()
    for session_name in sessions:
        if all_members := []:
            break
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
        client = await connect_client(session_name, proxy)
        if client is None:
            continue
        try:
            source_entity = await client.get_entity(source)
            all_members = []
            async for user in client.iter_participants(source_entity, limit=total, aggressive=True):
                if user.bot or user.deleted or user.access_hash is None:
                    continue
                all_members.append(InputPeerUser(user.id, user.access_hash))
                if len(all_members) >= total:
                    break
        except Exception as e:
            logger.error("[g2g] scrape error: %s", e)
            all_members = []
        finally:
            await safe_disconnect(client)
        if all_members:
            break
        await asyncio.sleep(1)

    if not all_members:
        await update_task(tid, {"status": "failed", "error": "no members scraped"})
        return

    remaining = list(all_members)
    for session_name in sessions:
        if not remaining or await is_cancelled(tid):
            break
        batch = remaining[:per_session]
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += len(batch)
            remaining = remaining[per_session:]
            await update_task(tid, {"done": done, "failed": failed})
            continue
        peer_flooded = False
        try:
            try:
                dest_entity = await client.get_entity(dest)
                await client(JoinChannelRequest(dest_entity))
                await asyncio.sleep(random.uniform(2, 4))
            except UserAlreadyParticipantError:
                dest_entity = await client.get_entity(dest)
            except Exception as e:
                failed += len(batch)
                remaining = remaining[per_session:]
                continue
            processed = 0
            for input_user in batch:
                if await is_cancelled(tid) or peer_flooded:
                    break
                try:
                    await client(InviteToChannelRequest(dest_entity, [input_user]))
                    done += 1
                    processed += 1
                    await update_task(tid, {"done": done, "failed": failed})
                    await asyncio.sleep(random.uniform(ADD_DELAY_MIN, ADD_DELAY_MAX))
                except UserAlreadyParticipantError:
                    done += 1
                    processed += 1
                except PeerFloodError:
                    peer_flooded = True
                    failed += len(batch) - processed
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 180))
                except (UserPrivacyRestrictedError, UserBannedInChannelError,
                        InputUserDeactivatedError, UserNotMutualContactError):
                    failed += 1
                    processed += 1
                except Exception as e:
                    failed += 1
                    processed += 1
            remaining = remaining[processed:]
            try:
                await client(LeaveChannelRequest(dest_entity))
            except Exception:
                pass
        finally:
            await safe_disconnect(client)
        await asyncio.sleep(random.uniform(5, 10))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ================================================================
# VIEW
# ================================================================
async def run_view(task: dict, redis: Redis):
    tid      = task["id"]
    channel  = parse_target(task["target"])
    msg_id   = int(task.get("msg_id", 0))
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    used_hosts: set = set()
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(channel)
            ids = [msg_id] if msg_id else [m.id for m in await client.get_messages(entity, limit=5)]
            await client(GetMessagesViewsRequest(peer=entity, id=ids, increment=True))
            done += 1
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error("[view] %s: %s", session_name, e)
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(1, 3))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ================================================================
# REACTION
# ================================================================
async def run_reaction(task: dict, redis: Redis):
    tid      = task["id"]
    channel  = parse_target(task["target"])
    msg_id   = int(task.get("msg_id", 0))
    emoji    = task.get("emoji", "\U0001f44d")
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    used_hosts: set = set()
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(channel)
            await client(SendReactionRequest(
                peer=entity,
                msg_id=msg_id,
                reaction=[ReactionEmoji(emoticon=emoji)]
            ))
            done += 1
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error("[reaction] %s: %s", session_name, e)
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(1, 3))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ================================================================
# LEAVE
# ================================================================
async def run_leave(task: dict, redis: Redis):
    tid      = task["id"]
    target   = parse_target(task["target"])
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    used_hosts: set = set()
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(target)
            await client(LeaveChannelRequest(entity))
            done += 1
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error("[leave] %s: %s", session_name, e)
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(2, 5))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ================================================================
# ADD BOT
# ================================================================
async def run_add_bot(task: dict, redis: Redis):
    tid      = task["id"]
    target   = parse_target(task["target"])
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    used_hosts: set = set()
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(target)
            await client.send_message(entity, "/start")
            done += 1
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error("[add_bot] %s: %s", session_name, e)
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(3, 8))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ================================================================
# REPORT
# ================================================================
REPORT_REASON_MAP = {
    "spam":     "InputReportReasonSpam",
    "illegal":  "InputReportReasonIllegalDrugs",
    "violence": "InputReportReasonViolence",
    "other":    "InputReportReasonOther",
}

async def run_report(task: dict, redis: Redis):
    from telethon.tl.functions.account import ReportPeerRequest
    from telethon.tl import types as tl_types
    tid      = task["id"]
    target   = parse_target(task["target"])
    reason   = task.get("reason", "spam")
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    used_hosts: set = set()
    reason_cls_name = REPORT_REASON_MAP.get(reason, "InputReportReasonSpam")
    reason_cls = getattr(tl_types, reason_cls_name, tl_types.InputReportReasonSpam)
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy = await get_best_proxy(redis, exclude_hosts=used_hosts)
        if proxy:
            used_hosts.add(proxy.get("host", ""))
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(target)
            await client(ReportPeerRequest(peer=entity, reason=reason_cls(), message=""))
            done += 1
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error("[report] %s: %s", session_name, e)
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(3, 8))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ================================================================
# PROXY TEST
# ================================================================
async def _test_proxies_task(redis: Redis):
    try:
        total  = await redis.llen("tsb:proxies")
        sample = min(50, total)
        logger.info("[proxy_test] Testing %d/%d proxies...", sample, total)
        indices = random.sample(range(total), sample)
        raws    = await asyncio.gather(*[redis.lindex("tsb:proxies", i) for i in indices])
        proxies = [json.loads(r) for r in raws if r]
        pings   = await asyncio.gather(*[
            ping_proxy(p["host"], int(p["port"])) for p in proxies
        ])
        alive = sum(1 for p in pings if p < 5000)
        avg   = round(sum(p for p in pings if p < 5000) / max(alive, 1), 1)
        logger.info("[proxy_test] alive=%d/%d avg_ping=%.1fms", alive, sample, avg)
        await redis.set("tsb:proxy_test_result", json.dumps({
            "total": total, "tested": sample, "alive": alive,
            "avg_ping_ms": avg,
            "ts": datetime.now(timezone.utc).isoformat()
        }))
    except Exception as e:
        logger.error("[proxy_test] %s", e)


# ================================================================

# ================================================================
# ORDER AUTO-CANCEL LOOP
# ================================================================
async def order_auto_cancel_loop():
    """
    هر 30 دقیقه سفارشات قدیمی‌تر از N ساعت رو چک می‌کنه.
    N از جدول admin_settings خونده میشه (کلید: order_auto_cancel_hours).
    پیش‌فرض: 48 ساعت.
    اگه N=0 باشه، auto-cancel غیرفعاله.
    """
    import aiohttp
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, text

    DB_URL = os.getenv("DATABASE_URL", "")
    if not DB_URL:
        logger.warning("[auto_cancel] DATABASE_URL not set — loop disabled")
        return

    engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    logger.info("[auto_cancel] Loop started — checking every 30 min")
    await asyncio.sleep(60)  # اولین چک بعد از 1 دقیقه از start

    while True:
        try:
            async with AsyncSessionLocal() as session:
                # خواندن تنظیم N ساعت
                res = await session.execute(
                    text("SELECT value FROM admin_settings WHERE key = 'order_auto_cancel_hours'")
                )
                row = res.fetchone()
                try:
                    hours = int(row[0]) if row and row[0] else 48
                except Exception:
                    hours = 48

                if hours <= 0:
                    logger.info("[auto_cancel] Disabled (hours=0)")
                    await asyncio.sleep(1800)
                    continue

                # پیدا کردن سفارشات stale
                from datetime import timedelta
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
                res2 = await session.execute(
                    text(
                        "SELECT id, api_order_id, user_id, service_name, sell_price, quantity "
                        "FROM orders "
                        "WHERE status IN ('pending', 'processing', 'in progress') "
                        "  AND created_at <= :cutoff "
                        "ORDER BY created_at ASC"
                    ),
                    {"cutoff": cutoff}
                )
                stale = res2.fetchall()

            if stale:
                logger.info("[auto_cancel] Found %d stale orders (>%dh)", len(stale), hours)

            for row in stale:
                order_id, api_order_id, user_id, svc_name, sell_price, quantity = row
                sell_price = float(sell_price or 0)

                # ── کنسل از SMMPass API ───────────────────────────────────────
                api_error = None
                if api_order_id and str(api_order_id).isdigit():
                    try:
                        from services.smmpass import cancel_order as smm_cancel
                        await smm_cancel(int(api_order_id))
                        logger.info("[auto_cancel] API cancel OK — order #%d api_id=%s",
                                    order_id, api_order_id)
                    except Exception as e:
                        api_error = str(e)[:80]
                        logger.warning("[auto_cancel] API cancel failed order #%d: %s",
                                       order_id, api_error)
                else:
                    api_error = "no api_order_id"

                # ── آپدیت DB + refund ─────────────────────────────────────────
                refunded = 0.0
                try:
                    async with AsyncSessionLocal() as session:
                        # وضعیت رو cancelled کن
                        await session.execute(
                            text("UPDATE orders SET status='cancelled', "
                                 "updated_at=NOW() WHERE id=:oid"),
                            {"oid": order_id}
                        )
                        # موجودی کاربر رو برگردون
                        await session.execute(
                            text("UPDATE users SET balance = balance + :amt WHERE id=:uid"),
                            {"amt": sell_price, "uid": user_id}
                        )
                        # ثبت تراکنش refund
                        await session.execute(
                            text(
                                "INSERT INTO transactions "
                                "(user_id, type, amount, status, method, description, created_at) "
                                "VALUES (:uid, 'refund', :amt, 'approved', 'auto', :desc, NOW())"
                            ),
                            {
                                "uid":  user_id,
                                "amt":  sell_price,
                                "desc": f"Auto-cancel refund for order #{order_id} (>{hours}h)",
                            }
                        )
                        await session.commit()
                        refunded = sell_price
                        logger.info("[auto_cancel] Refunded $%.4f to user %d for order #%d",
                                    refunded, user_id, order_id)
                except Exception as e:
                    logger.error("[auto_cancel] DB update failed order #%d: %s", order_id, e)
                    continue

                # ── اطلاع‌رسانی به کاربر از طریق Bot API ─────────────────────
                if BOT_TOKEN and user_id:
                    try:
                        msg = (
                            f"⏰ <b>سفارش #{order_id} به‌صورت خودکار کنسل شد</b>\n\n"
                            f"🛒 {svc_name}\n"
                            f"⏳ سفارش بیش از <b>{hours} ساعت</b> در صف ماند و پردازش نشد.\n"
                            f"💰 <b>${refunded:.4f}</b> به موجودی شما برگشت داده شد."
                        )
                        async with aiohttp.ClientSession() as http:
                            await http.post(
                                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                json={"chat_id": user_id, "text": msg, "parse_mode": "HTML"},
                                timeout=aiohttp.ClientTimeout(total=10)
                            )
                    except Exception as e:
                        logger.warning("[auto_cancel] Notify user %d failed: %s", user_id, e)

                await asyncio.sleep(0.5)  # throttle بین سفارشات

        except asyncio.CancelledError:
            logger.info("[auto_cancel] Loop cancelled")
            break
        except Exception as e:
            logger.error("[auto_cancel] Unexpected error: %s", e)

        await asyncio.sleep(1800)  # هر 30 دقیقه


# MAIN LOOP
# ================================================================
async def main():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Worker started | API_ID=%d | SESSIONS_DIR=%s", API_ID, SESSIONS_DIR)
    warmer_bg      = asyncio.create_task(auto_warmer(redis))
    auto_cancel_bg = asyncio.create_task(order_auto_cancel_loop())
    handlers = {
        "join":        run_join,
        "group2group": run_group2group,
        "view":        run_view,
        "reaction":    run_reaction,
        "leave":       run_leave,
        "add_bot":     run_add_bot,
        "report":      run_report,
    }
    while True:
        try:
            item = await redis.blpop(TASK_QUEUE, timeout=5)
            if not item:
                continue
            _, raw = item
            try:
                task = json.loads(raw)
            except Exception as e:
                logger.error("JSON parse error: %s", e)
                continue
            task_type = task.get("type")
            if task_type == "start_warming":
                sessions = task.get("sessions") or get_session_files()
                logger.info("[main] Manual warming for %d sessions", len(sessions))
                asyncio.create_task(run_warming(redis, sessions))
                continue
            if task_type == "test_proxies":
                asyncio.create_task(_test_proxies_task(redis))
                continue
            tid = task.get("id", "?")
            t   = await load_task(tid)
            if t and t.get("status") == "cancelled":
                continue
            handler = handlers.get(task_type)
            if handler:
                logger.info(">>> Starting task id=%s type=%s", tid, task_type)
                try:
                    await handler(task, redis)
                except Exception as e:
                    logger.error("Handler %s crashed: %s", task_type, e)
                    await update_task(tid, {"status": "failed", "error": str(e)})
            else:
                logger.warning("Unknown task type: %s", task_type)
        except asyncio.CancelledError:
            warmer_bg.cancel()
            auto_cancel_bg.cancel()
            break
        except Exception as e:
            logger.error("Worker loop error: %s: %s", type(e).__name__, e)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
