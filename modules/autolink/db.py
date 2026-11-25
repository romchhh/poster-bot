"""Storage for channel autolink sets (one URL, many phrases)."""

from __future__ import annotations

from datetime import datetime, timezone

from database_functions.connection import conn, cursor


def create_autolink_tables() -> None:
    cursor.executescript(
        """
        CREATE TABLE IF NOT EXISTS autolink_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_autolink_sets_channel
            ON autolink_sets(channel_id, enabled);
        CREATE TABLE IF NOT EXISTS autolink_phrases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER NOT NULL,
            phrase TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (set_id) REFERENCES autolink_sets(id) ON DELETE CASCADE,
            UNIQUE(set_id, phrase)
        );
        """
    )
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def list_sets(channel_id: int, *, enabled_only: bool = False) -> list[tuple]:
    if enabled_only:
        cursor.execute(
            """
            SELECT id, user_id, channel_id, name, url, enabled
            FROM autolink_sets
            WHERE channel_id = ? AND enabled = 1
            ORDER BY id
            """,
            (int(channel_id),),
        )
    else:
        cursor.execute(
            """
            SELECT id, user_id, channel_id, name, url, enabled
            FROM autolink_sets
            WHERE channel_id = ?
            ORDER BY id
            """,
            (int(channel_id),),
        )
    return cursor.fetchall() or []


def get_set(set_id: int) -> tuple | None:
    cursor.execute(
        """
        SELECT id, user_id, channel_id, name, url, enabled
        FROM autolink_sets WHERE id = ?
        """,
        (int(set_id),),
    )
    return cursor.fetchone()


def phrase_count(set_id: int) -> int:
    cursor.execute(
        "SELECT COUNT(*) FROM autolink_phrases WHERE set_id = ?",
        (int(set_id),),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def list_phrases(set_id: int) -> list[tuple]:
    cursor.execute(
        """
        SELECT id, phrase FROM autolink_phrases
        WHERE set_id = ?
        ORDER BY length(phrase) DESC, id
        """,
        (int(set_id),),
    )
    return cursor.fetchall() or []


def rules_for_channel(channel_id: int) -> list[tuple[str, str]]:
    """Enabled (phrase, url) pairs, longest phrase first."""
    cursor.execute(
        """
        SELECT p.phrase, s.url
        FROM autolink_phrases p
        JOIN autolink_sets s ON s.id = p.set_id
        WHERE s.channel_id = ? AND s.enabled = 1
        ORDER BY length(p.phrase) DESC
        """,
        (int(channel_id),),
    )
    return [(row[0], row[1]) for row in (cursor.fetchall() or []) if row[0] and row[1]]


def add_set(user_id: int, channel_id: int, name: str, url: str) -> int:
    now = _now()
    cursor.execute(
        """
        INSERT INTO autolink_sets (user_id, channel_id, name, url, enabled, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (int(user_id), int(channel_id), name.strip(), url.strip(), now, now),
    )
    conn.commit()
    return int(cursor.lastrowid)


def add_phrases(set_id: int, phrases: list[str]) -> int:
    now = _now()
    added = 0
    for phrase in phrases:
        cleaned = " ".join(phrase.split())
        if not cleaned:
            continue
        cursor.execute(
            """
            INSERT OR IGNORE INTO autolink_phrases (set_id, phrase, created_at)
            VALUES (?, ?, ?)
            """,
            (int(set_id), cleaned, now),
        )
        if cursor.rowcount:
            added += 1
    conn.commit()
    return added


def toggle_set(set_id: int) -> bool:
    row = get_set(set_id)
    if not row:
        return False
    enabled = 0 if row[5] else 1
    cursor.execute(
        "UPDATE autolink_sets SET enabled = ?, updated_at = ? WHERE id = ?",
        (enabled, _now(), int(set_id)),
    )
    conn.commit()
    return bool(enabled)


def delete_set(set_id: int) -> None:
    cursor.execute("DELETE FROM autolink_phrases WHERE set_id = ?", (int(set_id),))
    cursor.execute("DELETE FROM autolink_sets WHERE id = ?", (int(set_id),))
    conn.commit()


def delete_phrase(phrase_id: int) -> None:
    cursor.execute("DELETE FROM autolink_phrases WHERE id = ?", (int(phrase_id),))
    conn.commit()


def get_phrase(phrase_id: int) -> tuple | None:
    cursor.execute(
        "SELECT id, set_id, phrase FROM autolink_phrases WHERE id = ?",
        (int(phrase_id),),
    )
    return cursor.fetchone()
