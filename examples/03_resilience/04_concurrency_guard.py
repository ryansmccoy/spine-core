#!/usr/bin/env python3
"""Concurrency Guard — Prevent overlapping operation runs.

WHY CONCURRENCY GUARDS MATTER
─────────────────────────────
When a cron job, manual trigger, and a catch-up backfill all try to
ingest the same week simultaneously, you get duplicate rows, corrupted
aggregates, or deadlocks.  ConcurrencyGuard uses database-level advisory
locks to ensure exactly one instance of a keyed operation runs at a time,
without requiring an external lock service.

ARCHITECTURE
────────────
    Worker A                    core_concurrency_locks
    ────────                    ──────────────────────
    guard.acquire(key, id)  ──▶ INSERT lock_key, exec_id, expires_at
                                   ✓ acquired
    ... processing ...
    guard.release(key)      ──▶ DELETE lock_key

    Worker B (concurrent)
    ────────
    guard.acquire(key, id2) ──▶ SELECT → row exists → ✗ blocked

DATABASE SCHEMA
───────────────
    core_concurrency_locks
    ┌──────────────┬──────────┬─────────────────────────────┐
    │ Column       │ Type     │ Purpose                     │
    ├──────────────┼──────────┼─────────────────────────────┤
    │ lock_key     │ TEXT PK  │ "operation:partition" key     │
    │ execution_id │ TEXT     │ Which execution holds lock  │
    │ acquired_at  │ TEXT     │ UTC timestamp               │
    │ expires_at   │ TEXT     │ Auto-expiry for crashed runs│
    └──────────────┴──────────┴─────────────────────────────┘

    The lock_key is typically "operation_name:date_partition" so
    different partitions can run in parallel while the same
    partition is protected.

LOCK LIFECYCLE
──────────────
    acquire(key, exec_id, timeout_seconds=300)
        │
        ├─ No existing lock  → INSERT → return True
        ├─ Lock exists, not expired → return False
        └─ Lock exists, expired → DELETE old → INSERT → return True

    release(key) → DELETE row → return True

BEST PRACTICES
──────────────
• Use descriptive lock keys: "finra.otc.ingest:2024-W03".
• Always release in a finally block to avoid stale locks.
• Set timeout_seconds > expected run time to allow crash recovery.
• Use is_locked() before enqueueing to skip unnecessary work.
• Combine with DLQ (05_dead_letter_queue) to capture blocked runs.

Run: python examples/03_resilience/04_concurrency_guard.py

See Also:
    05_dead_letter_queue — capture runs that couldn't acquire locks
    06_timeout_enforcement — bound the protected section
"""
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta, timezone
from spine.execution import ConcurrencyGuard


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def setup_database(db_path: str) -> sqlite3.Connection:
    """Create a SQLite database with the concurrency table."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS core_concurrency_locks (
            lock_key TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            acquired_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def main():
    print("=" * 60)
    print("Concurrency Guard Examples")
    print("=" * 60)
    
    # Create temporary database
    db_path = os.path.join(tempfile.gettempdir(), "concurrency_demo.db")
    conn = setup_database(db_path)
    
    try:
        # === 1. Create concurrency guard ===
        print("\n[1] Create Concurrency Guard")
        
        guard = ConcurrencyGuard(conn)
        print(f"  Guard created with SQLite connection")
        
        # === 2. Acquire lock ===
        print("\n[2] Acquire Lock")
        
        lock_key = "finra.otc.ingest:2024-01-19"
        execution_id = "exec-001"
        
        acquired = guard.acquire(lock_key, execution_id, timeout_seconds=60)
        print(f"  Lock key: {lock_key}")
        print(f"  Execution ID: {execution_id}")
        print(f"  Acquired: {acquired}")
        
        # === 3. Second acquire fails ===
        print("\n[3] Second Acquire (Same Key)")
        
        execution_id_2 = "exec-002"
        acquired_2 = guard.acquire(lock_key, execution_id_2)
        print(f"  Execution ID: {execution_id_2}")
        print(f"  Acquired: {acquired_2} (blocked by exec-001)")
        
        # === 4. Different key succeeds ===
        print("\n[4] Different Key (Succeeds)")
        
        lock_key_2 = "finra.otc.ingest:2024-01-26"
        acquired_3 = guard.acquire(lock_key_2, execution_id_2)
        print(f"  Lock key: {lock_key_2}")
        print(f"  Acquired: {acquired_3}")
        
        # === 5. Release lock ===
        print("\n[5] Release Lock")
        
        released = guard.release(lock_key)
        print(f"  Released: {lock_key}")
        print(f"  Success: {released}")
        
        # Now exec-002 can acquire
        acquired_4 = guard.acquire(lock_key, execution_id_2)
        print(f"  exec-002 now acquired: {acquired_4}")
        
        # === 6. Check lock status ===
        print("\n[6] Check Lock Status")
        
        is_locked = guard.is_locked(lock_key)
        holder = guard.get_lock_holder(lock_key)
        print(f"  Lock '{lock_key}':")
        print(f"    Is locked: {is_locked}")
        print(f"    Held by: {holder}")
        
        # === 7. Real-world: Operation with guard ===
        print("\n[7] Real-world: Operation with Guard")
        
        def run_operation(name: str, week: str, exec_id: str) -> dict:
            """Run a operation with concurrency protection."""
            lock_key = f"{name}:{week}"
            
            if guard.acquire(lock_key, exec_id, timeout_seconds=300):
                try:
                    print(f"    [{exec_id}] Processing {name} for {week}...")
                    # Simulate work
                    result = {"operation": name, "week": week, "status": "success"}
                    print(f"    [{exec_id}] Complete!")
                    return result
                finally:
                    guard.release(lock_key)
            else:
                print(f"    [{exec_id}] Skipped - already running")
                return {"operation": name, "week": week, "status": "skipped"}
        
        # Cleanup from previous tests
        guard.release(lock_key)
        guard.release(lock_key_2)
        
        # Run operation
        result1 = run_operation("otc_volume", "2024-01-19", "exec-100")
        print(f"  Result: {result1}")
        
        # Try to run same operation again (would block if lock wasn't released)
        result2 = run_operation("otc_volume", "2024-01-19", "exec-101")
        print(f"  Result: {result2}")
        
        print("\n" + "=" * 60)
        print("[OK] Concurrency Guard Complete!")
        print("=" * 60)
        
    finally:
        conn.close()
        # Cleanup
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    main()
