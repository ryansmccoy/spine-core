"""Base repository with dialect-aware database access.

Provides :class:`BaseRepository` — an abstract base class that pairs a
:class:`~spine.core.protocols.Connection` with a :class:`~spine.core.dialect.Dialect`
so that domain repositories can write **portable** SQL without referencing
any specific database driver.

Architecture::

    ┌────────────────────────────────────────────────────────────────────┐
    │                       BaseRepository                               │
    │                                                                    │
    │   conn: Connection        ← protocol from spine.core.protocols     │
    │   dialect: Dialect         ← from spine.core.dialect                │
    │                                                                    │
    │   execute(sql, params)     → cursor                                │
    │   query(sql, params)       → list[dict]                            │
    │   query_one(sql, params)   → dict | None                           │
    │   insert(table, data)      → cursor                                │
    │   insert_many(table, rows) → int                                   │
    └────────────────────────────────────────────────────────────────────┘

Usage:
    >>> class MyRepo(BaseRepository):
    ...     def get_by_id(self, id: str):
    ...         return self.query_one(
    ...             f"SELECT * FROM my_table WHERE id = {self.ph(1)}",
    ...             (id,),
    ...         )

Tags:
    repository, database, abstraction, portability
"""

from __future__ import annotations

from typing import Any

from spine.core.dialect import Dialect, SQLiteDialect
from spine.core.protocols import Connection


class BaseRepository:
    """Dialect-aware base class for data-access repositories.

    Subclasses gain portable helper methods for building and executing
    SQL.  The :attr:`dialect` determines placeholder style, timestamp
    functions, and DML syntax.

    Parameters:
        conn: Any object satisfying the :class:`Connection` protocol.
        dialect: SQL dialect to use.  Defaults to :class:`SQLiteDialect`
                 for backward compatibility with existing code that passes
                 raw ``sqlite3.Connection`` objects.
    """

    def __init__(self, conn: Connection, dialect: Dialect | None = None) -> None:
        self.conn = conn
        self.dialect: Dialect = dialect or SQLiteDialect()

    @classmethod
    def from_session(
        cls,
        session: Any,
        dialect: Dialect | None = None,
        **kwargs: Any,
    ) -> BaseRepository:
        """Create a repository backed by a SQLAlchemy ORM session.

        Wraps *session* in :class:`~spine.core.orm.session.SAConnectionBridge`
        so that the same ``Connection``-based helpers (``execute``, ``query``,
        ``insert``, ``insert_many``) work transparently over an ORM session.

        Parameters:
            session: A ``sqlalchemy.orm.Session`` instance.
            dialect: SQL dialect.  Defaults to :class:`SQLiteDialect`.
            **kwargs: Forwarded to the subclass constructor (after *conn*
                      and *dialect*).

        Returns:
            A repository instance whose :attr:`conn` is the bridge adapter.

        Example::

            from sqlalchemy.orm import Session
            from spine.core.repository import BaseRepository

            with Session(engine) as session:
                repo = BaseRepository.from_session(session)
                repo.insert("my_table", {"id": "1", "name": "x"})
                repo.commit()
        """
        from spine.core.orm.session import SAConnectionBridge

        bridge = SAConnectionBridge(session)
        return cls(conn=bridge, dialect=dialect, **kwargs)  # type: ignore[arg-type]

    # -- Convenience shortcuts ---------------------------------------------

    def ph(self, count: int) -> str:
        """Shortcut for ``self.dialect.placeholders(count)``.

        Embed directly in f-strings:

            f"SELECT * FROM t WHERE id = {self.ph(1)}"
        """
        return self.dialect.placeholders(count)

    # -- Query helpers -----------------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute a statement and return the raw cursor/result."""
        return self.conn.execute(sql, params)

    def execute_many(self, sql: str, params: list[tuple]) -> Any:
        """Execute a statement with multiple parameter sets."""
        return self.conn.executemany(sql, params)

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute a SELECT and return rows as dicts.

        If the cursor exposes ``description`` (standard DB-API 2.0), column
        names are extracted automatically.  Falls back to list-of-tuples
        (wrapped in dicts with integer keys) when description is absent.
        """
        cursor = self.conn.execute(sql, params)
        rows = cursor.fetchall()
        if not rows:
            return []

        # Try dict(row) first — works with sqlite3.Row and psycopg2.DictCursor
        try:
            return [dict(row) for row in rows]
        except (TypeError, ValueError):
            pass

        # Fallback: use cursor.description
        if hasattr(cursor, "description") and cursor.description:
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row, strict=False)) for row in rows]

        # Last resort: integer-keyed dicts
        return [{i: v for i, v in enumerate(row)} for row in rows]

    def query_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Execute a SELECT and return the first row as a dict (or None)."""
        results = self.query(sql, params)
        return results[0] if results else None

    # -- Insert helpers ----------------------------------------------------

    def insert(self, table: str, data: dict[str, Any]) -> Any:
        """Insert a single row from a dict.

        Column names come from ``data.keys()``; values are bound via
        dialect placeholders.
        """
        columns = list(data.keys())
        values = list(data.values())
        ph = self.dialect.placeholders(len(values))
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({ph})"
        return self.conn.execute(sql, tuple(values))

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> int:
        """Insert multiple rows from a list of dicts.

        Returns the number of rows inserted.
        """
        if not rows:
            return 0

        columns = list(rows[0].keys())
        ph = self.dialect.placeholders(len(columns))
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({ph})"
        params = [tuple(row[col] for col in columns) for row in rows]
        self.conn.executemany(sql, params)
        return len(rows)

    def commit(self) -> None:
        """Commit the current transaction."""
        self.conn.commit()


__all__ = [
    "BaseRepository",
]
