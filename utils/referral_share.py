"""Cache referral invite photo file_id for inline sharing."""

from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from app.config import administrators
from app.paths import DATABASE_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

REFERRAL_SHARE_QUERY = "invite"
_FILE_ID_CACHE = DATABASE_DIR / "referral_share_file_id.txt"
_PHOTO_CANDIDATES = (
    PROJECT_ROOT / "assets" / "referral_share.jpg",
    PROJECT_ROOT / "2026-11-25 18.40.33.jpg",
)


def referral_share_image_path() -> Path | None:
    for path in _PHOTO_CANDIDATES:
        if path.is_file():
            return path
    return None


def read_cached_photo_file_id() -> str | None:
    if not _FILE_ID_CACHE.is_file():
        return None
    value = _FILE_ID_CACHE.read_text(encoding="utf-8").strip()
    return value or None


def write_cached_photo_file_id(file_id: str) -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    _FILE_ID_CACHE.write_text(file_id.strip(), encoding="utf-8")


async def ensure_referral_photo_file_id(bot: Bot) -> str | None:
    cached = read_cached_photo_file_id()
    if cached:
        return cached
    image = referral_share_image_path()
    if not image:
        logger.warning("Referral share image not found")
        return None
    target_chat = next((int(x) for x in (administrators or []) if str(x).isdigit()), None)
    if target_chat is None:
        logger.warning("No admin id for referral photo upload cache")
        return None
    try:
        sent = await bot.send_photo(
            target_chat,
            FSInputFile(image),
            caption="Кеш для реферального запрошення",
            disable_notification=True,
        )
        file_id = sent.photo[-1].file_id
        write_cached_photo_file_id(file_id)
        try:
            await sent.delete()
        except Exception:
            pass
        return file_id
    except Exception:
        logger.exception("Failed to cache referral share photo")
        return None


async def get_referral_photo_file_id(bot: Bot) -> str | None:
    cached = read_cached_photo_file_id()
    if cached:
        return cached
    return await ensure_referral_photo_file_id(bot)