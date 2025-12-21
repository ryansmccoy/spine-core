#!/usr/bin/env python3
"""Database Lifecycle — Initialize, inspect, health-check, and purge.

WHY AN OPERATIONS LAYER
───────────────────────
Calling raw SQL or schema functions directly couples your code to the
database layout.  The ops layer wraps every database action in a typed
request/response contract (OperationResult) — no exceptions escape, every
result includes timing and metadata, and the same interface works with
SQLite or PostgreSQL.

ARCHITECTURE
────────────
    Caller                            Ops Layer
    ──────                            ─────────
    init_database(ctx)         ──▶  create_core_tables + schema_loader
    inspect_database(ctx)      ──▶  list tables, row counts, size
    health_check(ctx)          ──▶  connection + read/write probe
    purge_database(ctx)        ──▶  drop all core_* tables

    Every function returns OperationResult:
      .success   → bool
      .data      → dict (schema-specific payload)
      .error     → str | None
      .duration  → float (seconds)

DATABASE TABLES MANAGED
───────────────────────
    27 core_* tables (see 10_full_table_population for complete list).
    _migrations table tracks applied schema versions.
    Schema upgrades are idempotent (safe to run repeatedly).

BEST PRACTICES
──────────────
• Always call init_database() at startup — it is idempotent.
• Use health_check() for Docker/K8s liveness probes.
• Use inspect_database() for operational dashboards.
• Never call purge_database() in production (test teardown only).

Run: python examples/10_operations/01_database_lifecycle.py

See Also:
    02_run_management — CRUD on execution runs
    10_full_table_population — populate all 27 tables
"""

import sys
from pathlib import Path

# Add examples directory to path for _db import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import get_demo_connection, load_env

from spine.ops.context import OperationContext
from spine.ops.database import (
    check_database_health,
    get_table_counts,
    initialize_database,
    purge_old_data,
)
from spine.ops.requests import DatabaseInitRequest, PurgeRequest


def main():
    print("=" * 60)
    print("Operations Layer — Database Lifecycle")
    print("=" * 60)

    # --- 1. Create an OperationContext ------------------------------------
    print("\n[1] OperationContext")
    
    # Load .env and get connection (in-memory or persistent based on config)
    load_env()
    conn, info = get_demo_connection(init_schema=False)  # We'll use initialize_database
    print(f"  Backend: {'persistent' if info.persistent else 'in-memory'}")

    ctx = OperationContext(conn=conn, caller="example")
    print(f"  request_id : {ctx.request_id}")
    print(f"  caller     : {ctx.caller}")
    print(f"  dry_run    : {ctx.dry_run}")

    # --- 2. Initialize database -------------------------------------------
    print("\n[2] Initialize Database (creates all core tables)")

    result = initialize_database(ctx)
    assert result.success
    print(f"  ✓ success       : {result.success}")
    print(f"  tables created  : {len(result.data.tables_created)}")
    for t in result.data.tables_created:
        print(f"    - {t}")
    print(f"  elapsed         : {result.elapsed_ms:.1f} ms")

    # --- 3. Dry-run mode --------------------------------------------------
    print("\n[3] Dry-Run Mode (preview without side effects)")

    dry_ctx = OperationContext(conn=conn, caller="example", dry_run=True)
    dry_result = initialize_database(dry_ctx)
    assert dry_result.success
    assert dry_result.data.dry_run is True
    print(f"  ✓ dry_run       : {dry_result.data.dry_run}")
    print(f"  would create    : {len(dry_result.data.tables_created)} tables")

    # --- 4. Table counts --------------------------------------------------
    print("\n[4] Table Counts")

    counts = get_table_counts(ctx)
    assert counts.success
    for tc in counts.data:
        print(f"  {tc.table:30s} → {tc.count} rows")

    # --- 5. Database health -----------------------------------------------
    print("\n[5] Database Health Check")

    health = check_database_health(ctx)
    assert health.success
    h = health.data
    print(f"  connected   : {h.connected}")
    print(f"  backend     : {h.backend}")
    print(f"  table_count : {h.table_count}")
    print(f"  latency     : {h.latency_ms:.2f} ms")

    # --- 6. Purge old data ------------------------------------------------
    print("\n[6] Purge Old Data (dry-run)")

    purge_dry = purge_old_data(
        dry_ctx,
        PurgeRequest(older_than_days=30),
    )
    assert purge_dry.success
    print(f"  ✓ dry_run       : {purge_dry.data.dry_run}")
    print(f"  would purge     : {purge_dry.data.tables_purged}")

    print("\n[6b] Purge Old Data (actual — empty tables, 0 deleted)")
    purge = purge_old_data(ctx, PurgeRequest(older_than_days=1))
    assert purge.success
    print(f"  rows deleted    : {purge.data.rows_deleted}")
    print(f"  tables purged   : {purge.data.tables_purged}")

    # --- 7. Serialisation -------------------------------------------------
    print("\n[7] Result → dict (JSON-ready)")

    d = health.to_dict()
    for k, v in d.items():
        print(f"  {k}: {v}")

    conn.close()
    print("\n✓ Database lifecycle complete.")


if __name__ == "__main__":
    main()
