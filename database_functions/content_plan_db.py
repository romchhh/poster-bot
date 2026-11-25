import json
from typing import List, Optional, Sequence, Tuple

from database_functions.channels_db import get_channel_by_id
from database_functions.connection import conn, cursor
from database_functions.posts_db import _safe_json_loads
from utils.post_utils import parse_url_buttons, serialize_url_buttons


def get_day_post_stats_for_channel(channel_id: int, date_str: str) -> dict:
    """Статистика за календарний день для одного каналу."""
    cursor.execute(
        """
        SELECT COUNT(*) FROM scheduled_posts
        WHERE channel_id = ? AND status = 'pending'
          AND substr(scheduled_time, 1, 10) = ?
        """,
        (channel_id, date_str),
    )
    scheduled = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT COUNT(*) FROM posts
        WHERE channel_id = ? AND is_deleted = 0
          AND substr(published_date, 1, 10) = ?
          AND COALESCE(published_source, 'bot') = 'bot'
        """,
        (channel_id, date_str),
    )
    published_bot = cursor.fetchone()[0] or 0

    cursor.execute(
        """
        SELECT COUNT(*) FROM posts
        WHERE channel_id = ? AND is_deleted = 0
          AND substr(published_date, 1, 10) = ?
          AND published_source = 'external'
        """,
        (channel_id, date_str),
    )
    published_external = cursor.fetchone()[0] or 0

    return {
        "scheduled": int(scheduled),
        "published_bot": int(published_bot),
        "published_external": int(published_external),
    }


def get_day_post_stats_for_channels(
    channel_ids: Sequence[int], date_str: str
) -> dict:
    """Агрегована статистика по кількох каналах (папка)."""
    ids = [int(x) for x in channel_ids if x is not None]
    if not ids:
        return {"scheduled": 0, "published_bot": 0, "published_external": 0}
    placeholders = ",".join("?" * len(ids))
    cursor.execute(
        f"""
        SELECT COUNT(*) FROM scheduled_posts
        WHERE channel_id IN ({placeholders}) AND status = 'pending'
          AND substr(scheduled_time, 1, 10) = ?
        """,
        (*ids, date_str),
    )
    scheduled = cursor.fetchone()[0] or 0

    cursor.execute(
        f"""
        SELECT COUNT(*) FROM posts
        WHERE channel_id IN ({placeholders}) AND is_deleted = 0
          AND substr(published_date, 1, 10) = ?
          AND COALESCE(published_source, 'bot') = 'bot'
        """,
        (*ids, date_str),
    )
    published_bot = cursor.fetchone()[0] or 0

    cursor.execute(
        f"""
        SELECT COUNT(*) FROM posts
        WHERE channel_id IN ({placeholders}) AND is_deleted = 0
          AND substr(published_date, 1, 10) = ?
          AND published_source = 'external'
        """,
        (*ids, date_str),
    )
    published_external = cursor.fetchone()[0] or 0

    return {
        "scheduled": int(scheduled),
        "published_bot": int(published_bot),
        "published_external": int(published_external),
    }


def _normalize_scheduled_time(value: str) -> str:
    if not value:
        return value
    if "T" in value:
        return value
    # 'YYYY-MM-DD HH:MM:SS' -> fromisoformat-friendly
    parts = value.split(" ")
    if len(parts) == 2:
        return f"{parts[0]}T{parts[1]}"
    return value


def _build_content_json_from_row(row: tuple) -> str:
    post_text = row[3] or ""
    media_type = row[4]
    media_file_id = row[5]
    media_files_json = row[6]
    url_buttons_text = row[7] or ""
    settings_json = row[11]

    media_files = json.loads(media_files_json) if media_files_json else []
    settings = json.loads(settings_json) if settings_json else {}

    url_buttons_parsed = parse_url_buttons(url_buttons_text) if url_buttons_text else []
    serialized_buttons = (
        serialize_url_buttons(url_buttons_parsed) if url_buttons_parsed else []
    )

    payload = {
        "text": post_text,
        "media_type": media_type,
        "media_file_id": media_file_id,
        "media_files": media_files,
        "has_media": bool(media_files or media_file_id),
        "url_buttons": serialized_buttons,
        "settings": settings,
    }
    return json.dumps(payload, ensure_ascii=False)


def scheduled_row_to_legacy_tuple(row: tuple) -> tuple: 
    if not row:
        return None
    ch = get_channel_by_id(row[2])
    title = ch[2] if ch else "Канал"
    return (
        row[0],
        row[1],
        row[2],
        title,
        _build_content_json_from_row(row),
        _normalize_scheduled_time(row[8]),
        row[10],
    )


def get_scheduled_post_by_id_content_plan(post_id: int) -> Optional[tuple]:
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    row = cursor.fetchone()
    if not row:
        return None
    return scheduled_row_to_legacy_tuple(row)


def get_published_post_by_id_content_plan(post_id: int) -> Optional[tuple]:
    cursor.execute(
        """
        SELECT id, user_id, channel_id, message_id, post_text, media_type,
               url_buttons, published_date, is_deleted,
               media_file_id, media_files, settings
        FROM posts
        WHERE id = ?
        """,
        (post_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    if row[8]:
        return None
    return row


def published_post_content_data(row: tuple) -> dict:
    """content_data для превʼю опублікованого поста з рядка posts."""
    post_text = row[4] or ""
    media_type = row[5]
    url_buttons_raw = row[6] or ""
    media_file_id = row[9] if len(row) > 9 else None
    media_files = (
        _safe_json_loads(row[10], default=[])
        if len(row) > 10 and row[10]
        else []
    )
    settings = (
        _safe_json_loads(row[11], default={})
        if len(row) > 11 and row[11]
        else {}
    )
    if not media_files and media_file_id:
        media_files = [
            {"type": media_type or "photo", "file_id": media_file_id, "caption": ""}
        ]
    parsed_buttons: list = []
    if url_buttons_raw:
        try:
            loaded = json.loads(url_buttons_raw)
            if isinstance(loaded, list):
                parsed_buttons = loaded
            else:
                parsed_buttons = (
                    serialize_url_buttons(parse_url_buttons(url_buttons_raw) or []) or []
                )
        except Exception:
            parsed_buttons = (
                serialize_url_buttons(parse_url_buttons(url_buttons_raw) or []) or []
            )
    return {
        "text": post_text,
        "media_type": media_type,
        "media_file_id": media_file_id,
        "media_files": media_files,
        "has_media": bool(media_files or media_type or media_file_id),
        "url_buttons": parsed_buttons,
        "settings": settings if isinstance(settings, dict) else {},
    }


def get_posts_for_date(channel_id: int, date_str: str) -> List[dict]:
    cursor.execute(
        """
        SELECT * FROM scheduled_posts
        WHERE channel_id = ? AND status = 'pending'
          AND substr(scheduled_time, 1, 10) = ?
        ORDER BY scheduled_time ASC
        """,
        (channel_id, date_str),
    )
    rows = cursor.fetchall()
    posts = []
    for row in rows:
        leg = scheduled_row_to_legacy_tuple(row)
        posts.append(
            {
                "type": "scheduled",
                "status": row[10],
                "id": row[0],
                "data": leg,
            }
        )
    cursor.execute(
        """
        SELECT id, channel_id, post_text, media_type, url_buttons, published_date,
               COALESCE(published_source, 'bot') AS published_source
        FROM posts
        WHERE channel_id = ? AND is_deleted = 0
          AND substr(published_date, 1, 10) = ?
        ORDER BY published_date ASC
        """,
        (channel_id, date_str),
    )
    published_rows = cursor.fetchall()
    for row in published_rows:
        url_buttons_raw = row[4] or ""
        parsed_buttons = []
        if url_buttons_raw:
            try:
                loaded = json.loads(url_buttons_raw)
                if isinstance(loaded, list):
                    parsed_buttons = loaded
                else:
                    parsed_buttons = serialize_url_buttons(parse_url_buttons(url_buttons_raw) or []) or []
            except Exception:
                parsed_buttons = serialize_url_buttons(parse_url_buttons(url_buttons_raw) or []) or []

        payload = {
            "text": row[2] or "",
            "media_type": row[3],
            "media_files": [],
            "has_media": bool(row[3]),
            "url_buttons": parsed_buttons,
            "settings": {},
        }
        posts.append(
            {
                "type": "published_log",
                "status": "published",
                "id": row[0],
                "data": (None, None, row[1], "Канал", json.dumps(payload, ensure_ascii=False), row[5], "published"),
                "published_source": row[6] if len(row) > 6 else "bot",
            }
        )
    posts.sort(key=lambda p: p["data"][5] if p.get("data") and len(p["data"]) > 5 else "")
    return posts


def get_scheduled_dates_for_channels(
    channel_ids: Sequence[int], start_date: str, end_date: str
) -> List[Tuple[str]]:
    ids = [int(x) for x in channel_ids if x is not None]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    cursor.execute(
        f"""
        SELECT DISTINCT substr(scheduled_time, 1, 10) AS d
        FROM scheduled_posts
        WHERE channel_id IN ({placeholders}) AND status = 'pending'
          AND substr(scheduled_time, 1, 10) >= ?
          AND substr(scheduled_time, 1, 10) <= ?
        ORDER BY d
        """,
        (*ids, start_date, end_date),
    )
    return cursor.fetchall()


def get_posts_for_date_channels(
    channel_ids: Sequence[int], date_str: str
) -> List[dict]:
    ids = [int(x) for x in channel_ids if x is not None]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    cursor.execute(
        f"""
        SELECT * FROM scheduled_posts
        WHERE channel_id IN ({placeholders}) AND status = 'pending'
          AND substr(scheduled_time, 1, 10) = ?
        ORDER BY scheduled_time ASC
        """,
        (*ids, date_str),
    )
    rows = cursor.fetchall()
    posts = []
    for row in rows:
        leg = scheduled_row_to_legacy_tuple(row)
        ch = get_channel_by_id(row[2])
        title = ch[2] if ch else "Канал"
        posts.append(
            {
                "type": "scheduled",
                "status": row[10],
                "id": row[0],
                "data": leg,
                "source_channel_title": title,
            }
        )
    cursor.execute(
        f"""
        SELECT id, channel_id, post_text, media_type, url_buttons, published_date,
               COALESCE(published_source, 'bot') AS published_source
        FROM posts
        WHERE channel_id IN ({placeholders}) AND is_deleted = 0
          AND substr(published_date, 1, 10) = ?
        ORDER BY published_date ASC
        """,
        (*ids, date_str),
    )
    published_rows = cursor.fetchall()
    for row in published_rows:
        ch = get_channel_by_id(row[1])
        title = ch[2] if ch else "Канал"
        url_buttons_raw = row[4] or ""
        parsed_buttons = []
        if url_buttons_raw:
            try:
                loaded = json.loads(url_buttons_raw)
                if isinstance(loaded, list):
                    parsed_buttons = loaded
                else:
                    parsed_buttons = serialize_url_buttons(parse_url_buttons(url_buttons_raw) or []) or []
            except Exception:
                parsed_buttons = serialize_url_buttons(parse_url_buttons(url_buttons_raw) or []) or []

        payload = {
            "text": row[2] or "",
            "media_type": row[3],
            "media_files": [],
            "has_media": bool(row[3]),
            "url_buttons": parsed_buttons,
            "settings": {},
        }
        posts.append(
            {
                "type": "published_log",
                "status": "published",
                "id": row[0],
                "data": (None, None, row[1], title, json.dumps(payload, ensure_ascii=False), row[5], "published"),
                "source_channel_title": title,
                "published_source": row[6] if len(row) > 6 else "bot",
            }
        )
    posts.sort(key=lambda p: p["data"][5] if p.get("data") and len(p["data"]) > 5 else "")
    return posts


def get_scheduled_dates_for_channel(
    channel_id: int, start_date: str, end_date: str
) -> List[Tuple[str]]:
    cursor.execute(
        """
        SELECT DISTINCT substr(scheduled_time, 1, 10) as d
        FROM scheduled_posts
        WHERE channel_id = ? AND status = 'pending'
          AND substr(scheduled_time, 1, 10) >= ?
          AND substr(scheduled_time, 1, 10) <= ?
        ORDER BY d
        """,
        (channel_id, start_date, end_date),
    )
    return cursor.fetchall()


def delete_all_scheduled_posts_for_channel(user_id: int, channel_id: int) -> int:
    cursor.execute(
        """
        DELETE FROM scheduled_posts
        WHERE user_id = ? AND channel_id = ? AND status = 'pending'
        """,
        (user_id, channel_id),
    )
    conn.commit()
    return cursor.rowcount or 0


def update_scheduled_post_time(post_id: int, new_time_iso: str) -> None:
    normalized = new_time_iso.replace("T", " ") if "T" in new_time_iso else new_time_iso
    if len(normalized) == 16:
        normalized = normalized + ":00"
    cursor.execute(
        "UPDATE scheduled_posts SET scheduled_time = ? WHERE id = ?",
        (normalized, post_id),
    )
    conn.commit()
