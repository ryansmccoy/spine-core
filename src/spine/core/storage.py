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
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Connection(Protocol):
    """
    Minimal SYNCHRONOUS connection interface for database operations.
    
    This is a SYNC-ONLY protocol that defines the minimum operations
    needed for domain code to interact with databases. Tiers with async
    drivers (asyncpg) must provide sync adapters.
    
    Manifesto:
        Domain code should never deal with async complexity. By defining
        a sync protocol, we:
        - Keep domain logic simple and testable
        - Enable portability across deployment tiers
        - Push async wrapping to infrastructure
        
        The same domain code runs on SQLite (Basic tier) and PostgreSQL
        (Intermediate/Advanced/Full tiers) without modification.
    
    Architecture:
        ::
        
            Connection Protocol:
            ┌────────────────────────────────────────────────────────┐
            │ execute(sql, params)   → Execute single statement      │
            │ executemany(sql, list) → Execute for multiple params   │
            │ fetchone()             → Get one result row            │
            │ fetchall()             → Get all result rows           │
            │ commit()               → Commit transaction            │
            └────────────────────────────────────────────────────────┘
            
            Implementations:
            ┌────────────────────────────────────────────────────────┐
            │ Basic Tier        → sqlite3.Connection (native sync)   │
            │ Intermediate Tier → SyncPgAdapter wrapping asyncpg     │
            │ Advanced Tier     → SyncPgAdapter wrapping asyncpg     │
            │ Full Tier         → SyncPgAdapter wrapping asyncpg     │
            └────────────────────────────────────────────────────────┘
    
    Examples:
        >>> def store_records(conn: Connection, records: list[tuple]):
        ...     conn.executemany(
        ...         "INSERT INTO data (id, value) VALUES (?, ?)",
        ...         records
        ...     )
        ...     conn.commit()
        
        >>> result = conn.execute("SELECT * FROM data WHERE id = ?", (1,))
        >>> row = conn.fetchone()
    
    Tags:
        protocol, connection, sync, database, tier-agnostic
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
