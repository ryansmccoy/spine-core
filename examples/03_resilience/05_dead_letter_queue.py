#!/usr/bin/env python3
"""Dead Letter Queue — Handle failed executions gracefully.

WHY DEAD LETTER QUEUES MATTER
─────────────────────────────
In a pipeline that runs hundreds of jobs nightly, some will fail due to
API outages, bad data, or transient bugs.  Without a DLQ those failures
are silently lost — the data gap remains until someone notices days later.
A Dead Letter Queue captures every failure with full context so that
operators can inspect, fix, and replay without re-running the entire
batch.

ARCHITECTURE
────────────
    ┌──────────┐  success   ┌──────────┐
    │ Pipeline │───────────▶│  Result  │
    └────┬─────┘            └──────────┘
         │ failure
         ▼
    ┌──────────────┐  inspect   ┌──────────┐
    │  DLQManager   │───────────▶│ Operator │
    │  .add_to_dlq()│            │  review  │
    └────┬─────────┘            └────┬─────┘
         │                           │ fix + replay
         ▼                           ▼
    ┌──────────────┐         ┌──────────────┐
    │ core_dead_   │         │  .resolve()  │
    │ letters table│◀────────│  or auto-    │
    └──────────────┘         │  retry       │
                             └──────────────┘

DATABASE SCHEMA
───────────────
    core_dead_letters
    ┌───────────────┬─────────┬──────────────────────────────┐
    │ Column        │ Type    │ Purpose                      │
    ├───────────────┼─────────┼──────────────────────────────┤
    │ id            │ TEXT PK │ Unique dead-letter ID        │
    │ execution_id  │ TEXT    │ Original execution reference │
    │ pipeline      │ TEXT    │ Which pipeline failed        │
    │ params        │ TEXT    │ JSON serialised parameters   │
    │ error         │ TEXT    │ Full error message           │
    │ retry_count   │ INT     │ How many retries attempted   │
    │ max_retries   │ INT     │ Cap before giving up         │
    │ created_at    │ TEXT    │ When the failure occurred     │
    │ last_retry_at │ TEXT    │ Timestamp of last retry      │
    │ resolved_at   │ TEXT    │ When resolved (null if open) │
    │ resolved_by   │ TEXT    │ Who/what resolved it         │
    └───────────────┴─────────┴──────────────────────────────┘

DLQ LIFECYCLE
─────────────
    add_to_dlq(exec_id, pipeline, params, error)
        → DeadLetter created with retry_count=0

    mark_retry_attempted(id)  → retry_count += 1, last_retry_at = now
    resolve(id, resolved_by)  → resolved_at = now

    list_unresolved()         → all entries where resolved_at IS NULL
    list_all(pipeline=...)    → filter by pipeline name

BEST PRACTICES
──────────────
• Store full params so replays don't need to re-derive inputs.
• Set max_retries to 3-5 — beyond that, the issue needs human attention.
• Build dashboards on list_unresolved() with age-based alerting.
• Use resolved_by to track whether resolution was human or automatic.
• Combine with RetryStrategy (01_retry_strategies) for inline retries
  before an item reaches the DLQ.

Run: python examples/03_resilience/05_dead_letter_queue.py

See Also:
    01_retry_strategies — exhaust retries before DLQ
    04_concurrency_guard — capture blocked runs in DLQ
"""
import sqlite3
import tempfile
import os
from datetime import datetime, timezone
from spine.execution import DLQManager, DeadLetter


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def setup_database(db_path: str) -> sqlite3.Connection:
    """Create a SQLite database with the DLQ table."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS core_dead_letters (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            workflow TEXT NOT NULL,
            params TEXT NOT NULL,
            error TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            created_at TEXT NOT NULL,
            last_retry_at TEXT,
            resolved_at TEXT,
            resolved_by TEXT
        )
    """)
    conn.commit()
    return conn


