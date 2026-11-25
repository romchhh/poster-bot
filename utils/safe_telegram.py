"""Telegram API helpers that tolerate benign errors."""

from __future__ import annotations

from aiogram import types
from aiogram.exceptions import TelegramBadRequest


def _is_message_not_modified(exc: TelegramBadRequest) -> bool:
    text = (exc.message or str(exc)).lower()
    return "message is not modified" in text


async def safe_edit_text(message: types.Message, **kwargs) -> bool:
    """``edit_text``; returns False if Telegram says content is unchanged."""
    try:
        await message.edit_text(**kwargs)
        return True
    except TelegramBadRequest as exc:
        if _is_message_not_modified(exc):
            return False
        raise