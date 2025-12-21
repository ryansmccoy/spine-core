#!/usr/bin/env python3
"""ExecutionHealthChecker — System Health Monitoring for Operation Infrastructure.

================================================================================
WHY HEALTH CHECKS?
================================================================================

Operation infrastructure needs continuous health monitoring beyond
"is the process alive?"::

    Kubernetes liveness:  "Is the container running?"  (basic)
    Execution health:     "Are operations actually succeeding?" (what matters)

ExecutionHealthChecker answers operational questions:
    - "Are there stale executions stuck in RUNNING?"
    - "Is the dead letter queue growing?"
    - "What's the failure rate in the last hour?"
    - "Are we meeting our SLA for execution latency?"


================================================================================
HEALTH STATUS MODEL
================================================================================

::

    ┌─────────────┬─────────────────────────────────────────────────────────┐
    │ HEALTHY     │ All metrics within thresholds                          │
    │ DEGRADED    │ Warning thresholds breached, needs monitoring          │
    │ UNHEALTHY   │ Critical thresholds breached, needs intervention       │
    └─────────────┴─────────────────────────────────────────────────────────┘

    HealthThresholds:
    ┌─────────────────────────┬──────────┬──────────────────────────────────┐
    │ Metric                  │ Default  │ Why                               │
    ├─────────────────────────┼──────────┼──────────────────────────────────┤
    │ max_stale_minutes       │ 60       │ RUNNING > 1h = stuck             │
    │ max_dlq_depth           │ 100      │ Unprocessed failures growing     │
    │ max_failure_rate_pct    │ 10       │ > 10% failure = systemic issue   │
    │ max_pending_count       │ 500      │ Queue backing up                 │
    └─────────────────────────┴──────────┴──────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/12_health_checks.py

See Also:
    - :mod:`spine.execution` — ExecutionHealthChecker, HealthStatus
    - :mod:`spine.core.health` — Health router for API endpoints
    - ``examples/02_execution/10_execution_repository.py`` — Analytics queries
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from spine.core.schema import create_core_tables
from spine.execution import (
    ExecutionLedger,
    ExecutionRepository,
    ExecutionHealthChecker,
    HealthStatus,
    HealthThresholds,
    HealthReport,
    Execution,
    ExecutionStatus,
    ConcurrencyGuard,
    DLQManager,
)


def main():
    """Demonstrate ExecutionHealthChecker for monitoring."""
    print("=" * 60)
    print("ExecutionHealthChecker - System Health Monitoring")
    print("=" * 60)
    
    # Create in-memory database
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    # Create components
    ledger = ExecutionLedger(conn)
    repo = ExecutionRepository(conn)
    dlq = DLQManager(conn)
    guard = ConcurrencyGuard(conn)
    
    # Create health checker with custom thresholds
    thresholds = HealthThresholds(
        dlq_warning_count=5,
        dlq_critical_count=10,
        stale_warning_minutes=30,
        stale_critical_minutes=60,
        failure_rate_warning=10.0,
        failure_rate_critical=25.0,
    )
    
    checker = ExecutionHealthChecker(
        ledger=ledger,
        dlq=dlq,
        guard=guard,
        repo=repo,
        thresholds=thresholds,
    )
    
    print("\n1. Initial health check (empty system)...")
    
    report = checker.check()
    print(f"   Overall status: {report.status.value}")
    print(f"   Healthy: {report.healthy}")
    
    # Add some executions
    print("\n2. Creating sample executions...")
    
    for i in range(10):
        exec = Execution.create(
            workflow=f"operation.test.{i % 3}",
            params={"batch": i},
        )
        ledger.create_execution(exec)
        
        # Complete most, fail some
        if i % 4 == 0:
            ledger.update_status(exec.id, ExecutionStatus.FAILED, error="Test failure")
        else:
            ledger.update_status(exec.id, ExecutionStatus.COMPLETED, result={"ok": True})
    
    print(f"   ✓ Created 10 executions (2 failed, 8 completed)")
    
    # Add DLQ entries
    print("\n3. Adding DLQ entries...")
    
    for i in range(3):
        dlq.add_to_dlq(
            execution_id=f"exec-{i}",
            workflow=f"operation.failed.{i}",
            params={"batch": i},
            error=f"Error message {i}",
        )
    
    print(f"   ✓ Added 3 DLQ entries")
    
    # Run health check
    print("\n4. Running health check...")
    
    report = checker.check()
    
    print(f"\n   Overall Status: {report.status.value.upper()}")
    print(f"   Timestamp: {report.timestamp.isoformat()}")
    print(f"\n   Individual checks:")
    
    for check in report.checks:
        icon = "✓" if check.status == HealthStatus.HEALTHY else "⚠" if check.status == HealthStatus.DEGRADED else "✗"
        print(f"     {icon} {check.name}: {check.status.value}")
        print(f"       {check.message}")
        if check.details:
            for k, v in check.details.items():
                print(f"         {k}: {v}")
    
    # Serialize to dict (for API responses)
    print("\n5. Serialized health report...")
    
    report_dict = report.to_dict()
    print(f"   Status: {report_dict['status']}")
    print(f"   Checks: {len(report_dict['checks'])}")
    
    # Health status levels
    print("\n6. Health status levels:")
    for status in HealthStatus:
        print(f"   {status.value}")
    
    # Threshold configuration
    print("\n7. Configurable thresholds:")
    print(f"   DLQ warning: {thresholds.dlq_warning_count}")
    print(f"   DLQ critical: {thresholds.dlq_critical_count}")
    print(f"   Stale warning: {thresholds.stale_warning_minutes} min")
    print(f"   Failure rate warning: {thresholds.failure_rate_warning}%")
    
    conn.close()
    print("\n" + "=" * 60)
    print("ExecutionHealthChecker demo complete!")


if __name__ == "__main__":
    main()
