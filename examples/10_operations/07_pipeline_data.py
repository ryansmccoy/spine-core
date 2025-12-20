#!/usr/bin/env python3
"""Pipeline Data Processing — Manifest, rejects, and work items.

WHY OPS-LAYER DATA TRACKING
────────────────────────────
Pipelines process data.  The ops layer tracks *what* was processed
(manifest), *what* was rejected (rejects), and *what* is still pending
(work items).  This gives operators a flight-recorder view of every
ingest run without digging through logs.

ARCHITECTURE
────────────
    Pipeline/Workflow step
         │
         ▼
    ops.manifest.record(key, hash)    → core_manifest
    ops.rejects.add(record, reason)   → core_rejects
    ops.work.claim(item_id)           → core_work_items
    ops.work.complete(item_id)
    ops.work.fail(item_id, error)
         │
         ▼
    Work Item Lifecycle:
    PENDING → CLAIMED → COMPLETED
                     └─→ FAILED → (retry) → PENDING

MANIFEST vs REJECTS vs WORK ITEMS
──────────────────────────────────
    Table            Answers
    ──────────────── ──────────────────────────────────
    core_manifest    "Did we already process this file?"
    core_rejects     "Which records were rejected and why?"
    core_work_items  "What work is pending / in-progress?"

BEST PRACTICES
──────────────
• Use manifest hashes for idempotent re-runs.
• Record rejects with enough context to reproduce the issue.
• Use work items for distributed claim/complete patterns.

Run: python examples/10_operations/07_pipeline_data.py

See Also:
    01_core/04_reject_handling — core RejectSink
    03_resilience/05_dead_letter_queue — DLQ for exhausted retries
"""

import json
from datetime import datetime, timezone

from spine.core.schema import create_core_tables
from spine.core.schema_loader import apply_all_schemas
from spine.ops.context import OperationContext
from spine.ops.sqlite_conn import SqliteConnection
from spine.ops.processing import (
    list_manifest_entries,
    get_manifest_entry,
    list_rejects,
    count_rejects_by_reason,
    list_work_items,
    claim_work_item,
    complete_work_item,
    fail_work_item,
    cancel_work_item,
    retry_failed_work_items,
)
from spine.ops.requests import (
    ListManifestEntriesRequest,
    ListRejectsRequest,
    ListWorkItemsRequest,
    ClaimWorkItemRequest,
)


def _seed_manifest(conn) -> None:
    """Insert sample manifest entries."""
    now = datetime.now(timezone.utc).isoformat()
    entries = [
        ("otc", "2026-02-15", "ingest", 1, 5000, "exec-001", "batch-a"),
        ("otc", "2026-02-15", "validate", 2, 4800, "exec-001", "batch-a"),
        ("otc", "2026-02-15", "transform", 3, 4800, "exec-001", "batch-a"),
        ("equity", "2026-02-15", "ingest", 1, 12000, "exec-002", "batch-b"),
        ("equity", "2026-02-15", "validate", 2, 11500, "exec-002", "batch-b"),
    ]
    for domain, pk, stage, rank, cnt, eid, bid in entries:
        conn.execute(
            "INSERT INTO core_manifest "
            "(domain, partition_key, stage, stage_rank, row_count, execution_id, batch_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (domain, pk, stage, rank, cnt, eid, bid, now),
        )
    conn.commit()


def _seed_rejects(conn) -> None:
    """Insert sample reject records."""
    now = datetime.now(timezone.utc).isoformat()
    rejects = [
        ("otc", "2026-02-15", "validate", "MISSING_FIELD", "exec-001", "CIK field is null", '{"row": 42}'),
        ("otc", "2026-02-15", "validate", "INVALID_FORMAT", "exec-001", "Date format invalid", '{"row": 87}'),
        ("otc", "2026-02-15", "validate", "MISSING_FIELD", "exec-001", "Symbol field empty", '{"row": 153}'),
        ("equity", "2026-02-15", "validate", "OUT_OF_RANGE", "exec-002", "Price negative", '{"row": 7}'),
        ("equity", "2026-02-15", "validate", "DUPLICATE", "exec-002", "Duplicate ticker", '{"row": 201}'),
    ]
    for domain, pk, stage, reason, eid, detail, raw in rejects:
        conn.execute(
            "INSERT INTO core_rejects "
            "(domain, partition_key, stage, reason_code, execution_id, reason_detail, raw_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (domain, pk, stage, reason, eid, detail, raw, now),
        )
    conn.commit()


