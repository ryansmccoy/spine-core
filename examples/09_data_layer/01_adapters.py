#!/usr/bin/env python3
"""Database Adapters — Portable data access with SQLiteAdapter.

WHY ADAPTERS
────────────
Calling `sqlite3.connect()` directly scatters DB-specific code across
every module.  The Adapter pattern wraps connection, query, and
transaction logic behind a uniform interface.  When you switch from
SQLite to PostgreSQL, you swap the adapter — not every callsite.

ARCHITECTURE
────────────
    ┌─────────────────────────────────────┐
    │ get_adapter("sqlite", ":memory:")   │
    └─────────────────┬───────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────┐
    │ SQLiteAdapter                       │
    │   .execute(sql, params)             │
    │   .query(sql) → list[dict]          │
    │   .query_one(sql) → dict | None     │
    │   .transaction() → context manager  │
    └─────────────────────────────────────┘

    AdapterRegistry maps "sqlite" → SQLiteAdapter,
    "postgresql" → PostgresAdapter, etc.

BEST PRACTICES
──────────────
• Use get_adapter() factory instead of constructing directly.
• Wrap multi-statement work in adapter.transaction().
• Use query() for SELECT, execute() for INSERT/UPDATE/DDL.
• See 02_protocols for protocol-level abstraction.

Run: python examples/09_data_layer/01_adapters.py

See Also:
    02_protocols_and_storage — Connection protocol abstraction
    03_db_provider — dependency-injected connections
"""

from spine.core.adapters.registry import AdapterRegistry, adapter_registry, get_adapter
from spine.core.adapters.sqlite import SQLiteAdapter


def main():
    print("=" * 60)
    print("Database Adapters")
    print("=" * 60)

    # ── 1. Create adapter via factory ───────────────────────────
    print("\n--- 1. get_adapter() factory ---")
    adapter = get_adapter("sqlite", path=":memory:")
    adapter.connect()
    print(f"  Type:      {adapter.db_type.value}")
    print(f"  Connected: {adapter.is_connected}")

    # ── 2. Create table and insert data ─────────────────────────
    print("\n--- 2. Create table + insert ---")
    adapter.execute("""
        CREATE TABLE stocks (
            ticker TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sector TEXT,
            price REAL
        )
    """)

    stocks = [
        ("AAPL", "Apple Inc.", "Technology", 198.50),
        ("MSFT", "Microsoft Corp.", "Technology", 420.30),
        ("JPM", "JPMorgan Chase", "Financials", 195.80),
        ("JNJ", "Johnson & Johnson", "Healthcare", 155.20),
    ]
    adapter.executemany(
        "INSERT INTO stocks (ticker, name, sector, price) VALUES (?, ?, ?, ?)",
        stocks,
    )
    adapter.get_connection().commit()
    print(f"  Inserted {len(stocks)} stocks")

    # ── 3. Query data ───────────────────────────────────────────
    print("\n--- 3. Query ---")
    results = adapter.query("SELECT * FROM stocks ORDER BY ticker")
    for row in results:
        print(f"  {row['ticker']:5s} | {row['name']:20s} | {row['sector']:12s} | ${row['price']:.2f}")

    # query_one
    one = adapter.query_one("SELECT * FROM stocks WHERE ticker = ?", ("AAPL",))
    print(f"\n  query_one('AAPL'): {one['name']}, ${one['price']}")

    # ── 4. Transaction context manager ──────────────────────────
    print("\n--- 4. Transaction ---")
    with adapter.transaction() as conn:
        conn.execute(
            "UPDATE stocks SET price = ? WHERE ticker = ?",
            (200.00, "AAPL"),
        )
        conn.execute(
            "INSERT INTO stocks (ticker, name, sector, price) VALUES (?, ?, ?, ?)",
            ("GOOG", "Alphabet Inc.", "Technology", 178.20),
        )
    # Auto-committed on clean exit

    updated = adapter.query_one("SELECT price FROM stocks WHERE ticker = ?", ("AAPL",))
    print(f"  AAPL updated price: ${updated['price']:.2f}")

    total = adapter.query("SELECT COUNT(*) as cnt FROM stocks")
    print(f"  Total stocks: {total[0]['cnt']}")

    # ── 5. Transaction rollback on error ────────────────────────
    print("\n--- 5. Transaction rollback ---")
    try:
        with adapter.transaction() as conn:
            conn.execute("UPDATE stocks SET price = 999.99 WHERE ticker = 'AAPL'")
            raise ValueError("Simulated error!")
    except ValueError:
        pass  # Expected

    price_after = adapter.query_one("SELECT price FROM stocks WHERE ticker = ?", ("AAPL",))
    print(f"  AAPL price after rollback: ${price_after['price']:.2f} (unchanged)")

    # ── 6. Direct SQLiteAdapter usage ───────────────────────────
    print("\n--- 6. Direct SQLiteAdapter ---")
    direct = SQLiteAdapter(path=":memory:")
    direct.connect()
    direct.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)")
    direct.execute("INSERT INTO test VALUES (1, 'hello')")
    direct.get_connection().commit()
    row = direct.query_one("SELECT * FROM test WHERE id = 1")
    print(f"  Direct query: {dict(row)}")
    direct.disconnect()
    print(f"  Disconnected: {not direct.is_connected}")

    # ── 7. Adapter registry ─────────────────────────────────────
    print("\n--- 7. AdapterRegistry ---")
    print(f"  Registered adapters: {adapter_registry.list_adapters()}")

    # Clean up
    adapter.disconnect()

    print("\n" + "=" * 60)
    print("[OK] Database adapters example complete")


if __name__ == "__main__":
    main()
