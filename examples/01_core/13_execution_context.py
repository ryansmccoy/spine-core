#!/usr/bin/env python3
"""ExecutionContext — Lineage Tracking and Correlation IDs for Data Pipelines.

================================================================================
WHY EXECUTION CONTEXT?
================================================================================

In distributed data systems, you need to answer questions like:

    - "Which pipeline run produced this row?"
    - "Why is this data different from yesterday?"
    - "Did the 9am run and 10am run overlap?"
    - "Which stage failed for batch XYZ?"

**ExecutionContext** provides the correlation IDs that link:
- Pipeline runs → Data rows
- Parent pipelines → Child pipelines
- Log entries → Database records

Without ExecutionContext::

    # Data appears in the database...
    SELECT * FROM prices WHERE symbol = 'AAPL' AND date = '2024-01-19'
    # → 3 rows with different prices. Which is correct? When did each arrive?
    #   No way to know without execution tracking.

With ExecutionContext::

    SELECT * FROM prices WHERE symbol = 'AAPL' AND date = '2024-01-19'
    # → 3 rows, each with execution_id and batch_id
    #   Row 1: exec_id=abc, batch_id="ingest-2024-01-19-09:00" (initial load)
    #   Row 2: exec_id=def, batch_id="backfill-2024-01-19" (correction)
    #   Row 3: exec_id=ghi, batch_id="manual-fix-123" (ops intervention)


================================================================================
CONTEXT HIERARCHY
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  EXECUTION CONTEXT HIERARCHY                                            │
    └─────────────────────────────────────────────────────────────────────────┘

    batch_id: "ingest-2024-01-19"
    │
    └── execution_id: "abc123"  (parent pipeline)
        │
        ├── execution_id: "def456"  (child: extract stage)
        │   └── parent_execution_id: "abc123"
        │
        ├── execution_id: "ghi789"  (child: transform stage)
        │   └── parent_execution_id: "abc123"
        │
        └── execution_id: "jkl012"  (child: load stage)
            └── parent_execution_id: "abc123"


    batch_id — Groups related pipeline runs
    │          "All runs in the January 19th daily batch"
    │
    └── execution_id — Unique identifier for ONE pipeline run
        │              "This specific invocation of ingest_filings"
        │
        └── parent_execution_id — Links child runs to parent
                                  "This transform was spawned by that ingest"


================================================================================
DATABASE SCHEMA: STORING LINEAGE
================================================================================

Every data table should include execution lineage columns::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: bronze_filings                                                  │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  -- Business columns                                                    │
    │  accession_number  VARCHAR(25)  PRIMARY KEY                             │
    │  cik              VARCHAR(10)   NOT NULL                                │
    │  form_type        VARCHAR(10)   NOT NULL                                │
    │  filing_date      DATE          NOT NULL                                │
    │  raw_content      TEXT                                                  │
    │                                                                         │
    │  -- Lineage columns (from ExecutionContext)                             │
    │  execution_id     VARCHAR(36)   NOT NULL  -- Who created this row      │
    │  batch_id         VARCHAR(64)             -- Which batch run           │
    │  ingested_at      TIMESTAMP     NOT NULL  -- When it was created       │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_executions (system table)                                  │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  execution_id        VARCHAR(36)  PRIMARY KEY                           │
    │  parent_execution_id VARCHAR(36)            -- NULL for root runs      │
    │  batch_id            VARCHAR(64)                                        │
    │  started_at          TIMESTAMP    NOT NULL                              │
    │  completed_at        TIMESTAMP                                          │
    │  status              VARCHAR(20)  NOT NULL  -- pending/running/done    │
    │  pipeline_name       VARCHAR(100) NOT NULL                              │
    │  parameters          JSON                   -- Input params            │
    │  result              JSON                   -- Output summary          │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
LINEAGE QUERIES
================================================================================

Find all data produced by a specific run::

    SELECT * FROM bronze_filings WHERE execution_id = 'abc123'

Find all runs in a batch::

    SELECT * FROM core_executions WHERE batch_id = 'ingest-2024-01-19'

Trace data back to its root pipeline::

    WITH RECURSIVE lineage AS (
        SELECT * FROM core_executions WHERE execution_id = 'child-xyz'
        UNION ALL
        SELECT e.* FROM core_executions e
        JOIN lineage l ON e.execution_id = l.parent_execution_id
    )
    SELECT * FROM lineage ORDER BY started_at


================================================================================
INTEGRATION WITH LOGGING
================================================================================

ExecutionContext should be bound to your logger::

    import structlog

    ctx = new_context(batch_id="ingest-2024-01-19")

    log = structlog.get_logger().bind(
        execution_id=ctx.execution_id,
        batch_id=ctx.batch_id,
    )

    log.info("Starting pipeline")
    # → {"event": "Starting pipeline",
    #    "execution_id": "abc123",
    #    "batch_id": "ingest-2024-01-19"}

This allows you to:
- Search logs by execution_id
- Correlate logs with database rows
- Trace issues across distributed services


================================================================================
BEST PRACTICES
================================================================================

1. **Create context at pipeline entry**::

       def run_daily_ingest():
           ctx = new_context(batch_id=f"daily-{date.today()}")
           extract(ctx)
           transform(ctx)
           load(ctx)

2. **Use child contexts for sub-pipelines**::

       def extract(ctx: ExecutionContext):
           child = ctx.child()  # Links to parent
           fetch_data(child)

3. **Store execution_id with every data row**::

       cursor.execute(
           "INSERT INTO filings (..., execution_id) VALUES (..., ?)",
           [..., ctx.execution_id]
       )

4. **Use batch_id for operational grouping**::

       # All runs in one cron schedule belong to same batch
       batch_id = f"cron-{schedule_time.isoformat()}"

5. **Pass context through function parameters**::

       # GOOD: Explicit context flow
       def process(ctx: ExecutionContext, data: list):
           ...

       # BAD: Global context (hidden dependency)
       def process(data: list):
           ctx = get_global_context()  # Where did this come from?


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/13_execution_context.py

See Also:
    - :mod:`spine.core.context` — ExecutionContext, new_context
    - :mod:`spine.execution.runs` — RunRecord with execution tracking
    - :mod:`spine.execution.ledger` — Execution history persistence
"""
from spine.core import ExecutionContext, new_context, new_batch_id


