import os, json, asyncio, logging, io, random
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest
from config import API_ID, API_HASH, SESSIONS_DIR, DATA_DIR
import aiofiles, aiohttp

logger = logging.getLogger("session_manager")
SESSIONS_META = os.path.join(DATA_DIR, "sessions_meta.json")

async def load_meta() -> dict:
    if os.path.exists(SESSIONS_META):
        async with aiofiles.open(SESSIONS_META, "r") as f:
            return json.loads(await f.read())
    return {}

async def save_meta(meta: dict):
    async with aiofiles.open(SESSIONS_META, "w") as f:
        await f.write(json.dumps(meta, ensure_ascii=False, indent=2))

async def get_all_sessions() -> list:
    meta = await load_meta()
    sessions = []
    if not os.path.exists(SESSIONS_DIR):
        return []
    for fname in os.listdir(SESSIONS_DIR):
        if fname.endswith(".session"):
            name = fname[:-8]
            info = dict(meta.get(name, {}))
            info["name"] = name
            sessions.append(info)
    return sessions

async def get_active_sessions() -> list:
    return [s for s in await get_all_sessions() if s.get("status") == "active"]

async def get_client(session_name: str, proxy: dict = None) -> TelegramClient:
    session_path = os.path.join(SESSIONS_DIR, session_name)
    kwargs = {}
    if proxy and proxy.get("type") in ("socks5", "socks4", "http"):
        kwargs["proxy"] = (proxy["type"], proxy["host"], int(proxy["port"]))
    return TelegramClient(session_path, API_ID, API_HASH, **kwargs)

async def check_session(session_name: str, proxy: dict = None) -> dict:
    try:
        client = await get_client(session_name, proxy)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return {"status": "unauthorized", "session": session_name}
        me = await client.get_me()
        await client.disconnect()
        return {"status": "active", "session": session_name, "phone": me.phone,
                "username": me.username, "first_name": me.first_name, "id": me.id}
    except Exception as e:
        return {"status": "error", "session": session_name, "error": str(e)}

async def update_session_meta(session_name: str, data: dict):
    meta = await load_meta()
    meta.setdefault(session_name, {}).update(data)
    await save_meta(meta)

async def delete_session(session_name: str):
    path = os.path.join(SESSIONS_DIR, session_name + ".session")
    if os.path.exists(path):
        os.remove(path)
    meta = await load_meta()
    meta.pop(session_name, None)
    await save_meta(meta)

async def auto_setup_profile(session_name: str, proxy: dict = None) -> bool:
    FIRST = ["Alex","Sam","Jordan","Taylor","Morgan","Casey","Riley","Avery","Quinn","Blake"]
    LAST  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis"]
    BIOS  = ["Just here to connect 🌟","Living life one day at a time ✨","Explorer | Dreamer 🚀","Coffee lover ☕","Making memories 📸"]
    first = random.choice(FIRST)
    last  = random.choice(LAST)
    bio   = random.choice(BIOS)
    uname = f"{first.lower()}{last.lower()}{random.randint(100,9999)}"
    try:
        client = await get_client(session_name, proxy)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return False
        await client(UpdateProfileRequest(first_name=first, last_name=last, about=bio))
        try:
            await client(UpdateUsernameRequest(uname))
        except Exception:
            pass
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.dicebear.com/7.x/avataaars/png?seed={uname}&size=200") as r:
                    if r.status == 200:
                        data = await r.read()
                        f = await client.upload_file(io.BytesIO(data), file_name="avatar.png")
                        await client(UploadProfilePhotoRequest(file=f))
        except Exception:
            pass
        await client.disconnect()
        await update_session_meta(session_name, {"first_name": first, "last_name": last,
            "username": uname, "bio": bio, "auto_setup": True})
        return True
    except Exception as e:
        logger.error(f"auto_setup error {session_name}: {e}")
        return False
