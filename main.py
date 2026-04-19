from __future__ import annotations

import logging

from app.bot import start_bot
from app.config import load_settings
from app.db import Database


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    db = Database(settings.db_path)
    start_bot(settings, db)


if __name__ == "__main__":
    main()
