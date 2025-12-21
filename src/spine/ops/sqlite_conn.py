"""SQLite connection adapter.

Wraps a raw :class:`sqlite3.Connection` to satisfy the
:class:`~spine.core.protocols.Connection` protocol.

A bare ``sqlite3.Connection`` exposes ``execute()`` (returns a cursor)
but not ``fetchone()`` / ``fetchall()`` at the connection level.  This
adapter bridges the gap so domain code using the ``Connection`` protocol
works identically on SQLite and PostgreSQL.

Usage::

    from spine.ops.sqlite_conn import SqliteConnection

    conn = SqliteConnection(":memory:")
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.execute("INSERT INTO t VALUES (?)", (1,))
    conn.execute("SELECT * FROM t")
    row = conn.fetchone()          # works!
    conn.commit()
    conn.close()
"""

from __future__ import annotations

import sqlite3
from typing import Any


class SqliteConnection:
    """Adapter: ``sqlite3.Connection`` → ``Connection`` protocol.

    Maintains a single cursor so that ``execute`` / ``fetchone`` /
    ``fetchall`` operate on the same result set, matching the protocol
    contract used by ``spine.ops`` functions.
    """

    def __init__(self, path: str = ":memory:", *, row_factory: Any = sqlite3.Row) -> None:
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = row_factory
        self._cursor = self._conn.cursor()

    # -- Connection protocol -----------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> Any:
        self._cursor.execute(sql, params)
        return self._cursor

    def executemany(self, sql: str, params: list[tuple]) -> Any:
        self._cursor.executemany(sql, params)
        return self._cursor

    def fetchone(self) -> Any:
        return self._cursor.fetchone()

    def fetchall(self) -> list:
        return self._cursor.fetchall()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    # -- convenience -------------------------------------------------------

    @property
    def raw(self) -> sqlite3.Connection:
        """Access the underlying ``sqlite3.Connection`` (e.g. for pragmas)."""
        return self._conn

    def __repr__(self) -> str:
        return f"SqliteConnection({self._conn!r})"
