#!/usr/bin/env python3
"""Lock and DLQ Management — Concurrency locks, schedule locks, dead letters.

WHY OPS-LAYER LOCK AND DLQ MANAGEMENT
──────────────────────────────────────
The resilience primitives (03_resilience/) acquire locks and fill DLQs.
The ops layer lets operators *inspect* and *manage* those resources:
force-release stale locks, replay dead letters, and review quality
scores — all through typed OperationResult contracts.

ARCHITECTURE
────────────
    CLI / Dashboard
         │
    ┌────┴──────────────────────────────────────────┐
    │  ops.locks                                     │
    │    list_locks() → core_concurrency_locks       │
    │    force_release() → DELETE stale lock          │
    │    list_schedule_locks() → core_schedule_locks  │
    │                                                 │
    │  ops.dlq                                        │
    │    list_dead_letters() → core_dead_letters      │
    │    replay(id) → re-submit to pipeline           │
    │                                                 │
    │  ops.quality                                    │
    │    list_anomalies() → core_anomalies            │
    │    list_quality() → core_quality                │
    └───────────────────────────────────────────────┘

BEST PRACTICES
──────────────
• Use force_release() for locks held by crashed processes.
• Set up alerts on DLQ depth — growing queue means systemic issue.
• Review anomalies daily; resolve or suppress known patterns.
• Quality scores feed into workflow gates (StepResult.fail).

Run: python examples/10_operations/09_locks_dlq_quality.py

See Also:
    03_resilience/04_concurrency_guard — how locks are acquired
    03_resilience/05_dead_letter_queue — how DLQ entries are created
    01_core/11_anomaly_recording — anomaly lifecycle
"""

import json
from datetime import datetime, timedelta, timezone

from spine.core.schema import create_core_tables
from spine.core.schema_loader import apply_all_schemas
from spine.ops.context import OperationContext
from spine.ops.sqlite_conn import SqliteConnection
from spine.ops.locks import (
    list_locks,
    release_lock,
    list_schedule_locks,
    release_schedule_lock,
)
from spine.ops.dlq import list_dead_letters, replay_dead_letter
from spine.ops.anomalies import list_anomalies
from spine.ops.quality import list_quality_results
from spine.ops.requests import (
    ListDeadLettersRequest,
    ReplayDeadLetterRequest,
    ListAnomaliesRequest,
    ListQualityResultsRequest,
    ListScheduleLocksRequest,
)


def _seed_locks(conn) -> None:
    """Insert sample concurrency lock records."""
    now = datetime.now(timezone.utc)
    locks = [
        ("pipeline:otc.ingest", "exec-001", now, now + timedelta(minutes=30)),
        ("pipeline:equity.eod", "exec-002", now - timedelta(minutes=10), now + timedelta(minutes=20)),
        ("pipeline:recon.full", "exec-003", now - timedelta(hours=2), now - timedelta(hours=1)),
    ]
    for key, exec_id, acquired, expires in locks:
        conn.execute(
            "INSERT INTO core_concurrency_locks (lock_key, execution_id, acquired_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (key, exec_id, acquired.isoformat(), expires.isoformat()),
        )
    conn.commit()


def _seed_schedule_locks(conn) -> None:
    """Insert sample schedule lock records."""
    now = datetime.now(timezone.utc)
    locks = [
        ("sched:otc-daily", "scheduler-01", now, now + timedelta(minutes=5)),
        ("sched:equity-eod", "scheduler-01", now, now + timedelta(minutes=5)),
    ]
    for schedule_id, locked_by, locked_at, expires in locks:
        conn.execute(
            "INSERT INTO core_schedule_locks (schedule_id, locked_by, locked_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (schedule_id, locked_by, locked_at.isoformat(), expires.isoformat()),
        )
    conn.commit()


def _seed_dead_letters(conn) -> None:
    """Insert sample dead letter records."""
    now = datetime.now(timezone.utc).isoformat()
    letters = [
        ("dl-001", "exec-fail-001", "finra.otc.ingest", '{}',
         "ConnectionError: FINRA endpoint timeout", 3, 3),
        ("dl-002", "exec-fail-002", "equity.market.calc", '{}',
         "ValueError: Negative price in row 42", 1, 3),
        ("dl-003", "exec-fail-003", "otc.report.gen", '{}',
         "PermissionError: /output/reports not writable", 5, 5),
    ]
    for dl_id, exec_id, workflow, params, error, retry_count, max_retries in letters:
        conn.execute(
            "INSERT INTO core_dead_letters "
            "(id, execution_id, workflow, params, error, "
            "retry_count, max_retries, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (dl_id, exec_id, workflow, params, error, retry_count, max_retries, now),
        )
    conn.commit()


