#!/usr/bin/env python3
"""ExecutionLedger — Persistent Execution Audit Trail with Full Lifecycle.

================================================================================
WHY AN EXECUTION LEDGER?
================================================================================

The ExecutionLedger provides an **append-only audit trail** of all pipeline
executions.  Unlike RunRecord (which tracks individual tasks), the ledger
tracks **high-level executions** — a workflow run comprising many tasks::

    execution = Execution(
        pipeline_name="daily_ingest",
        trigger_source=TriggerSource.SCHEDULE,
        status=ExecutionStatus.RUNNING,
    )
    ledger.create(execution)
    # ... tasks run ...
    ledger.complete(execution.id, ExecutionStatus.COMPLETED)

Key capabilities:
    - **Create/Update/Query** executions by ID, status, pipeline, time
    - **Lifecycle tracking** — PENDING → RUNNING → COMPLETED/FAILED
    - **Duration recording** — started_at, completed_at, duration_sec
    - **Trigger provenance** — SCHEDULE, MANUAL, WEBHOOK, BACKFILL


================================================================================
DATABASE: core_executions TABLE
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_executions                                                 │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  id              VARCHAR(36)  PRIMARY KEY  -- ULID                     │
    │  pipeline_name   VARCHAR(255) NOT NULL     -- "daily_ingest"           │
    │  status          VARCHAR(20)  NOT NULL     -- ExecutionStatus enum     │
    │  trigger_source  VARCHAR(20)               -- SCHEDULE/MANUAL/WEBHOOK │
    │  event_type      VARCHAR(20)               -- EventType enum          │
    │  started_at      TIMESTAMP                 -- When execution began    │
    │  completed_at    TIMESTAMP                 -- When it finished        │
    │  duration_sec    REAL                      -- Total elapsed time      │
    │  result          JSON                      -- Output on success       │
    │  error           TEXT                      -- Error on failure        │
    │  metadata        JSON                      -- Arbitrary context       │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/09_execution_ledger.py

See Also:
    - :mod:`spine.execution` — ExecutionLedger, Execution, ExecutionStatus
    - ``examples/02_execution/10_execution_repository.py`` — Analytics queries
    - ``examples/02_execution/13_tracked_execution.py`` — Context manager usage
"""

import sqlite3
from datetime import datetime, timezone

from spine.core.schema import create_core_tables
from spine.execution import (
    ExecutionLedger,
    Execution,
    ExecutionStatus,
    EventType,
    TriggerSource,
)


def main():
    """Demonstrate ExecutionLedger for tracking executions."""
    print("=" * 60)
    print("ExecutionLedger - Persistent Execution Records")
    print("=" * 60)
    
    # Create in-memory database
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    # Create ledger
    ledger = ExecutionLedger(conn)
    
    print("\n1. Creating an execution...")
    
    # Create a new execution
    execution = Execution.create(
        workflow="finra.otc.ingest",
        params={"week_ending": "2025-12-26", "tier": "NMS_TIER_1"},
        trigger_source=TriggerSource.API,
    )
    
    ledger.create_execution(execution)
    print(f"   ✓ Created execution: {execution.id[:8]}...")
    print(f"   Workflow: {execution.workflow}")
    print(f"   Status: {execution.status.value}")
    
    # Retrieve execution
    print("\n2. Retrieving execution...")
    
    retrieved = ledger.get_execution(execution.id)
    print(f"   ✓ Retrieved: {retrieved.id[:8]}...")
    print(f"   Status: {retrieved.status.value}")
    
    # Update status to running
    print("\n3. Starting execution...")
    
    ledger.update_status(execution.id, ExecutionStatus.RUNNING)
    ledger.record_event(execution.id, EventType.STARTED)
    
    updated = ledger.get_execution(execution.id)
    print(f"   Status: {updated.status.value}")
    
    # Complete execution
    print("\n4. Completing execution...")
    
    result = {"rows_processed": 1000, "duration_seconds": 45.2}
    ledger.update_status(
        execution.id,
        ExecutionStatus.COMPLETED,
        result=result,
    )
    ledger.record_event(
        execution.id,
        EventType.COMPLETED,
        data=result,
    )
    
    completed = ledger.get_execution(execution.id)
    print(f"   Status: {completed.status.value}")
    print(f"   Result: {completed.result}")
    
    # Create a failed execution
    print("\n5. Recording a failed execution...")
    
    failed_exec = Execution.create(
        workflow="finra.otc.normalize",
        params={"week_ending": "2025-12-26"},
    )
    ledger.create_execution(failed_exec)
    ledger.update_status(failed_exec.id, ExecutionStatus.RUNNING)
    ledger.update_status(
        failed_exec.id,
        ExecutionStatus.FAILED,
        error="Connection timeout to database",
    )
    
    failed = ledger.get_execution(failed_exec.id)
    print(f"   Status: {failed.status.value}")
    print(f"   Error: {failed.error}")
    
    # List executions
    print("\n6. Listing recent executions...")
    
    recent = ledger.list_executions(limit=10)
    for exec in recent:
        print(f"   [{exec.status.value}] {exec.workflow} ({exec.id[:8]}...)")
    
    # Idempotency key lookup
    print("\n7. Idempotency key lookup...")
    
    idem_exec = Execution.create(
        workflow="finra.otc.aggregate",
        params={"week_ending": "2025-12-26"},
        idempotency_key="agg-2025-12-26-NMS_TIER_1",
    )
    ledger.create_execution(idem_exec)
    
    found = ledger.get_by_idempotency_key("agg-2025-12-26-NMS_TIER_1")
    print(f"   Found by idempotency key: {found.id[:8]}...")
    print(f"   Workflow: {found.workflow}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("ExecutionLedger demo complete!")


if __name__ == "__main__":
    main()
