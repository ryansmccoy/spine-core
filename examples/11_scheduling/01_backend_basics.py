#!/usr/bin/env python3
"""Backend Basics — Pluggable timing backends and the SchedulerBackend protocol.

WHY A PLUGGABLE BACKEND ARCHITECTURE
─────────────────────────────────────
Scheduling has a clean separation of concerns:
  • The **backend** controls WHEN ticks happen (timer, cron, APScheduler).
  • The **SchedulerService** controls WHAT happens on each tick.

This lets you swap from a simple thread-based poller in development to a
distributed APScheduler backend in production without changing any
schedule definitions or dispatch logic.

ARCHITECTURE
────────────
    SchedulerBackend (protocol)
    │
    ├─▶ ThreadSchedulerBackend   ─ simple, single-process
    ├─▶ APSchedulerBackend      ─ production, distributed
    └─▶ Custom (implement protocol)

    Backend lifecycle:
    start() → tick(…) → tick(…) → … → stop()
                 │
                 ▼
         SchedulerService.on_tick(schedules_due)

    BackendHealth:
      .healthy    → ticking normally
      .degraded   → running but drifting
      .unhealthy  → stopped or missing ticks

BEST PRACTICES
──────────────
• Use ThreadSchedulerBackend for local dev and single-process deploys.
• Use APSchedulerBackend when you need persistence or multi-node.
• Monitor BackendHealth in production for drift detection.
• Backends are intentionally simple — keep business logic in the service.

Run: python examples/11_scheduling/01_backend_basics.py

See Also:
    04_scheduler_service — the SchedulerService that consumes ticks
    05_health_monitoring — NTP drift and tick stability analysis
"""

import asyncio
import time

from spine.core.scheduling import ThreadSchedulerBackend
from spine.core.scheduling.protocol import BackendHealth, SchedulerBackend


def main():
    print("=" * 60)
    print("Scheduling — Backend Basics")
    print("=" * 60)

    # --- 1. Protocol compliance -------------------------------------------
    print("\n[1] ThreadSchedulerBackend implements SchedulerBackend protocol")

    backend = ThreadSchedulerBackend()
    assert isinstance(backend, SchedulerBackend)
    print(f"  name         : {backend.name}")
    print(f"  is_running   : {backend.is_running}")
    print(f"  tick_count   : {backend.tick_count}")
    print(f"  protocol ok  : {isinstance(backend, SchedulerBackend)}")

    # --- 2. Start and observe ticks ---------------------------------------
    print("\n[2] Start Backend — Observe Ticks")

    tick_log: list[str] = []

    async def my_tick():
        tick_log.append(f"tick #{len(tick_log) + 1}")

    backend.start(my_tick, interval_seconds=0.2)
    print(f"  started      : {backend.is_running}")

    time.sleep(0.7)  # Wait for ~3 ticks

    backend.stop()
    print(f"  stopped      : {not backend.is_running}")
    print(f"  ticks logged : {len(tick_log)}")
    for entry in tick_log:
        print(f"    • {entry}")

    # --- 3. Health reporting ----------------------------------------------
    print("\n[3] Backend Health Reporting")

    health = backend.health()
    for k, v in health.items():
        print(f"  {k:20s}: {v}")

    # --- 4. Structured health via BackendHealth ---------------------------
    print("\n[4] Structured BackendHealth (dataclass)")

    bh = backend.get_health()
    assert isinstance(bh, BackendHealth)
    print(f"  healthy    : {bh.healthy}")
    print(f"  backend    : {bh.backend}")
    print(f"  tick_count : {bh.tick_count}")
    print(f"  last_tick  : {bh.last_tick}")
    d = bh.to_dict()
    print(f"  to_dict()  : {sorted(d.keys())}")

    # --- 5. Error resilience ----------------------------------------------
    print("\n[5] Backend survives tick exceptions")

    error_backend = ThreadSchedulerBackend()
    call_count = 0

    async def flaky_tick():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("Simulated failure")

    error_backend.start(flaky_tick, interval_seconds=0.15)
    time.sleep(0.6)
    error_backend.stop()

    print(f"  calls made   : {call_count}")
    print(f"  still healthy: {error_backend.tick_count >= 3}")

    print("\n✓ Backend basics complete.")


if __name__ == "__main__":
    main()
