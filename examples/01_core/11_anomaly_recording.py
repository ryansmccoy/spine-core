#!/usr/bin/env python3
"""AnomalyRecorder — Structured Pipeline Anomaly Tracking and Resolution.

================================================================================
WHY ANOMALY RECORDING?
================================================================================

Pipeline anomalies aren't always errors.  They're *unexpected conditions*
that need human attention:

    - Row count dropped 30% from last week — source broken or holiday?
    - Null rate is 35% — above the 25% threshold but maybe a new filing type
    - API returned 429 — transient, but if it happens 10 times, escalate
    - Data arrived 6 hours late — SLA violation, notify stakeholders

Without AnomalyRecorder::

    # Anomalies are lost in log files
    logger.warning("Null rate 35%, threshold 25%")
    # Who saw this?  When was it resolved?  Is it still happening?

With AnomalyRecorder::

    # Anomalies are persisted, queryable, and resolvable
    anomaly_id = recorder.record(
        severity=Severity.ERROR,
        category=AnomalyCategory.QUALITY_GATE,
        message="Null rate 35% exceeds threshold 25%",
    )
    # Later: recorder.resolve(anomaly_id, "Holiday week — expected")


================================================================================
ARCHITECTURE: ANOMALY LIFECYCLE
================================================================================

::

    ┌──────────┐     record()      ┌──────────────┐     resolve()     ┌──────────┐
    │ Detected │───────────────────►│     OPEN     │──────────────────►│ RESOLVED │
    │          │                    │              │                   │          │
    │ Pipeline │                    │ core_anomaly │                   │ With     │
    │ checks   │                    │   table      │                   │ reason   │
    └──────────┘                    └──────┬───────┘                   └──────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │  Dashboard   │
                                    │  Alerting    │
                                    │  Reporting   │
                                    └──────────────┘

    Severity Levels:
    ┌──────────┬───────────────────────────────────────────────────────┐
    │ INFO     │ Noteworthy but not actionable (new filing type seen)  │
    │ WARN     │ Potential issue, monitor (row count dip 15%)          │
    │ ERROR    │ Threshold breached, investigate (null rate 35%)       │
    │ CRITICAL │ Pipeline integrity at risk, page on-call              │
    └──────────┴───────────────────────────────────────────────────────┘


================================================================================
DATABASE: core_anomalies TABLE
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_anomalies                                                  │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  id              VARCHAR(36)  PRIMARY KEY  -- ULID for time-sorting    │
    │  domain          VARCHAR(100) NOT NULL     -- 'finra.otc_transparency' │
    │  stage           VARCHAR(50)  NOT NULL     -- 'ingest', 'normalize'   │
    │  severity        VARCHAR(20)  NOT NULL     -- INFO/WARN/ERROR/CRITICAL│
    │  category        VARCHAR(50)  NOT NULL     -- QUALITY_GATE, NETWORK...│
    │  message         TEXT         NOT NULL     -- Human-readable detail   │
    │  metadata        JSON                      -- Metrics, thresholds     │
    │  partition_key   JSON                      -- {week_ending, tier}     │
    │  detected_at     TIMESTAMP    NOT NULL     -- When anomaly detected   │
    │  resolved_at     TIMESTAMP                 -- NULL = still open       │
    │  resolution_note TEXT                      -- Why it was resolved     │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/11_anomaly_recording.py

See Also:
    - :mod:`spine.core` — AnomalyRecorder, Severity, AnomalyCategory
    - :mod:`spine.core.quality` — Quality checks that trigger anomalies
    - ``examples/01_core/04_reject_handling.py`` — Per-record rejection
"""

import sqlite3
from spine.core import (
    AnomalyRecorder,
    Severity,
    AnomalyCategory,
    create_core_tables,
)


def main():
    """Demonstrate AnomalyRecorder for anomaly tracking."""
    print("=" * 60)
    print("AnomalyRecorder - Pipeline Anomaly Tracking")
    print("=" * 60)
    
    # Create in-memory database with core tables
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    # Create recorder for the "finra.otc" domain
    recorder = AnomalyRecorder(
        conn=conn,
        domain="finra.otc_transparency",
    )
    
    partition_key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
    
    print("\n1. Recording anomalies...")
    
    # Record a quality gate failure
    anomaly_id_1 = recorder.record(
        stage="ingest",
        partition_key=partition_key,
        severity=Severity.ERROR,
        category=AnomalyCategory.QUALITY_GATE,
        message="Null rate 35% exceeds threshold 25%",
        metadata={"null_rate": 0.35, "threshold": 0.25},
    )
    print(f"   ✓ Recorded ERROR: Quality gate failure (ID: {anomaly_id_1})")
    
    # Record a warning
    anomaly_id_2 = recorder.record(
        stage="normalize",
        partition_key=partition_key,
        severity=Severity.WARN,
        category=AnomalyCategory.DATA_QUALITY,
        message="Row count dropped 20% from previous week",
        metadata={"current": 8000, "previous": 10000, "drop_pct": 0.20},
    )
    print(f"   ✓ Recorded WARN: Data quality issue (ID: {anomaly_id_2})")
    
    # Record a transient error
    anomaly_id_3 = recorder.record(
        stage="ingest",
        partition_key=partition_key,
        severity=Severity.ERROR,
        category=AnomalyCategory.NETWORK,
        message="Connection timeout to FINRA API",
        metadata={"endpoint": "https://api.finra.org/data", "timeout_seconds": 30},
    )
    print(f"   ✓ Recorded ERROR: Network error (ID: {anomaly_id_3})")
    
    # Query open anomalies
    print("\n2. Querying open anomalies...")
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, severity, category, message, resolved_at
        FROM core_anomalies
        WHERE domain = 'finra.otc_transparency'
          AND resolved_at IS NULL
        ORDER BY detected_at DESC
    """)
    
    print("   Open anomalies:")
    for row in cursor.fetchall():
        print(f"     [{row[1]}] {row[2]}: {row[3][:40]}...")
    
    # Resolve an anomaly
    print("\n3. Resolving anomalies...")
    
    recorder.resolve(
        anomaly_id=anomaly_id_3,
        resolution_note="Transient network issue resolved on retry",
    )
    print(f"   ✓ Resolved network error anomaly")
    
    # Check remaining open anomalies
    cursor.execute("""
        SELECT COUNT(*) FROM core_anomalies
        WHERE domain = 'finra.otc_transparency'
          AND resolved_at IS NULL
    """)
    open_count = cursor.fetchone()[0]
    print(f"   Remaining open anomalies: {open_count}")
    
    # Severity levels demo
    print("\n4. Severity levels:")
    for sev in Severity:
        print(f"   {sev.name}: {sev.value}")
    
    # Categories demo
    print("\n5. Anomaly categories:")
    for cat in AnomalyCategory:
        print(f"   {cat.name}: {cat.value}")
    
    # Audit trail query
    print("\n6. Full audit trail...")
    
    cursor.execute("""
        SELECT detected_at, severity, category, message, 
               CASE WHEN resolved_at IS NOT NULL THEN 'RESOLVED' ELSE 'OPEN' END as status
        FROM core_anomalies
        WHERE domain = 'finra.otc_transparency'
        ORDER BY detected_at
    """)
    
    for row in cursor.fetchall():
        print(f"   [{row[4]}] {row[1]} {row[2]}: {row[3][:35]}...")
    
    conn.close()
    print("\n" + "=" * 60)
    print("AnomalyRecorder demo complete!")


if __name__ == "__main__":
    main()
