#!/usr/bin/env python3
"""Database Provider — Tier-agnostic connection injection.

WHY DEPENDENCY INJECTION
────────────────────────
Domain code shouldn’t know whether it’s running against SQLite (dev),
PostgreSQL (prod), or an in-memory database (tests).  The DB provider
pattern injects a connection factory at startup, and domain code calls
get_connection() without knowing the backend.

ARCHITECTURE
────────────
    startup:
        set_connection_provider(lambda: sqlite3.connect(...))

    domain code:
        conn = get_connection()   # no DB import needed
        conn.execute(sql)

    tests:
        set_connection_provider(lambda: in_memory_db())
        ...test...
        clear_connection_provider()

    The provider also resolves the correct Dialect
    for cross-backend SQL portability.

BEST PRACTICES
──────────────
• Call set_connection_provider() once at app startup.
• Call clear_connection_provider() in test teardown.
• Use get_connection() in all domain code — never import sqlite3.
• Combine with Dialect for portable SQL generation.

Run: python examples/09_data_layer/03_db_provider.py

See Also:
    01_adapters — adapter-based connection management
    02_protocols_and_storage — Connection protocol contract
    07_database_portability — Dialect abstraction
"""

import sqlite3

from spine.core.dialect import Dialect, SQLiteDialect
from spine.core.protocols import Connection
from spine.framework.db import (
    clear_connection_provider,
    get_connection,
    set_connection_provider,
)


def main():
    print("=" * 60)
    print("Database Provider Pattern")
    print("=" * 60)

    # ── 1. Problem: domain code needs DB but shouldn't know tier ─
    print("\n--- 1. The problem ---")
    print("  Domain code needs database access but shouldn't")
    print("  know if it's SQLite (dev) or PostgreSQL (prod).")
    print("  Solution: inject a connection provider at startup.")

    # ── 2. Set up provider (typically at application startup) ───
    print("\n--- 2. Set connection provider ---")

    # Basic tier: SQLite
    db_conn = sqlite3.connect(":memory:")
    db_conn.row_factory = sqlite3.Row
    db_conn.execute("PRAGMA foreign_keys = ON")

    # Set the global provider
    set_connection_provider(lambda: db_conn)
    print("  Provider set: SQLite in-memory")

    # ── 3. Domain code uses get_connection() ────────────────────
    print("\n--- 3. Domain code (knows nothing about SQLite) ---")

    def init_schema() -> None:
        """Domain code — create tables using provider."""
        conn = get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS filings (
                cik TEXT NOT NULL,
                form_type TEXT NOT NULL,
                filed_date TEXT,
                company TEXT,
                PRIMARY KEY (cik, form_type, filed_date)
            )
        """)
        conn.commit()

    def store_filing(
        cik: str, form_type: str, filed_date: str, company: str,
        dialect: Dialect = SQLiteDialect(),
    ) -> None:
        """Domain code — store a filing (portable SQL via dialect)."""
        conn = get_connection()
        ph = dialect.placeholders(4)
        conn.execute(
            f"INSERT INTO filings (cik, form_type, filed_date, company) VALUES ({ph})",
            (cik, form_type, filed_date, company),
        )
        conn.commit()

    def get_filings(cik: str, dialect: Dialect = SQLiteDialect()) -> list[dict]:
        """Domain code — query filings (portable SQL via dialect)."""
        conn = get_connection()
        cursor = conn.execute(
            f"SELECT * FROM filings WHERE cik = {dialect.placeholder(0)} ORDER BY filed_date DESC",
            (cik,),
        )
        return [dict(row) for row in cursor.fetchall()]

    # Execute domain operations
    init_schema()
    store_filing("0000320193", "10-K", "2025-01-03", "Apple Inc.")
    store_filing("0000320193", "10-Q", "2025-01-28", "Apple Inc.")
    store_filing("0000789019", "10-K", "2025-01-15", "Microsoft Corp.")

    apple_filings = get_filings("0000320193")
    print(f"  Apple filings: {len(apple_filings)}")
    for f in apple_filings:
        print(f"    {f['form_type']} filed {f['filed_date']}")

    msft_filings = get_filings("0000789019")
    print(f"  Microsoft filings: {len(msft_filings)}")

    # ── 4. Error when no provider set ───────────────────────────
    print("\n--- 4. Error without provider ---")
    clear_connection_provider()
    try:
        get_connection()
    except RuntimeError as e:
        print(f"  Expected error: {e}")

    # ── 5. Test isolation pattern ───────────────────────────────
    print("\n--- 5. Test isolation ---")
    print("  Tests can swap providers for isolation:")

    # Test 1: fresh DB
    test_db = sqlite3.connect(":memory:")
    test_db.row_factory = sqlite3.Row
    set_connection_provider(lambda: test_db)

    conn = get_connection()
    conn.execute("CREATE TABLE test (id INTEGER, val TEXT)")
    conn.execute("INSERT INTO test VALUES (1, 'test_value')")
    conn.commit()
    result = conn.execute("SELECT * FROM test").fetchall()
    print(f"  Test DB query: {[dict(r) for r in result]}")

    # Cleanup
    clear_connection_provider()
    test_db.close()
    print("  Provider cleared, test DB closed")

    # ── 6. Production pattern ───────────────────────────────────
    print("\n--- 6. Production pattern ---")
    print("  In production, the startup code would do:")
    print("    # Intermediate tier: PostgreSQL")
    print("    from myapp.db import create_pg_connection")
    print("    set_connection_provider(create_pg_connection)")
    print("")
    print("  Domain code stays IDENTICAL across tiers.")
    print("  Only the provider and dialect change at startup.")

    # Cleanup
    db_conn.close()

    print("\n" + "=" * 60)
    print("[OK] Database provider example complete")


if __name__ == "__main__":
    main()