def main():
    print("=" * 60)
    print("Dead Letter Queue Examples")
    print("=" * 60)
    
    # Create temporary database
    db_path = os.path.join(tempfile.gettempdir(), "dlq_demo.db")
    conn = setup_database(db_path)
    
    try:
        # === 1. Create DLQ manager ===
        print("\n[1] Create DLQ Manager")
        
        dlq = DLQManager(conn, max_retries=3)
        print(f"  DLQ Manager created with max_retries=3")
        
        # === 2. Add failed executions ===
        print("\n[2] Add Failed Executions")
        
        failures = [
            {
                "execution_id": "exec-001",
                "pipeline": "otc_volume",
                "error": "ConnectionError: API timeout",
                "params": {"week": "2024-01-19"},
            },
            {
                "execution_id": "exec-002",
                "pipeline": "price_fetch",
                "error": "ValidationError: Invalid symbol",
                "params": {"symbol": "INVALID"},
            },
            {
                "execution_id": "exec-003",
                "pipeline": "otc_volume",
                "error": "RateLimitError: Too many requests",
                "params": {"week": "2024-01-26"},
            },
        ]
        
        for f in failures:
            entry = dlq.add_to_dlq(
                execution_id=f["execution_id"],
                workflow=f["pipeline"],
                params=f["params"],
                error=f["error"],
            )
            print(f"    Added: {f['execution_id']} ({f['pipeline']})")
        
        # === 3. Query DLQ ===
        print("\n[3] Query DLQ")
        
        all_items = dlq.list_all()
        print(f"  Total items in DLQ: {len(all_items)}")
        
        for item in all_items:
            print(f"    {item.execution_id}: {item.workflow} - {item.error[:40]}...")
        
        # === 4. Get single entry ===
        print("\n[4] Get Single Entry")
        
        if all_items:
            entry = dlq.get(all_items[0].id)
            print(f"  Entry ID: {entry.id}")
            print(f"  Pipeline: {entry.workflow}")
            print(f"  Error: {entry.error}")
            print(f"  Retry count: {entry.retry_count}/{entry.max_retries}")
        
        # === 5. Filter by pipeline ===
        print("\n[5] Filter by Pipeline")
        
        otc_failures = dlq.list_all(workflow="otc_volume")
        print(f"  OTC volume failures: {len(otc_failures)}")
        
        for item in otc_failures:
            print(f"    {item.execution_id}: {item.params}")
        
        # === 6. Increment retry count ===
        print("\n[6] Increment Retry Count")
        
        if all_items:
            entry = all_items[0]
            print(f"  Before: {entry.execution_id} retry_count={entry.retry_count}")
            
            dlq.mark_retry_attempted(entry.id)
            updated = dlq.get(entry.id)
            print(f"  After: {updated.execution_id} retry_count={updated.retry_count}")
        
        # === 7. Resolve entry ===
        print("\n[7] Resolve Entry")
        
        if len(all_items) > 1:
            entry = all_items[1]
            dlq.resolve(
                entry.id,
                resolved_by="admin@example.com",
            )
            print(f"  Resolved: {entry.execution_id}")
            
            # Check resolved entries
            unresolved = dlq.list_unresolved()
            print(f"  Unresolved entries: {len(unresolved)}")
        
        # === 8. Real-world: Batch retry ===
        print("\n[8] Real-world: Batch Retry")
        
        def simulate_retry(entry: DeadLetter) -> bool:
            """Simulate retrying a failed execution."""
            # 50% success rate for demo
            return entry.retry_count > 0
        
        unresolved = dlq.list_unresolved()
        print(f"  Attempting retry of {len(unresolved)} entries:")
        
        for entry in unresolved:
            dlq.mark_retry_attempted(entry.id)
            success = simulate_retry(entry)
            
            if success:
                dlq.resolve(entry.id, resolved_by="auto-retry")
                print(f"    {entry.execution_id}: ✓ retry success")
            else:
                print(f"    {entry.execution_id}: ✗ retry failed")
        
        final_unresolved = dlq.list_unresolved()
        print(f"\n  Final unresolved: {len(final_unresolved)}")
        
        print("\n" + "=" * 60)
        print("[OK] Dead Letter Queue Complete!")
        print("=" * 60)
        
    finally:
        conn.close()
        # Cleanup
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    main()
