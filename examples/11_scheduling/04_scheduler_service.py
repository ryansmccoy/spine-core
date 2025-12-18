#!/usr/bin/env python3
"""Scheduler Service — Full lifecycle: start, tick, dispatch, pause, resume, health.

WHY A UNIFIED SCHEDULER SERVICE
───────────────────────────────
The SchedulerService is the orchestrator that ties together:
  • Backend (timing)  — WHEN to check for due schedules
  • Repository (data)  — WHAT schedules exist / are due
  • LockManager (safety) — WHO dispatches each one
  • Dispatcher (action) — HOW to execute the workflow

This single-responsibility split means each component is testable
in isolation, while the service handles the coordination.

ARCHITECTURE
────────────
    SchedulerService
    │
    ├─▶ SchedulerBackend.start()       ─ begin ticking
    │       on each tick:
    │       ├─ ScheduleRepository.get_due() ─ find due schedules
    │       ├─ LockManager.acquire()        ─ prevent duplicates
    │       └─ dispatch(schedule)            ─ call workflow
    │           └─ LockManager.release()
    │           └─ ScheduleRepository.record_run()
    │
    ├─▶ pause() / resume()              ─ maintenance windows
    └─▶ health()                        ─ BackendHealth + stats

SERVICE STATES
──────────────
    STOPPED → RUNNING → PAUSED → RUNNING → STOPPED
                  │
                  └─ dispatching on tick

BEST PRACTICES
──────────────
• Run as a long-lived async service (not a cron job).
• Use pause() before maintenance, resume() after.
• Monitor health() on every tick for drift detection.
• Build custom dispatchers that call WorkflowRunner.execute().

Run: python examples/11_scheduling/04_scheduler_service.py

See Also:
    01_backend_basics — pluggable timing backends
    02_schedule_repository — CRUD on schedules
    03_distributed_locks — preventing duplicate dispatch
    05_health_monitoring — NTP drift and stability
"""

import asyncio
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from spine.core.scheduling import (
    LockManager,
    ScheduleCreate,
    ScheduleRepository,
    SchedulerService,
    ThreadSchedulerBackend,
    create_scheduler,
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
    print("Scheduling — Scheduler Service")
    print("=" * 60)

    conn = _create_db()

    # --- 1. Factory function (recommended) --------------------------------
    print("\n[1] Create via Factory Function")

    service = create_scheduler(conn, interval_seconds=0.5)
    print(f"  backend  : {service.backend.name}")
    print(f"  interval : {service.interval}s")
    print(f"  running  : {service.is_running}")

    # --- 2. Manual assembly -----------------------------------------------
    print("\n[2] Manual Component Assembly")

    backend = ThreadSchedulerBackend()
    repo = ScheduleRepository(conn)
    locks = LockManager(conn, instance_id="demo-instance")

    service = SchedulerService(
        backend=backend,
        repository=repo,
        lock_manager=locks,
        dispatcher=None,  # No dispatcher → test mode
        interval_seconds=0.3,
    )
    print(f"  backend      : {backend.name}")
    print(f"  instance_id  : {locks.instance_id}")

    # --- 3. Create schedules before starting ------------------------------
    print("\n[3] Register Schedules")

    sched1 = repo.create(ScheduleCreate(
        name="fast-interval",
        target_type="workflow",
        target_name="demo.fast",
        schedule_type="interval",
        interval_seconds=1,
    ))
    print(f"  created: {sched1.name} (interval=1s)")

    sched2 = repo.create(ScheduleCreate(
        name="daily-report",
        target_type="workflow",
        target_name="demo.report",
        schedule_type="cron",
        cron_expression="0 8 * * *",
    ))
    print(f"  created: {sched2.name} (cron=0 8 * * *)")

    enabled = repo.count_enabled()
    print(f"  enabled: {enabled}")

    # --- 4. Start service -------------------------------------------------
    print("\n[4] Start Scheduler Service")

    service.start()
    print(f"  is_running : {service.is_running}")

    # Let ticks happen
    time.sleep(1.0)

    stats = service.get_stats()
    print(f"  tick_count : {stats.tick_count}")
    print(f"  processed  : {stats.schedules_processed}")

    service.stop()
    print(f"  stopped    : {not service.is_running}")

    # --- 5. Pause and resume ----------------------------------------------
    print("\n[5] Pause / Resume")

    paused = service.pause("fast-interval")
    print(f"  paused 'fast-interval' : {paused}")

    sched = repo.get_by_name("fast-interval")
    print(f"  enabled                : {sched.enabled}")

    resumed = service.resume("fast-interval")
    print(f"  resumed                : {resumed}")

    sched = repo.get_by_name("fast-interval")
    print(f"  enabled                : {sched.enabled}")

    # --- 6. Manual trigger ------------------------------------------------
    print("\n[6] Manual Trigger")

    run_id = asyncio.run(service.trigger("daily-report"))
    print(f"  trigger 'daily-report' → run_id: {run_id}")

    # With override params
    run_id2 = asyncio.run(service.trigger(
        "daily-report",
        params={"format": "pdf"},
    ))
    print(f"  trigger with params    → run_id: {run_id2}")

    # --- 7. Health status -------------------------------------------------
    print("\n[7] Health Status")

    # Start briefly to get health data
    service.start()
    time.sleep(0.5)

    health = service.health()
    print(f"  healthy          : {health.healthy}")
    print(f"  schedules_enabled: {health.schedules_enabled}")
    print(f"  active_locks     : {health.active_locks}")

    d = health.to_dict()
    print(f"  stats:")
    for k, v in d["stats"].items():
        print(f"    {k:25s}: {v}")

    service.stop()

    # --- 8. Stats reset ---------------------------------------------------
    print("\n[8] Stats Reset")

    final_stats = service.get_stats()
    print(f"  tick_count before reset : {final_stats.tick_count}")

    service.reset_stats()
    print(f"  tick_count after reset  : {service.get_stats().tick_count}")

    conn.close()
    print("\n✓ Scheduler service complete.")


if __name__ == "__main__":
    main()
