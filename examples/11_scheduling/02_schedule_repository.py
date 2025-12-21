#!/usr/bin/env python3
"""Schedule Repository — CRUD, cron evaluation, and run tracking.

WHY A SCHEDULE REPOSITORY
─────────────────────────
Schedules are data, not code.  Instead of hardcoding cron expressions
in workflow definitions, the repository stores them in the database so
they can be created, updated, paused, and inspected at runtime — from
the API, CLI, or a dashboard.

ARCHITECTURE
────────────
    ScheduleRepository
    │
    ├─▶ create(ScheduleCreate)    → INSERT into core_schedules
    ├─▶ get(id) / list()          → SELECT with filters
    ├─▶ update(id, ScheduleUpdate)→ UPDATE cron, enabled, etc.
    ├─▶ delete(id)                → DELETE schedule
    ├─▶ get_due(now)              → schedules past next_run_at
    └─▶ record_run(id, result)    → core_schedule_runs
         │
         ▼
    ┌────────────────────────────────────┐
    │ core_schedules              │
    │ core_schedule_runs          │
    └────────────────────────────────────┘

SCHEDULE LIFECYCLE
──────────────────
    Create → Enabled → Due (past next_run_at) → Dispatched
                │                                       │
                └─ Paused                              record_run()

BEST PRACTICES
──────────────
• Set timezone explicitly in cron expressions for clarity.
• Use record_run() after every dispatch for audit trail.
• Query get_due(now) from the scheduler tick — never poll manually.
• Pause schedules instead of deleting them during maintenance.

Run: python examples/11_scheduling/02_schedule_repository.py

See Also:
    03_distributed_locks — prevent duplicate dispatch
    04_scheduler_service — the service that calls get_due()
    10_operations/08_schedule_metadata — data readiness checks
"""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from spine.core.dialect import SQLiteDialect
from spine.core.scheduling import (
    ScheduleCreate,
    ScheduleRepository,
    ScheduleUpdate,
)


def _create_db() -> sqlite3.Connection:
    """Create in-memory DB with scheduler schema."""
    conn = sqlite3.connect(":memory:")
    schema = Path(__file__).parent.parent.parent / "src" / "spine" / "core" / "schema" / "03_scheduler.sql"
    if schema.exists():
        conn.executescript(schema.read_text())
    return conn


def main():
    print("=" * 60)
    print("Scheduling — Schedule Repository")
    print("=" * 60)

    conn = _create_db()
    repo = ScheduleRepository(conn)

    # --- 1. Create schedules ----------------------------------------------
    print("\n[1] Create Schedules")

    cron_sched = repo.create(ScheduleCreate(
        name="daily-report",
        target_type="workflow",
        target_name="generate-report",
        schedule_type="cron",
        cron_expression="0 8 * * *",
        timezone="UTC",
        created_by="example",
    ))
    print(f"  created: {cron_sched.name}")
    print(f"    id            : {cron_sched.id[:12]}...")
    print(f"    schedule_type : {cron_sched.schedule_type}")
    print(f"    cron          : {cron_sched.cron_expression}")
    print(f"    next_run_at   : {cron_sched.next_run_at}")

    interval_sched = repo.create(ScheduleCreate(
        name="health-check",
        target_type="operation",
        target_name="system.health",
        schedule_type="interval",
        interval_seconds=300,
    ))
    print(f"\n  created: {interval_sched.name}")
    print(f"    interval      : {interval_sched.interval_seconds}s")
    print(f"    next_run_at   : {interval_sched.next_run_at}")

    # --- 2. Read operations -----------------------------------------------
    print("\n[2] Read Operations")

    by_id = repo.get(cron_sched.id)
    print(f"  get(id)     : {by_id.name}")

    by_name = repo.get_by_name("health-check")
    print(f"  get_by_name : {by_name.name}")

    missing = repo.get("nonexistent")
    print(f"  get(bad-id) : {missing}")

    # --- 3. List and count ------------------------------------------------
    print("\n[3] List & Count")

    all_scheds = repo.list_all()
    print(f"  list_all()     : {len(all_scheds)} schedule(s)")

    enabled = repo.list_enabled()
    print(f"  list_enabled() : {len(enabled)} schedule(s)")

    count = repo.count_enabled()
    print(f"  count_enabled(): {count}")

    # --- 4. Update --------------------------------------------------------
    print("\n[4] Update Schedule")

    updated = repo.update(cron_sched.id, ScheduleUpdate(
        cron_expression="30 7 * * 1-5",
        misfire_grace_seconds=120,
    ))
    print(f"  name    : {updated.name}")
    print(f"  cron    : {updated.cron_expression}")
    print(f"  grace   : {updated.misfire_grace_seconds}s")
    print(f"  version : {updated.version} (incremented)")

    # --- 5. Compute next run ----------------------------------------------
    print("\n[5] Compute Next Run")

    now = datetime.now(UTC)
    next_cron = repo.compute_next_run(updated, now)
    print(f"  cron next_run : {next_cron}")

    next_interval = repo.compute_next_run(interval_sched, now)
    print(f"  interval next : {next_interval}")
    print(f"  delta         : {(next_interval - now).total_seconds():.0f}s")

    # --- 6. Due schedules -------------------------------------------------
    print("\n[6] Due Schedules Query")

    # Manually set next_run to past to simulate due
    dialect = SQLiteDialect()
    past = (now - timedelta(minutes=5)).isoformat()
    conn.execute(
        f"UPDATE core_schedules SET next_run_at = {dialect.placeholder(0)} WHERE id = {dialect.placeholder(1)}",
        (past, cron_sched.id),
    )
    conn.commit()

    due = repo.get_due_schedules(now)
    print(f"  due count     : {len(due)}")
    for s in due:
        print(f"    • {s.name} (next_run: {s.next_run_at})")

    # --- 7. Run tracking --------------------------------------------------
    print("\n[7] Run Tracking")

    run_id = repo.mark_run_started(cron_sched.id, "wf-run-001")
    print(f"  mark_run_started → schedule_run_id: {run_id[:12]}...")

    sched_after = repo.get(cron_sched.id)
    print(f"  last_run_at     : {sched_after.last_run_at}")
    print(f"  last_run_status : {sched_after.last_run_status}")

    repo.mark_run_completed(cron_sched.id, "COMPLETED")
    sched_done = repo.get(cron_sched.id)
    print(f"  after complete  : status={sched_done.last_run_status}, next={sched_done.next_run_at}")

    runs = repo.list_runs(cron_sched.id)
    print(f"  run history     : {len(runs)} run(s)")
    for r in runs:
        print(f"    {r.id[:12]}... status={r.status}")

    # --- 8. Delete --------------------------------------------------------
    print("\n[8] Delete Schedule")

    deleted = repo.delete(interval_sched.id)
    print(f"  deleted       : {deleted}")
    print(f"  remaining     : {len(repo.list_all())}")

    conn.close()
    print("\n✓ Schedule repository complete.")


if __name__ == "__main__":
    main()
