"""
Canonical protocol definitions for spine-core.

This module defines the SINGLE SOURCE OF TRUTH for all structural
protocols used across spine-core. Every module that needs a Connection,
AsyncConnection, or other protocol should import from here.

Manifesto:
    Protocols define contracts without inheritance. They enable:
    - **Decoupling:** Modules depend on shape, not implementation
    - **Testability:** Any object matching the protocol works
    - **Portability:** Same domain code on SQLite, PostgreSQL, async drivers

    Before this module existed, Connection(Protocol) was duplicated in 9 files
    (~400 LOC of pure duplication). Now there is ONE definition, ONE docstring,
    ONE place to evolve the contract.

Architecture:
    ::

        protocols.py (YOU ARE HERE)
        ├── Connection          — sync DB protocol (sqlite3, psycopg2, etc.)
        ├── AsyncConnection     — async DB protocol (asyncpg, aiosqlite, etc.)
        ├── StorageBackend      — sync storage with connection + transaction mgmt
        ├── DispatcherProtocol  — event/task dispatch contract
        ├── OperationProtocol    — data operation contract
        └── ExecutorProtocol    — task executor contract

    Consumers:
        anomalies.py, idempotency.py, manifest.py, quality.py, rejects.py,
        storage.py, adapters/database.py, framework/db.py,
        orchestration/tracked_runner.py

Features:
    - **Connection:** Sync DB protocol (execute, fetchone, fetchall, commit)
    - **AsyncConnection:** Async DB protocol for advanced tier adapters
    - **StorageBackend:** Connection lifecycle + transaction management
    - **DispatcherProtocol:** Event/task dispatch contract for decoupled messaging
    - **OperationProtocol:** Data operation contract for operation steps
    - **ExecutorProtocol:** Task executor contract for scheduled/queued work

Guardrails:
    ❌ DON'T: Duplicate Connection(Protocol) in other modules
    ✅ DO: Import from spine.core.protocols (single source of truth)

    ❌ DON'T: Add async methods to the Connection protocol
    ✅ DO: Use AsyncConnection for async needs; domain code stays sync

    ❌ DON'T: Add implementation logic to protocol classes
    ✅ DO: Keep protocols pure contracts — implementations go in adapters

Performance:
    - Protocol overhead: Zero at runtime (structural subtyping)
    - isinstance() checks: Enabled via @runtime_checkable, O(n) on methods
    - No registration needed: Any object matching the shape satisfies the protocol

Context:
    Problem: Connection(Protocol) was duplicated in 9 files (~400 LOC of pure
        duplication). Changes to the contract required editing all 9 files.
    Solution: Single canonical definition with all protocols in one module.
        Every module imports from here.
    Alternatives Considered: ABC base classes (require inheritance), zope.interface
        (external dependency), informal duck typing (no IDE support).

Tags:
    protocol, connection, async, database, dispatcher, operation, executor,
    spine-core, contracts

Doc-Types:
    - API Reference
    - Architecture Decision Record
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Database Connection Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class Connection(Protocol):
    """
    Minimal SYNCHRONOUS connection interface for database operations.

    This is the CANONICAL definition — all modules must import from here.
    Defines the minimum operations for domain code to interact with databases.
    Tiers with async drivers (asyncpg) must provide sync adapters.

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
            │ rollback()             → Rollback transaction          │
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

    def rollback(self) -> None:
        """Rollback current transaction. SYNC."""
        ...


@runtime_checkable
class AsyncConnection(Protocol):
    """
    Async database connection interface for async-native consumers.

    Mirrors the sync Connection protocol but uses async/await. Designed
    for consumers that operate in async contexts (genai-spine, search-spine,
    feedspine) where wrapping async in sync adapters is wasteful.

    Manifesto:
        While domain code stays sync (via Connection), infrastructure and
        API layers often need native async. AsyncConnection provides that
        contract without forcing sync adapters on inherently async code.

    Examples:
        >>> async def fetch_records(conn: AsyncConnection):
        ...     await conn.execute("SELECT * FROM data WHERE active = ?", (True,))
        ...     return await conn.fetchall()

    Tags:
        protocol, connection, async, database, asyncpg, aiosqlite
    """

    async def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL statement with optional parameters. ASYNC."""
        ...

    async def executemany(self, sql: str, params: list[tuple]) -> Any:
        """Execute SQL statement for multiple parameter sets. ASYNC."""
        ...

    async def fetchone(self) -> Any:
        """Fetch one row from last query. ASYNC."""
        ...

    async def fetchall(self) -> list:
        """Fetch all rows from last query. ASYNC."""
        ...

    async def commit(self) -> None:
        """Commit current transaction. ASYNC."""
        ...

    async def rollback(self) -> None:
        """Rollback current transaction. ASYNC."""
        ...


# ---------------------------------------------------------------------------
# Component Protocols
# ---------------------------------------------------------------------------


class DispatcherProtocol(Protocol):
    """
    Contract for event/task dispatchers.

    Defines the minimal interface that dispatchers must satisfy.
    Enables orchestration code to depend on shape rather than concrete classes.

    Tags:
        protocol, dispatcher, event, decoupling
    """

    def dispatch(self, event: Any, **kwargs: Any) -> Any:
        """Dispatch an event or task for processing."""
        ...

    def register(self, event_type: str, handler: Any) -> None:
        """Register a handler for an event type."""
        ...


class OperationProtocol(Protocol):
    """
    Contract for data operations.

    Defines the minimal interface that all operation implementations must
    satisfy. Enables the framework to run arbitrary operations without
    knowing their concrete type.

    Tags:
        protocol, operation, data-processing, decoupling
    """

    @property
    def name(self) -> str:
        """Operation name."""
        ...

    def run(self, conn: Connection, **kwargs: Any) -> Any:
        """Execute the operation with a database connection."""
        ...


class ExecutorProtocol(Protocol):
    """
    Contract for task executors.

    Defines the minimal interface for running work units. Implementations
    include LocalExecutor (in-process), CeleryExecutor (distributed),
    and ThreadPoolExecutor (concurrent).

    Tags:
        protocol, executor, task, decoupling
    """

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Submit a callable for execution."""
        ...

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the executor, optionally waiting for pending tasks."""
        ...
