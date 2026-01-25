"""
Database-agnostic storage protocol (SYNC-ONLY).

Defines minimal interfaces that domains use for data access.
Tier-specific adapters implement these protocols.

IMPORTANT: All spine.core primitives use SYNCHRONOUS APIs only.
Higher tiers (Intermediate, Advanced, Full) provide sync adapters
that wrap their async drivers (asyncpg, etc.) for use with these primitives.

This design:
- Keeps domain code simple (no async/await)
- Makes domains truly portable across tiers
- Pushes async complexity to tier-specific infrastructure
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Connection(Protocol):
    """
    Minimal SYNCHRONOUS connection interface.

    This is a SYNC-ONLY protocol. Tiers with async drivers must provide
    sync adapters (e.g., run_sync() wrappers around asyncpg).

    Implementations:
    - Basic: sqlite3.Connection (native)
    - Intermediate: SyncPgAdapter wrapping asyncpg
    - Advanced: SyncPgAdapter wrapping asyncpg
    - Full: SyncPgAdapter wrapping asyncpg
    """

    def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement with optional parameters. SYNC."""
        ...

    def executemany(self, sql: str, params: list[tuple]) -> Any:
        """Execute SQL statement for multiple parameter sets. SYNC."""
        ...

    def fetchone(self) -> Any:
        """Fetch one row from last query. SYNC."""
        ...

    def fetchall(self) -> list:
        """Fetch all rows from last query. SYNC."""
        ...

    def commit(self) -> None:
        """Commit current transaction. SYNC."""
        ...


@runtime_checkable
class StorageBackend(Protocol):
    """
    Abstract SYNCHRONOUS storage for domain data.

    Provides connection access and transaction management.
    All methods are SYNC-ONLY.
    """

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """Context manager for a transaction. SYNC."""
        ...

    def get_connection(self) -> Connection:
        """Get a connection (may be from pool). SYNC."""
        ...


# =============================================================================
# SYNC ADAPTER PATTERN FOR ASYNC TIERS
# =============================================================================


class SyncPgAdapter:
    """
    Example sync adapter for asyncpg (used by Intermediate/Advanced/Full tiers).

    This class shows how higher tiers wrap async drivers to provide
    the sync Connection protocol that spine.core primitives require.

    Usage in higher tiers:
        import asyncio
        import asyncpg

        class SyncPgAdapter:
            def __init__(self, async_conn):
                self._conn = async_conn
                self._loop = asyncio.get_event_loop()

            def execute(self, sql, params=()):
                # Convert ? placeholders to $1, $2, etc.
                sql = self._convert_placeholders(sql)
                return self._loop.run_until_complete(
                    self._conn.fetch(sql, *params)
                )

            def commit(self):
                # asyncpg auto-commits; for explicit transactions use
                # async with conn.transaction()
                pass

    This adapter pattern allows the SAME domain code to run on:
    - Basic tier (sqlite3 native)
    - Intermediate tier (asyncpg via SyncPgAdapter)
    - Advanced tier (asyncpg via SyncPgAdapter)
    - Full tier (asyncpg via SyncPgAdapter)

    Note: For actual async workloads in pipelines, the tier's infrastructure
    handles async orchestration. The spine.core primitives always see sync.
    """

    pass  # Implementation provided by each tier


class SQLHelper:
    """
    SQL generation helpers that work across SQLite/PostgreSQL.

    Helps domains avoid writing DB-specific SQL.
    """

    @staticmethod
    def insert_or_replace(table: str, columns: list[str], dialect: str = "sqlite") -> str:
        """
        Generate INSERT OR REPLACE statement.

        Args:
            table: Table name
            columns: Column names
            dialect: "sqlite" or "postgres"
        """
        placeholders = ", ".join(
            "?" if dialect == "sqlite" else f"${i + 1}" for i in range(len(columns))
        )
        cols = ", ".join(columns)

        if dialect == "sqlite":
            return f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"
        else:
            # PostgreSQL uses ON CONFLICT
            return f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"

    @staticmethod
    def upsert(
        table: str, columns: list[str], key_columns: list[str], dialect: str = "sqlite"
    ) -> str:
        """
        Generate UPSERT statement.

        Args:
            table: Table name
            columns: All column names
            key_columns: Primary key columns (for conflict detection)
            dialect: "sqlite" or "postgres"
        """
        placeholders = ", ".join(
            "?" if dialect == "sqlite" else f"${i + 1}" for i in range(len(columns))
        )
        cols = ", ".join(columns)
        update_cols = [c for c in columns if c not in key_columns]

        if dialect == "sqlite":
            updates = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
            keys = ", ".join(key_columns)
            return f"""
                INSERT INTO {table} ({cols}) VALUES ({placeholders})
                ON CONFLICT ({keys}) DO UPDATE SET {updates}
            """
        else:
            # PostgreSQL version
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            keys = ", ".join(key_columns)
            return f"""
                INSERT INTO {table} ({cols}) VALUES ({placeholders})
                ON CONFLICT ({keys}) DO UPDATE SET {updates}
            """
