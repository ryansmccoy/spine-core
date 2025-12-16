#!/usr/bin/env python3
"""Backfill Plan — Structured backfill planning with checkpoint resume.

Demonstrates spine-core's backfill primitives:
1. Creating a backfill plan with partitions
2. Lifecycle transitions (PLANNED → RUNNING → COMPLETED/FAILED)
3. Partition-level progress tracking
4. Checkpoint for resume after interruption
5. Cancellation and serialisation

Real-World Context:
    A gap detector finds that Q1-Q3 2024 filings are missing for 200
    companies.  The backfill will take 6+ hours due to rate limits.
    At hour 4, EDGAR returns a 429 (rate limit).  Without BackfillPlan,
    the operator has no idea which companies succeeded and which didn't.
    With BackfillPlan, progress is tracked per partition, a checkpoint
    saves the resume point, and the plan can be restarted from where
    it left off — no duplicate work, full audit trail.

Run: python examples/01_core/15_backfill_planning.py
"""

from spine.core.backfill import BackfillPlan, BackfillReason, BackfillStatus


def main():
    print("=" * 60)
    print("Backfill Plan — Structured Backfill with Checkpoints")
    print("=" * 60)

    # ── 1. Create a backfill plan ───────────────────────────────
    print("\n--- 1. Create backfill plan ---")
    plan = BackfillPlan.create(
        domain="sec_filings",
        source="edgar",
        reason=BackfillReason.GAP,
        partition_keys=["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"],
        created_by="gap_detector",
    )
    print(f"  Plan ID:     {plan.plan_id}")
    print(f"  Domain:      {plan.domain}")
    print(f"  Source:       {plan.source}")
    print(f"  Reason:      {plan.reason.value}")
    print(f"  Status:      {plan.status.value}")
    print(f"  Partitions:  {plan.partition_keys}")
    print(f"  Progress:    {plan.progress_pct}%")

    # ── 2. Enums ────────────────────────────────────────────────
    print("\n--- 2. BackfillReason enum ---")
    for reason in BackfillReason:
        print(f"    {reason.name}: {reason.value}")

    print("\n  BackfillStatus enum:")
    for status in BackfillStatus:
        print(f"    {status.name}: {status.value}")

    # ── 3. Start the backfill ───────────────────────────────────
    print("\n--- 3. Start backfill ---")
    plan.start()
    print(f"  Status:     {plan.status.value}")
    print(f"  Started at: {plan.started_at}")
    print(f"  Remaining:  {plan.remaining_keys}")

    # ── 4. Process partitions ───────────────────────────────────
    print("\n--- 4. Process partitions ---")
    plan.mark_partition_done("2024-Q1")
    print(f"  Completed 2024-Q1: progress={plan.progress_pct}%")

    plan.mark_partition_done("2024-Q2")
    print(f"  Completed 2024-Q2: progress={plan.progress_pct}%")

    plan.mark_partition_failed("2024-Q3", "EDGAR 429 rate limit")
    print(f"  Failed 2024-Q3:    progress={plan.progress_pct}%")
    print(f"  Remaining: {plan.remaining_keys}")

    # ── 5. Checkpoint (save state for resume) ───────────────────
    print("\n--- 5. Checkpoint ---")
    plan.save_checkpoint("resumed_after_Q2")
    print(f"  Checkpoint:   {plan.checkpoint}")
    print(f"  Is resumable? {plan.is_resumable}")

    # ── 6. Serialisation ────────────────────────────────────────
    print("\n--- 6. Serialise to dict ---")
    d = plan.to_dict()
    print(f"  Keys: {sorted(d.keys())}")
    print(f"  Status:   {d['status']}")
    print(f"  Domain:   {d['domain']}")

    # ── 7. Complete the remaining partition ──────────────────────
    print("\n--- 7. Complete remaining work ---")
    plan.mark_partition_done("2024-Q4")
    print(f"  Status:   {plan.status.value}")
    print(f"  Progress: {plan.progress_pct}%")

    # ── 8. Create and cancel a plan ─────────────────────────────
    print("\n--- 8. Cancel workflow ---")
    plan2 = BackfillPlan.create(
        domain="prices",
        source="vendor_a",
        reason=BackfillReason.MANUAL,
        partition_keys=["2025-01", "2025-02"],
    )
    plan2.start()
    plan2.cancel()
    print(f"  Status:       {plan2.status.value}")
    print(f"  Is resumable? {plan2.is_resumable}")

    # ── 9. Different reasons ────────────────────────────────────
    print("\n--- 9. Backfill for different reasons ---")
    for reason in [BackfillReason.CORRECTION, BackfillReason.SCHEMA_CHANGE, BackfillReason.QUALITY_FAILURE]:
        p = BackfillPlan.create(
            domain="analytics",
            source="internal",
            reason=reason,
            partition_keys=["batch-1"],
        )
        print(f"    {reason.value:20s} -> plan_id={p.plan_id[:12]}...")

    print("\n" + "=" * 60)
    print("[OK] Backfill plan example complete")


if __name__ == "__main__":
    main()
