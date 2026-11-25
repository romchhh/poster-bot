from datetime import datetime
import sqlite3
import json
from database_functions.connection import conn, cursor

SCOPE_FOLDER = "folder"
SCOPE_CHANNEL = "channel"


def create_copy_mirror_tables():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copy_mirror_destinations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scope_type TEXT NOT NULL CHECK(scope_type IN ('folder', 'channel')),
            scope_id INTEGER NOT NULL,
            destination_group_id INTEGER NOT NULL,
            destination_title TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(user_id, scope_type, scope_id)
        )
        """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copy_mirror_donors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scope_type TEXT NOT NULL CHECK(scope_type IN ('folder', 'channel')),
            scope_id INTEGER NOT NULL,
            donor_channel_id INTEGER NOT NULL,
            donor_title TEXT,
            added_at TEXT NOT NULL,
            UNIQUE(user_id, scope_type, scope_id, donor_channel_id)
        )
        """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copy_mirror_donor_join_pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id INTEGER NOT NULL,
            fingerprint TEXT NOT NULL,
            invite_hash TEXT,
            preview_title TEXT,
            notify_chat_id INTEGER NOT NULL,
            notify_message_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, scope_type, scope_id, fingerprint)
        )
        """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copy_mirror_processed_source (
            donor_channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            processed_at TEXT NOT NULL,
            PRIMARY KEY (donor_channel_id, message_id)
        )
        """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copy_mirror_seen_route (
            donor_channel_id INTEGER NOT NULL,
            first_message_id INTEGER NOT NULL,
            owner_user_id INTEGER NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id INTEGER NOT NULL,
            seen_at TEXT NOT NULL,
            PRIMARY KEY (donor_channel_id, first_message_id, owner_user_id, scope_type, scope_id)
        )
        """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copy_mirror_pending_publish (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER NOT NULL,
            scope_type TEXT NOT NULL,
            scope_id INTEGER NOT NULL,
            donor_channel_id INTEGER NOT NULL,
            donor_title TEXT,
            message_ids_json TEXT NOT NULL,
            destination_group_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
        """)
    conn.commit()
    _migrate_copy_mirror_columns()
    _create_copy_mirror_ai_images_table()
    _create_copy_mirror_dest_notify_table()


def _migrate_copy_mirror_columns():
    cursor.execute("PRAGMA table_info(copy_mirror_pending_publish)")
    cols = {r[1] for r in cursor.fetchall()}
    if "extras_json" not in cols:
        cursor.execute(
            "ALTER TABLE copy_mirror_pending_publish ADD COLUMN extras_json TEXT DEFAULT '{}'"
        )
        conn.commit()


def _create_copy_mirror_dest_notify_table():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copy_mirror_dest_owner_notify (
            user_id INTEGER NOT NULL,
            destination_group_id INTEGER NOT NULL,
            last_notified_at TEXT NOT NULL,
            PRIMARY KEY (user_id, destination_group_id)
        )
        """)
    conn.commit()


def mirror_dest_owner_notify_due(
    user_id: int,
    destination_group_id: int,
    *,
    cooldown_hours: float = 6.0,
) -> bool:
    """True якщо минув cooldown з останнього сповіщення власнику."""
    now = datetime.now()
    cursor.execute(
        """
        SELECT last_notified_at FROM copy_mirror_dest_owner_notify
        WHERE user_id = ? AND destination_group_id = ?
        """,
        (int(user_id), int(destination_group_id)),
    )
    row = cursor.fetchone()
    if not row or not row[0]:
        return True
    try:
        prev = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return (now - prev).total_seconds() >= cooldown_hours * 3600


def mark_mirror_dest_owner_notified(user_id: int, destination_group_id: int) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO copy_mirror_dest_owner_notify
            (user_id, destination_group_id, last_notified_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, destination_group_id) DO UPDATE SET
            last_notified_at = excluded.last_notified_at
        """,
        (int(user_id), int(destination_group_id), stamp),
    )
    conn.commit()


