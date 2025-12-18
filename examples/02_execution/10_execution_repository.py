#!/usr/bin/env python3
"""ExecutionRepository — Analytics and Maintenance Queries for Executions.

================================================================================
WHY AN EXECUTION REPOSITORY?
================================================================================

While ExecutionLedger handles CRUD, the ExecutionRepository provides
**operational analytics** — the queries ops teams actually need::

    "How many runs failed in the last 24 hours?"
    "Which pipelines have stuck executions?"
    "What's the average duration for 'daily_ingest'?"
    "Find all runs that started but never completed."

These queries enable:
    - **Dashboards** — Real-time execution health metrics
    - **Alerting** — "5+ failures in the last hour" triggers PagerDuty
    - **Debugging** — Find the run that produced bad data
    - **Capacity planning** — Average duration trending up? Need more workers


================================================================================
KEY QUERIES
================================================================================

::

    ┌─────────────────────────────────────┬────────────────────────────────────┐
    │ Query                               │ Use Case                          │
    ├─────────────────────────────────────┼────────────────────────────────────┤
    │ find_stuck(threshold_minutes=60)    │ Zombie detection — runs stuck     │
    │                                     │ in RUNNING > 1 hour              │
    │ find_by_status(FAILED)              │ Failure investigation             │
    │ compute_stats(pipeline_name)        │ Duration avg, success rate, count│
    │ find_recent(limit=20)              │ Dashboard "last N runs" view     │
    │ count_by_status()                   │ Aggregate health: 5 RUNNING,     │
    │                                     │ 12 COMPLETED, 1 FAILED           │
    │ purge_old(days=90)                  │ Data retention — remove old runs │
    └─────────────────────────────────────┴────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/10_execution_repository.py

See Also:
    - :mod:`spine.execution` — ExecutionRepository
    - ``examples/02_execution/09_execution_ledger.py`` — Ledger CRUD
    - ``examples/02_execution/12_health_checks.py`` — Health monitoring
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from spine.core.schema import create_core_tables
from spine.execution import (
    ExecutionLedger,
    ExecutionRepository,
    Execution,
    ExecutionStatus,
)


def main():
    """Demonstrate ExecutionRepository for analytics queries."""
    print("=" * 60)
    print("ExecutionRepository - Analytics & Maintenance")
    print("=" * 60)
    
    # Create in-memory database
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    ledger = ExecutionLedger(conn)
    repo = ExecutionRepository(conn)
    
    # Create sample executions
    print("\n1. Creating sample executions...")
    
    pipelines = [
        ("finra.otc.ingest", ExecutionStatus.COMPLETED),
        ("finra.otc.ingest", ExecutionStatus.COMPLETED),
        ("finra.otc.ingest", ExecutionStatus.FAILED),
        ("finra.otc.normalize", ExecutionStatus.COMPLETED),
        ("finra.otc.normalize", ExecutionStatus.COMPLETED),
        ("finra.otc.aggregate", ExecutionStatus.RUNNING),  # Stale
        ("sec.filings.ingest", ExecutionStatus.COMPLETED),
        ("sec.filings.ingest", ExecutionStatus.FAILED),
    ]
    
    for i, (pipeline, status) in enumerate(pipelines):
        exec = Execution.create(workflow=pipeline, params={"batch": i})
        ledger.create_execution(exec)
        
        if status in (ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
            ledger.update_status(exec.id, ExecutionStatus.RUNNING)
            
            # Simulate timing
            if status == ExecutionStatus.RUNNING:
                # Make it look stale (started 2 hours ago)
                cursor = conn.cursor()
                stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
                cursor.execute(
                    "UPDATE core_executions SET started_at = ? WHERE id = ?",
                    (stale_time, exec.id)
                )
                conn.commit()
            else:
                # Complete or fail
                result = {"rows": 100} if status == ExecutionStatus.COMPLETED else None
                error = "Test error" if status == ExecutionStatus.FAILED else None
                ledger.update_status(exec.id, status, result=result, error=error)
    
    print(f"   ✓ Created {len(pipelines)} executions")
    
    # Get execution stats
    print("\n2. Execution statistics (last 24 hours)...")
    
    stats = repo.get_execution_stats(hours=24)
    
    print("   Status counts:")
    for status, count in stats.get("status_counts", {}).items():
        print(f"     {status}: {count}")
    
    print("\n   Pipeline counts:")
    for pipeline, count in stats.get("pipeline_counts", {}).items():
        print(f"     {pipeline}: {count}")
    
    # Find stale executions
    print("\n3. Finding stale executions...")
    
    stale = repo.get_stale_executions(older_than_minutes=60)
    
    if stale:
        print(f"   Found {len(stale)} stale execution(s):")
        for s in stale:
            print(f"     {s['workflow']} ({s['id'][:8]}...) - started {s['started_at']}")
    else:
        print("   No stale executions found")
    
    # Failure rate analysis
    print("\n4. Failure rate by pipeline...")
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT workflow,
               COUNT(*) as total,
               SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM core_executions
        GROUP BY workflow
    """)
    
    for row in cursor.fetchall():
        workflow, total, failed = row
        rate = (failed / total * 100) if total > 0 else 0
        print(f"   {workflow}: {failed}/{total} failed ({rate:.1f}%)")
    
    # Recent failures
    print("\n5. Recent failures...")
    
    cursor.execute("""
        SELECT workflow, error, created_at
        FROM core_executions
        WHERE status = 'failed'
        ORDER BY created_at DESC
        LIMIT 5
    """)
    
    for row in cursor.fetchall():
        print(f"   [{row[2][:19]}] {row[0]}: {row[1]}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("ExecutionRepository demo complete!")


if __name__ == "__main__":
    main()
