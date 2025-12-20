#!/usr/bin/env python3
"""Database Portability — Write SQL that runs on any backend.

WHY DIALECT ABSTRACTION
───────────────────────
Different databases use different placeholder syntax (?, %s, :1),
timestamp functions (datetime('now'), NOW(), CURRENT_TIMESTAMP),
and upsert syntax (INSERT OR REPLACE, ON CONFLICT, MERGE).  The
Dialect abstraction generates correct SQL for each backend so your
domain code never contains `if sqlite: ... elif postgres: ...`.

DIALECT IMPLEMENTATIONS
───────────────────────
    Dialect          Placeholder   Timestamp         Upsert
    ──────────────── ───────────── ───────────────── ──────────────
    SQLiteDialect    ?             datetime('now')   INSERT OR REPLACE
    PostgresDialect  %s            NOW()             ON CONFLICT
    MySQLDialect     %s            NOW()             ON DUPLICATE KEY
    OracleDialect    :1            SYSTIMESTAMP      MERGE
    DB2Dialect       ?             CURRENT TIMESTAMP MERGE

    BaseRepository wraps Dialect for convenient
    insert(), query(), upsert() methods.

BEST PRACTICES
──────────────
• Use get_dialect(conn) to auto-detect from connection type.
• Use dialect.placeholder(n) instead of hard-coding ? or %s.
• Use dialect.upsert() for portable conflict resolution.
• Use BaseRepository to avoid writing raw SQL entirely.

Run: python examples/09_data_layer/07_database_portability.py

See Also:
    02_protocols_and_storage — Connection/StorageBackend protocols
    08_orm_integration — ORM alternative to raw Dialect SQL
"""

from __future__ import annotations

import sqlite3

from spine.core.dialect import (
    DB2Dialect,
    Dialect,
    MySQLDialect,
    OracleDialect,
    PostgreSQLDialect,
    SQLiteDialect,
    get_dialect,
    register_dialect,
)
from spine.core.repository import BaseRepository


def main() -> None:
    print("=" * 60)
    print("Database Portability via Dialect Abstraction")
    print("=" * 60)

    # ── 1. Meet the dialects ────────────────────────────────────
    print("\n--- 1. Built-in Dialects ---")
    dialects: list[Dialect] = [
        SQLiteDialect(),
        PostgreSQLDialect(),
        MySQLDialect(),
        DB2Dialect(),
        OracleDialect(),
    ]
    for d in dialects:
        print(f"  {d.name:12s}  placeholder(0) = {d.placeholder(0):6s}  "
              f"now() = {d.now()}")

    # ── 2. Placeholder generation ───────────────────────────────
    print("\n--- 2. Placeholders (for a 4-column INSERT) ---")
    for d in dialects:
        ph = d.placeholders(4)
        print(f"  {d.name:12s}  VALUES ({ph})")

    # ── 3. Portable timestamps ──────────────────────────────────
    print("\n--- 3. Interval expressions (24 hours ago) ---")
    for d in dialects:
        expr = d.interval(-24, "hours")
        print(f"  {d.name:12s}  {expr}")

    # ── 4. INSERT OR IGNORE ─────────────────────────────────────
    print("\n--- 4. INSERT OR IGNORE ---")
    cols = ["id", "name", "value"]
    for d in dialects:
        sql = d.insert_or_ignore("config", cols)
        # Show first 80 chars to keep it readable
        display = sql if len(sql) <= 80 else sql[:77] + "..."
        print(f"  {d.name:12s}  {display}")

    # ── 5. UPSERT ──────────────────────────────────────────────
    print("\n--- 5. UPSERT (key=id) ---")
    for d in dialects:
        sql = d.upsert("config", cols, ["id"])
        lines = sql.strip().split("\n")
        print(f"  {d.name:12s}  {lines[0]}")
        for line in lines[1:4]:
            print(f"  {'':12s}  {line}")
        if len(lines) > 4:
            print(f"  {'':12s}  ... ({len(lines) - 4} more lines)")

    # ── 6. get_dialect() factory (singleton) ────────────────────
    print("\n--- 6. get_dialect() factory ---")
    d1 = get_dialect("sqlite")
    d2 = get_dialect("sqlite")
    print(f"  get_dialect('sqlite') is singleton: {d1 is d2}")
    print(f"  get_dialect('postgresql').name: {get_dialect('postgresql').name}")

    # ── 7. Live demo with BaseRepository (SQLite) ───────────────
    print("\n--- 7. BaseRepository (SQLite in-memory) ---")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    dialect = SQLiteDialect()
    repo = BaseRepository(conn, dialect)

    # Create table
    repo.execute("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # Insert via dict
    repo.insert("events", {"domain": "sec", "message": "Filing received"})
    repo.insert("events", {"domain": "market", "message": "Price alert"})
    repo.insert("events", {"domain": "sec", "message": "Amendment filed"})
    repo.commit()

    # Query
    rows = repo.query(
        f"SELECT * FROM events WHERE domain = {repo.ph(1)}",
        ("sec",),
    )
    print(f"  Inserted 3 events, queried domain='sec': {len(rows)} rows")
    for row in rows:
        print(f"    id={row['id']}  message={row['message']}")

    # Query one
    row = repo.query_one(
        f"SELECT COUNT(*) as cnt FROM events WHERE domain = {repo.ph(1)}",
        ("market",),
    )
    print(f"  Market events count: {row['cnt']}")

    conn.close()

    # ── 8. Custom Dialect Registration ──────────────────────────
    print("\n--- 8. Custom Dialect Registration ---")

    class CockroachDialect(PostgreSQLDialect):
        """CockroachDB dialect — PostgreSQL compatible with tweaks."""
        name = "cockroach"

    register_dialect("cockroach", CockroachDialect())
    crdb = get_dialect("cockroach")
    print(f"  Registered 'cockroach' dialect: {crdb.name}")
    print(f"  placeholder(0) = {crdb.placeholder(0)}")
    print(f"  now() = {crdb.now()}")

    # ── 9. Portable query building pattern ──────────────────────
    print("\n--- 9. Portable Query Building ---")

    def build_purge_query(
        table: str, ts_col: str, days: int, dialect: Dialect,
    ) -> str:
        """Build a DELETE query that works on any backend."""
        cutoff = dialect.interval(-days, "days")
        return f"DELETE FROM {table} WHERE {ts_col} < {cutoff}"

    for d in dialects:
        sql = build_purge_query("core_anomalies", "detected_at", 30, d)
        print(f"  {d.name:12s}  {sql}")

    print("\n" + "=" * 60)
    print("Done! All SQL generated portably for 5 database backends.")
    print("=" * 60)


if __name__ == "__main__":
    main()
