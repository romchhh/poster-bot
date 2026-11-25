from datetime import datetime
from database_functions.connection import conn, cursor


def _migrate_auto_signatures_one_per_channel():
    """Keep a single signature row per channel (prefer enabled, then oldest id)."""
    cursor.execute("SELECT DISTINCT channel_id FROM auto_signatures")
    for (cid,) in cursor.fetchall():
        cursor.execute(
            """
            SELECT id FROM auto_signatures
            WHERE channel_id = ?
            ORDER BY is_enabled DESC, id ASC
            LIMIT 1
            """,
            (cid,),
        )
        row = cursor.fetchone()
        if not row:
            continue
        keep_id = row[0]
        cursor.execute(
            "DELETE FROM auto_signatures WHERE channel_id = ? AND id != ?",
            (cid, keep_id),
        )
    conn.commit()


def create_auto_signatures_tables():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_signatures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            signature_name TEXT NOT NULL,
            signature_text TEXT NOT NULL,
            is_enabled INTEGER DEFAULT 0,
            created_date TEXT NOT NULL
        )
        """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_auto_sig_settings (
            channel_id INTEGER PRIMARY KEY,
            manual_posting INTEGER DEFAULT 0,
            forwarding INTEGER DEFAULT 0
        )
        """)
    conn.commit()
    _migrate_auto_signatures_one_per_channel()


def get_auto_signatures(channel_id: int):
    cursor.execute(
        """
        SELECT id, channel_id, signature_name, signature_text, is_enabled, created_date
        FROM auto_signatures
        WHERE channel_id = ?
        ORDER BY id ASC
        """,
        (channel_id,),
    )
    return cursor.fetchall()


def get_auto_signature_by_id(signature_id: int):
    cursor.execute(
        """
        SELECT id, channel_id, signature_name, signature_text, is_enabled, created_date
        FROM auto_signatures
        WHERE id = ?
        """,
        (signature_id,),
    )
    return cursor.fetchone()


def get_auto_signature(channel_id: int):
    """Єдиний підпис каналу (для постів); прапорець is_enabled більше не керує UI."""
    cursor.execute(
        """
        SELECT id, channel_id, signature_name, signature_text, is_enabled, created_date
        FROM auto_signatures
        WHERE channel_id = ?
        LIMIT 1
        """,
        (channel_id,),
    )
    return cursor.fetchone()


def add_auto_signature(
    channel_id: int, signature_name: str, signature_text: str
) -> bool:
    """Replace any existing signature for this channel with one new row (enabled)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("DELETE FROM auto_signatures WHERE channel_id = ?", (channel_id,))
    cursor.execute(
        """
        INSERT INTO auto_signatures (channel_id, signature_name, signature_text, is_enabled, created_date)
        VALUES (?, ?, ?, 1, ?)
        """,
        (channel_id, signature_name, signature_text, now),
    )
    conn.commit()
    return True


def update_auto_signature(
    signature_id: int, signature_name: str, signature_text: str
) -> bool:
    cursor.execute(
        """
        UPDATE auto_signatures
        SET signature_name = ?, signature_text = ?, is_enabled = 1
        WHERE id = ?
        """,
        (signature_name, signature_text, signature_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_auto_signature(signature_id: int) -> bool:
    cursor.execute("DELETE FROM auto_signatures WHERE id = ?", (signature_id,))
    conn.commit()
    return cursor.rowcount > 0
