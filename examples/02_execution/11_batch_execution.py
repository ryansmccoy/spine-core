#!/usr/bin/env python3
"""BatchExecutor — Coordinated Multi-Operation Execution with Progress Tracking.

================================================================================
WHY BATCH EXECUTION?
================================================================================

Data platforms often need to run multiple operations as a **coordinated unit**::

    # "Ingest all 5 data sources, then run analytics"
    batch = BatchBuilder()
    batch.add("ingest_10k", params={"filing_type": "10-K"})
    batch.add("ingest_10q", params={"filing_type": "10-Q"})
    batch.add("ingest_8k",  params={"filing_type": "8-K"})
    batch.add("fetch_prices", params={"date": "2025-01-15"})
    batch.add("fetch_fundamentals")

    result = executor.run(batch)
    # result.total=5, result.succeeded=4, result.failed=1

Without BatchExecutor, you'd need to manage:
    - Parallel execution and thread safety
    - Progress reporting across items
    - Aggregate success/failure counting
    - Timeout enforcement across the batch


================================================================================
ARCHITECTURE: BATCH EXECUTION FLOW
================================================================================

::

    ┌─────────────┐     ┌───────────────────────────────────────────────┐
    │BatchBuilder │────►│              BatchExecutor                    │
    │ .add()      │     │                                              │
    │ .add()      │     │  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
    │ .add()      │     │  │ Item 1  │  │ Item 2  │  │ Item 3  │     │
    └─────────────┘     │  │ RUNNING │  │ PENDING │  │ PENDING │     │
                        │  └────┬────┘  └─────────┘  └─────────┘     │
                        │       │                                      │
                        │       ▼                                      │
                        │  BatchResult                                │
                        │  total=3, succeeded=2, failed=1             │
                        │  duration_sec=12.5                          │
                        │  items: [BatchItemResult, ...]              │
                        └──────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/11_batch_execution.py

See Also:
    - :mod:`spine.execution` — BatchBuilder, BatchExecutor, BatchResult
    - ``examples/02_execution/16_async_batch_executor.py`` — Async batch version
"""

import sqlite3
import time
from datetime import datetime, timezone

from spine.core.schema import create_core_tables
from spine.execution import (
    BatchBuilder,
    BatchExecutor,
    BatchItem,
    BatchResult,
    ExecutionLedger,
    ExecutionStatus,
)


def main():
    """Demonstrate BatchExecutor for coordinated execution."""
    print("=" * 60)
    print("BatchExecutor - Coordinated Batch Execution")
    print("=" * 60)
    
    # Create in-memory database
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    ledger = ExecutionLedger(conn)
    
    print("\n1. Building a batch with BatchBuilder...")
    
    # Define operation handlers
    def ingest_handler(params: dict) -> dict:
        """Simulate ingestion work."""
        time.sleep(0.05)
        tier = params.get("tier", "unknown")
        
        # Simulate a failure for one tier
        if tier == "OTC_TIER_1":
            raise ValueError(f"Simulated failure for {tier}")
        
        return {"rows_processed": 1000, "tier": tier}
    
    def generic_handler(params: dict) -> dict:
        """Generic operation handler."""
        time.sleep(0.05)
        return {"rows_processed": 500, "params": params}
    
    # Use BatchBuilder to construct and execute a batch
    result = (
        BatchBuilder(ledger)
        .add("finra.otc.ingest", {"week": "2025-12-26", "tier": "NMS_TIER_1"})
        .add("finra.otc.ingest", {"week": "2025-12-26", "tier": "NMS_TIER_2"})
        .add("finra.otc.ingest", {"week": "2025-12-26", "tier": "OTC_TIER_1"})
        .add("sec.filings.ingest", {"date": "2025-12-26"})
        .add("market.prices.ingest", {"symbol": "AAPL"})
        .handler("finra.otc.ingest", ingest_handler)
        .handler("sec.filings.ingest", generic_handler)
        .handler("market.prices.ingest", generic_handler)
        .sequential()
        .run()
    )
    
    print(f"   Batch ID: {result.batch_id[:8]}...")
    print(f"   Items: {result.total}")
    
    # Show individual results
    print("\n2. Individual results...")
    for item in result.items:
        status_icon = "✓" if item.status == ExecutionStatus.COMPLETED else "✗"
        if item.error:
            print(f"   {status_icon} [{item.status.value}] {item.workflow}: {item.error}")
        else:
            print(f"   {status_icon} [{item.status.value}] {item.workflow}: {item.result}")
    
    # Batch summary
    print("\n3. Batch summary...")
    print(f"   Total items: {result.total}")
    print(f"   Successful: {result.successful}")
    print(f"   Failed: {result.failed}")
    print(f"   Success rate: {result.success_rate:.1f}%")
    if result.duration_seconds is not None:
        print(f"   Duration: {result.duration_seconds:.2f}s")
    
    # Serialize to dict
    print("\n4. Serialized batch result...")
    result_dict = result.to_dict()
    print(f"   Batch ID: {result_dict['batch_id'][:8]}...")
    print(f"   Status summary: {result_dict['successful']}/{result_dict['total']} successful")
    
    # === Using BatchExecutor directly ===
    print("\n5. Using BatchExecutor directly...")
    
    executor = BatchExecutor(
        ledger,
        max_parallel=2,
        default_handler=lambda params: {"processed": True},
    )
    
    executor.add("operation.a", {"x": 1})
    executor.add("operation.b", {"x": 2})
    executor.add("operation.c", {"x": 3})
    
    exec_result = executor.run_all(parallel=False)
    
    print(f"   Total: {exec_result.total}")
    print(f"   Successful: {exec_result.successful}")
    print(f"   Failed: {exec_result.failed}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("BatchExecutor demo complete!")


if __name__ == "__main__":
    main()
