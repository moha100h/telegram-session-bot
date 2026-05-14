import asyncio
import json
import logging
import os
import random
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

API_ID       = int(os.getenv("API_ID", "0"))
API_HASH     = os.getenv("API_HASH", "")
REDIS_URL    = os.getenv("REDIS_URL", "redis://redis:6379")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR     = os.getenv("DATA_DIR", "/app/data")
TASK_QUEUE   = "tsb:task_queue"
TASK_FILE    = os.path.join(DATA_DIR, "tasks.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# PeerFlood cooldown per session (seconds)
PEER_FLOOD_COOLDOWN = 300   # 5 min rest then retry with next session
ADD_DELAY_MIN = 15          # min seconds between each add
ADD_DELAY_MAX = 30          # max seconds between each add


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


async def make_client(session_name: str, proxy: dict = None) -> TelegramClient:
    path = os.path.join(SESSIONS_DIR, session_name)
    kwargs = {}
    if proxy and proxy.get("type") in ("socks5", "socks4", "http"):
        try:
            kwargs["proxy"] = (proxy["type"], proxy["host"], int(proxy["port"]))
        except Exception:
            pass
    return TelegramClient(path, API_ID, API_HASH, **kwargs)


async def connect_client(session_name: str, proxy: dict = None) -> TelegramClient | None:
    if proxy:
        try:
            client = await make_client(session_name, proxy)
            await asyncio.wait_for(client.connect(), timeout=10)
            if await client.is_user_authorized():
                return client
            await client.disconnect()
        except Exception as e:
            logger.warning(f"[connect] proxy failed {session_name}: {e} -> direct")
            try:
                await client.disconnect()
            except Exception:
                pass
    try:
        client = await make_client(session_name, proxy=None)
        await asyncio.wait_for(client.connect(), timeout=15)
        if await client.is_user_authorized():
            return client
        await client.disconnect()
        return None
    except Exception as e:
        logger.error(f"[connect] {session_name} failed: {e}")
        try:
            await client.disconnect()
        except Exception:
            pass
        return None


async def get_proxy(redis: Redis) -> dict | None:
    try:
        data = await redis.lrange("tsb:proxies", 0, -1)
        if not data:
            return None
        return json.loads(random.choice(data))
    except Exception:
        return None


async def load_task(tid: str) -> dict | None:
    try:
        import aiofiles
        if not os.path.exists(TASK_FILE):
            return None
        async with aiofiles.open(TASK_FILE, "r") as f:
            raw = json.loads(await f.read())
        # support both list [{id:...}] and dict {tid:{...}} formats
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
            # support both list and dict formats
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


async def safe_disconnect(client):
    try:
        if client and client.is_connected():
            await client.disconnect()
    except Exception:
        pass


# ================================================================
# JOIN
# ================================================================
async def run_join(task: dict, redis: Redis):
    tid = task["id"]
    target = parse_target(task["target"])
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    logger.info(f"[join] task={tid} target={target} sessions={len(sessions)}")
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy  = await get_proxy(redis)
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(target)
            await client(JoinChannelRequest(entity))
            done += 1
            logger.info(f"[join] {session_name} -> {target} OK")
        except UserAlreadyParticipantError:
            done += 1
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error(f"[join] {session_name}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(2, 5))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})
    logger.info(f"[join] DONE task={tid} done={done} failed={failed}")


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
    logger.info(f"[g2g] task={tid} {source}->{dest} total={total} per={per_session} sessions={len(sessions)}")

    all_members = []
    for session_name in sessions:
        if all_members:
            break
        proxy  = await get_proxy(redis)
        client = await connect_client(session_name, proxy)
        if client is None:
            continue
        try:
            logger.info(f"[g2g] scraping {source} via {session_name} (need {total})")
            source_entity = await client.get_entity(source)
            async for user in client.iter_participants(source_entity, limit=total, aggressive=True):
                if user.bot or user.deleted or user.access_hash is None:
                    continue
                all_members.append(InputPeerUser(user.id, user.access_hash))
                if len(all_members) >= total:
                    break
            logger.info(f"[g2g] scraped {len(all_members)} members")
        except Exception as e:
            logger.error(f"[g2g] scrape error: {type(e).__name__}: {e}")
        finally:
            await safe_disconnect(client)
        await asyncio.sleep(1)

    if not all_members:
        await update_task(tid, {"status": "failed", "error": "no members scraped"})
        return

    remaining = list(all_members)
    for session_name in sessions:
        if not remaining:
            break
        if await is_cancelled(tid):
            break
        batch  = remaining[:per_session]
        proxy  = await get_proxy(redis)
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
                logger.error(f"[g2g] {session_name} join dest: {type(e).__name__}: {e}")
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
                    logger.warning(f"[g2g] {session_name} PeerFlood, switching session")
                    peer_flooded = True
                    failed += len(batch) - processed
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 180))
                except (UserPrivacyRestrictedError, UserBannedInChannelError,
                        InputUserDeactivatedError, UserNotMutualContactError):
                    failed += 1
                    processed += 1
                except Exception as e:
                    logger.error(f"[g2g] add {input_user.user_id}: {type(e).__name__}: {e}")
                    failed += 1
                    processed += 1

            remaining = remaining[processed:] if not peer_flooded else remaining[processed:]
            try:
                await client(LeaveChannelRequest(dest_entity))
            except Exception:
                pass
        finally:
            await safe_disconnect(client)
        await asyncio.sleep(random.uniform(5, 10))

    await update_task(tid, {"status": "completed", "done": done, "failed": failed})
    logger.info(f"[g2g] DONE task={tid} done={done} failed={failed}")


