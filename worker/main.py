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
    SessionPasswordNeededError, AuthKeyUnregisteredError,
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


def parse_target(target: str):
    target = target.strip().rstrip("/")
    if target.startswith("https://t.me/") or target.startswith("http://t.me/"):
        path = target.split("t.me/", 1)[1]
        if path.startswith("+") or path.startswith("joinchat/"):
            return target
        parts = path.split("/")
        username = parts[0]
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
    """Connect with proxy, fallback to direct."""
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
            logger.info(f"[connect] {session_name} direct OK")
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
            return json.loads(await f.read()).get(tid)
    except Exception:
        return None


async def update_task(tid: str, data: dict):
    import aiofiles
    for _ in range(3):
        try:
            tasks = {}
            if os.path.exists(TASK_FILE):
                async with aiofiles.open(TASK_FILE, "r") as f:
                    tasks = json.loads(await f.read())
            if tid in tasks:
                tasks[tid].update(data)
            async with aiofiles.open(TASK_FILE, "w") as f:
                await f.write(json.dumps(tasks, ensure_ascii=False, indent=2))
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
        proxy = await get_proxy(redis)
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
        await asyncio.sleep(random.uniform(3, 8))

    await update_task(tid, {"status": "completed", "done": done, "failed": failed})
    logger.info(f"[join] DONE task={tid} done={done} failed={failed}")


# ================================================================
# GROUP TO GROUP
# Flow per session:
#   1. Join source group
#   2. Collect members (up to per_session)
#   3. Join dest group
#   4. Add members by InputPeerUser
#   5. Leave source group
# ================================================================
async def run_group2group(task: dict, redis: Redis):
    tid        = task["id"]
    source     = parse_target(task["source"])
    dest       = parse_target(task["dest"])
    total      = int(task["count"])
    per_session = int(task.get("per_session", 20))
    sessions   = task.get("sessions", [])

    await update_task(tid, {"status": "running"})
    done = failed = 0
    global_offset = 0   # how many members we've already processed

    logger.info(f"[g2g] task={tid} {source}->{dest} total={total} per={per_session} sessions={len(sessions)}")

    for session_name in sessions:
        if global_offset >= total:
            break
        if await is_cancelled(tid):
            break

        proxy  = await get_proxy(redis)
        client = await connect_client(session_name, proxy)
        if client is None:
            logger.warning(f"[g2g] {session_name}: cannot connect, skip")
            continue

        joined_source = False
        try:
            # ---- 1. Join source ----
            try:
                source_entity = await client.get_entity(source)
                await client(JoinChannelRequest(source_entity))
                joined_source = True
                logger.info(f"[g2g] {session_name} joined source {source}")
                await asyncio.sleep(2)
            except UserAlreadyParticipantError:
                source_entity = await client.get_entity(source)
                joined_source = True
            except Exception as e:
                logger.error(f"[g2g] {session_name} join source failed: {type(e).__name__}: {e}")
                continue

            # ---- 2. Collect members (skip already processed) ----
            members = []
            try:
                async for user in client.iter_participants(
                    source_entity,
                    limit=global_offset + per_session + 50,  # overfetch
                    aggressive=True
                ):
                    if user.bot or user.deleted:
                        continue
                    if len(members) < global_offset:
                        # skip already processed
                        # (iter_participants returns from beginning)
                        pass
                    else:
                        members.append(user)
                    if len(members) >= per_session:
                        break
                logger.info(f"[g2g] {session_name} collected {len(members)} members (offset={global_offset})")
            except Exception as e:
                logger.error(f"[g2g] {session_name} collect error: {type(e).__name__}: {e}")

            if not members:
                logger.warning(f"[g2g] {session_name} no members to add")
                continue

            # ---- 3. Join dest ----
            try:
                dest_entity = await client.get_entity(dest)
                await client(JoinChannelRequest(dest_entity))
                logger.info(f"[g2g] {session_name} joined dest {dest}")
                await asyncio.sleep(2)
            except UserAlreadyParticipantError:
                dest_entity = await client.get_entity(dest)
            except Exception as e:
                logger.error(f"[g2g] {session_name} join dest failed: {type(e).__name__}: {e}")
                continue

            # ---- 4. Add members ----
            session_blocked = False
            for user in members:
                if await is_cancelled(tid) or session_blocked:
                    break
                try:
                    # Use InputPeerUser for reliable add
                    input_user = InputPeerUser(user.id, user.access_hash)
                    await client(InviteToChannelRequest(dest_entity, [input_user]))
                    done += 1
                    global_offset += 1
                    logger.info(f"[g2g] added user_id={user.id} ({done}/{total})")
                    await asyncio.sleep(random.uniform(4, 9))
                except UserAlreadyParticipantError:
                    done += 1
                    global_offset += 1
                except FloodWaitError as e:
                    wait = min(e.seconds, 120)
                    logger.warning(f"[g2g] FloodWait {e.seconds}s, sleeping {wait}s")
                    await asyncio.sleep(wait)
                    failed += 1
                    global_offset += 1
                except UserPrivacyRestrictedError:
                    logger.debug(f"[g2g] user {user.id} privacy restricted")
                    failed += 1
                    global_offset += 1
                except (InputUserDeactivatedError, UserNotMutualContactError):
                    failed += 1
                    global_offset += 1
                except (PeerFloodError, UserBannedInChannelError,
                        ChatWriteForbiddenError, ChatAdminRequiredError) as e:
                    logger.warning(f"[g2g] {session_name} blocked: {type(e).__name__}")
                    session_blocked = True
                    failed += len(members) - members.index(user)
                    global_offset += len(members) - members.index(user)
                except Exception as e:
                    logger.error(f"[g2g] add user {user.id}: {type(e).__name__}: {e}")
                    failed += 1
                    global_offset += 1
                await update_task(tid, {"done": done, "failed": failed})

        except Exception as e:
            logger.error(f"[g2g] {session_name} outer error: {type(e).__name__}: {e}")
        finally:
            # ---- 5. Leave source ----
            if joined_source:
                try:
                    src_ent = await client.get_entity(source)
                    await client(LeaveChannelRequest(src_ent))
                    logger.info(f"[g2g] {session_name} left source {source}")
                except Exception as e:
                    logger.warning(f"[g2g] {session_name} leave source error: {e}")
            await safe_disconnect(client)

        await asyncio.sleep(random.uniform(10, 20))

    await update_task(tid, {"status": "completed", "done": done, "failed": failed})
    logger.info(f"[g2g] DONE task={tid} done={done} failed={failed} total_processed={global_offset}")


