import json, os, uuid, aiofiles
from datetime import datetime
from redis.asyncio import Redis
from config import DATA_DIR

TASK_FILE = os.path.join(DATA_DIR, "tasks.json")
TASK_QUEUE = "tsb:task_queue"

async def load_tasks() -> dict:
    if os.path.exists(TASK_FILE):
        async with aiofiles.open(TASK_FILE, "r") as f:
            return json.loads(await f.read())
    return {}

async def save_tasks(tasks: dict):
    async with aiofiles.open(TASK_FILE, "w") as f:
        await f.write(json.dumps(tasks, ensure_ascii=False, indent=2))

async def create_task(redis: Redis, task: dict) -> str:
    tid = str(uuid.uuid4())[:8]
    task.update({"id": tid, "status": "pending", "done": 0, "failed": 0,
                 "created_at": datetime.now().isoformat()})
    tasks = await load_tasks()
    tasks[tid] = task
    await save_tasks(tasks)
    await redis.rpush(TASK_QUEUE, json.dumps(task))
    return tid

async def get_task(tid: str):
    return (await load_tasks()).get(tid)

async def update_task(tid: str, data: dict):
    tasks = await load_tasks()
    if tid in tasks:
        tasks[tid].update(data)
        await save_tasks(tasks)

async def get_all_tasks() -> list:
    return list((await load_tasks()).values())

async def cancel_task(redis: Redis, tid: str):
    await update_task(tid, {"status": "cancelled"})
