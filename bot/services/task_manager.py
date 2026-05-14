import json
import os
import logging
from typing import Optional

logger = logging.getLogger("task_manager")

DATA_DIR  = os.getenv("DATA_DIR", "/app/data")
TASK_FILE = os.path.join(DATA_DIR, "tasks.json")

os.makedirs(DATA_DIR, exist_ok=True)


def _load() -> dict:
    try:
        if os.path.exists(TASK_FILE):
            with open(TASK_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


async def get_all_tasks() -> list:
    return list(_load().values())


async def get_task(tid: str) -> Optional[dict]:
    return _load().get(tid)


async def cancel_task(tid: str):
    data = _load()
    if tid in data:
        data[tid]["status"] = "cancelled"
        with open(TASK_FILE, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
