"""SQLite database adapter."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from spine.core.errors import DatabaseConnectionError
from spine.core.protocols import Connection

from .base import DatabaseAdapter
from .types import DatabaseConfig, DatabaseType


class SQLiteAdapter(DatabaseAdapter):
    """
    SQLite database adapter.

    Uses the built-in sqlite3 module. Suitable for:
    - Development and testing
    - Basic tier deployments
    - Single-process applications
    """

    def __init__(
        self,
        path: str = ":memory:",
        *,
        readonly: bool = False,
        timeout: float = 5.0,
        **kwargs: Any,
    ):
        config = DatabaseConfig(
            db_type=DatabaseType.SQLITE,
            path=path,
            readonly=readonly,
            options=kwargs,
        )
        super().__init__(config)
        self._timeout = timeout
        self._conn: Any = None

    def connect(self) -> None:
        """Connect to SQLite database."""
        import sqlite3

        path = self._config.path or ":memory:"
        uri = path.startswith("file:") or "?" in path

        try:
            self._conn = sqlite3.connect(
                path,
                timeout=self._timeout,
                check_same_thread=False,
                uri=uri,
            )
            self._conn.row_factory = sqlite3.Row

            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")

            if self._config.readonly:
                self._conn.execute("PRAGMA query_only = ON")

            self._connected = True

        except sqlite3.Error as e:
            raise DatabaseConnectionError(
                f"Failed to connect to SQLite: {e}",
                cause=e,
            ) from e

    def disconnect(self) -> None:
        """Close SQLite connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._connected = False

    def get_connection(self) -> Connection:
        """Get the SQLite connection."""
        if not self._conn:
            self.connect()
        return self._conn

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Transaction context manager."""
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute query and return results as dicts."""
        conn = self.get_connection()
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


__all__ = [
    "SQLiteAdapter",
]
