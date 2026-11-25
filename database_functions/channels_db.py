from datetime import datetime
import html as html_lib
from database_functions.connection import conn, cursor


def create_channels_table():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER UNIQUE NOT NULL,
            channel_title TEXT NOT NULL,
            channel_username TEXT,
            channel_link TEXT,
            channel_type TEXT,
            added_by_user_id INTEGER NOT NULL,
            added_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            discussion_group_id INTEGER,
            last_post_date TEXT,
            folder_id INTEGER
        )
    ''')
    conn.commit()
    create_channel_memberships_table()
    migrate_existing_channel_memberships()


def create_channel_memberships_table():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channel_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            joined_date TEXT NOT NULL,
            UNIQUE(channel_id, user_id)
        )
    ''')
    conn.commit()


def migrate_existing_channel_memberships():
    cursor.execute("SELECT channel_id, added_by_user_id, added_date FROM channels")
    rows = cursor.fetchall()
    for channel_id, user_id, added_date in rows:
        cursor.execute(
            '''
            INSERT OR IGNORE INTO channel_memberships (channel_id, user_id, role, joined_date)
            VALUES (?, ?, 'owner', ?)
            ''',
            (channel_id, user_id, added_date or datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
    conn.commit()


def add_channel(channel_id: int, channel_title: str, channel_username: str, 
                channel_link: str, added_by_user_id: int, chat_type: str = 'channel', 
                folder_id: int = None, user_role: str = 'admin'):
    cursor.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,))
    existing_channel = cursor.fetchone()
    
    if existing_channel:
        cursor.execute('''
            UPDATE channels 
            SET channel_title = ?, channel_username = ?, channel_link = ?,
                channel_type = ?, is_active = 1, folder_id = ?
            WHERE channel_id = ?
        ''', (channel_title, channel_username, channel_link, chat_type, folder_id, channel_id))
        conn.commit()
        is_new_channel = False
    else:
        from database_functions.billing_db import ChannelLimitError, can_add_channel

        reason = can_add_channel(added_by_user_id)
        if reason:
            raise ChannelLimitError(reason)
        current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO channels (channel_id, channel_title, channel_username, channel_link,
                                channel_type, added_by_user_id, added_date, is_active, folder_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
        ''', (channel_id, channel_title, channel_username, channel_link, 
              chat_type, added_by_user_id, current_date, folder_id))
        conn.commit()
        is_new_channel = True

    current_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    role = 'owner' if user_role == 'owner' else 'admin'
    cursor.execute(
        '''
        INSERT INTO channel_memberships (channel_id, user_id, role, joined_date)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(channel_id, user_id) DO UPDATE SET
            role = excluded.role
        ''',
        (channel_id, added_by_user_id, role, current_date)
    )
    conn.commit()

    if folder_id:
        from database_functions.folders_db import update_channels_count
        update_channels_count(folder_id)

    return is_new_channel


def get_channel_by_id(channel_id: int, user_id: int = None):
    if user_id is None:
        cursor.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,))
    else:
        cursor.execute(
            '''
            SELECT c.*, cm.role
            FROM channels c
            INNER JOIN channel_memberships cm ON cm.channel_id = c.channel_id
            WHERE c.channel_id = ? AND cm.user_id = ?
            ''',
            (channel_id, user_id)
        )
    return cursor.fetchone()


def get_all_channels(user_id: int = None, only_active: bool = True):
    if user_id:
        if only_active:
            cursor.execute(
                '''
                SELECT c.*, cm.role
                FROM channels c
                INNER JOIN channel_memberships cm ON cm.channel_id = c.channel_id
                WHERE cm.user_id = ? AND c.is_active = 1
                ORDER BY c.added_date DESC
                ''',
                (user_id,)
            )
        else:
            cursor.execute(
                '''
                SELECT c.*, cm.role
                FROM channels c
                INNER JOIN channel_memberships cm ON cm.channel_id = c.channel_id
                WHERE cm.user_id = ?
                ORDER BY c.added_date DESC
                ''',
                (user_id,)
            )
    else:
        if only_active:
            cursor.execute("SELECT * FROM channels WHERE is_active = 1 ORDER BY added_date DESC")
        else:
            cursor.execute("SELECT * FROM channels ORDER BY added_date DESC")
    
    return cursor.fetchall()


def remove_channel(channel_id: int, user_id: int = None):
    if user_id is not None:
        cursor.execute(
            "DELETE FROM channel_memberships WHERE channel_id = ? AND user_id = ?",
            (channel_id, user_id)
        )
        removed = cursor.rowcount > 0
        if removed:
            cursor.execute(
                "SELECT 1 FROM channel_memberships WHERE channel_id = ? LIMIT 1",
                (channel_id,)
            )
            has_members = cursor.fetchone() is not None
            if not has_members:
                cursor.execute(
                    "UPDATE channels SET is_active = 0 WHERE channel_id = ?",
                    (channel_id,)
                )
        conn.commit()
        return removed

    cursor.execute("UPDATE channels SET is_active = 0 WHERE channel_id = ?", (channel_id,))
    channel_updated = cursor.rowcount > 0
    cursor.execute("DELETE FROM channel_memberships WHERE channel_id = ?", (channel_id,))
    memberships_deleted = cursor.rowcount > 0
    conn.commit()
    return channel_updated or memberships_deleted


def set_discussion_group(channel_id: int, discussion_group_id: int):
    cursor.execute(
        "UPDATE channels SET discussion_group_id = ? WHERE channel_id = ?",
        (discussion_group_id, channel_id)
    )
    conn.commit()


async def auto_detect_discussion_group(bot, channel_id: int):
    try:
        chat = await bot.get_chat(channel_id)
        if hasattr(chat, 'linked_chat_id') and chat.linked_chat_id:
            set_discussion_group(channel_id, chat.linked_chat_id)
            return chat.linked_chat_id
    except Exception as e:
        print(f"Error detecting discussion group for channel {channel_id}: {e}")
    return None


def set_channel_folder(channel_id: int, folder_id: int = None):
    cursor.execute(
        "UPDATE channels SET folder_id = ? WHERE channel_id = ?",
        (folder_id, channel_id)
    )
    conn.commit()
    
    if folder_id:
        from database_functions.folders_db import update_channels_count
        update_channels_count(folder_id)


def get_channels_by_folder(folder_id: int, only_active: bool = True):
    if only_active:
        cursor.execute(
            "SELECT * FROM channels WHERE folder_id = ? AND is_active = 1 ORDER BY added_date DESC",
            (folder_id,)
        )
    else:
        cursor.execute(
            "SELECT * FROM channels WHERE folder_id = ? ORDER BY added_date DESC",
            (folder_id,)
        )
    return cursor.fetchall()


def get_channels_without_folder(user_id: int, only_active: bool = True):
    if only_active:
        cursor.execute(
            '''
            SELECT c.*, cm.role
            FROM channels c
            INNER JOIN channel_memberships cm ON cm.channel_id = c.channel_id
            WHERE cm.user_id = ? AND c.folder_id IS NULL AND c.is_active = 1
            ORDER BY c.added_date DESC
            ''',
            (user_id,)
        )
    else:
        cursor.execute(
            '''
            SELECT c.*, cm.role
            FROM channels c
            INNER JOIN channel_memberships cm ON cm.channel_id = c.channel_id
            WHERE cm.user_id = ? AND c.folder_id IS NULL
            ORDER BY c.added_date DESC
            ''',
            (user_id,)
        )
    return cursor.fetchall()


def remove_channels_from_folder(folder_id: int):
    cursor.execute(
        "UPDATE channels SET folder_id = NULL WHERE folder_id = ?",
        (folder_id,)
    )
    conn.commit()
    return cursor.rowcount > 0


def get_user_channel_role(user_id: int, channel_id: int):
    cursor.execute(
        "SELECT role FROM channel_memberships WHERE channel_id = ? AND user_id = ?",
        (channel_id, user_id)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def get_channel_members(channel_id: int):
    cursor.execute(
        '''
        SELECT
            cm.user_id,
            cm.role,
            u.user_name,
            u.user_first_name,
            u.user_last_name
        FROM channel_memberships cm
        LEFT JOIN users u ON u.user_id = cm.user_id
        WHERE cm.channel_id = ?
        ORDER BY CASE cm.role WHEN 'owner' THEN 0 ELSE 1 END, cm.joined_date ASC
        ''',
        (channel_id,)
    )
    return cursor.fetchall()


def remove_channel_admin(channel_id: int, admin_user_id: int):
    cursor.execute(
        "DELETE FROM channel_memberships WHERE channel_id = ? AND user_id = ? AND role = 'admin'",
        (channel_id, admin_user_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def get_mirror_publish_target_channel_ids(
    owner_user_id: int, scope_type: str, scope_id: int
) -> list[int]:
    """channel_id з SkyPost (Telegram) для публікації копії: один канал або всі активні в папці."""
    if scope_type == "channel":
        cursor.execute(
            """
            SELECT c.channel_id FROM channels c
            INNER JOIN channel_memberships cm ON cm.channel_id = c.channel_id
            WHERE c.channel_id = ? AND cm.user_id = ? AND c.is_active = 1
            """,
            (scope_id, owner_user_id),
        )
        row = cursor.fetchone()
        return [int(row[0])] if row else []
    if scope_type == "folder":
        cursor.execute(
            """
            SELECT c.channel_id FROM channels c
            INNER JOIN channel_memberships cm ON cm.channel_id = c.channel_id
            WHERE c.folder_id = ? AND cm.user_id = ? AND c.is_active = 1
            ORDER BY c.added_date ASC
            """,
            (scope_id, owner_user_id),
        )
        return [int(r[0]) for r in cursor.fetchall()]
    return []


def add_channel_editor(channel_id: int, editor_user_id: int) -> str:
    """
    Додає роль admin (редактор) для каналу.
    Повертає: 'ok' | 'already_owner' | 'already_editor' | 'not_found' (канал без рядка в channels — малоймовірно).
    """
    cursor.execute(
        "SELECT 1 FROM channels WHERE channel_id = ? AND is_active = 1",
        (channel_id,),
    )
    if not cursor.fetchone():
        return "not_found"
    role = get_user_channel_role(editor_user_id, channel_id)
    if role == "owner":
        return "already_owner"
    if role == "admin":
        return "already_editor"
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO channel_memberships (channel_id, user_id, role, joined_date)
        VALUES (?, ?, 'admin', ?)
        """,
        (channel_id, editor_user_id, current_date),
    )
    conn.commit()
    return "ok"


def telegram_tme_chat_url(chat_id: int) -> str:
    """Публічне посилання на чат/канал у форматі t.me/c/… (як у Telegram)."""
    sid = str(int(chat_id))
    if sid.startswith("-100"):
        return f"https://t.me/c/{sid[4:]}/1"
    if sid.startswith("-"):
        return f"https://t.me/c/{str(abs(int(sid)))}/1"
    return f"https://t.me/c/{sid}/1"


def chat_title_html_link_by_id(title: str | None, telegram_chat_id: int) -> str:
    """HTML-посилання для довільної назви та числового id чату (донор тощо)."""
    label = (title or "").strip() or f"id {telegram_chat_id}"
    esc = html_lib.escape(label, quote=False)
    url = telegram_tme_chat_url(telegram_chat_id)
    return f'<a href="{html_lib.escape(url, quote=True)}">{esc}</a>'


def channel_row_public_url(row: tuple | None) -> str | None:
    """URL з рядка channels (або SELECT c.*, cm.role — channel_link лишається на індексі 4)."""
    if not row or len(row) < 4:
        return None
    link = row[4]
    if link and str(link).strip():
        u = str(link).strip()
        if u.startswith(("http://", "https://")):
            return u
        if u.startswith("t.me/"):
            return f"https://{u}"
        if u.startswith("//"):
            return f"https:{u}"
    uname = row[3]
    if uname and str(uname).strip():
        return f"https://t.me/{str(uname).strip().lstrip('@')}"
    if len(row) > 1 and row[1] is not None:
        return telegram_tme_chat_url(int(row[1]))
    return None


def channel_title_html_link(row: tuple | None, *, fallback_chat_id: int | None = None) -> str:
    """HTML: посилання з назви каналу за рядком БД; без рядка — за fallback_chat_id."""
    if not row or len(row) < 3:
        if fallback_chat_id is not None:
            return chat_title_html_link_by_id(f"id {fallback_chat_id}", fallback_chat_id)
        return html_lib.escape("Канал", quote=False)
    title = str(row[2] or "Канал").strip() or "Канал"
    esc_t = html_lib.escape(title, quote=False)
    url = channel_row_public_url(row)
    if not url:
        return esc_t
    return f'<a href="{html_lib.escape(url, quote=True)}">{esc_t}</a>'
