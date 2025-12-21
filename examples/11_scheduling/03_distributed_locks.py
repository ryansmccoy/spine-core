#!/usr/bin/env python3
"""Distributed Locks — Atomic lock acquire/release with TTL expiry.

WHY DISTRIBUTED LOCKS FOR SCHEDULING
───────────────────────────────────
When multiple scheduler instances run behind a load balancer, a due
schedule would be dispatched N times without coordination.  The
LockManager uses atomic INSERT-or-FAIL to ensure exactly ONE instance
acquires a schedule lock, even under concurrent access.

ARCHITECTURE
────────────
    Scheduler Instance A              Scheduler Instance B
    ──────────────────────          ──────────────────────
    lock.acquire("sched-42")         lock.acquire("sched-42")
         │                                   │
         ▼                                   ▼
    ┌─────────────────────────────────────────────┐
    │ core_schedule_locks (PRIMARY KEY)           │
    │                                             │
    │  Instance A: ✔ acquired (first INSERT wins)  │
    │  Instance B: ✘ blocked  (conflict)            │
    └─────────────────────────────────────────────┘

    TTL expiry: stale locks auto-expire so crashed instances
    don’t block schedules forever.

LOCK API
────────
    acquire(key, holder, ttl_seconds) → bool
    release(key, holder)              → bool
    is_locked(key)                    → bool
    cleanup_expired()                 → int (count released)

BEST PRACTICES
──────────────
• Set TTL to 2× expected execution time to avoid false expiry.
• Always release in a finally block.
• Run cleanup_expired() on a timer (the SchedulerService does this).
• Use holder = hostname:pid for debugging lock ownership.

Run: python examples/11_scheduling/03_distributed_locks.py

See Also:
    04_scheduler_service — uses LockManager internally
    10_operations/09_locks_dlq_quality — ops-layer lock inspection
    03_resilience/04_concurrency_guard — runtime concurrency locks
"""

import sqlite3
import time
from pathlib import Path

from spine.core.scheduling import LockManager


def _create_db() -> sqlite3.Connection:
    """Create in-memory DB with scheduler schema."""
    conn = sqlite3.connect(":memory:")
    schema = Path(__file__).parent.parent.parent / "src" / "spine" / "core" / "schema" / "03_scheduler.sql"
    if schema.exists():
        conn.executescript(schema.read_text())
    return conn


def main():
    print("=" * 60)
    print("Scheduling — Distributed Locks")
    print("=" * 60)

    conn = _create_db()

    # --- 1. Basic lock acquire/release ------------------------------------
    print("\n[1] Basic Lock Acquire / Release")

    mgr = LockManager(conn, instance_id="scheduler-A")
    print(f"  instance_id : {mgr.instance_id}")

    acquired = mgr.acquire_schedule_lock("sched-001", ttl_seconds=300)
    print(f"  acquire     : {acquired}")
    print(f"  is_locked   : {mgr.is_locked('sched-001')}")
    print(f"  holder      : {mgr.get_lock_holder('sched-001')}")

    released = mgr.release_schedule_lock("sched-001")
    print(f"  release     : {released}")
    print(f"  is_locked   : {mgr.is_locked('sched-001')}")

    # --- 2. Contention between instances ----------------------------------
    print("\n[2] Lock Contention (Two Instances)")

    mgr_a = LockManager(conn, instance_id="scheduler-A")
    mgr_b = LockManager(conn, instance_id="scheduler-B")

    a_got = mgr_a.acquire_schedule_lock("sched-002")
    b_got = mgr_b.acquire_schedule_lock("sched-002")

    print(f"  A acquired : {a_got}")
    print(f"  B acquired : {b_got}  (blocked — A holds the lock)")
    print(f"  holder     : {mgr_a.get_lock_holder('sched-002')}")

    # B cannot release A's lock
    b_released = mgr_b.release_schedule_lock("sched-002")
    print(f"  B release  : {b_released}  (cannot release A's lock)")

    # A releases
    mgr_a.release_schedule_lock("sched-002")
    b_retry = mgr_b.acquire_schedule_lock("sched-002")
    print(f"  B retry    : {b_retry}  (A released → B now holds it)")

    mgr_b.release_schedule_lock("sched-002")

    # --- 3. Lock refresh (re-acquire own lock) ----------------------------
    print("\n[3] Lock Refresh (Same Instance Re-acquire)")

    mgr_a.acquire_schedule_lock("sched-003", ttl_seconds=60)
    refreshed = mgr_a.acquire_schedule_lock("sched-003", ttl_seconds=300)
    print(f"  re-acquire : {refreshed}  (TTL refreshed, not blocked)")

    mgr_a.release_schedule_lock("sched-003")

    # --- 4. TTL-based expiry ----------------------------------------------
    print("\n[4] TTL Expiry")

    mgr_a.acquire_schedule_lock("sched-004", ttl_seconds=1)
    print(f"  locked     : {mgr_a.is_locked('sched-004')}")

    time.sleep(1.2)
    print(f"  after 1.2s : {mgr_a.is_locked('sched-004')}  (expired)")

    # Another instance can now acquire
    b_after = mgr_b.acquire_schedule_lock("sched-004")
    print(f"  B acquire  : {b_after}  (expired lock → available)")
    mgr_b.release_schedule_lock("sched-004")

    # --- 5. Concurrency locks (general purpose) ---------------------------
    print("\n[5] General Concurrency Locks")

    mgr_a.acquire_concurrency_lock("operation", "data-refresh", ttl_seconds=120)
    print(f"  acquired operation:data-refresh")

    b_blocked = mgr_b.acquire_concurrency_lock("operation", "data-refresh")
    print(f"  B blocked  : {not b_blocked}")

    mgr_a.release_concurrency_lock("operation", "data-refresh")
    print(f"  released")

    # --- 6. Maintenance: cleanup & listing --------------------------------
    print("\n[6] Maintenance Operations")

    # Create some locks with short TTL
    mgr_a.acquire_schedule_lock("stale-1", ttl_seconds=1)
    mgr_a.acquire_schedule_lock("stale-2", ttl_seconds=1)
    mgr_a.acquire_schedule_lock("active-1", ttl_seconds=300)

    time.sleep(1.2)

    locks_before = mgr_a.list_active_locks()
    print(f"  active locks before cleanup : {len(locks_before)}")

    cleaned = mgr_a.cleanup_expired_locks()
    print(f"  expired locks cleaned       : {cleaned}")

    locks_after = mgr_a.list_active_locks()
    print(f"  active locks after cleanup  : {len(locks_after)}")
    for lk in locks_after:
        print(f"    • {lk['schedule_id']} held by {lk['locked_by']}")

    # --- 7. Force release all ---------------------------------------------
    print("\n[7] Force Release All (recovery)")

    count = mgr_a.force_release_all()
    print(f"  force released : {count}")
    print(f"  active locks   : {len(mgr_a.list_active_locks())}")

    conn.close()
    print("\n✓ Distributed locks complete.")


if __name__ == "__main__":
    main()
