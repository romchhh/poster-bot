from database_functions.connection import conn, cursor


def create_channel_start_emoji_table():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_start_emoji (
            channel_id INTEGER PRIMARY KEY,
            emoji_id TEXT NOT NULL,
            emoji_text TEXT NOT NULL
        )
        """
    )
    conn.commit()


def get_channel_start_emoji(channel_id: int):
    cursor.execute(
        "SELECT emoji_id, emoji_text FROM channel_start_emoji WHERE channel_id = ?",
        (channel_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def save_channel_start_emoji(channel_id: int, emoji_id: str, emoji_text: str) -> bool:
    cursor.execute(
        """
        INSERT INTO channel_start_emoji (channel_id, emoji_id, emoji_text)
        VALUES (?, ?, ?)
        ON CONFLICT(channel_id) DO UPDATE SET
            emoji_id = excluded.emoji_id,
            emoji_text = excluded.emoji_text
        """,
        (channel_id, emoji_id, emoji_text),
    )
    conn.commit()
    return True


def remove_channel_start_emoji(channel_id: int) -> bool:
    cursor.execute("DELETE FROM channel_start_emoji WHERE channel_id = ?", (channel_id,))
    conn.commit()
    return cursor.rowcount > 0
