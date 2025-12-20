#!/usr/bin/env python3
"""Run Management — List, inspect, cancel, and retry execution runs.

WHY OPERATIONS-LAYER RUN MANAGEMENT
────────────────────────────────────
The core_executions table tracks every pipeline and workflow run.
The ops layer provides typed CRUD operations over those records —
the same operations that the API endpoints and CLI commands call.
This means you can build custom dashboards, retry UIs, or ChatOps
bots using the exact same logic.

ARCHITECTURE
────────────
    API / CLI / Notebook
         │
         ▼
    ops.runs.list_runs(ctx, filters)      → [{id, status, pipeline, ...}]
    ops.runs.get_run(ctx, run_id)         → {full run detail}
    ops.runs.cancel_run(ctx, run_id)      → OperationResult
    ops.runs.retry_run(ctx, run_id)       → OperationResult (new run)
         │
         ▼
    core_executions table (SQLite / PostgreSQL)

RUN STATES
──────────
    PENDING → RUNNING → COMPLETED
                    └─→ FAILED → (retry) → PENDING
                    └─→ CANCELLED

BEST PRACTICES
──────────────
• Use list_runs() with status filters for monitoring dashboards.
• Cancel then retry — never modify a completed run.
• Retried runs link back to the original via parent_run_id.

Run: python examples/10_operations/02_run_management.py

See Also:
    01_database_lifecycle — initialise the schema first
    03_workflow_ops — workflow-level run management
"""

import sqlite3
from datetime import datetime, timezone

from spine.core.schema import create_core_tables
from spine.ops.context import OperationContext
from spine.ops.sqlite_conn import SqliteConnection
from spine.ops.runs import cancel_run, get_run, list_runs, retry_run
from spine.ops.requests import (
    CancelRunRequest,
    GetRunRequest,
    ListRunsRequest,
    RetryRunRequest,
)


def _insert_run(conn, run_id: str, workflow: str, status: str) -> None:
    """Helper: insert a fake execution row."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO core_executions "
        "(id, workflow, status, created_at, started_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (run_id, workflow, status, now, now),
    )
    conn.commit()


def main():
    print("=" * 60)
    print("Operations Layer — Run Management")
    print("=" * 60)

    conn = SqliteConnection(":memory:")
    create_core_tables(conn)
    ctx = OperationContext(conn=conn, caller="example")

    # --- 1. Empty list ----------------------------------------------------
    print("\n[1] List Runs (empty table)")

    result = list_runs(ctx, ListRunsRequest())
    assert result.success
    print(f"  total : {result.total}")
    print(f"  items : {len(result.data)}")

    # --- 2. Populate runs -------------------------------------------------
    print("\n[2] Insert sample runs")

    runs = [
        ("run-001", "finra.otc.ingest", "completed"),
        ("run-002", "finra.otc.ingest", "running"),
        ("run-003", "sec.filing.ingest", "failed"),
        ("run-004", "sec.filing.ingest", "completed"),
        ("run-005", "equity.market.calc", "pending"),
    ]
    for rid, pipe, status in runs:
        _insert_run(conn, rid, pipe, status)
        print(f"  + {rid}  {pipe:25s}  {status}")

    # --- 3. List all runs -------------------------------------------------
    print("\n[3] List All Runs")

    result = list_runs(ctx, ListRunsRequest())
    assert result.success
    print(f"  total : {result.total}")
    for r in result.data:
        print(f"  {r.run_id}  {r.workflow:25s}  {r.status}")

    # --- 4. Filter by status ----------------------------------------------
    print("\n[4] Filter by Status = 'completed'")

    result = list_runs(ctx, ListRunsRequest(status="completed"))
    assert result.success
    print(f"  total : {result.total}")
    for r in result.data:
        print(f"  {r.run_id}  {r.status}")

    # --- 5. Filter by pipeline --------------------------------------------
    print("\n[5] Filter by Pipeline = 'finra.otc.ingest'")

    result = list_runs(ctx, ListRunsRequest(workflow="finra.otc.ingest"))
    assert result.success
    print(f"  total : {result.total}")
    for r in result.data:
        print(f"  {r.run_id}  {r.workflow}")

    # --- 6. Pagination ----------------------------------------------------
    print("\n[6] Pagination (limit=2, offset=0)")

    result = list_runs(ctx, ListRunsRequest(limit=2, offset=0))
    print(f"  total    : {result.total}")
    print(f"  page     : {len(result.data)} items")
    print(f"  has_more : {result.has_more}")

    # --- 7. Get single run ------------------------------------------------
    print("\n[7] Get Run Detail")

    detail = get_run(ctx, GetRunRequest(run_id="run-003"))
    assert detail.success
    print(f"  run_id   : {detail.data.run_id}")
    print(f"  workflow : {detail.data.workflow}")
    print(f"  status   : {detail.data.status}")

    # --- 8. Get non-existent run ------------------------------------------
    print("\n[8] Get Non-Existent Run")

    missing = get_run(ctx, GetRunRequest(run_id="nope"))
    assert not missing.success
    print(f"  ✗ error.code    : {missing.error.code}")
    print(f"  ✗ error.message : {missing.error.message}")

    # --- 9. Cancel a running run ------------------------------------------
    print("\n[9] Cancel Running Run")

    cancel = cancel_run(ctx, CancelRunRequest(run_id="run-002"))
    assert cancel.success
    print(f"  ✓ cancelled run-002")

    # Verify status changed
    updated = get_run(ctx, GetRunRequest(run_id="run-002"))
    print(f"  new status : {updated.data.status}")

    # --- 10. Cancel completed run fails -----------------------------------
    print("\n[10] Cancel Completed Run (should fail)")

    cancel2 = cancel_run(ctx, CancelRunRequest(run_id="run-001"))
    assert not cancel2.success
    print(f"  ✗ error.code    : {cancel2.error.code}")
    print(f"  ✗ error.message : {cancel2.error.message}")

    # --- 11. Retry a failed run -------------------------------------------
    print("\n[11] Retry Failed Run")

    retry = retry_run(ctx, RetryRunRequest(run_id="run-003"))
    assert retry.success
    print(f"  ✓ retry accepted")
    print(f"  would_execute : {retry.data.would_execute}")

    # --- 12. Retry dry-run ------------------------------------------------
    print("\n[12] Retry Dry-Run")

    dry_ctx = OperationContext(conn=conn, caller="example", dry_run=True)
    dry_retry = retry_run(dry_ctx, RetryRunRequest(run_id="run-003"))
    assert dry_retry.success
    assert dry_retry.data.dry_run is True
    print(f"  ✓ dry_run       : {dry_retry.data.dry_run}")
    print(f"  would_execute   : {dry_retry.data.would_execute}")

    conn.close()
    print("\n✓ Run management complete.")


if __name__ == "__main__":
    main()
