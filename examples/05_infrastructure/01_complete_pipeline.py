"""Complete Execution Infrastructure — Full pipeline with all resilience primitives.

WHY THIS PATTERN
────────────────
A production data pipeline needs more than just "run the code".  It needs
idempotency (don't re-process), locking (don't run twice), failure
capture (don't lose failed work), and analytics (what happened?).  This
example wires all four execution primitives together in the recommended
production pattern.

ARCHITECTURE
────────────
    ┌────────────────────────────────────────────┐
    │   run_pipeline(name, params)               │
    │                                            │
    │  1. ExecutionLedger.get_by_idempotency_key  │
    │     └─ already done? → skip                 │
    │                                            │
    │  2. Execution.create() → ledger.create      │
    │                                            │
    │  3. ConcurrencyGuard.acquire(lock_key)     │
    │     └─ can't lock? → CANCELLED             │
    │                                            │
    │  4. ledger.update_status(RUNNING)           │
    │     └─ do work ...                          │
    │                                            │
    │  5a. Success → ledger.update_status(DONE)   │
    │  5b. Failure → DLQManager.add_to_dlq()     │
    │                                            │
    │  6. guard.release(lock_key)  (finally)      │
    └────────────────────────────────────────────┘

COMPONENTS
──────────
    Component             Purpose
    ───────────────────── ─────────────────────────────────
    ExecutionLedger        Track every run with status/error
    ConcurrencyGuard       Prevent overlapping pipeline runs
    DLQManager             Capture failures for later replay
    ExecutionRepository    Analytics: success rates, durations

BEST PRACTICES
──────────────
• Always use idempotency keys to make re-runs safe.
• Release locks in finally blocks — never rely on cleanup.
• Process the DLQ on a schedule (e.g., every 15 minutes).
• Use ExecutionRepository.get_execution_stats() for dashboards.

Run: python examples/05_infrastructure/01_complete_pipeline.py

See Also:
    03_resilience/04_concurrency_guard — locking details
    03_resilience/05_dead_letter_queue — DLQ details
    02_execution/09_execution_ledger — ledger details
"""

import sqlite3
import time

from spine.core.schema import CORE_DDL
from spine.execution import (
    Execution,
    ExecutionLedger,
    ConcurrencyGuard,
    DLQManager,
    ExecutionRepository,
    ExecutionStatus,
    TriggerSource,
)


def setup_database() -> sqlite3.Connection:
    """Create database with all required tables."""
    conn = sqlite3.connect(":memory:")
    for name, ddl in CORE_DDL.items():
        conn.execute(ddl)
    conn.commit()
    return conn


def run_pipeline(name: str, params: dict, ledger: ExecutionLedger, 
                 guard: ConcurrencyGuard, dlq: DLQManager) -> bool:
    """Run a pipeline with full execution tracking.
    
    Args:
        name: Pipeline identifier
        params: Parameters for the pipeline
        ledger: Execution ledger for tracking
        guard: Concurrency guard for locking
        dlq: Dead letter queue for failures
        
    Returns:
        True if successful, False otherwise
    """
    # Check for idempotency using a key
    idempotency_key = f"{name}:{params.get('date', 'default')}"
    existing = ledger.get_by_idempotency_key(idempotency_key)
    if existing and existing.status == ExecutionStatus.COMPLETED:
        print(f"  ⏭️  Already completed: {idempotency_key}")
        return True
    
    # Create execution object and record
    execution = Execution.create(
        workflow=name,
        params=params,
        trigger_source=TriggerSource.SCHEDULE,
        idempotency_key=idempotency_key,
    )
    ledger.create_execution(execution)
    print(f"  📝 Created execution: {execution.id[:8]}...")
    
    # Try to acquire a lock
    lock_key = f"workflow:{name}"
    acquired = guard.acquire(
        lock_key=lock_key,
        execution_id=execution.id,
        timeout_seconds=300,  # 5 minute lock
    )
    
    if not acquired:
        print(f"  🔒 Could not acquire lock for {name}")
        ledger.update_status(execution.id, ExecutionStatus.CANCELLED)
        return False
    
    print(f"  🔓 Acquired lock: {lock_key}")
    
    try:
        # Mark as running
        ledger.update_status(execution.id, ExecutionStatus.RUNNING)
        
        # Simulate work
        print(f"  ⚙️  Processing {name}...")
        time.sleep(0.2)  # Simulate processing
        
        # Simulate occasional failure
        if params.get("fail", False):
            raise RuntimeError("Simulated failure for testing")
        
        # Mark complete
        ledger.update_status(execution.id, ExecutionStatus.COMPLETED)
        print(f"  ✅ Completed: {execution.id[:8]}...")
        return True
        
    except Exception as e:
        # Mark as failed
        ledger.update_status(
            execution.id, 
            ExecutionStatus.FAILED,
            error=str(e)
        )
        
        # Add to dead letter queue for retry
        dlq_entry = dlq.add_to_dlq(
            execution_id=execution.id,
            workflow=name,
            params=params,
            error=str(e),
        )
        print(f"  ❌ Failed: {e}")
        print(f"  📬 Added to DLQ: {dlq_entry.id[:8]}...")
        return False
        
    finally:
        # Always release the lock
        guard.release(lock_key, execution_id=execution.id)
        print(f"  🔓 Released lock: {lock_key}")


