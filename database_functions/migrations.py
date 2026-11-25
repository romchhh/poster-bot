"""
Схемні міграції SQLite для існуючих баз.
Викликати з create_dbs() після create_* таблиць.
"""

from database_functions.posts_db import conn, cursor


def migrate_posts_url_buttons_column() -> None:
    """Додає колонку url_buttons до posts, якщо її ще немає (старі інсталяції)."""
    cursor.execute("PRAGMA table_info(posts)")
    cols = {row[1] for row in cursor.fetchall()}
    if "url_buttons" not in cols:
        cursor.execute("ALTER TABLE posts ADD COLUMN url_buttons TEXT")
        conn.commit()


def migrate_posts_media_columns() -> None:
    cursor.execute("PRAGMA table_info(posts)")
    cols = {row[1] for row in cursor.fetchall()}
    if "media_file_id" not in cols:
        cursor.execute("ALTER TABLE posts ADD COLUMN media_file_id TEXT")
        conn.commit()
    if "media_files" not in cols:
        cursor.execute("ALTER TABLE posts ADD COLUMN media_files TEXT")
        conn.commit()


def migrate_posts_published_source_column() -> None:
    """Джерело публікації: bot | external (пости в каналі не через бота)."""
    cursor.execute("PRAGMA table_info(posts)")
    cols = {row[1] for row in cursor.fetchall()}
    if "published_source" not in cols:
        cursor.execute(
            "ALTER TABLE posts ADD COLUMN published_source TEXT DEFAULT 'bot'"
        )
        conn.commit()


def run_posts_migrations() -> None:
    """Усі міграції таблиці posts."""
    migrate_posts_url_buttons_column()
    migrate_posts_published_source_column()
    migrate_posts_media_columns()
