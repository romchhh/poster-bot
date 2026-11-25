from __future__ import annotations

import logging

from aiogram import Bot

from app.paths import ensure_runtime_dirs
from app.runtime import bot, ensure_scheduler_started, scheduler

logger = logging.getLogger(__name__)


async def register_jobs(bot_instance: Bot) -> None:
    from utils.copy_utils.copy_donor_pending_poll import poll_pending_copy_mirror_donors
    from utils.scheduler import check_and_publish_scheduled_posts

    ensure_scheduler_started()

    scheduler.add_job(
        check_and_publish_scheduled_posts,
        "interval",
        seconds=30,
        args=[bot_instance],
        id="check_scheduled_posts",
        replace_existing=True,
    )
    scheduler.add_job(
        poll_pending_copy_mirror_donors,
        "interval",
        seconds=120,
        args=[bot_instance],
        id="poll_copy_mirror_donor_joins",
        replace_existing=True,
    )


async def on_startup(*_args) -> None:
    from database_functions.create_dbs import create_dbs
    from utils.copy_utils.copy_mirror_monitor import start_copy_mirror_monitor

    ensure_runtime_dirs()
    create_dbs()
    await register_jobs(bot)
    await start_copy_mirror_monitor(bot)

    from utils.referral_share import ensure_referral_photo_file_id

    me = await bot.get_me()
    await ensure_referral_photo_file_id(bot)
    logger.info("Bot @%s is up", me.username)


async def on_shutdown(*_args) -> None:
    from utils.copy_utils.copy_mirror_monitor import stop_copy_mirror_monitor
    from utils.copy_utils.telethon_copy_client import disconnect_telethon

    username = None
    try:
        me = await bot.get_me()
        username = me.username
    except Exception:
        logger.debug("get_me during shutdown failed", exc_info=True)

    await stop_copy_mirror_monitor()
    await disconnect_telethon()

    if scheduler.running:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("Scheduler shutdown failed")

    if username:
        logger.info("Bot @%s stopped", username)
    else:
        logger.info("Bot stopped")
