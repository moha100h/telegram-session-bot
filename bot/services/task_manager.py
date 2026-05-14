import json
import os
import uuid
import asyncio
import aiofiles
from datetime import datetime
from redis.asyncio import Redis
from config import DATA_DIR

TASK_FILE  = os.path.join(DATA_DIR, "tasks.json")
TASK_QUEUE = "tsb:task_queue"

_lock = asyncio.Lock()


async def load_tasks() -> dict:
    if not os.path.exists(TASK_FILE):
        return {}
    try:
        async with aiofiles.open(TASK_FILE, "r") as f:
            return json.loads(await f.read())
    except Exception:
        return {}


async def save_tasks(tasks: dict):
    async with _lock:
        async with aiofiles.open(TASK_FILE, "w") as f:
            await f.write(json.dumps(tasks, ensure_ascii=False, indent=2))


async def create_task(redis: Redis, task: dict) -> str:
    tid = str(uuid.uuid4())[:8]
    task.update({
        "id": tid,
        "status": "pending",
        "done": 0,
        "failed": 0,
        "created_at": datetime.now().isoformat(),
    })
    # Save to file first
    tasks = await load_tasks()
    tasks[tid] = task
    await save_tasks(tasks)
    # Push to Redis queue as JSON string
    payload = json.dumps(task, ensure_ascii=False)
    await redis.rpush(TASK_QUEUE, payload)
    return tid


async def get_task(tid: str) -> dict | None:
    return (await load_tasks()).get(tid)


async def update_task(tid: str, data: dict):
    async with _lock:
        tasks = await load_tasks()
        if tid in tasks:
            tasks[tid].update(data)
            await save_tasks(tasks)


async def get_all_tasks() -> list:
    tasks = await load_tasks()
    return sorted(tasks.values(), key=lambda t: t.get("created_at", ""), reverse=True)


async def cancel_task(redis: Redis, tid: str):
    await update_task(tid, {"status": "cancelled"})
