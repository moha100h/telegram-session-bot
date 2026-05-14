import asyncio
import json
import logging
import os
import random
from redis.asyncio import Redis
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest, InviteToChannelRequest
from telethon.tl.functions.messages import GetMessagesViewsRequest, SendReactionRequest
from telethon.tl.types import ReactionEmoji
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, UserAlreadyParticipantError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("worker")

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/app/sessions")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
TASK_QUEUE = "tsb:task_queue"
TASK_FILE = os.path.join(DATA_DIR, "tasks.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)


async def get_client(session_name: str, proxy: dict = None) -> TelegramClient:
    path = os.path.join(SESSIONS_DIR, session_name)
    kwargs = {}
    if proxy and proxy.get("type") in ("socks5", "socks4", "http"):
        kwargs["proxy"] = (proxy["type"], proxy["host"], int(proxy["port"]))
    return TelegramClient(path, API_ID, API_HASH, **kwargs)


async def get_proxy(redis: Redis) -> dict | None:
    data = await redis.lrange("tsb:proxies", 0, -1)
    if not data:
        return None
    return json.loads(random.choice(data))


async def update_task(task_id: str, data: dict):
    import aiofiles
    if not os.path.exists(TASK_FILE):
        return
    async with aiofiles.open(TASK_FILE, "r") as f:
        tasks = json.loads(await f.read())
    if task_id in tasks:
        tasks[task_id].update(data)
    async with aiofiles.open(TASK_FILE, "w") as f:
        await f.write(json.dumps(tasks, ensure_ascii=False, indent=2))


# ── JOIN TASK ────────────────────────────────────────────────────
async def run_join(task: dict, redis: Redis):
    tid = task["id"]
    target = task["target"]
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    for session_name in sessions:
        t = await _load_task(tid)
        if t and t.get("status") == "cancelled":
            break
        proxy = await get_proxy(redis)
        try:
            client = await get_client(session_name, proxy)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                failed += 1
                continue
            entity = await client.get_entity(target)
            await client(JoinChannelRequest(entity))
            done += 1
            logger.info(f"[join] {session_name} joined {target}")
            await client.disconnect()
        except FloodWaitError as e:
            logger.warning(f"[join] FloodWait {e.seconds}s for {session_name}")
            await asyncio.sleep(e.seconds)
            failed += 1
        except UserAlreadyParticipantError:
            done += 1
        except Exception as e:
            logger.error(f"[join] {session_name} error: {e}")
            failed += 1
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(3, 8))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


async def _load_task(tid: str) -> dict | None:
    import aiofiles
    if not os.path.exists(TASK_FILE):
        return None
    async with aiofiles.open(TASK_FILE, "r") as f:
        tasks = json.loads(await f.read())
    return tasks.get(tid)


# ── GROUP TO GROUP ───────────────────────────────────────────────
async def run_group2group(task: dict, redis: Redis):
    tid = task["id"]
    source = task["source"]
    dest = task["dest"]
    total = task["count"]
    per_session = task.get("per_session", 20)
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    # Get members from source group using first available session
    members = []
    for session_name in sessions:
        proxy = await get_proxy(redis)
        try:
            client = await get_client(session_name, proxy)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                continue
            source_entity = await client.get_entity(source)
            async for user in client.iter_participants(source_entity, limit=total):
                if not user.bot and user.username:
                    members.append(user)
                if len(members) >= total:
                    break
            await client.disconnect()
            if members:
                break
        except Exception as e:
            logger.error(f"[g2g] get members error: {e}")
    if not members:
        await update_task(tid, {"status": "failed", "error": "no members found"})
        return
    # Add members to dest using sessions in batches
    member_idx = 0
    for session_name in sessions:
        if member_idx >= len(members):
            break
        t = await _load_task(tid)
        if t and t.get("status") == "cancelled":
            break
        batch = members[member_idx:member_idx + per_session]
        proxy = await get_proxy(redis)
        try:
            client = await get_client(session_name, proxy)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                continue
            dest_entity = await client.get_entity(dest)
            for user in batch:
                try:
                    await client(InviteToChannelRequest(dest_entity, [user]))
                    done += 1
                    await asyncio.sleep(random.uniform(2, 5))
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                    failed += 1
                except UserPrivacyRestrictedError:
                    failed += 1
                except Exception as e:
                    logger.error(f"[g2g] add {user.username}: {e}")
                    failed += 1
                await update_task(tid, {"done": done, "failed": failed})
            member_idx += per_session
            await client.disconnect()
        except Exception as e:
            logger.error(f"[g2g] session {session_name}: {e}")
        await asyncio.sleep(random.uniform(5, 15))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ── VIEW POST ────────────────────────────────────────────────────
async def run_view(task: dict, redis: Redis):
    tid = task["id"]
    target = task["target"]
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    # Parse channel and message id from link
    # e.g. https://t.me/channel/123
    parts = target.rstrip("/").split("/")
    try:
        msg_id = int(parts[-1])
        channel = parts[-2]
    except Exception:
        await update_task(tid, {"status": "failed", "error": "invalid link"})
        return
    for session_name in sessions:
        t = await _load_task(tid)
        if t and t.get("status") == "cancelled":
            break
        proxy = await get_proxy(redis)
        try:
            client = await get_client(session_name, proxy)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                failed += 1
                continue
            entity = await client.get_entity(channel)
            await client(GetMessagesViewsRequest(peer=entity, id=[msg_id], increment=True))
            done += 1
            await client.disconnect()
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            failed += 1
        except Exception as e:
            logger.error(f"[view] {session_name}: {e}")
            failed += 1
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(1, 3))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ── REACTION ─────────────────────────────────────────────────────
async def run_reaction(task: dict, redis: Redis):
    tid = task["id"]
    target = task["target"]
    emoji = task.get("emoji", "👍")
    sessions = task.get("sessions", [])
    await update_task(tid, {"status": "running"})
    done = failed = 0
    parts = target.rstrip("/").split("/")
    try:
        msg_id = int(parts[-1])
        channel = parts[-2]
    except Exception:
        await update_task(tid, {"status": "failed", "error": "invalid link"})
        return
    for session_name in sessions:
        t = await _load_task(tid)
        if t and t.get("status") == "cancelled":
            break
        proxy = await get_proxy(redis)
        try:
            client = await get_client(session_name, proxy)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                failed += 1
                continue
            entity = await client.get_entity(channel)
            await client(SendReactionRequest(
                peer=entity,
                msg_id=msg_id,
                reaction=[ReactionEmoji(emoticon=emoji)]
            ))
            done += 1
            await client.disconnect()
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            failed += 1
        except Exception as e:
            logger.error(f"[reaction] {session_name}: {e}")
            failed += 1
        await update_task(tid, {"done": done, "failed": failed})
        await asyncio.sleep(random.uniform(2, 5))
    await update_task(tid, {"status": "completed", "done": done, "failed": failed})


# ── MAIN LOOP ────────────────────────────────────────────────────
async def main():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Worker started, waiting for tasks...")
    handlers = {
        "join": run_join,
        "group2group": run_group2group,
        "view": run_view,
        "reaction": run_reaction,
    }
    while True:
        try:
            item = await redis.blpop(TASK_QUEUE, timeout=5)
            if not item:
                continue
            _, raw = item
            task = json.loads(raw)
            task_type = task.get("type")
            handler = handlers.get(task_type)
            if handler:
                logger.info(f"Running task {task['id']} type={task_type}")
                asyncio.create_task(handler(task, redis))
            else:
                logger.warning(f"Unknown task type: {task_type}")
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
