import asyncio
import random
import logging
import json
import os
from telethon import TelegramClient
from telethon.tl.functions.messages import ReadHistoryRequest, SendReactionRequest
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.types import ReactionEmoji
from datetime import datetime

logger = logging.getLogger("session_warmer")

SAFE_CHANNELS = [
    "durov", "telegram", "bbcpersian",
    "irna_ir", "isna_ir", "techcrunch"
]

REACTIONS = ["👍", "❤️", "🔥", "👏", "😍", "🎉", "😮"]


class SessionWarmer:
    def __init__(self, client: TelegramClient, session_name: str):
        self.client = client
        self.session_name = session_name
        self.state_file = f"/app/sessions/.warm_{session_name}.json"
        self.state = self._load_state()

    def _load_state(self):
        if os.path.exists(self.state_file):
            with open(self.state_file) as f:
                return json.load(f)
        return {
            "phase": "new",
            "day": 0,
            "total_actions": 0,
            "last_active": None,
            "score": 0
        }

    def _save_state(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def is_warm(self) -> bool:
        return self.state["phase"] in ("warm", "active")

    def get_status(self) -> dict:
        return self.state

    async def _human_delay(self, min_s=2, max_s=8):
        delay = random.uniform(min_s, max_s)
        if random.random() < 0.15:
            delay *= random.uniform(2, 4)
        await asyncio.sleep(delay)

    async def _online_presence(self):
        try:
            await self.client(UpdateStatusRequest(offline=False))
            online_time = random.randint(30, 180)
            await asyncio.sleep(online_time)
            await self.client(UpdateStatusRequest(offline=True))
            logger.info(f"[{self.session_name}] Online presence: {online_time}s")
        except Exception as e:
            logger.warning(f"[{self.session_name}] Online presence error: {e}")

    async def _read_dialogs(self):
        try:
            dialogs = await self.client.get_dialogs(limit=random.randint(3, 8))
            for dialog in dialogs:
                if random.random() < 0.6:
                    await self._human_delay(1, 4)
                    try:
                        await self.client(ReadHistoryRequest(
                            peer=dialog.input_entity,
                            max_id=0
                        ))
                        logger.info(f"[{self.session_name}] Read: {dialog.name}")
                    except Exception:
                        pass
            self.state["total_actions"] += 1
        except Exception as e:
            logger.warning(f"[{self.session_name}] Read dialogs error: {e}")

    async def _browse_channel(self):
        try:
            channel = random.choice(SAFE_CHANNELS)
            entity = await self.client.get_entity(channel)
            messages = await self.client.get_messages(entity, limit=random.randint(5, 15))
            for msg in messages:
                await self._human_delay(3, 12)
                if random.random() < 0.08 and msg.id:
                    try:
                        reaction = random.choice(REACTIONS)
                        await self.client(SendReactionRequest(
                            peer=entity,
                            msg_id=msg.id,
                            reaction=[ReactionEmoji(emoticon=reaction)]
                        ))
                        logger.info(f"[{self.session_name}] Reacted {reaction}")
                        self.state["score"] += 2
                    except Exception:
                        pass
            self.state["total_actions"] += 1
            self.state["score"] += 1
            logger.info(f"[{self.session_name}] Browsed @{channel}")
        except Exception as e:
            logger.warning(f"[{self.session_name}] Browse error: {e}")

    async def _update_profile(self):
        try:
            from telethon.tl.functions.account import UpdateProfileRequest
            await self.client(UpdateProfileRequest(
                about=random.choice(["", "👋", "Hi", "Hello"])
            ))
            self.state["score"] += 3
            logger.info(f"[{self.session_name}] Profile updated")
        except Exception as e:
            logger.warning(f"[{self.session_name}] Profile update error: {e}")

    async def run_warming_session(self):
        logger.info(
            f"[{self.session_name}] Warm session | "
            f"Phase: {self.state['phase']} | Day: {self.state['day']}"
        )
        actions = []

        if self.state["phase"] == "new":
            actions = [self._online_presence, self._read_dialogs]
            self.state["phase"] = "warming"

        elif self.state["phase"] == "warming":
            day = self.state["day"]
            if day < 2:
                actions = [self._online_presence, self._read_dialogs, self._browse_channel]
            elif day < 5:
                actions = [
                    self._online_presence, self._read_dialogs,
                    self._browse_channel, self._browse_channel, self._update_profile
                ]
            else:
                actions = [
                    self._online_presence, self._read_dialogs,
                    self._browse_channel, self._browse_channel, self._browse_channel
                ]
                if self.state["score"] >= 15:
                    self.state["phase"] = "warm"
                    logger.info(f"[{self.session_name}] Session is now WARM!")

        elif self.state["phase"] in ("warm", "active"):
            actions = [self._online_presence, self._read_dialogs, self._browse_channel]
            if random.random() < 0.3:
                actions.append(self._browse_channel)

        random.shuffle(actions)
        for action in actions:
            await self._human_delay(5, 20)
            await action()

        self.state["day"] += 1
        self.state["last_active"] = datetime.now().isoformat()
        self._save_state()
        return self.state
