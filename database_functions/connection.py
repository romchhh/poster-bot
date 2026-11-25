from __future__ import annotations

import sqlite3
import threading
from typing import Any, Iterable, Sequence

from app.paths import DB_PATH, ensure_runtime_dirs

ensure_runtime_dirs()

_db_lock = threading.Lock()

_raw_conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30.0)
_raw_conn.execute("PRAGMA foreign_keys = ON")
_raw_conn.execute("PRAGMA journal_mode = WAL")
_raw_conn.execute("PRAGMA busy_timeout = 30000")


class LockedCursor:
    """One cursor per thread. A query and its rows are read under the same lock."""

    def __init__(self, connection: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = connection
        self._lock = lock
        self._local = threading.local()

    def _state(self) -> dict[str, Any]:
        state = getattr(self._local, "state", None)
        if state is None:
            state = {
                "cur": self._conn.cursor(),
                "rows": None,
                "index": 0,
                "lastrowid": None,
                "rowcount": -1,
                "description": None,
            }
            self._local.state = state
        return state

    def _capture(self, state: dict[str, Any]) -> None:
        cur = state["cur"]
        state["lastrowid"] = cur.lastrowid
        state["rowcount"] = cur.rowcount
        state["description"] = cur.description
        if cur.description is not None:
            state["rows"] = cur.fetchall()
        else:
            state["rows"] = None
        state["index"] = 0

    def execute(self, sql: str, parameters: Sequence[Any] | None = None):
        with self._lock:
            state = self._state()
            if parameters is None:
                state["cur"].execute(sql)
            else:
                state["cur"].execute(sql, parameters)
            self._capture(state)
            return self

    def executemany(self, sql: str, seq_of_parameters: Iterable[Sequence[Any]]):
        with self._lock:
            state = self._state()
            state["cur"].executemany(sql, seq_of_parameters)
            self._capture(state)
            return self

    def executescript(self, sql_script: str):
        with self._lock:
            state = self._state()
            state["cur"].executescript(sql_script)
            self._capture(state)
            return self

    def fetchone(self):
        state = self._state()
        rows = state["rows"] or []
        index = state["index"]
        if index >= len(rows):
            return None
        state["index"] = index + 1
        return rows[index]

    def fetchall(self):
        state = self._state()
        rows = state["rows"] or []
        index = state["index"]
        state["index"] = len(rows)
        return list(rows[index:])

    def fetchmany(self, size: int | None = None):
        state = self._state()
        rows = state["rows"] or []
        index = state["index"]
        take = len(rows) - index if size is None else size
        chunk = list(rows[index : index + take])
        state["index"] = index + len(chunk)
        return chunk

    @property
    def description(self):
        return self._state()["description"]

    @property
    def lastrowid(self):
        return self._state()["lastrowid"]

    @property
    def rowcount(self):
        return self._state()["rowcount"]

    def close(self) -> None:
        state = getattr(self._local, "state", None)
        if state is None:
            return
        with self._lock:
            state["cur"].close()
        self._local.state = None


class LockedConnection:
    """Proxy around sqlite3.Connection with a process-wide lock for commit/execute."""

    def __init__(self, connection: sqlite3.Connection, lock: threading.Lock) -> None:
        self._conn = connection
        self._lock = lock

    def execute(self, sql: str, parameters: Sequence[Any] | None = None):
        with self._lock:
            if parameters is None:
                return self._conn.execute(sql)
            return self._conn.execute(sql, parameters)

    def executemany(self, sql: str, seq_of_parameters: Iterable[Sequence[Any]]):
        with self._lock:
            return self._conn.executemany(sql, seq_of_parameters)

    def executescript(self, sql_script: str):
        with self._lock:
            return self._conn.executescript(sql_script)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    def cursor(self) -> LockedCursor:
        return LockedCursor(self._conn, self._lock)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


conn = LockedConnection(_raw_conn, _db_lock)
cursor = LockedCursor(_raw_conn, _db_lock)