def main():
    print("=" * 60)
    print("Execution Context Examples")
    print("=" * 60)
    
    # === 1. Create new context ===
    print("\n[1] Create New Context")
    
    ctx = new_context()
    print(f"  Execution ID: {ctx.execution_id[:8]}...")
    print(f"  Batch ID: {ctx.batch_id}")
    print(f"  Started at: {ctx.started_at}")
    
    # === 2. Generate batch IDs ===
    print("\n[2] Generate Batch IDs")
    
    for i in range(3):
        batch_id = new_batch_id()
        print(f"  Batch {i+1}: {batch_id}")
    
    # === 3. Context with custom batch ID ===
    print("\n[3] Context with Custom Batch ID")
    
    custom_batch = "my-pipeline-2024-01-19-001"
    ctx = new_context(batch_id=custom_batch)
    print(f"  Execution ID: {ctx.execution_id[:8]}...")
    print(f"  Batch ID: {ctx.batch_id}")
    
    # === 4. Context attributes ===
    print("\n[4] Context Attributes")
    
    ctx = new_context()
    batched = ctx.with_batch("backfill_20240119")
    child = ctx.child()
    
    print(f"  Execution ID: {ctx.execution_id[:8]}...")
    print(f"  Batch ID (original): {ctx.batch_id}")
    print(f"  Batch ID (with_batch): {batched.batch_id}")
    print(f"  Child execution ID: {child.execution_id[:8]}...")
    print(f"  Child parent ID: {child.parent_execution_id[:8]}...")
    print(f"  Parent matches: {child.parent_execution_id == ctx.execution_id}")
    
    # === 5. Real-world: Pipeline with context ===
    print("\n[5] Real-world: Pipeline with Context")
    
    def extract(ctx: ExecutionContext) -> list:
        """Extract stage - fetch data."""
        print(f"    [Extract] exec_id={ctx.execution_id[:8]}...")
        return [{"symbol": "AAPL", "price": 150.0}]
    
    def transform(ctx: ExecutionContext, data: list) -> list:
        """Transform stage - process data."""
        print(f"    [Transform] exec_id={ctx.execution_id[:8]}...")
        return [{"symbol": d["symbol"], "price": d["price"], "batch_id": ctx.batch_id} for d in data]
    
    def load(ctx: ExecutionContext, data: list) -> int:
        """Load stage - persist data."""
        print(f"    [Load] exec_id={ctx.execution_id[:8]}...")
        return len(data)
    
    # Run pipeline
    batch_id = new_batch_id("etl")
    ctx = new_context(batch_id=batch_id)
    print(f"  Starting pipeline with batch_id={ctx.batch_id[:20]}...")
    
    raw = extract(ctx)
    transformed = transform(ctx, raw)
    count = load(ctx, transformed)
    
    print(f"  Pipeline complete: {count} records processed")
    
    # === 6. Context for logging ===
    print("\n[6] Context for Logging")
    
    ctx = new_context(batch_id=new_batch_id("logging"))
    
    # Use context fields in log messages
    log_fields = {
        "execution_id": ctx.execution_id,
        "batch_id": ctx.batch_id,
        "started_at": ctx.started_at.isoformat(),
    }
    print(f"  Log context: {log_fields}")
    
    print("\n" + "=" * 60)
    print("[OK] Execution Context Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
