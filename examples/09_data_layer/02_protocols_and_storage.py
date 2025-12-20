#!/usr/bin/env python3
"""Protocols and Storage — Type contracts and cross-dialect SQL.

WHY PROTOCOLS
─────────────
Inheriting from a base class to satisfy a type contract couples your
code to that base class.  Python Protocols (PEP 544) define contracts
via structural typing — any object with the right methods satisfies
the protocol automatically.  This means domain code depends on
*shapes*, not *implementations*.

ARCHITECTURE
────────────
    Domain Code
         │
    uses ▼
    ┌──────────────────┐       ┌─────────────────┐
    │ Connection       │       │ StorageBackend  │
    │ (Protocol)       │       │ (Protocol)      │
    │  .execute()      │       │  .store()       │
    │  .commit()       │       │  .retrieve()    │
    └────┬─────┬───────┘       └─────────────────┘
         │     │
    sqlite3  SAConnectionBridge
    conn     (wraps SA session)

    isinstance(sqlite3_conn, Connection) → True
    Dialect + SQLHelper generates portable SQL.

KEY COMPONENTS
──────────────
    Component       Purpose
    ─────────────── ───────────────────────────────
    Connection      Protocol for execute/commit/cursor
    Dialect         Generates backend-specific SQL
    SQLHelper       Cross-dialect upsert, placeholder
    StorageBackend  Protocol for store/retrieve

Run: python examples/09_data_layer/02_protocols_and_storage.py

See Also:
    01_adapters — concrete adapter implementations
    07_database_portability — all 5 dialect implementations
"""

import sqlite3

from spine.core.dialect import Dialect, SQLiteDialect, get_dialect
from spine.core.protocols import Connection
from spine.core.storage import SQLHelper, StorageBackend


def main():
    print("=" * 60)
    print("Protocols and Storage")
    print("=" * 60)

    # ── 1. Connection protocol conformance ──────────────────────
    print("\n--- 1. Connection protocol ---")
    # sqlite3.Connection satisfies the Connection protocol
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    is_connection = isinstance(conn, Connection)
    print(f"  sqlite3.Connection satisfies Connection protocol: {is_connection}")
    print(f"  Has execute:     {hasattr(conn, 'execute')}")
    print(f"  Has commit:      {hasattr(conn, 'commit')}")
    print(f"  Has rollback:    {hasattr(conn, 'rollback')}")
    print(f"  Has fetchall:    {hasattr(conn, 'fetchall') or hasattr(conn.execute('SELECT 1'), 'fetchall')}")

    # ── 2. Domain code using Connection protocol ────────────────
    print("\n--- 2. Protocol-based domain code ---")

    def create_schema(c: Connection) -> None:
        """Domain code that only depends on Connection protocol."""
        c.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending'
            )
        """)
        c.commit()

    def store_event(
        c: Connection, event_id: str, ticker: str, event_type: str,
        dialect: Dialect = SQLiteDialect(),
    ) -> None:
        """Insert using protocol + dialect — portable across all backends."""
        ph = dialect.placeholders(3)
        c.execute(
            f"INSERT INTO events (id, ticker, event_type) VALUES ({ph})",
            (event_id, ticker, event_type),
        )
        c.commit()

    def query_events(c: Connection, ticker: str, dialect: Dialect = SQLiteDialect()) -> list[dict]:
        """Query using protocol + dialect — portable across all backends."""
        cursor = c.execute(
            f"SELECT * FROM events WHERE ticker = {dialect.placeholder(0)}",
            (ticker,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # Use it with sqlite3 (Basic tier)
    dialect = SQLiteDialect()
    create_schema(conn)
    store_event(conn, "evt_001", "AAPL", "earnings_release", dialect)
    store_event(conn, "evt_002", "AAPL", "guidance_update", dialect)
    store_event(conn, "evt_003", "MSFT", "earnings_call", dialect)

    events = query_events(conn, "AAPL", dialect)
    print(f"  Stored {len(events)} AAPL events via Connection protocol:")
    for e in events:
        print(f"    {e['id']}: {e['event_type']}")

    # ── 3. SQLHelper — cross-dialect SQL ────────────────────────
    print("\n--- 3. SQLHelper ---")
    columns = ["id", "ticker", "event_type", "status"]
    key_cols = ["id"]

    # INSERT OR REPLACE
    sqlite_insert = SQLHelper.insert_or_replace("events", columns, dialect="sqlite")
    pg_insert = SQLHelper.insert_or_replace("events", columns, dialect="postgres")
    print("  INSERT OR REPLACE:")
    print(f"    SQLite: {sqlite_insert.strip()}")
    print(f"    PG:     {pg_insert.strip()}")

    # UPSERT
    sqlite_upsert = SQLHelper.upsert("events", columns, key_cols, dialect="sqlite")
    pg_upsert = SQLHelper.upsert("events", columns, key_cols, dialect="postgres")
    print("\n  UPSERT:")
    print(f"    SQLite: {' '.join(sqlite_upsert.split())}")
    print(f"    PG:     {' '.join(pg_upsert.split())}")

    # ── 4. Placeholder differences across backends ──────────────
    print("\n--- 4. Placeholder styles via Dialect ---")
    for name in ["sqlite", "postgresql", "mysql", "db2", "oracle"]:
        d = get_dialect(name)
        ph = d.placeholders(3)
        print(f"  {name:12s}: VALUES ({ph})")

    # ── 5. StorageBackend protocol check ────────────────────────
    print("\n--- 5. StorageBackend protocol ---")

    class SimpleBackend:
        """Minimal StorageBackend implementation for demo."""

        def __init__(self):
            self._conn = sqlite3.connect(":memory:")
            self._conn.row_factory = sqlite3.Row

        def get_connection(self) -> Connection:
            return self._conn

        def transaction(self):
            from contextlib import contextmanager

            @contextmanager
            def _txn():
                try:
                    yield self._conn
                    self._conn.commit()
                except Exception:
                    self._conn.rollback()
                    raise

            return _txn()

    backend = SimpleBackend()
    conforms = isinstance(backend, StorageBackend)
    print(f"  SimpleBackend conforms to StorageBackend: {conforms}")

    # Use the backend
    with backend.transaction() as c:
        c.execute("CREATE TABLE demo (id INTEGER, name TEXT)")
        c.execute("INSERT INTO demo VALUES (1, 'test')")

    result = backend.get_connection().execute("SELECT * FROM demo").fetchall()
    print(f"  Query via backend: {[dict(r) for r in result]}")

    conn.close()

    print("\n" + "=" * 60)
    print("[OK] Protocols and storage example complete")


if __name__ == "__main__":
    main()
