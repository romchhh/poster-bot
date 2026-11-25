"""Допоміжні функції для контент-плану."""
import html
import re
from typing import Any, Optional, Tuple

from utils.post_utils import deserialize_url_buttons, send_post_preview


async def send_post_preview_to_user(bot, user_id: int, content_data: dict) -> Any:
    """Превʼю поста користувачу в особисті (як у батьківському контент-плані)."""
    data = dict(content_data)
    ub = data.get("url_buttons")
    if ub and isinstance(ub, list) and len(ub) > 0:
        sample = ub[0][0] if ub[0] else None
        if isinstance(sample, dict):
            data["url_buttons"] = deserialize_url_buttons(ub)
    return await send_post_preview(bot, user_id, data)


async def send_published_post_preview_to_user(
    bot,
    user_id: int,
    *,
    channel_id: int,
    message_id: int,
    content_data: dict,
) -> Any:
    """Превʼю опублікованого поста: file_id з БД або copy з каналу."""
    has_files = bool(
        content_data.get("media_files")
        or content_data.get("media_file_id")
    )
    if has_files:
        return await send_post_preview_to_user(bot, user_id, content_data)

    settings = content_data.get("settings") or {}
    msg_ids = settings.get("message_ids")
    if not isinstance(msg_ids, list) or not msg_ids:
        msg_ids = [int(message_id)]

    try:
        if len(msg_ids) > 1:
            copied = await bot.copy_messages(
                chat_id=user_id,
                from_chat_id=int(channel_id),
                message_ids=[int(x) for x in msg_ids[:10]],
            )
            if copied:
                return copied[0]
        return await bot.copy_message(
            chat_id=user_id,
            from_chat_id=int(channel_id),
            message_id=int(message_id),
        )
    except Exception:
        return await send_post_preview_to_user(bot, user_id, content_data)


def format_post_preview(content_data: dict) -> str:
    """Короткий HTML-текст для картки поста в контент-плані."""
    parts = []
    text = (content_data.get("text") or "").strip()
    if text:
        snippet = text[:400] + ("…" if len(text) > 400 else "")
        parts.append(html.escape(snippet))
    media_files = content_data.get("media_files") or []
    if len(media_files) > 1:
        parts.append(f"📎 Медіагрупа: {len(media_files)} файлів")
    elif content_data.get("has_media") or (len(media_files) == 1):
        mtype = content_data.get("media_type") or (
            media_files[0].get("type") if media_files else ""
        )
        parts.append(f"📎 Медіа: {html.escape(str(mtype or 'файл'))}")
    return "\n".join(parts) if parts else "—"


def parse_time_input_content_plan(text: str) -> Optional[Tuple[int, int]]:
    """Парсинг часу для зміни плану: HH:MM, HH MM, HHMM, H."""
    if not text:
        return None
    raw = text.strip()
    m = re.match(r"^(\d{1,2})[:h](\d{1,2})$", raw, re.I)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
        return None
    m = re.match(r"^(\d{1,2})\s+(\d{1,2})$", raw)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
        return None
    m = re.match(r"^(\d{3,4})$", raw)
    if m:
        digits = m.group(1)
        if len(digits) == 3:
            h, mi = int(digits[0]), int(digits[1:3])
        else:
            h, mi = int(digits[:2]), int(digits[2:4])
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return h, mi
        return None
    m = re.match(r"^(\d{1,2})$", raw)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return h, 0
    return None


def post_data_from_scheduled_sqlite_row(row: tuple) -> dict:
    """post_data для PostCreation з сирого рядка scheduled_posts."""
    import json

    post_text = row[3] or ""
    media_type = row[4]
    media_file_id = row[5]
    media_files_json = row[6]
    url_buttons_val = row[7]
    settings_json = row[11]
    media_files = []
    if media_files_json:
        try:
            media_files = json.loads(media_files_json)
        except (json.JSONDecodeError, TypeError):
            media_files = []
    if not media_files and media_file_id:
        media_files = [
            {
                "type": media_type or "photo",
                "file_id": media_file_id,
                "caption": "",
            }
        ]
    settings = {}
    if settings_json:
        try:
            settings = json.loads(settings_json)
        except (json.JSONDecodeError, TypeError):
            settings = {}
    base = {"notification": True, "pin_message": False, "disable_comments": False}
    base.update(settings)
    ub_raw = url_buttons_val if isinstance(url_buttons_val, str) else ""
    return {
        "text": post_text,
        "media_files": media_files,
        "url_buttons_raw_text": ub_raw,
        "url_buttons_entities": [],
        "settings": base,
    }