def process_dlq(dlq: DLQManager, ledger: ExecutionLedger, 
                guard: ConcurrencyGuard) -> int:
    """Process items in the dead letter queue.
    
    Returns number of items retried.
    """
    retried = 0
    
    for entry in dlq.list_unresolved():
        if not dlq.can_retry(entry.id):
            print(f"  ⛔ Max retries reached: {entry.workflow}")
            continue
            
        print(f"  🔄 Retrying: {entry.workflow}")
        dlq.mark_retry_attempted(entry.id)
        
        # Try running again (without the fail flag)
        params = entry.params.copy() if entry.params else {}
        params.pop("fail", None)  # Remove fail flag for retry
        
        success = run_pipeline(entry.workflow, params, ledger, guard, dlq)
        
        if success:
            dlq.resolve(entry.id, resolved_by="retry-worker")
            print(f"  ✅ Resolved DLQ entry: {entry.id[:8]}...")
            
        retried += 1
    
    return retried


def print_stats(repo: ExecutionRepository, dlq: DLQManager):
    """Print execution statistics."""
    print("\n📊 Execution Statistics:")
    print("-" * 40)
    
    stats = repo.get_execution_stats(hours=1)
    for status, count in stats.get("status_counts", {}).items():
        print(f"  {status}: {count}")
    
    print(f"\n📬 Dead Letter Queue: {dlq.count_unresolved()} unresolved")


def main():
    """Demonstrate execution infrastructure."""
    print("=" * 60)
    print("Execution Infrastructure Demo")
    print("=" * 60)
    
    # Setup
    conn = setup_database()
    ledger = ExecutionLedger(conn)
    guard = ConcurrencyGuard(conn)
    dlq = DLQManager(conn, max_retries=3)
    repo = ExecutionRepository(conn)
    
    # Run successful pipelines
    print("\n1️⃣  Running successful pipelines...")
    run_pipeline("sec.filings", {"date": "2024-01-01"}, ledger, guard, dlq)
    run_pipeline("sec.filings", {"date": "2024-01-02"}, ledger, guard, dlq)
    run_pipeline("market.prices", {"symbol": "AAPL"}, ledger, guard, dlq)
    
    # Demonstrate idempotency
    print("\n2️⃣  Testing idempotency (re-run same job)...")
    run_pipeline("sec.filings", {"date": "2024-01-01"}, ledger, guard, dlq)
    
    # Run a failing pipeline
    print("\n3️⃣  Running failing pipeline...")
    run_pipeline("failing.job", {"date": "2024-01-01", "fail": True}, ledger, guard, dlq)
    
    # Print stats after initial runs
    print_stats(repo, dlq)
    
    # Process the DLQ
    print("\n4️⃣  Processing Dead Letter Queue...")
    retried = process_dlq(dlq, ledger, guard)
    print(f"  Retried {retried} items")
    
    # Print final stats
    print_stats(repo, dlq)
    
    # Show recent failures
    print("\n5️⃣  Recent failures:")
    print("-" * 40)
    failures = repo.get_recent_failures(hours=1, limit=5)
    for failure in failures:
        print(f"  [{failure['workflow']}] {failure.get('error', 'Unknown error')}")
    
    # Cleanup
    conn.close()
    print("\n✨ Demo complete!")


if __name__ == "__main__":
    main()
