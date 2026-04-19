from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    db_path: str
    log_level: str


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    admin_ids = {
        int(value.strip())
        for value in admin_ids_raw.split(",")
        if value.strip().isdigit()
    }

    db_path = os.getenv("BOT_DB_PATH", "data/bot.db").strip() or "data/bot.db"
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    return Settings(
        bot_token=token,
        admin_ids=admin_ids,
        db_path=db_path,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
