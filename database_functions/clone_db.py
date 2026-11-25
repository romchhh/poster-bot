"""Параметри копії для scope (`copy_scope_*` у SQLite)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from database_functions.connection import conn, cursor


def create_clone_tables() -> None:
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS copy_scope_settings (
            scope_type TEXT NOT NULL,
            scope_id   TEXT NOT NULL,
            paused     INTEGER NOT NULL DEFAULT 0,
            bell       INTEGER NOT NULL DEFAULT 1,
            ai_rewrite INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT    NOT NULL,
            PRIMARY KEY (scope_type, scope_id)
        );

        CREATE TABLE IF NOT EXISTS copy_scope_blacklist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            scope_type TEXT    NOT NULL,
            scope_id   TEXT    NOT NULL,
            word       TEXT    NOT NULL,
            created_at TEXT    NOT NULL,
            UNIQUE (user_id, scope_type, scope_id, word)
        );

        CREATE INDEX IF NOT EXISTS idx_cscope_bl
            ON copy_scope_blacklist (user_id, scope_type, scope_id);

        CREATE TABLE IF NOT EXISTS copy_scope_auto_subscribe (
            scope_type TEXT NOT NULL,
            scope_id   TEXT NOT NULL,
            body_html  TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (scope_type, scope_id)
        );
        """)
    conn.commit()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _key(scope_type: str, scope_id: Any) -> tuple[str, str]:
    return scope_type, str(scope_id)


def _ensure(scope_type: str, scope_id: Any) -> None:
    st, sid = _key(scope_type, scope_id)
    cursor.execute(
        "SELECT 1 FROM copy_scope_settings WHERE scope_type=? AND scope_id=?", (st, sid)
    )
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO copy_scope_settings (scope_type,scope_id,paused,bell,ai_rewrite,updated_at)"
            " VALUES(?,?,0,1,0,?)",
            (st, sid, _now()),
        )
        conn.commit()


# ── читання ──────────────────────────────────────────────────────────────────


def get_copy_scope_settings(scope_type: str, scope_id: Any) -> dict[str, bool]:
    _ensure(scope_type, scope_id)
    st, sid = _key(scope_type, scope_id)
    cursor.execute(
        "SELECT paused, bell, ai_rewrite FROM copy_scope_settings WHERE scope_type=? AND scope_id=?",
        (st, sid),
    )
    row = cursor.fetchone()
    if not row:
        return {"paused": False, "bell": True, "ai_rewrite": False}
    return {"paused": bool(row[0]), "bell": bool(row[1]), "ai_rewrite": bool(row[2])}


# ── перемикачі ───────────────────────────────────────────────────────────────

_TOGGLEABLE_FIELDS = frozenset({"bell", "paused", "ai_rewrite"})


def _toggle_field(field: str, scope_type: str, scope_id: Any) -> bool:
    if field not in _TOGGLEABLE_FIELDS:
        raise ValueError(f"Unsupported settings field: {field}")
    _ensure(scope_type, scope_id)
    st, sid = _key(scope_type, scope_id)
    cursor.execute(
        f"UPDATE copy_scope_settings SET {field}=1-{field}, updated_at=? WHERE scope_type=? AND scope_id=?",
        (_now(), st, sid),
    )
    conn.commit()
    cursor.execute(
        f"SELECT {field} FROM copy_scope_settings WHERE scope_type=? AND scope_id=?",
        (st, sid),
    )
    return bool(cursor.fetchone()[0])


def toggle_copy_bell(scope_type: str, scope_id: Any) -> bool:
    return _toggle_field("bell", scope_type, scope_id)


def toggle_copy_pause(scope_type: str, scope_id: Any) -> bool:
    return _toggle_field("paused", scope_type, scope_id)


def toggle_copy_ai(scope_type: str, scope_id: Any) -> bool:
    return _toggle_field("ai_rewrite", scope_type, scope_id)


# ── чорний список ────────────────────────────────────────────────────────────


def get_copy_blacklist(
    user_id: int, scope_type: str, scope_id: Any
) -> list[tuple[int, str]]:
    st, sid = _key(scope_type, scope_id)
    cursor.execute(
        "SELECT id, word FROM copy_scope_blacklist WHERE user_id=? AND scope_type=? AND scope_id=? ORDER BY id",
        (user_id, st, sid),
    )
    return [(int(r[0]), str(r[1])) for r in cursor.fetchall()]


def add_copy_blacklist_word(
    user_id: int, scope_type: str, scope_id: Any, word: str
) -> bool:
    w = word.strip()
    if not w:
        return False
    st, sid = _key(scope_type, scope_id)
    try:
        cursor.execute(
            "INSERT INTO copy_scope_blacklist (user_id,scope_type,scope_id,word,created_at) VALUES(?,?,?,?,?)",
            (user_id, st, sid, w, _now()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_copy_blacklist_word_by_id(word_id: int) -> str | None:
    cursor.execute("SELECT word FROM copy_scope_blacklist WHERE id=?", (word_id,))
    r = cursor.fetchone()
    return str(r[0]) if r else None


def remove_copy_blacklist_word(word_id: int) -> bool:
    cursor.execute("DELETE FROM copy_scope_blacklist WHERE id=?", (word_id,))
    conn.commit()
    return cursor.rowcount > 0


def clear_copy_blacklist(user_id: int, scope_type: str, scope_id: Any) -> bool:
    st, sid = _key(scope_type, scope_id)
    cursor.execute(
        "DELETE FROM copy_scope_blacklist WHERE user_id=? AND scope_type=? AND scope_id=?",
        (user_id, st, sid),
    )
    conn.commit()
    return True