def _seed_anomalies(conn) -> None:
    """Insert sample anomaly records."""
    now = datetime.now(timezone.utc).isoformat()
    anomalies = [
        ("otc", "finra.otc.ingest", None, "validate", "WARNING", "ROW_COUNT_DROP",
         "Row count drop: 5000->3200 (-36%)", None, 1800),
        ("equity", "equity.price.ingest", None, "ingest", "ERROR", "SCHEMA_DRIFT",
         "Schema mismatch: extra column 'adj_close_v2'", None, None),
        ("otc", "finra.otc.ingest", None, "transform", "INFO", "NEW_SYMBOL",
         "New symbol detected: ACME", None, 1),
    ]
    for domain, workflow, pk, stage, severity, category, message, details, affected in anomalies:
        conn.execute(
            "INSERT INTO core_anomalies "
            "(domain, workflow, partition_key, stage, severity, category, message, "
            "details_json, affected_records, detected_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (domain, workflow, pk, stage, severity, category, message, details, affected, now, now),
        )
    conn.commit()


def _seed_quality(conn) -> None:
    """Insert sample quality check records."""
    now = datetime.now(timezone.utc).isoformat()
    checks = [
        ("otc", "2026-02-15", "completeness", "COMPLETENESS", "PASS", "98% complete", "0.98", "0.95", '{}', "exec-001"),
        ("otc", "2026-02-15", "freshness", "COMPLETENESS", "PASS", "Within SLA", "1.0", "0.99", '{}', "exec-001"),
        ("otc", "2026-02-15", "uniqueness", "INTEGRITY", "FAIL", "400 duplicates", "0.92", "0.95", '{"dups":400}', "exec-001"),
        ("equity", "2026-02-15", "completeness", "COMPLETENESS", "PASS", "All records present", "1.0", "0.95", '{}', "exec-002"),
        ("equity", "2026-02-15", "validity", "BUSINESS_RULE", "WARN", "480 invalid", "0.96", "0.98", '{"invalid":480}', "exec-002"),
    ]
    for domain, pk, check_name, category, status, message, actual, expected, details, exec_id in checks:
        conn.execute(
            "INSERT INTO core_quality "
            "(domain, partition_key, check_name, category, status, message, "
            "actual_value, expected_value, details_json, execution_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (domain, pk, check_name, category, status, message, actual, expected, details, exec_id, now),
        )
    conn.commit()


