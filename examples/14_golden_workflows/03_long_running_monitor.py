"""Long-Running Workflow Monitor — timeouts, progress, concurrency guards.

Demonstrates patterns for managing long-running workflow steps that may
take minutes or hours, with:

    - Progress tracking via ExecutionLedger events
    - Concurrency guards to prevent overlapping runs
    - Timeout enforcement per step
    - Idempotent re-runs (pick up where you left off)
    - WorkManifest stage tracking for multi-phase processing

This is the pattern you'd use for an overnight batch job that processes
millions of SEC filings, a weekly FINRA data aggregation, or any workflow
where individual steps may take 30+ minutes.

Key spine modules:
    - spine.execution.context      — tracked_execution (sync context manager)
    - spine.execution.ledger       — ExecutionLedger (create/update/query executions)
    - spine.execution.concurrency  — ConcurrencyGuard (prevent double-runs)
    - spine.core.manifest          — WorkManifest (stage-based progress)
    - spine.core.quality           — QualityRunner (quality gates)

Tier: Basic (spine-core only)
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from spine.core.connection import create_connection

# ── Database setup ──────────────────────────────────────────────────────

conn, info = create_connection(init_schema=True)

# ExecutionLedger and ConcurrencyGuard require a raw sqlite3.Connection
# (they call cursor()), while SqliteConnection only exposes execute().
raw_conn = conn.raw if hasattr(conn, "raw") else conn

print("=" * 72)
print("LONG-RUNNING WORKFLOW MONITOR")
print("=" * 72)
print(f"  Backend: {info.backend}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 1 — ExecutionLedger: track every workflow run
# ═════════════════════════════════════════════════════════════════════
#
# ExecutionLedger records workflow executions in core_executions table.
# Each execution has: id, pipeline (API field), params, status, timestamps.
# Record events as progress markers within a run.

from spine.execution.ledger import ExecutionLedger
from spine.execution.models import Execution, ExecutionStatus

print("\n── Section 1: ExecutionLedger ──────────────────────────")

ledger = ExecutionLedger(raw_conn)

# Create an execution record
exec1 = Execution.create(
    workflow="sec.filing_backfill",
    params={"start_date": "2020-01-01", "end_date": "2024-12-31"},
)
ledger.create_execution(exec1)
print(f"  Created execution: {exec1.id[:12]}...")
print(f"  Workflow : {exec1.workflow}")
print(f"  Status  : {exec1.status.value}")

# Record progress events as the workflow processes data
ledger.record_event(exec1.id, event_type="progress", data={"message": "Fetching filing index", "page": 1})
ledger.record_event(exec1.id, event_type="progress", data={"message": "Downloaded 50,000 filings", "page": 50})
ledger.record_event(exec1.id, event_type="progress", data={"message": "Processing XBRL facts", "batch": 1})

# Update status through the lifecycle
ledger.update_status(exec1.id, ExecutionStatus.RUNNING)
print(f"  Status → RUNNING")

# Simulate processing work
time.sleep(0.05)

ledger.update_status(exec1.id, ExecutionStatus.COMPLETED, result={"filings_processed": 50000})
print(f"  Status → COMPLETED")

# Query execution
stored = ledger.get_execution(exec1.id)
if stored:
    print(f"  Duration: created_at={stored.created_at}")
    print(f"  Final status: {stored.status.value}")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 2 — ConcurrencyGuard: prevent overlapping runs
# ═══════════════════════════════════════════════════════════════════════
#
# ConcurrencyGuard uses database-level locking so only one instance of
# a workflow+params combination can run at a time.  Locks auto-expire.

from spine.execution.concurrency import ConcurrencyGuard

print("\n── Section 2: ConcurrencyGuard ─────────────────────────")

guard = ConcurrencyGuard(raw_conn)

lock_key = "workflow:sec.filing_backfill:2024-Q4"
exec_id = str(uuid.uuid4())

# First acquire succeeds
acquired = guard.acquire(lock_key, execution_id=exec_id, timeout_seconds=300)
print(f"  Lock acquired (first): {acquired}")

# Second acquire fails — workflow already running
exec_id_2 = str(uuid.uuid4())
acquired_2 = guard.acquire(lock_key, execution_id=exec_id_2, timeout_seconds=300)
print(f"  Lock acquired (second, same key): {acquired_2}")

# Release the lock
guard.release(lock_key, execution_id=exec_id)
print(f"  Lock released")

# Now third attempt succeeds
exec_id_3 = str(uuid.uuid4())
acquired_3 = guard.acquire(lock_key, execution_id=exec_id_3, timeout_seconds=300)
print(f"  Lock acquired (third, after release): {acquired_3}")
guard.release(lock_key, execution_id=exec_id_3)


# ═══════════════════════════════════════════════════════════════════════
# SECTION 3 — tracked_execution: all-in-one context manager
# ═══════════════════════════════════════════════════════════════════════
#
# tracked_execution() wraps all the manual steps above into a single
# context manager: create → lock → RUNNING → yield → COMPLETED/FAILED.

from spine.execution.context import tracked_execution

print("\n── Section 3: tracked_execution context manager ────────")


def simulate_heavy_processing(ctx):
    """Simulate a multi-phase processing job."""
    phases = [
        ("fetch_index", 0.02),
        ("download_filings", 0.03),
        ("parse_xbrl", 0.02),
        ("calculate_metrics", 0.01),
        ("write_results", 0.01),
    ]

    for phase_name, duration in phases:
        ctx.log_progress(f"Starting {phase_name}")
        time.sleep(duration)  # Simulate work
        ctx.log_progress(f"Completed {phase_name}")

    return {
        "filings_processed": 12500,
        "metrics_calculated": 87000,
        "quality_score": 98.5,
    }


with tracked_execution(
    ledger=ledger,
    guard=guard,
    dlq=None,  # No DLQ for this example
    workflow="sec.quarterly_analysis",
    params={"quarter": "2024-Q4", "cik": "0000320193"},
    idempotency_key="sec.quarterly_analysis:2024-Q4:320193",
) as ctx:
    print(f"  Execution ID: {ctx.id[:12]}...")
    print(f"  Workflow  : {ctx.workflow}")
    print(f"  Params      : {ctx.params}")

    result = simulate_heavy_processing(ctx)
    ctx.set_result(result)
    print(f"  Result      : {result}")

print(f"  Status → COMPLETED (auto-set by context manager)")

# Idempotent re-run — same idempotency_key skips execution
with tracked_execution(
    ledger=ledger,
    guard=guard,
    dlq=None,
    workflow="sec.quarterly_analysis",
    params={"quarter": "2024-Q4", "cik": "0000320193"},
    idempotency_key="sec.quarterly_analysis:2024-Q4:320193",
    skip_if_completed=True,
) as ctx2:
    print(f"\n  Re-run (same idempotency_key):")
    print(f"  Execution ID: {ctx2.id[:12]}...")
    print(f"  Skipped: reused previous completed execution")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 4 — WorkManifest: stage-based progress tracking
# ═══════════════════════════════════════════════════════════════════════
#
# WorkManifest tracks which processing stages have completed for a
# given partition key.  Perfect for multi-day batch jobs that need
# to resume from the last completed stage.

from spine.core.manifest import WorkManifest

print("\n── Section 4: WorkManifest (stage tracking) ────────────")

stages = ["FETCHED", "PARSED", "ENRICHED", "SCORED", "PUBLISHED"]
manifest = WorkManifest(conn, domain="sec.backfill", stages=stages)

partition = {"cik": "320193", "period": "2024"}

# Advance through stages — each call is idempotent
manifest.advance_to(partition, "FETCHED")
print(f"  Stage → FETCHED")
print(f"  At least FETCHED? {manifest.is_at_least(partition, 'FETCHED')}")

manifest.advance_to(partition, "PARSED")
print(f"  Stage → PARSED")
print(f"  At least FETCHED? {manifest.is_at_least(partition, 'FETCHED')}")
print(f"  At least PARSED?  {manifest.is_at_least(partition, 'PARSED')}")

# In a real workflow, you'd check stage before doing expensive work:
if not manifest.is_at_least(partition, "ENRICHED"):
    print(f"  Partition not yet ENRICHED — would run enrichment here")
    manifest.advance_to(partition, "ENRICHED")
else:
    print(f"  Partition already ENRICHED — skipping")

manifest.advance_to(partition, "SCORED")
manifest.advance_to(partition, "PUBLISHED")
print(f"  Stage → PUBLISHED (final)")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 5 — Quality gates on long-running results
# ═══════════════════════════════════════════════════════════════════════
#
# After a long-running step completes, run quality checks before
# proceeding to the next stage.

from spine.core.quality import (
    QualityCategory,
    QualityCheck,
    QualityResult,
    QualityRunner,
    QualityStatus,
)

print("\n── Section 5: Post-processing quality gates ────────────")

# Simulate results from a long-running computation
batch_results = {
    "total_filings": 50000,
    "successful_parses": 49850,
    "failed_parses": 150,
    "parse_success_rate": 99.7,
    "avg_facts_per_filing": 342,
    "outlier_count": 23,
}


def check_parse_success_rate(ctx: dict) -> QualityResult:
    rate = ctx.get("parse_success_rate", 0)
    if rate >= 99.0:
        return QualityResult(QualityStatus.PASS, f"Parse rate {rate}% >= 99%", rate, ">=99%")
    elif rate >= 95.0:
        return QualityResult(QualityStatus.WARN, f"Parse rate {rate}% is low", rate, ">=99%")
    return QualityResult(QualityStatus.FAIL, f"Parse rate {rate}% below threshold", rate, ">=99%")


def check_outlier_ratio(ctx: dict) -> QualityResult:
    total = ctx.get("total_filings", 1)
    outliers = ctx.get("outlier_count", 0)
    ratio = outliers / total * 100
    if ratio < 1.0:
        return QualityResult(QualityStatus.PASS, f"Outlier ratio {ratio:.2f}% < 1%", ratio, "<1%")
    return QualityResult(QualityStatus.WARN, f"Outlier ratio {ratio:.2f}% elevated", ratio, "<1%")


qr = QualityRunner(conn, domain="sec.backfill", execution_id=exec1.id)
qr.add(QualityCheck("parse_success", QualityCategory.COMPLETENESS, check_parse_success_rate))
qr.add(QualityCheck("outlier_ratio", QualityCategory.INTEGRITY, check_outlier_ratio))

checks = qr.run_all(batch_results)
for name, status in checks.items():
    icon = "✓" if status == QualityStatus.PASS else "⚠" if status == QualityStatus.WARN else "✗"
    print(f"  [{icon}] {name}: {status.value}")

if qr.has_failures():
    print("  ✗ Quality gate FAILED — results not promoted")
else:
    print("  ✓ Quality gate passed — results ready for promotion")


# ═══════════════════════════════════════════════════════════════════════
# SECTION 6 — Full pattern: ManagedWorkflow with monitoring
# ═══════════════════════════════════════════════════════════════════════
#
# Wire everything together: ManagedWorkflow where each step simulates
# a long-running operation with progress tracking.

from spine.orchestration.managed_workflow import ManagedWorkflow

print("\n── Section 6: Full monitored workflow ──────────────────")


def step_fetch_filing_index(**kwargs: Any) -> dict[str, Any]:
    """Step 1: Fetch SEC EDGAR full-text search index (long-running)."""
    time.sleep(0.03)
    return {"index_entries": 85000, "date_range": "2020-2024", "size_mb": 1200}


def step_download_and_parse(**kwargs: Any) -> dict[str, Any]:
    """Step 2: Download and parse XBRL filings (longest step)."""
    index_entries = kwargs.get("index_entries", 0)
    time.sleep(0.05)  # Would be hours in production
    return {
        "filings_parsed": index_entries,
        "facts_extracted": index_entries * 342,
        "parse_errors": int(index_entries * 0.003),
    }


def step_calculate_metrics(**kwargs: Any) -> dict[str, Any]:
    """Step 3: Compute financial metrics and risk scores."""
    facts = kwargs.get("facts_extracted", 0)
    time.sleep(0.02)
    return {"metrics_computed": facts, "risk_scores_generated": facts // 100}


def step_publish_results(**kwargs: Any) -> dict[str, Any]:
    """Step 4: Publish to data warehouse / API."""
    time.sleep(0.01)
    return {"published": True, "destination": "data_warehouse", "api_available": True}


wf = (
    ManagedWorkflow("golden.long_running_batch")
    .step("fetch_index", step_fetch_filing_index)
    .step("parse_filings", step_download_and_parse)
    .step("calculate", step_calculate_metrics)
    .step("publish", step_publish_results)
    .build()
)

result = wf.run(partition={"batch": "2024-annual", "scope": "all_ciks"})
wf.show()

# Output summary
import json

summary = {
    "workflow": result.workflow_name,
    "status": result.status.value,
    "completed_steps": result.completed_steps,
    "duration_seconds": result.duration_seconds,
    "run_id": result.run_id,
}
print(f"\n  Summary JSON:")
print(f"  {json.dumps(summary, indent=2, default=str)}")


# ═══════════════════════════════════════════════════════════════════════
# RECAP
# ═══════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 72}")
print("LONG-RUNNING PATTERNS — COMPLETE")
print("=" * 72)
print("""
  Building blocks for long-running workflows:

    ExecutionLedger     → Record every run with status lifecycle
    ConcurrencyGuard    → Prevent overlapping workflow executions
    tracked_execution   → All-in-one: create → lock → run → complete/fail
    WorkManifest        → Stage-based progress (resume where you left off)
    QualityRunner       → Quality gates after expensive computations
    ManagedWorkflow     → Combines all of the above in a fluent builder

  Production patterns:
    - Use idempotency_key to make re-runs safe
    - Use WorkManifest stages for multi-day batch jobs
    - Use ConcurrencyGuard to prevent duplicate cron triggers
    - Run QualityRunner after each expensive stage
    - Set lock_timeout to match your SLA
""")

wf.close()
