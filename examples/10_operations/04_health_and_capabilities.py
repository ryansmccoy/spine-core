#!/usr/bin/env python3
"""Health & Capabilities — Aggregate health checks and runtime introspection.

WHY HEALTH AND CAPABILITY REPORTING
────────────────────────────────────
Every spine-core deployment can report its health status and available
capabilities through the ops layer.  This feeds into /health API
endpoints (for Docker/K8s probes) and CLI status commands.

ARCHITECTURE
────────────
    Docker/K8s              API                  Ops Layer
    ──────────              ───                  ─────────
    liveness probe   ──▶  /health/live   ──▶  health_check()
    readiness probe  ──▶  /health/ready  ──▶  aggregate_health()
    startup probe    ──▶  /health        ──▶  capabilities_check()

    Health returns:  {status, connected, backend, latency_ms, table_count}
    Capabilities:    {pipelines, workflows, schedulers, alerting, sources}

HEALTH STATUS VALUES
────────────────────
    Status      Meaning
    ─────────── ───────────────────────────────────
    healthy     All checks pass
    degraded    DB connected but slow or missing tables
    unhealthy   DB unreachable or critical failure

BEST PRACTICES
──────────────
• Wire health_check() into container liveness probes.
• Use capabilities_check() to build dynamic CLI help.
• Set readiness to fail when DB has 0 tables (migration pending).

Run: python examples/10_operations/04_health_and_capabilities.py

See Also:
    01_database_lifecycle — DB init that makes health pass
    12_deploy/ — Docker deployment with health probes
"""

import sqlite3

from spine.core.schema import create_core_tables
from spine.ops.context import OperationContext
from spine.ops.sqlite_conn import SqliteConnection
from spine.ops.database import initialize_database
from spine.ops.health import get_capabilities, get_health
from spine.ops.result import OperationResult


def main():
    print("=" * 60)
    print("Operations Layer — Health & Capabilities")
    print("=" * 60)

    conn = SqliteConnection(":memory:")
    ctx = OperationContext(conn=conn, caller="example")
    initialize_database(ctx)

    # --- 1. Health status -------------------------------------------------
    print("\n[1] Aggregate Health Status")

    health = get_health(ctx)
    assert health.success

    hs = health.data
    print(f"  status   : {hs.status}")
    print(f"  version  : {hs.version}")
    print(f"  checks:")
    for name, status in hs.checks.items():
        icon = "✓" if status == "ok" else "✗"
        print(f"    {icon} {name}: {status}")

    if hs.database:
        print(f"  database:")
        print(f"    connected   : {hs.database.connected}")
        print(f"    backend     : {hs.database.backend}")
        print(f"    table_count : {hs.database.table_count}")
        print(f"    latency     : {hs.database.latency_ms:.2f} ms")

    # --- 2. Unhealthy state -----------------------------------------------
    print("\n[2] Unhealthy State (no tables)")

    empty_conn = SqliteConnection(":memory:")
    bad_ctx = OperationContext(conn=empty_conn, caller="example")
    # Don't initialize — tables are missing
    health_bad = get_health(bad_ctx)
    assert health_bad.success  # health op itself doesn't fail
    print(f"  status      : {health_bad.data.status}")
    print(f"  db.connected: {health_bad.data.database.connected}")
    # table_count is 0 because no tables exist
    print(f"  table_count : {health_bad.data.database.table_count}")
    empty_conn.close()

    # --- 3. Runtime capabilities ------------------------------------------
    print("\n[3] Runtime Capabilities")

    caps = get_capabilities(ctx)
    assert caps.success

    c = caps.data
    print(f"  tier              : {c.tier}")
    print(f"  sync_execution    : {c.sync_execution}")
    print(f"  async_execution   : {c.async_execution}")
    print(f"  scheduling        : {c.scheduling}")
    print(f"  rate_limiting     : {c.rate_limiting}")
    print(f"  execution_history : {c.execution_history}")
    print(f"  dlq               : {c.dlq}")

    # --- 4. Result envelope anatomy ---------------------------------------
    print("\n[4] OperationResult Envelope Anatomy")

    # Show the full structure of a result
    result = health
    print(f"  success     : {result.success}")
    print(f"  data type   : {type(result.data).__name__}")
    print(f"  error       : {result.error}")
    print(f"  warnings    : {result.warnings}")
    print(f"  elapsed_ms  : {result.elapsed_ms:.2f}")
    print(f"  metadata    : {result.metadata}")

    # --- 5. JSON serialization round-trip ---------------------------------
    print("\n[5] JSON Serialization")

    d = caps.to_dict()
    print(f"  keys: {sorted(d.keys())}")
    print(f"  data: {d.get('data')}")

    # --- 6. The OperationResult.fail path ---------------------------------
    print("\n[6] Explicit Failure")

    fail = OperationResult.fail(
        "SERVICE_UNAVAILABLE",
        "External dependency down",
        retryable=True,
        details={"service": "redis", "port": 6379},
    )
    print(f"  success   : {fail.success}")
    print(f"  code      : {fail.error.code}")
    print(f"  message   : {fail.error.message}")
    print(f"  retryable : {fail.error.retryable}")
    print(f"  details   : {fail.error.details}")

    conn.close()
    print("\n✓ Health & capabilities complete.")


if __name__ == "__main__":
    main()
