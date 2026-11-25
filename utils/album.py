"""Collect a Telegram media group into one post (up to 10 items).

Telegram delivers an album as several messages with the same media_group_id.
The first handler to see the group waits briefly, then returns every item.
Later handlers for the same group get None and should stop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiogram.types import Message

from utils.message_html import message_to_html

MAX_ALBUM_ITEMS = 10
_ALBUM_WAIT_SECONDS = 1.0

_lock = asyncio.Lock()
_buckets: dict[str, list[Message]] = {}
_leaders: set[str] = set()


async def take_album(message: Message) -> list[Message] | None:
    """Return the album once it is complete, or None if another update owns it."""
    group_id = message.media_group_id
    if not group_id:
        return [message]

    async with _lock:
        _buckets.setdefault(group_id, []).append(message)
        is_leader = group_id not in _leaders
        if is_leader:
            _leaders.add(group_id)

    if not is_leader:
        return None

    await asyncio.sleep(_ALBUM_WAIT_SECONDS)

    async with _lock:
        items = _buckets.pop(group_id, [])
        _leaders.discard(group_id)

    items.sort(key=lambda item: item.message_id)
    return items


def media_item_from_message(message: Message) -> dict[str, Any] | None:
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id}
    if message.animation:
        return {"type": "animation", "file_id": message.animation.file_id}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id}
    if message.audio:
        return {"type": "audio", "file_id": message.audio.file_id}
    if message.voice:
        return {"type": "voice", "file_id": message.voice.file_id}
    if message.video_note:
        return {"type": "video_note", "file_id": message.video_note.file_id}
    return None


def album_to_post_parts(messages: list[Message]) -> tuple[str, list[dict[str, Any]], bool]:
    """Caption HTML, media items, and whether the original album was longer than 10."""
    trimmed = len(messages) > MAX_ALBUM_ITEMS
    messages = messages[:MAX_ALBUM_ITEMS]
    text = ""
    files: list[dict[str, Any]] = []
    for message in messages:
        html = message_to_html(message)
        if html and not text:
            text = html
        item = media_item_from_message(message)
        if item:
            if html:
                item["caption"] = html
            files.append(item)
    if len(files) > MAX_ALBUM_ITEMS:
        trimmed = True
    return text, files[:MAX_ALBUM_ITEMS], trimmed


def clear_url_buttons(post_data: dict) -> None:
    post_data["url_buttons"] = []
    post_data["url_buttons_raw_text"] = ""
    post_data["url_buttons_entities"] = []


def has_url_buttons(post_data: dict) -> bool:
    return bool(post_data.get("url_buttons") or post_data.get("url_buttons_raw_text"))
