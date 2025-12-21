#!/usr/bin/env python3
"""Source Management — Data sources, fetches, cache, and database connections.

WHY OPS-LAYER SOURCE MANAGEMENT
────────────────────────────────
The framework FileSource (08_framework/06) fetches data; the ops layer
tracks *which* sources exist, *when* they were last fetched, *what*
changed (cache hashes), and *which* database connections are available.
This enables data lineage, incremental processing, and operational
dashboards.

ARCHITECTURE
────────────
    FileSource.fetch()                 ← 08_framework/06
         │
         ▼
    ops.sources.register_source()      ← this example
    ops.sources.record_fetch()
    ops.sources.check_cache()
    ops.sources.list_connections()
         │
         ▼
    ┌──────────────────────────────────────┐
    │ core_sources                     │
    │ core_source_fetches              │
    │ core_source_cache                │
    │ core_database_connections        │
    └──────────────────────────────────────┘

BEST PRACTICES
──────────────
• Register sources at startup so lineage is traceable.
• Record every fetch for audit and debugging.
• Use cache hashes to skip unchanged files (incremental ingest).
• Track database connections for multi-backend management.

Run: python examples/10_operations/06_source_management.py

See Also:
    08_framework/06_source_connectors — framework-level FileSource
    05_alert_management — alert on source failures
"""

import sys
from pathlib import Path

# Add examples directory to path for _db import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import get_demo_connection, load_env

from spine.core.schema_loader import apply_all_schemas
from spine.ops.context import OperationContext
from spine.ops.sources import (
    list_sources,
    get_source,
    register_source,
    delete_source,
    enable_source,
    disable_source,
    list_source_fetches,
    list_source_cache,
    invalidate_source_cache,
    list_database_connections,
    register_database_connection,
    delete_database_connection,
    test_database_connection,
)
from spine.ops.requests import (
    ListSourcesRequest,
    CreateSourceRequest,
    ListSourceFetchesRequest,
    ListDatabaseConnectionsRequest,
    CreateDatabaseConnectionRequest,
)


