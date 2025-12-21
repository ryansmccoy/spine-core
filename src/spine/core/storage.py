"""
Database-agnostic storage protocol (SYNC-ONLY).

Defines minimal interfaces that domains use for data access.
Tier-specific adapters implement these protocols.

Manifesto:
    Spine domains must be portable across deployment tiers:
    - Basic: SQLite for single-machine development
    - Intermediate: PostgreSQL for production
    - Advanced/Full: Async PostgreSQL with connection pooling

    This module provides a SYNCHRONOUS protocol that all tiers implement.
    Higher tiers wrap their async drivers (asyncpg) in sync adapters.

    Key principles:
    - **Sync-only:** Domain code never sees async/await
    - **Protocol-based:** Duck typing via Protocol classes
    - **Tier-agnostic:** Same domain code on any tier

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Storage Protocol Stack                    │
        └─────────────────────────────────────────────────────────────┘

        Domain Code (SYNC):
        ┌────────────────────────────────────────────────────────────┐
        │ def process(conn: Connection):                             │
        │     conn.execute("INSERT INTO ...", (values,))             │
        │     conn.commit()                                          │
        └────────────────────────────────────────────────────────────┘
                              │
                              │ uses Protocol
                              ▼
        ┌────────────────────────────────────────────────────────────┐
        │              Connection Protocol (SYNC)                     │
        │  execute() | executemany() | fetchone() | fetchall() | ... │
        └────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
        ┌───────────▼────────┐  ┌──────▼──────────────┐
        │ Basic Tier:        │  │ Intermediate+:       │
        │ sqlite3.Connection │  │ SyncPgAdapter       │
        │ (native sync)      │  │ (wraps asyncpg)     │
        └────────────────────┘  └─────────────────────┘

Features:
    - **Connection protocol:** execute, executemany, fetchone, fetchall, commit
    - **StorageBackend protocol:** transaction(), get_connection()
    - **SyncPgAdapter pattern:** Example adapter for async drivers
    - **SQLHelper:** Cross-dialect SQL generation

Examples:
    Using Connection protocol:

    >>> def store_data(conn: Connection, data: list[tuple]):
    ...     conn.executemany("INSERT INTO table VALUES (?, ?)", data)
    ...     conn.commit()

    Using StorageBackend:

    >>> with backend.transaction() as conn:
    ...     conn.execute("UPDATE ...")
    ...     conn.execute("INSERT ...")
    ...     # auto-commits on exit

Performance:
    - Protocol overhead: Negligible (duck typing)
    - SyncPgAdapter: run_until_complete() overhead per call
    - For batch operations, use executemany()

Guardrails:
    - SYNC-ONLY: No async methods in protocols
    - runtime_checkable: Protocols can be used with isinstance()
    - Tier-specific adapters handle async wrapping
    - SQLHelper avoids dialect-specific SQL

Context:
    - Domain: Data access, database abstraction
    - Used By: All Spine domain code
    - Implements: Connection, StorageBackend protocols
    - Tiers: Basic (SQLite), Intermediate+ (PostgreSQL)

Tags:
    storage, protocol, database, sync, tier-agnostic,
    spine-core, connection, adapter

Doc-Types:
    - API Reference
    - Architecture Documentation
    - Tier Implementation Guide

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
from typing import Protocol, runtime_checkable

from .dialect import Dialect, SQLiteDialect, get_dialect
from .protocols import Connection


@runtime_checkable
class StorageBackend(Protocol):
    """
    Abstract SYNCHRONOUS storage backend for domain data.

    Provides connection access and transaction management. All methods
    are SYNC-ONLY. Use transaction() for automatic commit/rollback.

    Manifesto:
        StorageBackend abstracts away connection management:
        - Connection pooling (handled by tier infrastructure)
        - Transaction boundaries (via context manager)
        - Resource cleanup (automatic on context exit)

        Domains use StorageBackend without knowing about pools or drivers.

    Architecture:
        ::

            StorageBackend Protocol:
            ┌────────────────────────────────────────────────────────┐
            │ transaction()     → Context manager yielding Connection│
            │ get_connection()  → Get raw Connection (caller manages)│
            └────────────────────────────────────────────────────────┘

            Transaction Flow:
            ┌─────────────────────────────────────────────────────────┐
            │ with backend.transaction() as conn:                    │
            │     conn.execute("UPDATE ...")  # Within transaction   │
            │     conn.execute("INSERT ...")  # Still in transaction │
            │ # Auto-commits on successful exit                      │
            │ # Auto-rollbacks on exception                          │
            └─────────────────────────────────────────────────────────┘

    Examples:
        >>> with backend.transaction() as conn:
        ...     conn.execute("UPDATE accounts SET balance = balance - ?", (100,))
        ...     conn.execute("UPDATE accounts SET balance = balance + ?", (100,))
        ...     # Commits atomically on exit

    Tags:
        protocol, storage, transaction, sync, backend
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

    Note: For actual async workloads in operations, the tier's infrastructure
    handles async orchestration. The spine.core primitives always see sync.
    """

    pass  # Implementation provided by each tier


class SQLHelper:
    """
    SQL generation helpers that delegate to Dialect.

    Wraps Dialect methods for convenience. Prefer using Dialect directly
    in new code.
    """

    @staticmethod
    def _resolve_dialect(dialect: Dialect | str) -> Dialect:
        """Convert string dialect name to Dialect instance."""
        if isinstance(dialect, str):
            return get_dialect(dialect)
        return dialect

    @staticmethod
    def insert_or_replace(table: str, columns: list[str], dialect: Dialect | str = SQLiteDialect()) -> str:
        """
        Generate INSERT OR REPLACE statement.

        Args:
            table: Table name
            columns: Column names
            dialect: Dialect instance or name (default: SQLiteDialect)
        """
        d = SQLHelper._resolve_dialect(dialect)
        return d.insert_or_replace(table, columns)

    @staticmethod
    def upsert(table: str, columns: list[str], key_columns: list[str], dialect: Dialect | str = SQLiteDialect()) -> str:
        """
        Generate UPSERT statement.

        Args:
            table: Table name
            columns: All column names
            key_columns: Primary key columns (for conflict detection)
            dialect: Dialect instance or name (default: SQLiteDialect)
        """
        d = SQLHelper._resolve_dialect(dialect)
        return d.upsert(table, columns, key_columns)
