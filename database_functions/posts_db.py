from datetime import datetime
import json


from database_functions.connection import conn, cursor


def create_scheduled_posts_table():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scheduled_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            post_text TEXT,
            media_type TEXT,
            media_file_id TEXT,
            media_files TEXT,
            url_buttons TEXT,
            scheduled_time TEXT NOT NULL,
            created_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            settings TEXT,
            published_message_id INTEGER,
            error_message TEXT
        )
    ''')
    conn.commit()


def create_posts_table():
    """Створює таблицю опублікованих постів"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            post_text TEXT,
            media_type TEXT,
            url_buttons TEXT,
            published_date TEXT NOT NULL,
            settings TEXT,
            auto_delete_time TEXT,
            is_deleted INTEGER DEFAULT 0
        )
    ''')
    conn.commit()


def add_scheduled_post(user_id: int, channel_id: int, scheduled_time: str,
                      post_text: str, media_files: list = None,
                      url_buttons: str = None, settings: dict = None):
    current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    media_files_json = json.dumps(media_files) if media_files else None
    settings_json = json.dumps(settings) if settings else None
    
    media_type = None
    media_file_id = None
    if media_files and len(media_files) > 0:
        media_type = media_files[0].get('type')
        media_file_id = media_files[0].get('file_id')
    
    cursor.execute('''
        INSERT INTO scheduled_posts 
        (user_id, channel_id, post_text, media_type, media_file_id, 
         media_files, url_buttons, scheduled_time, created_date, settings)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, channel_id, post_text, media_type, media_file_id,
          media_files_json, url_buttons, scheduled_time, 
          current_date, settings_json))
    
    conn.commit()
    return cursor.lastrowid


def add_published_post(
    user_id: int,
    channel_id: int,
    message_id: int,
    post_text: str,
    media_type: str = None,
    url_buttons: str = None,
    settings: dict = None,
    auto_delete_time: datetime = None,
    scheduled_post_id: int = None,
    published_source: str = "bot",
    media_files: list | None = None,
):
    published_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    settings_obj = dict(settings) if settings else {}
    media_files_json = None
    media_file_id = None
    if media_files:
        media_files_json = json.dumps(media_files, ensure_ascii=False)
        media_file_id = media_files[0].get("file_id")
        if not media_type:
            media_type = media_files[0].get("type")
    settings_json = json.dumps(settings_obj, ensure_ascii=False) if settings_obj else None
    auto_delete_str = (
        auto_delete_time.strftime("%Y-%m-%d %H:%M:%S") if auto_delete_time else None
    )

    cursor.execute(
        """
        INSERT INTO posts
        (user_id, channel_id, message_id, post_text, media_type, media_file_id,
         media_files, url_buttons, published_date, settings, auto_delete_time,
         published_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            channel_id,
            message_id,
            post_text,
            media_type,
            media_file_id,
            media_files_json,
            url_buttons or "",
            published_date,
            settings_json,
            auto_delete_str,
            published_source or "bot",
        ),
    )

    conn.commit()
    return cursor.lastrowid


def published_post_exists(channel_id: int, message_id: int) -> bool:
    cursor.execute(
        "SELECT 1 FROM posts WHERE channel_id = ? AND message_id = ? AND is_deleted = 0",
        (channel_id, message_id),
    )
    return cursor.fetchone() is not None


def add_external_channel_post(
    user_id: int,
    channel_id: int,
    message_id: int,
    post_text: str,
    media_type: str | None,
    published_date: str,
) -> int | None:
    """Пост у каналі без бота (channel_post). Повертає id рядка або None якщо дублікат."""
    if published_post_exists(channel_id, message_id):
        return None
    cursor.execute(
        """
        INSERT INTO posts
        (user_id, channel_id, message_id, post_text, media_type, url_buttons,
         published_date, settings, auto_delete_time, is_deleted, published_source)
        VALUES (?, ?, ?, ?, ?, '', ?, NULL, NULL, 0, 'external')
        """,
        (user_id, channel_id, message_id, post_text or "", media_type, published_date),
    )
    conn.commit()
    return cursor.lastrowid


def get_pending_scheduled_posts():
    from database_functions.client_db import get_user_timezone, is_scheduled_post_due

    cursor.execute(
        """
        SELECT * FROM scheduled_posts 
        WHERE status = 'pending'
        ORDER BY scheduled_time ASC
        """
    )
    rows = cursor.fetchall()
    zones: dict[int, str] = {}
    due = []
    for row in rows:
        user_id = row[1]
        if user_id not in zones:
            zones[user_id] = get_user_timezone(user_id)
        if is_scheduled_post_due(row[8], user_id, zones[user_id]):
            due.append(row)
    return due


def update_scheduled_post_status(post_id: int, status: str, 
                                 published_message_id: int = None,
                                 error_message: str = None):
    cursor.execute('''
        UPDATE scheduled_posts 
        SET status = ?, published_message_id = ?, error_message = ?
        WHERE id = ?
    ''', (status, published_message_id, error_message, post_id))
    conn.commit()


update_post_status = update_scheduled_post_status


def delete_scheduled_post(post_id: int):
    cursor.execute('DELETE FROM scheduled_posts WHERE id = ?', (post_id,))
    conn.commit()
    return cursor.rowcount > 0


def get_scheduled_post_row(post_id: int):
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    return cursor.fetchone()


def update_scheduled_post_content(
    post_id: int,
    post_text: str,
    media_files: list,
    url_buttons: str,
    settings: dict,
):
    media_files_json = json.dumps(media_files) if media_files else None
    media_type = None
    media_file_id = None
    if media_files and len(media_files) > 0:
        media_type = media_files[0].get("type")
        media_file_id = media_files[0].get("file_id")
    settings_json = json.dumps(settings) if settings else None
    cursor.execute(
        """
        UPDATE scheduled_posts SET
            post_text = ?, media_type = ?, media_file_id = ?,
            media_files = ?, url_buttons = ?, settings = ?
        WHERE id = ?
        """,
        (
            post_text,
            media_type,
            media_file_id,
            media_files_json,
            url_buttons or "",
            settings_json,
            post_id,
        ),
    )
    conn.commit()


def _safe_json_loads(raw, default=None):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def get_scheduled_post_by_id(post_id: int):
    cursor.execute("SELECT * FROM scheduled_posts WHERE id = ?", (post_id,))
    result = cursor.fetchone()

    if not result:
        return None

    # url_buttons are stored as plain button text (same as scheduler), not JSON
    return {
        "id": result[0],
        "user_id": result[1],
        "channel_id": result[2],
        "post_text": result[3],
        "media_type": result[4],
        "media_file_id": result[5],
        "media_files": _safe_json_loads(result[6], default=[]),
        "url_buttons": result[7] or "",
        "scheduled_time": result[8],
        "created_date": result[9],
        "status": result[10],
        "settings": _safe_json_loads(result[11], default={}),
        "published_message_id": result[12] if len(result) > 12 else None,
        "error_message": result[13] if len(result) > 13 else None,
    }


def create_post_deletion_log_table() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS post_deletion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            post_row_id INTEGER,
            published_date TEXT,
            deleted_at TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT
        )
        """
    )
    conn.commit()


def search_published_posts(
    user_id: int,
    query: str = "",
    *,
    channel_id: int | None = None,
    folder_id: int | None = None,
    since: str | None = None,
    limit: int = 10,
) -> list[dict]:
    sql = """
        SELECT p.id, p.channel_id, p.message_id, p.post_text, p.published_date,
               p.is_deleted, c.channel_title, c.channel_username
        FROM posts p
        JOIN channels c ON c.channel_id = p.channel_id
        JOIN channel_memberships cm ON cm.channel_id = c.channel_id AND cm.user_id = ?
        WHERE 1=1
    """
    params: list = [user_id]
    if channel_id:
        sql += " AND p.channel_id = ?"
        params.append(channel_id)
    if folder_id:
        sql += " AND c.folder_id = ?"
        params.append(folder_id)
    if since:
        sql += " AND p.published_date >= ?"
        params.append(since)
    text = (query or "").strip()
    if text.isdigit():
        sql += " AND (p.id = ? OR p.message_id = ?)"
        number = int(text)
        params.extend([number, number])
    elif text:
        for word in text.split()[:6]:
            sql += " AND LOWER(COALESCE(p.post_text, '')) LIKE ?"
            params.append(f"%{word.casefold()}%")
    sql += " ORDER BY p.published_date DESC, p.id DESC LIMIT ?"
    params.append(limit)
    cursor.execute(sql, params)
    rows = []
    for row in cursor.fetchall():
        rows.append(
            {
                "id": row[0],
                "channel_id": row[1],
                "message_id": row[2],
                "post_text": row[3] or "",
                "published_date": row[4] or "",
                "is_deleted": bool(row[5]),
                "channel_title": row[6] or "Канал",
                "channel_username": row[7] or "",
            }
        )
    return rows


def get_last_published_post(channel_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT id, user_id, channel_id, message_id, post_text, published_date, settings, is_deleted
        FROM posts
        WHERE channel_id = ?
        ORDER BY published_date DESC, id DESC
        LIMIT 1
        """,
        (channel_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "channel_id": row[2],
        "message_id": row[3],
        "post_text": row[4] or "",
        "published_date": row[5] or "",
        "settings": _safe_json_loads(row[6], default={}),
        "is_deleted": bool(row[7]),
    }


def mark_published_post_deleted(post_id: int) -> None:
    cursor.execute("UPDATE posts SET is_deleted = 1 WHERE id = ?", (post_id,))
    conn.commit()


def add_post_deletion_log(
    *,
    user_id: int,
    channel_id: int,
    message_id: int | None,
    post_row_id: int | None,
    published_date: str | None,
    status: str,
    detail: str = "",
) -> None:
    deleted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO post_deletion_log
        (user_id, channel_id, message_id, post_row_id, published_date, deleted_at, status, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            channel_id,
            message_id,
            post_row_id,
            published_date,
            deleted_at,
            status,
            (detail or "")[:300],
        ),
    )
    conn.commit()


def list_post_deletion_log(channel_id: int, limit: int = 8) -> list[tuple]:
    cursor.execute(
        """
        SELECT deleted_at, status, message_id, published_date, detail
        FROM post_deletion_log
        WHERE channel_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (channel_id, limit),
    )
    return cursor.fetchall()
