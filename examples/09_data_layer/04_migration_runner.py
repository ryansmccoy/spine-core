#!/usr/bin/env python3
"""Migration Runner — Versioned schema upgrades with tracking.

WHY MIGRATIONS
──────────────
Manual ALTER TABLE scripts are error-prone and non-repeatable.
MigrationRunner tracks applied migrations in a `_migrations` table,
applies SQL files in filename order (00_, 01_, …), and is fully
idempotent — running it twice does nothing the second time.

ARCHITECTURE
────────────
    migrations/
    ├── 00_create_users.sql
    ├── 01_add_email_column.sql
    └── 02_create_audit_table.sql
         │
         ▼
    MigrationRunner(conn, migrations_dir)
    .apply_all()
         │
    ┌────┴───────────────────────┐
    │ _migrations table          │
    │   name, applied_at, hash   │
    │   (skip if already applied)│
    └───────────────────────────┘

BEST PRACTICES
──────────────
• Number migration files sequentially: 00_, 01_, 02_.
• Make each migration idempotent (IF NOT EXISTS).
• Never modify an already-applied migration file.
• Run apply_all() at app startup or deployment.

Run: python examples/09_data_layer/04_migration_runner.py

See Also:
    06_schema_loader — bulk schema loading utilities
    07_database_portability — dialect-aware DDL
"""

import sqlite3
import tempfile
from pathlib import Path

from spine.core.migrations import MigrationRunner


def main():
    print("=" * 60)
    print("Migration Runner Example")
    print("=" * 60)

    # Create temp directory with sample migrations
    with tempfile.TemporaryDirectory() as tmpdir:
        schema_dir = Path(tmpdir) / "migrations"
        schema_dir.mkdir()

        # Create numbered migration files
        # NOTE: Migration SQL is intentionally SQLite-specific.
        # In production, maintain per-dialect migration dirs
        # (e.g., migrations/sqlite/, migrations/postgresql/).
        # See src/spine/core/schema/ for the per-dialect DDL pattern.
        (schema_dir / "00_init.sql").write_text("""
            -- Initial schema
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)

        (schema_dir / "01_add_email.sql").write_text("""
            -- Add email column to users
            ALTER TABLE users ADD COLUMN email TEXT;
        """)

        (schema_dir / "02_orders.sql").write_text("""
            -- Orders table
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                total REAL,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)

        # Connect to in-memory database
        conn = sqlite3.connect(":memory:")
        runner = MigrationRunner(conn, schema_dir=schema_dir)

        # 1. Check pending migrations
        print("\n1. Checking pending migrations...")
        pending = runner.get_pending()
        print(f"   Pending: {pending}")

        # 2. Apply all pending
        print("\n2. Applying pending migrations...")
        result = runner.apply_pending()
        print(f"   Applied: {result.applied}")
        print(f"   Skipped: {result.skipped}")
        print(f"   Success: {result.success}")

        # 3. Verify idempotency
        print("\n3. Running again (should skip all)...")
        result2 = runner.apply_pending()
        print(f"   Applied: {result2.applied}")
        print(f"   Skipped: {result2.skipped}")

        # 4. Check applied migrations
        print("\n4. Checking applied migrations...")
        for rec in runner.get_applied():
            print(f"   {rec.id}: {rec.filename} @ {rec.applied_at}")

        # 5. Verify tables were created
        print("\n5. Verifying created tables...")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        print(f"   Tables: {tables}")

        # 6. Insert test data
        print("\n6. Inserting test data...")
        conn.execute("INSERT INTO users (username, email) VALUES (?, ?)", ("alice", "alice@example.com"))
        conn.execute("INSERT INTO orders (user_id, total) VALUES (?, ?)", (1, 99.99))
        conn.commit()

        cursor = conn.execute("SELECT * FROM users")
        print(f"   Users: {cursor.fetchall()}")

        cursor = conn.execute("SELECT * FROM orders")
        print(f"   Orders: {cursor.fetchall()}")

        # 7. Add a new migration and apply
        print("\n7. Adding new migration...")
        (schema_dir / "03_products.sql").write_text("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL
            );
        """)

        pending = runner.get_pending()
        print(f"   New pending: {pending}")

        result3 = runner.apply_pending()
        print(f"   Applied: {result3.applied}")

        # 8. Demonstrate rollback (tracking only)
        print("\n8. Rolling back last migration (tracking only)...")
        rolled_back = runner.rollback_last()
        print(f"   Rolled back: {rolled_back}")
        print(f"   Now pending: {runner.get_pending()}")

        conn.close()

    print("\n" + "=" * 60)
    print("Migration Runner Example Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
