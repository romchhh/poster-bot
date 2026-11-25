from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings

_settings = get_settings()

bot = Bot(
    token=_settings.token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

scheduler = AsyncIOScheduler(
    executors={"default": AsyncIOExecutor()},
    job_defaults={
        "coalesce": True,
        "max_instances": 3,
        "misfire_grace_time": 60,
    },
    timezone=_settings.timezone,
)


def ensure_scheduler_started() -> None:
    """Start APScheduler only when an event loop already exists."""
    if not scheduler.running:
        scheduler.start()
