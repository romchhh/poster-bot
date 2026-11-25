"""SkyPost bot entrypoint."""

from __future__ import annotations

import asyncio
import logging

from app.lifecycle import on_shutdown, on_startup
from app.logging_setup import setup_logging
from app.paths import ensure_runtime_dirs
from app.routers import register_routers
from app.runtime import bot, dp, ensure_scheduler_started

logger = logging.getLogger(__name__)


async def run() -> None:
    ensure_runtime_dirs()
    ensure_scheduler_started()

    from utils.copy_utils.telethon_copy_client import ensure_telethon_session_console

    await ensure_telethon_session_console()

    register_routers(dp)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # skip_updates was removed from start_polling; drop pending via deleteWebhook
    await bot.delete_webhook(drop_pending_updates=True)

    while True:
        try:
            await dp.start_polling(bot)
        except Exception:
            logger.exception("Polling crashed; restarting in 5s")
            await asyncio.sleep(5)


def main() -> None:
    setup_logging()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Interrupted")


if __name__ == "__main__":
    main()