# ================================================================
# VIEW
# ================================================================
async def run_view(task: dict, redis: Redis):
    tid = task["id"]
    target = task["target"].rstrip("/")
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    parts = target.split("/")
    try:
        msg_id  = int(parts[-1])
        channel = parse_target("/".join(parts[:-1]))
    except Exception:
        await update_task(tid, {"status": "failed", "error": "invalid link"})
        return
    logger.info(f"[view] task={tid} {channel}/{msg_id} sessions={len(sessions)}")
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
            logger.info(f"[view] {session_name} OK")
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
    logger.info(f"[view] DONE task={tid} done={done} failed={failed}")


# ================================================================
# REACTION
# ================================================================
async def run_reaction(task: dict, redis: Redis):
    tid = task["id"]
    target = task["target"].rstrip("/")
    emoji  = task.get("emoji", "👍")
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    parts = target.split("/")
    try:
        msg_id  = int(parts[-1])
        channel = parse_target("/".join(parts[:-1]))
    except Exception:
        await update_task(tid, {"status": "failed", "error": "invalid link"})
        return
    logger.info(f"[reaction] task={tid} {channel}/{msg_id} emoji={emoji}")
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
            logger.info(f"[reaction] {session_name} OK")
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 60))
            failed += 1
        except Exception as e:
            logger.error(f"[reaction] {session_name}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            await safe_disconnect(client)
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(2, 5))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})
    logger.info(f"[reaction] DONE task={tid} done={done} failed={failed}")


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
                logger.info(f"Task {tid} cancelled, skip")
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
