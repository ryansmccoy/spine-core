#!/usr/bin/env python3
"""TrackedExecution — Context Manager for Automatic Execution Recording.

================================================================================
WHY TRACKED EXECUTION?
================================================================================

Manual execution tracking is error-prone::

    execution = ledger.create(Execution(name="daily_ingest", ...))
    try:
        result = run_operation()
        ledger.complete(execution.id, "COMPLETED", result)  # Easy to forget
    except Exception as e:
        ledger.complete(execution.id, "FAILED", error=str(e))  # Easy to forget
    finally:
        guard.release_lock(lock_id)  # Easy to forget

TrackedExecution wraps this in a context manager::

    with TrackedExecution(ledger, "daily_ingest", guard=guard) as ctx:
        result = run_operation()
        ctx.set_result(result)
    # Automatically: creates execution, acquires lock, records result/failure,
    # releases lock, computes duration — even if an exception occurs


================================================================================
WHAT IT AUTOMATES
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  TrackedExecution context manager handles:                              │
    │                                                                         │
    │  __enter__()                                                           │
    │    1. Create Execution record in ledger (status=RUNNING)               │
    │    2. Acquire concurrency lock (if guard provided)                     │
    │    3. Record started_at timestamp                                      │
    │                                                                         │
    │  __exit__(normal)                                                      │
    │    1. Update execution to COMPLETED                                    │
    │    2. Record result, completed_at, duration_sec                        │
    │    3. Release concurrency lock                                         │
    │                                                                         │
    │  __exit__(exception)                                                   │
    │    1. Update execution to FAILED                                       │
    │    2. Record error message and type                                    │
    │    3. Send to DLQ (if dlq_manager provided)                            │
    │    4. Release concurrency lock                                         │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/13_tracked_execution.py

See Also:
    - :mod:`spine.execution` — TrackedExecution context manager
    - ``examples/02_execution/09_execution_ledger.py`` — Manual ledger usage
    - ``examples/03_resilience/04_concurrency_guard.py`` — Lock management
"""

import sqlite3
from datetime import datetime, timezone

from spine.core.schema import create_core_tables
from spine.execution import (
    ExecutionLedger,
    ConcurrencyGuard,
    DLQManager,
    ExecutionStatus,
    TriggerSource,
)
from spine.execution.context import (
    TrackedExecution,
    ExecutionContext,
    tracked_execution,
    ExecutionLockError,
)


def main():
    """Demonstrate TrackedExecution context manager."""
    print("=" * 60)
    print("TrackedExecution - Automatic Execution Tracking")
    print("=" * 60)
    
    # Create in-memory database
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    # Create components
    ledger = ExecutionLedger(conn)
    guard = ConcurrencyGuard(conn)
    dlq = DLQManager(conn)
    
    print("\n1. Basic tracked execution...")
    
    # Use context manager for automatic tracking
    with tracked_execution(
        ledger=ledger,
        guard=guard,
        dlq=dlq,
        workflow="finra.otc.ingest",
        params={"week_ending": "2025-12-26", "tier": "NMS_TIER_1"},
        trigger_source=TriggerSource.API,
    ) as ctx:
        print(f"   Execution ID: {ctx.id[:8]}...")
        print(f"   Workflow: {ctx.workflow}")
        print(f"   Params: {ctx.params}")
        
        # Simulate work
        rows_processed = 1000
        
        # Set result
        ctx.set_result({"rows_processed": rows_processed})
        print(f"   ✓ Processed {rows_processed} rows")
    
    # Check execution was recorded
    exec = ledger.get_execution(ctx.id)
    print(f"   Final status: {exec.status.value}")
    
    print("\n2. Execution with failure (auto DLQ)...")
    
    try:
        with tracked_execution(
            ledger=ledger,
            guard=guard,
            dlq=dlq,
        workflow="finra.otc.normalize",
        params={"week_ending": "2025-12-26"},
        add_to_dlq_on_failure=True,
        ) as ctx:
            print(f"   Execution ID: {ctx.id[:8]}...")
            
            # Simulate failure
            raise ValueError("Simulated database error")
            
    except ValueError:
        print("   ✗ Execution failed (exception propagated)")
    
    # Check DLQ
    dlq_count = dlq.count_unresolved()
    print(f"   DLQ entries: {dlq_count}")
    
    print("\n3. Idempotent execution...")
    
    idem_key = "ingest-2025-12-26-NMS_TIER_1"
    
    # First run
    with tracked_execution(
        ledger=ledger,
        guard=guard,
        dlq=dlq,
        workflow="finra.otc.aggregate",
        params={"week": "2025-12-26"},
        idempotency_key=idem_key,
    ) as ctx:
        ctx.set_result({"aggregated": True})
        print(f"   First run: {ctx.id[:8]}...")
    
    # Second run with same idempotency key (should skip)
    with tracked_execution(
        ledger=ledger,
        guard=guard,
        dlq=dlq,
        workflow="finra.otc.aggregate",
        params={"week": "2025-12-26"},
        idempotency_key=idem_key,
        skip_if_completed=True,
    ) as ctx:
        print(f"   Second run: {ctx.id[:8]}... (reused existing)")
    
    print("\n4. Progress logging...")
    
    with tracked_execution(
        ledger=ledger,
        guard=None,  # No locking for this example
        dlq=None,
        workflow="finra.otc.publish",
        params={"week": "2025-12-26"},
    ) as ctx:
        # Log progress events
        ctx.log_progress("Starting data fetch", batch_size=100)
        ctx.log_progress("Processing records", processed=50)
        ctx.log_progress("Finalizing", remaining=10)
        
        ctx.set_result({"published": True})
        print(f"   ✓ Logged progress events")
    
    print("\n5. Metadata tracking...")
    
    with tracked_execution(
        ledger=ledger,
        guard=None,
        dlq=None,
        workflow="finra.otc.validate",
        params={"week": "2025-12-26"},
    ) as ctx:
        # Set custom metadata
        ctx.set_metadata("source_file", "data/otc_2025_12_26.csv")
        ctx.set_metadata("row_count", 1000)
        ctx.set_metadata("validation_rules", ["null_check", "range_check"])
        
        ctx.set_result({"valid": True})
        print(f"   ✓ Set custom metadata")
    
    # Summary
    print("\n6. Execution summary...")
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT status, COUNT(*) FROM core_executions GROUP BY status
    """)
    
    for row in cursor.fetchall():
        print(f"   {row[0]}: {row[1]}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("TrackedExecution demo complete!")


if __name__ == "__main__":
    main()