# ================================================================
# VIEW
# ================================================================
async def run_view(task: dict, redis: Redis):
    tid      = task["id"]
    link     = task["target"]
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    try:
        parts  = link.rstrip("/").split("/")
        msg_id = int(parts[-1])
        channel = parse_target("/".join(parts[:-1]))
    except Exception:
        await update_task(tid, {"status": "failed", "error": "invalid link"})
        return
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy  = await get_proxy(redis)
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(channel)
            await client(GetMessagesViewsRequest(peer=entity, id=[msg_id], increment=True))
            done += 1
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error(f"[view] {session_name}: {type(e).__name__}: {e}")
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
    link     = task["target"]
    emoji    = task.get("emoji", "👍")
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    try:
        parts   = link.rstrip("/").split("/")
        msg_id  = int(parts[-1])
        channel = parse_target("/".join(parts[:-1]))
    except Exception:
        await update_task(tid, {"status": "failed", "error": "invalid link"})
        return
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy  = await get_proxy(redis)
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
            logger.error(f"[reaction] {session_name}: {type(e).__name__}: {e}")
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
    logger.info(f"[leave] task={tid} target={target} sessions={len(sessions)}")
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy  = await get_proxy(redis)
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(target)
            await client(LeaveChannelRequest(entity))
            done += 1
            logger.info(f"[leave] {session_name} left {target}")
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error(f"[leave] {session_name}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(2, 5))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})
    logger.info(f"[leave] DONE task={tid} done={done} failed={failed}")


# ================================================================
# ADD BOT
# ================================================================
async def run_add_bot(task: dict, redis: Redis):
    """Each session sends /start to the target bot."""
    tid      = task["id"]
    target   = parse_target(task["target"])
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    logger.info(f"[add_bot] task={tid} target={target} sessions={len(sessions)}")
    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy  = await get_proxy(redis)
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(target)
            await client.send_message(entity, "/start")
            done += 1
            logger.info(f"[add_bot] {session_name} started {target}")
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error(f"[add_bot] {session_name}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(3, 8))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})
    logger.info(f"[add_bot] DONE task={tid} done={done} failed={failed}")


# ================================================================
# REPORT / BAN
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
    logger.info(f"[report] task={tid} target={target} reason={reason} sessions={len(sessions)}")

    reason_cls_name = REPORT_REASON_MAP.get(reason, "InputReportReasonSpam")
    reason_cls = getattr(tl_types, reason_cls_name, tl_types.InputReportReasonSpam)

    for session_name in sessions:
        if await is_cancelled(tid):
            break
        proxy  = await get_proxy(redis)
        client = await connect_client(session_name, proxy)
        if client is None:
            failed += 1
            await update_task(tid, {"done": done, "failed": failed})
            continue
        try:
            entity = await client.get_entity(target)
            await client(ReportPeerRequest(
                peer=entity,
                reason=reason_cls(),
                message=""
            ))
            done += 1
            logger.info(f"[report] {session_name} reported {target} ({reason})")
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error(f"[report] {session_name}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(3, 8))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})
    logger.info(f"[report] DONE task={tid} done={done} failed={failed}")


# ================================================================
# MAIN LOOP
# ================================================================
async def main():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    logger.info(f"Worker started | API_ID={API_ID} | SESSIONS_DIR={SESSIONS_DIR}")
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
                logger.error(f"JSON parse error: {e}")
                continue
            tid = task.get("id", "?")
            t = await load_task(tid)
            if t and t.get("status") == "cancelled":
                continue
            task_type = task.get("type")
            handler   = handlers.get(task_type)
            if handler:
                logger.info(f">>> Starting task id={tid} type={task_type}")
                try:
                    await handler(task, redis)
                except Exception as e:
                    logger.error(f"Handler {task_type} crashed: {e}")
                    await update_task(tid, {"status": "failed", "error": str(e)})
            else:
                logger.warning(f"Unknown task type: {task_type}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker loop error: {type(e).__name__}: {e}")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
