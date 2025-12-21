"""Database adapter base class.

Manifesto:
    All database adapters share common lifecycle (connect/disconnect),
    query execution, and dialect management.  The abstract base class
    defines the interface contract so consumers never depend on a
    specific database vendor.

Features:
    - Abstract ``connect()``, ``disconnect()``, ``execute()``, ``query()``
    - Property-based dialect and connection-state introspection
    - Context-manager protocol for connection lifecycle
    - Config-driven construction from ``DatabaseConfig``

Tags:
    spine-core, database, abstract-base, adapter-pattern

Doc-Types:
    api-reference
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from spine.core.dialect import Dialect, get_dialect
from spine.core.protocols import Connection

from .types import DatabaseConfig, DatabaseType


class DatabaseAdapter(ABC):
    """
    Abstract base class for database adapters.

    Provides common functionality and defines the interface
    that all adapters must implement.
    """

    def __init__(self, config: DatabaseConfig):
        self._config = config
        self._connected = False
        self._dialect: Dialect = get_dialect(config.db_type.value)

    @property
    def dialect(self) -> Dialect:
        """SQL dialect for this adapter's database type."""
        return self._dialect

    @property
    def db_type(self) -> DatabaseType:
        """Database type."""
        return self._config.db_type

    @property
    def is_connected(self) -> bool:
        """Whether adapter is connected."""
        return self._connected

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to database."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection to database."""
        ...

    @abstractmethod
    def get_connection(self) -> Connection:
        """Get a connection (may be from pool)."""
        ...

    @abstractmethod
    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Context manager for a transaction."""
        ...

    def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement."""
        conn = self.get_connection()
        return conn.execute(sql, params)

    def executemany(self, sql: str, params: list[tuple]) -> Any:
        """Execute SQL for multiple parameter sets."""
        conn = self.get_connection()
        return conn.executemany(sql, params)

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute query and return results as dicts."""
        conn = self.get_connection()
        cursor = conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]

    def query_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Execute query and return single result."""
        results = self.query(sql, params)
        return results[0] if results else None

    def insert(
        self,
        table: str,
        data: dict[str, Any],
        returning: str | None = None,
    ) -> Any:
        """Insert a single row."""
        columns = list(data.keys())
        values = list(data.values())
        placeholders = self._get_placeholders(len(values))

        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        if returning:
            sql += f" RETURNING {returning}"

        return self.execute(sql, tuple(values))

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> int:
        """Insert multiple rows."""
        if not rows:
            return 0

        columns = list(rows[0].keys())
        placeholders = self._get_placeholders(len(columns))
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"

        params = [tuple(row[col] for col in columns) for row in rows]
        self.executemany(sql, params)
        return len(rows)

    def _get_placeholders(self, count: int) -> str:
        """Get placeholder string for SQL parameters.

        .. deprecated::
            Use ``self.dialect.placeholders(count)`` instead.
        """
        return self._dialect.placeholders(count)

    def __enter__(self) -> DatabaseAdapter:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


__all__ = [
    "DatabaseAdapter",
]