def _create_copy_mirror_ai_images_table():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS copy_mirror_ai_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            pending_publish_id INTEGER,
            telegram_file_id TEXT NOT NULL,
            telegram_file_unique_id TEXT,
            summary_text TEXT,
            search_blob TEXT,
            source TEXT NOT NULL DEFAULT 'ai_generate',
            created_at TEXT NOT NULL
        )
        """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_copy_mirror_ai_search ON copy_mirror_ai_images(search_blob)"
    )
    conn.commit()


def insert_copy_mirror_ai_image(
    *,
    user_id: int,
    pending_publish_id: int | None,
    telegram_file_id: str,
    telegram_file_unique_id: str | None,
    summary_text: str | None,
    search_blob: str | None,
    source: str = "ai_generate",
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO copy_mirror_ai_images
            (user_id, pending_publish_id, telegram_file_id, telegram_file_unique_id,
             summary_text, search_blob, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            pending_publish_id,
            telegram_file_id,
            telegram_file_unique_id or "",
            summary_text or "",
            search_blob or "",
            source,
            now,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def merge_copy_mirror_pending_extras(publish_id: int, patch: dict) -> dict:
    row = get_copy_mirror_pending_publish(publish_id)
    if not row:
        return {}
    raw = row[10] if len(row) > 10 else "{}"
    try:
        base = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        base = {}
    if not isinstance(base, dict):
        base = {}
    base.update(patch)
    cursor.execute(
        "UPDATE copy_mirror_pending_publish SET extras_json = ? WHERE id = ?",
        (json.dumps(base, ensure_ascii=False), publish_id),
    )
    conn.commit()
    return base


def get_copy_mirror_pending_extras(publish_id: int) -> dict:
    row = get_copy_mirror_pending_publish(publish_id)
    if not row or len(row) <= 10:
        return {}
    try:
        d = json.loads(row[10] or "{}")
        return d if isinstance(d, dict) else {}
    except json.JSONDecodeError:
        return {}


def upsert_copy_destination(
    user_id: int,
    scope_type: str,
    scope_id: int,
    destination_group_id: int,
    destination_title: str | None,
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO copy_mirror_destinations
            (user_id, scope_type, scope_id, destination_group_id, destination_title, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, scope_type, scope_id) DO UPDATE SET
            destination_group_id = excluded.destination_group_id,
            destination_title = excluded.destination_title,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            scope_type,
            scope_id,
            destination_group_id,
            destination_title or "",
            now,
        ),
    )
    conn.commit()


def get_copy_destination(user_id: int, scope_type: str, scope_id: int):
    cursor.execute(
        """
        SELECT destination_group_id, destination_title, updated_at
        FROM copy_mirror_destinations
        WHERE user_id = ? AND scope_type = ? AND scope_id = ?
        """,
        (user_id, scope_type, scope_id),
    )
    return cursor.fetchone()


def list_destinations_scopes_for_user(user_id: int) -> set[tuple[str, int]]:
    cursor.execute(
        """
        SELECT scope_type, scope_id FROM copy_mirror_destinations
        WHERE user_id = ?
        """,
        (user_id,),
    )
    return {(r[0], int(r[1])) for r in cursor.fetchall()}


def scope_has_copy_mirror_config(user_id: int, scope_type: str, scope_id: int) -> bool:
    """True, якщо для scope є хоч один донор або збережена група-отримувач копії."""
    if list_copy_donors(user_id, scope_type, scope_id):
        return True
    return get_copy_destination(user_id, scope_type, scope_id) is not None


def list_copy_donors(user_id: int, scope_type: str, scope_id: int) -> list[tuple]:
    cursor.execute(
        """
        SELECT donor_channel_id, donor_title, added_at
        FROM copy_mirror_donors
        WHERE user_id = ? AND scope_type = ? AND scope_id = ?
        ORDER BY added_at ASC
        """,
        (user_id, scope_type, scope_id),
    )
    return cursor.fetchall()


def try_add_copy_donor(
    user_id: int,
    scope_type: str,
    scope_id: int,
    donor_channel_id: int,
    donor_title: str | None,
) -> bool:
    """Повертає True якщо рядок новий, False якщо дублікат."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT OR IGNORE INTO copy_mirror_donors
            (user_id, scope_type, scope_id, donor_channel_id, donor_title, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            scope_type,
            scope_id,
            donor_channel_id,
            donor_title or "",
            now,
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def insert_copy_mirror_donor_pending(
    *,
    user_id: int,
    scope_type: str,
    scope_id: int,
    fingerprint: str,
    invite_hash: str | None,
    preview_title: str | None,
    notify_chat_id: int,
    notify_message_id: int,
) -> int | None:
    """Повертає id запису або None якщо вже є pending з таким fingerprint."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute(
            """
            INSERT INTO copy_mirror_donor_join_pending
                (user_id, scope_type, scope_id, fingerprint, invite_hash,
                 preview_title, notify_chat_id, notify_message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                scope_type,
                scope_id,
                fingerprint,
                invite_hash,
                preview_title or "",
                notify_chat_id,
                notify_message_id,
                now,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        conn.rollback()
        return None


def list_pending_copy_mirror_donor_joins() -> list[tuple]:
    """Рядки: id, user_id, scope_type, scope_id, fingerprint, invite_hash, preview_title,
    notify_chat_id, notify_message_id, created_at
    """
    cursor.execute("""
        SELECT id, user_id, scope_type, scope_id, fingerprint, invite_hash,
               preview_title, notify_chat_id, notify_message_id, created_at
        FROM copy_mirror_donor_join_pending
        ORDER BY created_at ASC
        LIMIT 200
        """)
    return cursor.fetchall()


def delete_copy_mirror_donor_pending(pending_id: int) -> None:
    cursor.execute(
        "DELETE FROM copy_mirror_donor_join_pending WHERE id = ?",
        (pending_id,),
    )
    conn.commit()


def mirror_routes_for_donor_channel(donor_channel_id: int) -> list[tuple]:
    """(owner_user_id, scope_type, scope_id, destination_group_id, donor_title_hint)."""
    cursor.execute(
        """
        SELECT d.user_id, d.scope_type, d.scope_id, dest.destination_group_id, COALESCE(d.donor_title, '')
        FROM copy_mirror_donors d
        INNER JOIN copy_mirror_destinations dest ON
            dest.user_id = d.user_id AND dest.scope_type = d.scope_type
            AND dest.scope_id = d.scope_id
        WHERE d.donor_channel_id = ?
        """,
        (donor_channel_id,),
    )
    rows = cursor.fetchall()
    return [
        (
            int(r[0]),
            str(r[1]),
            int(r[2]),
            int(r[3]),
            str(r[4] or "") or None,
        )
        for r in rows
    ]


def insert_copy_mirror_pending_publish(
    *,
    owner_user_id: int,
    scope_type: str,
    scope_id: int,
    donor_channel_id: int,
    donor_title: str | None,
    message_ids: list[int],
    destination_group_id: int,
) -> int:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO copy_mirror_pending_publish
            (owner_user_id, scope_type, scope_id, donor_channel_id, donor_title,
             message_ids_json, destination_group_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            owner_user_id,
            scope_type,
            scope_id,
            donor_channel_id,
            donor_title or "",
            json.dumps([int(x) for x in message_ids]),
            destination_group_id,
            now,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def get_copy_mirror_pending_publish(publish_id: int):
    cursor.execute(
        """
        SELECT id, owner_user_id, scope_type, scope_id, donor_channel_id,
               donor_title, message_ids_json, destination_group_id, status, created_at,
               COALESCE(extras_json, '{}')
        FROM copy_mirror_pending_publish
        WHERE id = ?
        """,
        (publish_id,),
    )
    return cursor.fetchone()


def set_copy_mirror_pending_publish_status(publish_id: int, status: str) -> None:
    cursor.execute(
        "UPDATE copy_mirror_pending_publish SET status = ? WHERE id = ?",
        (status, publish_id),
    )
    conn.commit()


def try_claim_mirror_route(
    donor_channel_id: int,
    first_message_id: int,
    owner_user_id: int,
    scope_type: str,
    scope_id: int,
) -> bool:
    """Атомарно резервує обробку поста для маршруту (PRIMARY KEY → один власник виграє гонку)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT OR IGNORE INTO copy_mirror_seen_route
            (donor_channel_id, first_message_id, owner_user_id, scope_type, scope_id, seen_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            donor_channel_id,
            first_message_id,
            owner_user_id,
            scope_type,
            scope_id,
            now,
        ),
    )
    conn.commit()
    return cursor.rowcount == 1


def release_mirror_route_claim(
    donor_channel_id: int,
    first_message_id: int,
    owner_user_id: int,
    scope_type: str,
    scope_id: int,
) -> None:
    """Скасувати резерв, якщо доставка превʼю не вдалась — щоб можна було повторити."""
    cursor.execute(
        """
        DELETE FROM copy_mirror_seen_route
        WHERE donor_channel_id = ? AND first_message_id = ? AND owner_user_id = ?
          AND scope_type = ? AND scope_id = ?
        """,
        (donor_channel_id, first_message_id, owner_user_id, scope_type, scope_id),
    )
    conn.commit()
