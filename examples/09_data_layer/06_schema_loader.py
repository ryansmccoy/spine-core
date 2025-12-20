#!/usr/bin/env python3
"""Schema Loader — Bulk schema loading and introspection.

WHY SCHEMA LOADER
─────────────────
Manually executing CREATE TABLE statements one by one is fragile
and doesn’t scale.  The schema loader applies all .sql files from
a directory in one call, creates preconfigured test databases, and
introspects table structures for documentation or validation.

ARCHITECTURE
────────────
    schema/
    ├── core_executions.sql
    ├── core_events.sql
    └── core_anomalies.sql
         │
    apply_all_schemas(conn, schema_dir)
         │
    create_test_database() → in-memory with all tables
         │
    introspect_tables(conn) → {table: [columns]}

BEST PRACTICES
──────────────
• Use create_test_database() in unit tests for consistency.
• Use introspect_tables() to validate schema after loading.
• Use skip= parameter to exclude specific schema files.

Run: python examples/09_data_layer/06_schema_loader.py

See Also:
    04_migration_runner — versioned schema changes
    01_adapters — running schema DDL through adapters
"""

import sqlite3
import tempfile
from pathlib import Path

from spine.core.schema_loader import (
    SCHEMA_DIR,
    apply_all_schemas,
    create_test_db,
    get_schema_files,
    get_table_list,
    get_table_schema,
    read_schema_sql,
)


def main():
    print("=" * 60)
    print("Schema Loader Example")
    print("=" * 60)

    # 1. List available schema files
    print("\n1. Available schema files...")
    schema_files = get_schema_files()
    for f in schema_files:
        print(f"   {f.name}")

    print(f"\n   Schema directory: {SCHEMA_DIR}")

    # 2. Read all schema SQL
    print("\n2. Combined schema SQL (first 500 chars)...")
    combined_sql = read_schema_sql()
    print(f"   Total length: {len(combined_sql)} characters")
    print("   ---")
    print(combined_sql[:500])
    print("   ...")

    # 3. Quick test database creation
    print("\n3. Creating test database with all schemas...")
    conn = create_test_db()

    tables = get_table_list(conn)
    print(f"   Created {len(tables)} tables:")
    for table in tables[:10]:
        print(f"   - {table}")
    if len(tables) > 10:
        print(f"   ... and {len(tables) - 10} more")

    # 4. Inspect table schema
    print("\n4. Inspecting core_executions schema...")
    schema = get_table_schema(conn, "core_executions")
    print(f"   {schema}")

    # 5. Inspect anomalies schema
    print("\n5. Inspecting core_anomalies schema...")
    schema = get_table_schema(conn, "core_anomalies")
    # Pretty print
    for line in schema.split("\n"):
        print(f"   {line}")

    conn.close()

    # 6. Custom schema directory
    print("\n6. Custom schema directory example...")
    with tempfile.TemporaryDirectory() as tmpdir:
        custom_dir = Path(tmpdir)
        (custom_dir / "00_users.sql").write_text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
        """)
        (custom_dir / "01_posts.sql").write_text("""
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                title TEXT,
                body TEXT
            );
        """)

        custom_conn = sqlite3.connect(":memory:")
        applied = apply_all_schemas(custom_conn, custom_dir)
        print(f"   Applied: {applied}")

        tables = get_table_list(custom_conn)
        print(f"   Tables: {tables}")

        custom_conn.close()

    # 7. Skip specific files
    print("\n7. Selective schema loading...")
    skip_conn = sqlite3.connect(":memory:")
    applied = apply_all_schemas(
        skip_conn,
        skip_files=["01_orchestration.sql", "02_workflow_history.sql"],
    )
    print(f"   Applied: {applied}")
    print(f"   Tables: {get_table_list(skip_conn)[:5]}...")
    skip_conn.close()

    print("\n" + "=" * 60)
    print("Schema Loader Example Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