def main():
    print("=" * 60)
    print("Operations Layer — Locks, DLQ & Quality")
    print("=" * 60)

    conn = SqliteConnection(":memory:")
    create_core_tables(conn)
    apply_all_schemas(conn)
    ctx = OperationContext(conn=conn, caller="example")

    # === CONCURRENCY LOCKS ================================================
    print("\n" + "-" * 40)
    print("CONCURRENCY LOCKS")
    print("-" * 40)

    # --- 1. Seed locks ----------------------------------------------------
    print("\n[1] Seed Concurrency Locks")
    _seed_locks(conn)
    print("  + 3 concurrency locks seeded")

    # --- 2. List all locks ------------------------------------------------
    print("\n[2] List All Concurrency Locks")

    result = list_locks(ctx)
    assert result.success
    print(f"  total : {result.total}")
    for lk in result.data:
        print(f"  {lk.lock_key:30s}  owner={lk.owner}")

    # --- 3. Release a lock ------------------------------------------------
    print("\n[3] Release Expired Lock")

    rel = release_lock(ctx, "pipeline:recon.full")
    assert rel.success
    print(f"  released : pipeline:recon.full")

    remaining = list_locks(ctx)
    print(f"  remaining : {remaining.total}")

    # === SCHEDULE LOCKS ===================================================
    print("\n" + "-" * 40)
    print("SCHEDULE LOCKS")
    print("-" * 40)

    # --- 4. Seed schedule locks -------------------------------------------
    print("\n[4] Seed Schedule Locks")
    _seed_schedule_locks(conn)
    print("  + 2 schedule locks seeded")

    # --- 5. List schedule locks -------------------------------------------
    print("\n[5] List Schedule Locks")

    result = list_schedule_locks(ctx, ListScheduleLocksRequest())
    assert result.success
    print(f"  total : {result.total}")
    for lk in result.data:
        print(f"  {lk.schedule_id:30s}  locked_by={lk.locked_by}")

    # --- 6. Release schedule lock -----------------------------------------
    print("\n[6] Release Schedule Lock")

    rel = release_schedule_lock(ctx, "sched:otc-daily")
    assert rel.success
    print(f"  released : sched:otc-daily")

    # === DEAD LETTER QUEUE ================================================
    print("\n" + "-" * 40)
    print("DEAD LETTER QUEUE")
    print("-" * 40)

    # --- 7. Seed dead letters ---------------------------------------------
    print("\n[7] Seed Dead Letters")
    _seed_dead_letters(conn)
    print("  + 3 dead letter records seeded")

    # --- 8. List dead letters ---------------------------------------------
    print("\n[8] List Dead Letters")

    result = list_dead_letters(ctx, ListDeadLettersRequest())
    assert result.success
    print(f"  total : {result.total}")
    for dl in result.data:
        print(f"  {dl.id}  {dl.workflow:25s}  replays={dl.replay_count}  {dl.error[:50]}")

    # --- 9. Filter by domain ----------------------------------------------
    print("\n[9] Filter Dead Letters by Pipeline")

    result = list_dead_letters(ctx, ListDeadLettersRequest(workflow="finra.otc.ingest"))
    assert result.success
    print(f"  total : {result.total}")
    for dl in result.data:
        print(f"  {dl.id}  {dl.workflow}")

    # --- 10. Replay dead letter -------------------------------------------
    print("\n[10] Replay Dead Letter")

    replay = replay_dead_letter(ctx, ReplayDeadLetterRequest(dead_letter_id="dl-002"))
    assert replay.success
    print(f"  replayed : dl-002 → {replay.data}")

    # === ANOMALIES ========================================================
    print("\n" + "-" * 40)
    print("ANOMALIES")
    print("-" * 40)

    # --- 11. Seed anomalies -----------------------------------------------
    print("\n[11] Seed Anomalies")
    _seed_anomalies(conn)
    print("  + 3 anomaly records seeded")

    # --- 12. List anomalies -----------------------------------------------
    print("\n[12] List All Anomalies")

    result = list_anomalies(ctx, ListAnomaliesRequest())
    assert result.success
    print(f"  total : {result.total}")
    for a in result.data:
        print(f"  [{a.severity:7s}]  workflow={a.workflow}  metric={a.metric}")

    # --- 13. Filter by domain ---------------------------------------------
    print("\n[13] Filter Anomalies by Pipeline")

    result = list_anomalies(ctx, ListAnomaliesRequest(workflow="finra.otc.ingest"))
    assert result.success
    print(f"  total : {result.total}")

    # === QUALITY CHECKS ===================================================
    print("\n" + "-" * 40)
    print("QUALITY CHECKS")
    print("-" * 40)

    # --- 14. Seed quality checks ------------------------------------------
    print("\n[14] Seed Quality Checks")
    _seed_quality(conn)
    print("  + 5 quality check records seeded")

    # --- 15. List quality results -----------------------------------------
    print("\n[15] List All Quality Results")

    result = list_quality_results(ctx, ListQualityResultsRequest())
    assert result.success
    print(f"  total : {result.total}")
    for q in result.data:
        print(f"  {q.workflow:12s}  passed={q.checks_passed}  failed={q.checks_failed}  score={q.score:.2f}")

    # --- 16. Filter by pipeline ----------------------------------------
    print("\n[16] Filter Quality by Pipeline = 'equity'")

    result = list_quality_results(ctx, ListQualityResultsRequest(workflow="equity"))
    assert result.success
    print(f"  total : {result.total}")
    for q in result.data:
        print(f"  {q.workflow:12s}  score={q.score:.2f}")

    conn.close()
    print("\n✓ Locks, DLQ & quality complete.")


if __name__ == "__main__":
    main()
