#!/usr/bin/env python3
"""RejectSink — Capturing Validation Failures Without Stopping Pipelines.

================================================================================
WHY REJECT HANDLING?
================================================================================

Data pipelines must handle invalid records gracefully.  The naive approach
fails in production::

    # BAD: One bad record kills the entire batch
    for record in records:
        validate(record)  # Raises on row 47 → 9,953 records never processed

    # BAD: Silently skip
    for record in records:
        if not valid(record):
            continue  # Lost forever — no audit trail, no way to fix

    # GOOD: RejectSink — capture, continue, audit
    for record in records:
        if not valid(record):
            reject_sink.write(Reject(
                stage="NORMALIZE",
                reason_code="INVALID_SYMBOL",
                reason_detail=f"Bad symbol: {record['symbol']}",
                raw_data=record,
            ))
            continue  # Process remaining records


================================================================================
ARCHITECTURE: REJECT FLOW
================================================================================

::

    ┌──────────┐                 ┌──────────┐
    │  Source   │────────────────►│  Ingest  │
    │  (EDGAR)  │  10,000 rows   │  Stage   │
    └──────────┘                 └─────┬────┘
                                       │
                          ┌────────────┼────────────┐
                          │ valid      │            │ invalid
                          ▼            │            ▼
                   ┌──────────┐        │     ┌──────────────┐
                   │Normalize │        │     │  RejectSink  │
                   │  Stage   │        │     │              │
                   └─────┬────┘        │     │ core_rejects │
                         │             │     │    table     │
                         ▼             │     └──────┬───────┘
                   ┌──────────┐        │            │
                   │   Load   │        │            ▼
                   │  Stage   │        │     ┌──────────────┐
                   └──────────┘        │     │   Alerting   │
                                       │     │  Dashboard   │
                                       │     │  Reprocess   │
                                       │     └──────────────┘


================================================================================
DATABASE: core_rejects TABLE
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_rejects                                                    │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  id              SERIAL       PRIMARY KEY                               │
    │  domain          VARCHAR(100) NOT NULL    -- 'otc', 'sec', 'finra'     │
    │  execution_id    VARCHAR(64)              -- Links to pipeline run     │
    │  stage           VARCHAR(50)  NOT NULL    -- 'INGEST', 'NORMALIZE'     │
    │  reason_code     VARCHAR(100) NOT NULL    -- 'INVALID_SYMBOL', etc.    │
    │  reason_detail   TEXT                     -- Human description         │
    │  raw_data        JSON                     -- Original record           │
    │  partition_key   JSON                     -- {week_ending, tier}       │
    │  created_at      TIMESTAMP    NOT NULL    -- When rejected             │
    └─────────────────────────────────────────────────────────────────────────┘

    Key Queries:
    - "How many rejects per reason this week?"  → GROUP BY reason_code
    - "Show me all rejects for AAPL"            → JSON search on raw_data
    - "Which execution had the most rejects?"   → GROUP BY execution_id


================================================================================
BEST PRACTICES
================================================================================

1. **Always preserve raw_data** — You'll need it for reprocessing::

       Reject(raw_data=original_record)  # Keep the evidence

2. **Use specific reason_codes** — Not just "INVALID"::

       "INVALID_SYMBOL"    not "INVALID"
       "NEGATIVE_VOLUME"   not "BAD_DATA"
       "NULL_FIELD:mpid"   not "MISSING"

3. **Include partition_key** — So you can reprocess specific batches::

       reject_sink.write(reject, partition_key={"week_ending": "2025-12-26"})

4. **Set alerts on reject rate** — 5% rejects is normal, 35% is a source problem


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/04_reject_handling.py

See Also:
    - :mod:`spine.core` — RejectSink, Reject
    - :mod:`spine.core.quality` — Quality checks that feed RejectSink
    - ``examples/01_core/09_quality_checks.py`` — Quality validation framework
"""

import sqlite3
from spine.core import RejectSink, Reject, create_core_tables


def main():
    """Demonstrate RejectSink for validation failures."""
    print("=" * 60)
    print("RejectSink - Validation Failure Handling")
    print("=" * 60)
    
    # Create in-memory database with core tables
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    # Create reject sink for the "otc" domain
    sink = RejectSink(
        conn=conn,
        domain="otc",
        execution_id="exec-12345",
    )
    
    partition_key = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
    
    print("\n1. Writing individual rejects...")
    
    # Reject 1: Invalid symbol
    sink.write(
        Reject(
            stage="NORMALIZE",
            reason_code="INVALID_SYMBOL",
            reason_detail="Symbol 'BAD$YM' contains invalid character '$'",
            raw_data={"symbol": "BAD$YM", "volume": 1000},
        ),
        partition_key=partition_key,
    )
    print("   ✓ Wrote reject: INVALID_SYMBOL")
    
    # Reject 2: Negative volume
    sink.write(
        Reject(
            stage="NORMALIZE",
            reason_code="NEGATIVE_VOLUME",
            reason_detail="Volume cannot be negative: -500",
            raw_data={"symbol": "AAPL", "volume": -500},
        ),
        partition_key=partition_key,
    )
    print("   ✓ Wrote reject: NEGATIVE_VOLUME")
    
    print(f"\n   Total rejects written: {sink.count}")
    
    # Batch rejects
    print("\n2. Writing batch rejects...")
    
    batch_rejects = [
        Reject(
            stage="INGEST",
            reason_code="NULL_FIELD",
            reason_detail="Required field 'mpid' is null",
            raw_data={"symbol": "MSFT", "mpid": None},
        ),
        Reject(
            stage="INGEST",
            reason_code="DATE_PARSE_ERROR",
            reason_detail="Invalid date format: '2025-13-45'",
            raw_data={"date": "2025-13-45", "symbol": "GOOG"},
        ),
        Reject(
            stage="INGEST",
            reason_code="DUPLICATE_RECORD",
            reason_detail="Duplicate key: AAPL-NITE-2025-12-26",
            raw_data={"symbol": "AAPL", "mpid": "NITE"},
        ),
    ]
    
    count = sink.write_batch(batch_rejects, partition_key=partition_key)
    print(f"   ✓ Wrote {count} batch rejects")
    print(f"   Total rejects written: {sink.count}")
    
    # Query rejects
    print("\n3. Querying rejects from database...")
    
    cursor = conn.cursor()
    cursor.execute("""
        SELECT stage, reason_code, reason_detail
        FROM core_rejects
        WHERE domain = 'otc'
        ORDER BY created_at
    """)
    
    for row in cursor.fetchall():
        print(f"   [{row[0]}] {row[1]}: {row[2][:50]}...")
    
    # Analyze reject patterns
    print("\n4. Analyzing reject patterns...")
    
    cursor.execute("""
        SELECT reason_code, COUNT(*) as count
        FROM core_rejects
        WHERE domain = 'otc'
        GROUP BY reason_code
        ORDER BY count DESC
    """)
    
    print("   Reject counts by reason:")
    for row in cursor.fetchall():
        print(f"     {row[0]}: {row[1]}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("RejectSink demo complete!")


if __name__ == "__main__":
    main()