def _seed_work_items(conn) -> None:
    """Insert sample work items."""
    now = datetime.now(timezone.utc).isoformat()
    items = [
        (1, "otc", "finra.otc.ingest", '{"date": "2026-02-15"}', "PENDING", None, now),
        (2, "otc", "finra.otc.validate", '{"date": "2026-02-15"}', "PENDING", None, now),
        (3, "equity", "equity.market.calc", '{"date": "2026-02-15"}', "PENDING", None, now),
        (4, "options", "options.chain.ingest", '{"date": "2026-02-14"}', "FAILED", "worker-01", now),
        (5, "equity", "equity.eod.report", '{"date": "2026-02-14"}', "COMPLETE", "worker-02", now),
    ]
    for item_id, domain, pipeline, pk, state, worker, ts in items:
        conn.execute(
            "INSERT INTO core_work_items "
            "(id, domain, pipeline, partition_key, desired_at, state, locked_by, "
            "params_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            (item_id, domain, pipeline, pk, ts, state, worker, ts, ts),
        )
    conn.commit()


def main():
    print("=" * 60)
    print("Operations Layer — Pipeline Data Processing")
    print("=" * 60)

    conn = SqliteConnection(":memory:")
    create_core_tables(conn)
    apply_all_schemas(conn)
    ctx = OperationContext(conn=conn, caller="example")

    # === MANIFEST =========================================================
    print("\n" + "-" * 40)
    print("MANIFEST TRACKING")
    print("-" * 40)

    # --- 1. Seed manifest data --------------------------------------------
    print("\n[1] Seed Manifest Entries")
    _seed_manifest(conn)
    print("  + 5 manifest entries seeded (otc:3, equity:2)")

    # --- 2. List all manifest entries -------------------------------------
    print("\n[2] List All Manifest Entries")

    result = list_manifest_entries(ctx, ListManifestEntriesRequest())
    assert result.success
    print(f"  total : {result.total}")
    for m in result.data:
        print(f"  {m.domain:8s}  {m.partition_key}  stage={m.stage:12s}  rows={m.row_count}")

    # --- 3. Filter by domain ----------------------------------------------
    print("\n[3] Filter Manifest by Domain = 'otc'")

    result = list_manifest_entries(ctx, ListManifestEntriesRequest(domain="otc"))
    assert result.success
    print(f"  total : {result.total}")
    for m in result.data:
        print(f"  {m.stage:12s}  rank={m.stage_rank}  rows={m.row_count}")

    # --- 4. Filter by stage -----------------------------------------------
    print("\n[4] Filter Manifest by Stage = 'validate'")

    result = list_manifest_entries(ctx, ListManifestEntriesRequest(stage="validate"))
    assert result.success
    print(f"  total : {result.total}")
    for m in result.data:
        print(f"  {m.domain:8s}  {m.partition_key}  rows={m.row_count}")

    # === REJECTS ==========================================================
    print("\n" + "-" * 40)
    print("REJECT TRACKING")
    print("-" * 40)

    # --- 5. Seed reject data ----------------------------------------------
    print("\n[5] Seed Reject Records")
    _seed_rejects(conn)
    print("  + 5 reject records seeded (otc:3, equity:2)")

    # --- 6. List all rejects ----------------------------------------------
    print("\n[6] List All Rejects")

    result = list_rejects(ctx, ListRejectsRequest())
    assert result.success
    print(f"  total : {result.total}")
    for r in result.data:
        print(f"  {r.domain:8s}  {r.reason_code:16s}  {r.reason_detail}")

    # --- 7. Filter by reason code -----------------------------------------
    print("\n[7] Filter Rejects by Reason = 'MISSING_FIELD'")

    result = list_rejects(ctx, ListRejectsRequest(reason_code="MISSING_FIELD"))
    assert result.success
    print(f"  total : {result.total}")
    for r in result.data:
        print(f"  {r.domain:8s}  {r.reason_detail}")

    # --- 8. Count by reason -----------------------------------------------
    print("\n[8] Count Rejects by Reason Code")

    result = count_rejects_by_reason(ctx)
    assert result.success
    for entry in result.data:
        print(f"  {entry['reason_code']:16s}  count={entry['count']}")

    # === WORK ITEMS =======================================================
    print("\n" + "-" * 40)
    print("WORK ITEM LIFECYCLE")
    print("-" * 40)

    # --- 9. Seed work items -----------------------------------------------
    print("\n[9] Seed Work Items")
    _seed_work_items(conn)
    print("  + 5 work items seeded (3 PENDING, 1 FAILED, 1 COMPLETE)")

    # --- 10. List all work items ------------------------------------------
    print("\n[10] List All Work Items")

    result = list_work_items(ctx, ListWorkItemsRequest())
    assert result.success
    print(f"  total : {result.total}")
    for w in result.data:
        print(f"  #{w.id}  {w.workflow:25s}  state={w.state:10s}  worker={w.locked_by}")

    # --- 11. Filter by state ----------------------------------------------
    print("\n[11] Filter Work Items by State = 'PENDING'")

    result = list_work_items(ctx, ListWorkItemsRequest(state="PENDING"))
    assert result.success
    print(f"  total : {result.total}")
    for w in result.data:
        print(f"  #{w.id}  {w.workflow}")

    # --- 12. Claim work item ----------------------------------------------
    print("\n[12] Claim Work Item #1")

    claim = claim_work_item(ctx, ClaimWorkItemRequest(item_id=1, worker_id="worker-alpha"))
    assert claim.success
    print(f"  claimed : #{claim.data.id} by {claim.data.locked_by}")

    # Verify state changed
    items = list_work_items(ctx, ListWorkItemsRequest())
    for w in items.data:
        if w.id == 1:
            print(f"  state now : {w.state}")
            print(f"  worker    : {w.locked_by}")

    # --- 13. Complete work item -------------------------------------------
    print("\n[13] Complete Work Item #1")

    comp = complete_work_item(ctx, item_id=1)
    assert comp.success
    print(f"  completed : #1")

    items = list_work_items(ctx, ListWorkItemsRequest())
    for w in items.data:
        if w.id == 1:
            print(f"  state now : {w.state}")

    # --- 14. Fail work item -----------------------------------------------
    print("\n[14] Fail Work Item #2")

    # First claim it
    claim_work_item(ctx, ClaimWorkItemRequest(item_id=2, worker_id="worker-beta"))
    fail = fail_work_item(ctx, item_id=2, error="Connection timeout to FINRA endpoint")
    assert fail.success
    print(f"  failed : #2")

    items = list_work_items(ctx, ListWorkItemsRequest())
    for w in items.data:
        if w.id == 2:
            print(f"  state now : {w.state}")

    # --- 15. Cancel work item ---------------------------------------------
    print("\n[15] Cancel Work Item #3")

    cancel = cancel_work_item(ctx, item_id=3)
    assert cancel.success
    print(f"  cancelled : #3")

    # --- 16. Retry failed items -------------------------------------------
    print("\n[16] Retry Failed Work Items")

    retry = retry_failed_work_items(ctx, domain="otc")
    assert retry.success
    print(f"  retried : {retry.data}")

    # --- 17. Final state summary ------------------------------------------
    print("\n[17] Final Work Item State Summary")

    result = list_work_items(ctx, ListWorkItemsRequest())
    state_counts = {}
    for w in result.data:
        state_counts[w.state] = state_counts.get(w.state, 0) + 1
    for state, count in sorted(state_counts.items()):
        print(f"  {state:12s}  {count}")

    conn.close()
    print("\n✓ Pipeline data processing complete.")


if __name__ == "__main__":
    main()