def main():
    print("=" * 60)
    print("Operations Layer — Source Management")
    print("=" * 60)
    
    # Load .env and get connection (in-memory or persistent based on config)
    load_env()
    conn, info = get_demo_connection()
    print(f"  Backend: {'persistent' if info.persistent else 'in-memory'}")

    apply_all_schemas(conn)
    ctx = OperationContext(conn=conn, caller="example")

    # --- 1. Empty sources -------------------------------------------------
    print("\n[1] List Sources (empty)")

    result = list_sources(ctx, ListSourcesRequest())
    assert result.success
    print(f"  total : {result.total}")

    # --- 2. Register sources ----------------------------------------------
    print("\n[2] Register Data Sources")

    sources_data = [
        CreateSourceRequest(
            name="sec-edgar-rss",
            source_type="http",
            config={"url": "https://www.sec.gov/cgi-bin/browse-edgar", "interval": 300},
            domain="sec",
        ),
        CreateSourceRequest(
            name="finra-otc-file",
            source_type="file",
            config={"path": "/data/finra/otc", "pattern": "*.csv"},
            domain="otc",
        ),
        CreateSourceRequest(
            name="equity-market-s3",
            source_type="s3",
            config={"bucket": "market-data", "prefix": "equity/daily/"},
            domain="equity",
        ),
        CreateSourceRequest(
            name="disabled-legacy",
            source_type="sftp",
            config={"host": "legacy.example.com", "path": "/exports"},
            domain="legacy",
            enabled=False,
        ),
    ]

    source_ids = []
    for req in sources_data:
        res = register_source(ctx, req)
        assert res.success, f"Failed: {res.error}"
        source_ids.append(res.data["id"])
        print(f"  + {res.data['id']}  {req.name:22s}  {req.source_type}  domain={req.domain}")

    # --- 3. List all sources ----------------------------------------------
    print("\n[3] List All Sources")

    result = list_sources(ctx, ListSourcesRequest())
    assert result.success
    print(f"  total : {result.total}")
    for src in result.data:
        print(f"  {src.id}  {src.name:22s}  type={src.source_type}  enabled={src.enabled}")

    # --- 4. Filter by type ------------------------------------------------
    print("\n[4] Filter Sources by Type = 'http'")

    result = list_sources(ctx, ListSourcesRequest(source_type="http"))
    assert result.success
    print(f"  total : {result.total}")
    for src in result.data:
        print(f"  {src.id}  {src.name}")

    # --- 5. Filter by domain ----------------------------------------------
    print("\n[5] Filter Sources by Domain = 'otc'")

    result = list_sources(ctx, ListSourcesRequest(domain="otc"))
    assert result.success
    print(f"  total : {result.total}")
    for src in result.data:
        print(f"  {src.id}  {src.name}  domain={src.domain}")

    # --- 6. Filter by enabled ---------------------------------------------
    print("\n[6] Filter Sources by Enabled = False")

    result = list_sources(ctx, ListSourcesRequest(enabled=False))
    assert result.success
    print(f"  total : {result.total}")
    for src in result.data:
        print(f"  {src.id}  {src.name}  enabled={src.enabled}")

    # --- 7. Get source detail ---------------------------------------------
    print("\n[7] Get Source Detail")

    detail = get_source(ctx, source_ids[0])
    assert detail.success
    d = detail.data
    print(f"  id        : {d.id}")
    print(f"  name      : {d.name}")
    print(f"  type      : {d.source_type}")
    print(f"  domain    : {d.domain}")
    print(f"  enabled   : {d.enabled}")

    # --- 8. Disable / Enable source ---------------------------------------
    print("\n[8] Disable and Re-Enable Source")

    dis = disable_source(ctx, source_ids[0])
    assert dis.success
    print(f"  disabled : {source_ids[0]}")

    verify = get_source(ctx, source_ids[0])
    print(f"  enabled now : {verify.data.enabled}")

    enab = enable_source(ctx, source_ids[0])
    assert enab.success
    print(f"  re-enabled : {source_ids[0]}")

    verify2 = get_source(ctx, source_ids[0])
    print(f"  enabled now : {verify2.data.enabled}")

    # --- 9. Source fetches (empty — no actual fetching) --------------------
    print("\n[9] List Source Fetches")

    result = list_source_fetches(ctx, ListSourceFetchesRequest())
    assert result.success
    print(f"  total : {result.total}")
    print(f"  (no fetches — expected without a fetch backend)")

    # --- 10. Source cache (empty) -----------------------------------------
    print("\n[10] List Source Cache")

    result = list_source_cache(ctx, source_ids[0])
    assert result.success
    print(f"  total : {result.total}")

    # --- 11. Invalidate cache (no-op on empty) ----------------------------
    print("\n[11] Invalidate Source Cache")

    inv = invalidate_source_cache(ctx, source_ids[0])
    assert inv.success
    print(f"  invalidated : {inv.data}")

    # --- 12. Delete source ------------------------------------------------
    print("\n[12] Delete Source")

    delete = delete_source(ctx, source_ids[3])
    assert delete.success
    print(f"  deleted : {source_ids[3]}")

    remaining = list_sources(ctx, ListSourcesRequest())
    print(f"  remaining : {remaining.total}")

    # --- 13. Get non-existent source --------------------------------------
    print("\n[13] Get Non-Existent Source")

    missing = get_source(ctx, "src_doesnotexist")
    assert not missing.success
    print(f"  error.code    : {missing.error.code}")
    print(f"  error.message : {missing.error.message}")

    # === DATABASE CONNECTIONS =============================================
    print("\n" + "=" * 60)
    print("Database Connection Management")
    print("=" * 60)

    # --- 14. Empty connections --------------------------------------------
    print("\n[14] List Database Connections (empty)")

    result = list_database_connections(ctx, ListDatabaseConnectionsRequest())
    assert result.success
    print(f"  total : {result.total}")

    # --- 15. Register connections -----------------------------------------
    print("\n[15] Register Database Connections")

    db_conns = [
        CreateDatabaseConnectionRequest(
            name="prod-postgres",
            dialect="postgresql",
            host="db.example.com",
            port=5432,
            database="spine_prod",
            username="spine_app",
            password_ref="vault:secrets/spine/db_password",
            pool_size=10,
        ),
        CreateDatabaseConnectionRequest(
            name="analytics-readonly",
            dialect="postgresql",
            host="analytics.example.com",
            port=5432,
            database="analytics",
            username="reader",
            password_ref="vault:secrets/spine/analytics_ro",
            pool_size=3,
            max_overflow=5,
        ),
        CreateDatabaseConnectionRequest(
            name="local-sqlite",
            dialect="sqlite",
            database="/data/local.db",
        ),
    ]

    db_conn_ids = []
    for req in db_conns:
        res = register_database_connection(ctx, req)
        assert res.success, f"Failed: {res.error}"
        db_conn_ids.append(res.data["id"])
        print(f"  + {res.data['id']}  {req.name:22s}  {req.dialect}")

    # --- 16. List connections ---------------------------------------------
    print("\n[16] List All Database Connections")

    result = list_database_connections(ctx, ListDatabaseConnectionsRequest())
    assert result.success
    print(f"  total : {result.total}")
    for c in result.data:
        print(f"  {c.id}  {c.name:22s}  {c.dialect}  host={c.host}")

    # --- 17. Filter by dialect --------------------------------------------
    print("\n[17] Filter Connections by Dialect = 'sqlite'")

    result = list_database_connections(ctx, ListDatabaseConnectionsRequest(dialect="sqlite"))
    assert result.success
    print(f"  total : {result.total}")
    for c in result.data:
        print(f"  {c.id}  {c.name}")

    # --- 18. Test connection (simulated) ----------------------------------
    print("\n[18] Test Database Connection")

    test = test_database_connection(ctx, db_conn_ids[2])
    print(f"  result : {test.data}")

    # --- 19. Delete connection --------------------------------------------
    print("\n[19] Delete Database Connection")

    delete = delete_database_connection(ctx, db_conn_ids[2])
    assert delete.success
    print(f"  deleted : {db_conn_ids[2]}")

    remaining = list_database_connections(ctx, ListDatabaseConnectionsRequest())
    print(f"  remaining : {remaining.total}")

    # --- 20. Dry-run register source --------------------------------------
    print("\n[20] Dry-Run Register Source")

    dry_ctx = OperationContext(conn=conn, caller="example", dry_run=True)
    dry = register_source(
        dry_ctx,
        CreateSourceRequest(name="dry-test", source_type="http"),
    )
    assert dry.success
    print(f"  dry_run      : {dry.data.get('dry_run')}")
    print(f"  would_create : {dry.data.get('would_create')}")

    conn.close()
    print("\n✓ Source management complete.")


if __name__ == "__main__":
    main()
