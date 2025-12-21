#!/usr/bin/env python3
"""Idempotency — Safe, Re-runnable Data Operations.

================================================================================
WHAT IS IDEMPOTENCY?
================================================================================

An operation is **idempotent** if running it multiple times produces the
same result as running it once.

    f(f(x)) = f(x)

For data operations, this means:
- Re-running an ingest job doesn't create duplicate records
- A crashed job can be safely restarted without side effects
- Backfills can be re-run if something went wrong


================================================================================
WHY IDEMPOTENCY MATTERS
================================================================================

Without idempotency::

    # Job runs at 9:00 AM - inserts 1000 records
    # Job crashes at 9:05 AM after inserting 800 records
    # Ops restarts job at 9:10 AM
    # Job inserts 1000 MORE records (duplicates!)
    # Database now has 1800 records, 800 duplicated

    # Result:
    # - Incorrect aggregations (double-counted)
    # - Compliance violations (duplicate transactions)
    # - Customer complaints (charged twice)

With idempotency::

    # Job runs at 9:00 AM - inserts 1000 records (with hashes)
    # Job crashes at 9:05 AM after inserting 800 records
    # Ops restarts job at 9:10 AM
    # Job checks hashes, skips 800 existing, inserts remaining 200
    # Database has exactly 1000 records


================================================================================
THREE LEVELS OF IDEMPOTENCY
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  LEVEL 1: APPEND (L1_APPEND)                                            │
    │  ────────────────────────────                                            │
    │  Always insert, no deduplication.                                       │
    │                                                                         │
    │  Use for: Audit logs, event streams, append-only tables                 │
    │  Dedup:   External (downstream aggregation or DISTINCT queries)         │
    │                                                                         │
    │  Run 1: INSERT event1, event2                                           │
    │  Run 2: INSERT event1, event2  (duplicates OK for audit trail)          │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  LEVEL 2: INPUT HASH (L2_INPUT)                                         │
    │  ─────────────────────────────                                           │
    │  Hash input data, skip if hash already exists.                          │
    │                                                                         │
    │  Use for: Bronze layer, raw API responses, source data capture          │
    │  Dedup:   Hash of business key fields stored with each record           │
    │                                                                         │
    │  Run 1: hash(AAPL,2024-01-19) not found → INSERT                        │
    │  Run 2: hash(AAPL,2024-01-19) exists → SKIP                             │
    │                                                                         │
    │  Table:                                                                 │
    │    record_hash   symbol   date         price                            │
    │    abc123        AAPL     2024-01-19   150.00                            │
    └─────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  LEVEL 3: STATE (L3_STATE)                                              │
    │  ─────────────────────────                                               │
    │  Delete existing data, then insert fresh. Full state replacement.       │
    │                                                                         │
    │  Use for: Silver/Gold layers, aggregated tables, latest-state views     │
    │  Dedup:   DELETE WHERE partition_key=X; INSERT new data                 │
    │                                                                         │
    │  Run 1: DELETE week=2024-01-19; INSERT 1000 rows                        │
    │  Run 2: DELETE week=2024-01-19; INSERT 1000 rows (fresh calculation)    │
    │                                                                         │
    │  This ensures aggregations reflect latest logic, not stale data.        │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
MEDALLION ARCHITECTURE MAPPING
================================================================================

::

    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │   BRONZE    │────►│   SILVER    │────►│    GOLD     │
    │  Raw Data   │     │  Cleaned    │     │  Aggregated │
    └─────┬───────┘     └─────┬───────┘     └─────┬───────┘
          │                   │                   │
       L2_INPUT            L3_STATE            L3_STATE
       (hash)              (delete+insert)     (delete+insert)

    Bronze: Keep all raw data versions (L2 dedup by source hash)
    Silver: Latest cleaned version only (L3 replace per partition)
    Gold:   Latest aggregates only (L3 replace per partition)


================================================================================
DATABASE PATTERNS
================================================================================

**L2_INPUT: Hash-based dedup**::

    -- Table with hash column
    CREATE TABLE bronze_prices (
        record_hash VARCHAR(64) PRIMARY KEY,
        symbol VARCHAR(10),
        date DATE,
        price DECIMAL(12,4),
        raw_json JSON,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Upsert pattern (INSERT ... ON CONFLICT DO NOTHING)
    INSERT INTO bronze_prices (record_hash, symbol, date, price, raw_json)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT (record_hash) DO NOTHING;

**L3_STATE: Delete + Insert**::

    -- Within a transaction
    BEGIN;
    DELETE FROM silver_volume WHERE week_ending = '2024-01-19';
    INSERT INTO silver_volume (week_ending, symbol, total_volume)
    SELECT '2024-01-19', symbol, SUM(volume)
    FROM bronze_trades
    WHERE trade_date BETWEEN '2024-01-15' AND '2024-01-19'
    GROUP BY symbol;
    COMMIT;


================================================================================
BEST PRACTICES
================================================================================

1. **Choose the right level per table**::

       # Audit logs: L1 (always append)
       # Raw API data: L2 (hash dedup)
       # Aggregated metrics: L3 (full replace)

2. **Include hash in INSERT**::

       record_hash = compute_hash(symbol, date, source)
       cursor.execute(
           "INSERT INTO bronze (..., record_hash) VALUES (..., ?)",
           [..., record_hash]
       )

3. **Use partition keys for L3**::

       # Delete by partition, not entire table
       DELETE FROM silver WHERE week_ending = ?  # Good
       DELETE FROM silver                        # Bad!

4. **Test idempotency explicitly**::

       def test_ingest_idempotent():
           run_ingest(week="2024-01-19")
           count_after_first = count_rows(week="2024-01-19")
           run_ingest(week="2024-01-19")  # Re-run
           count_after_second = count_rows(week="2024-01-19")
           assert count_after_first == count_after_second


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/10_idempotency.py

See Also:
    - :mod:`spine.core.idempotency` — IdempotencyHelper, IdempotencyLevel
    - :mod:`spine.core.hashing` — compute_hash for record deduplication
    - :mod:`spine.core.manifest` — WorkManifest for stage tracking
"""
import sys
from pathlib import Path

# Add examples directory to path for _db import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import get_demo_connection, load_env
from spine.core import IdempotencyHelper, IdempotencyLevel
from spine.core.hashing import compute_hash


def main():
    print("=" * 60)
    print("Idempotency Examples")
    print("=" * 60)
    
    # === 1. Idempotency levels ===
    print("\n[1] Idempotency Levels")
    
    for level in IdempotencyLevel:
        print(f"  {level.name} ({level.value})")
    
    print("\n  Level descriptions:")
    print("    L1_APPEND: Always insert, external deduplication")
    print("    L2_INPUT:  Hash-based dedup, skip if exists")
    print("    L3_STATE:  Delete + insert pattern")
    
    # === 2. Creating IdempotencyHelper ===
    print("\n[2] Creating IdempotencyHelper")
    
    # Load .env and get connection (in-memory or persistent based on config)
    load_env()
    conn, info = get_demo_connection()
    print(f"  Backend: {'persistent' if info.persistent else 'in-memory'}")
    
    # Create demo tables for this example
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze_raw (
            record_hash TEXT,
            symbol TEXT,
            date TEXT,
            price REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS silver_volume (
            week TEXT,
            tier TEXT,
            volume INTEGER
        )
    """)
    conn.commit()
    
    helper = IdempotencyHelper(conn)
    print("  Helper created with database connection")
    
    # === 3. L1 Append pattern ===
    print("\n[3] L1 APPEND Pattern")
    print("  Use case: Audit logs, raw event capture")
    print("  Behavior: Always insert, no checks")
    
    # Simulated
    audit_records = [
        {"event": "user_login", "timestamp": "2024-01-19T10:00:00"},
        {"event": "data_fetch", "timestamp": "2024-01-19T10:01:00"},
    ]
    print(f"  Would insert {len(audit_records)} audit records (no dedup)")
    
    # === 4. L2 Input-based dedup ===
    print("\n[4] L2 INPUT Pattern")
    print("  Use case: Bronze layer, raw API responses")
    print("  Behavior: Hash input, skip if hash exists")
    
    records = [
        {"symbol": "AAPL", "date": "2024-01-19", "price": 150.0},
        {"symbol": "MSFT", "date": "2024-01-19", "price": 350.0},
        {"symbol": "AAPL", "date": "2024-01-19", "price": 150.0},  # Duplicate
    ]
    
    # First pass: insert all unique records
    for record in records:
        h = compute_hash(record["symbol"], record["date"], record["price"])
        if not helper.hash_exists("bronze_raw", "record_hash", h):
            conn.execute(
                "INSERT INTO bronze_raw (record_hash, symbol, date, price) VALUES (?, ?, ?, ?)",
                (h, record["symbol"], record["date"], record["price"]),
            )
            print(f"  ✓ New: {record['symbol']} (hash={h[:8]}...)")
        else:
            print(f"  ✗ Skip: {record['symbol']} (duplicate hash)")
    conn.commit()
    
    # Verify count
    count = conn.execute("SELECT COUNT(*) FROM bronze_raw").fetchone()[0]
    print(f"  Result: {count} unique from {len(records)} total")
    
    # Second pass: all should be skipped (idempotent)
    print("\n  Re-run (idempotent):")
    skipped = 0
    for record in records:
        h = compute_hash(record["symbol"], record["date"], record["price"])
        if helper.hash_exists("bronze_raw", "record_hash", h):
            skipped += 1
    print(f"  All {skipped} records already exist - nothing to insert")
    
    # Batch hash preload
    print("\n  Batch hash preload:")
    existing = helper.get_existing_hashes("bronze_raw", "record_hash")
    print(f"  Loaded {len(existing)} existing hashes for batch check")
    
    # === 5. L3 State-based (delete+insert) ===
    print("\n[5] L3 STATE Pattern")
    print("  Use case: Silver/Gold layers, aggregations")
    print("  Behavior: Delete existing by key, then insert")
    
    # Insert initial data
    conn.execute(
        "INSERT INTO silver_volume (week, tier, volume) VALUES (?, ?, ?)",
        ("2024-01-19", "NMS_TIER_1", 1000000),
    )
    conn.execute(
        "INSERT INTO silver_volume (week, tier, volume) VALUES (?, ?, ?)",
        ("2024-01-19", "NMS_TIER_1", 2000000),
    )
    conn.commit()
    
    count_before = conn.execute("SELECT COUNT(*) FROM silver_volume").fetchone()[0]
    print(f"  Before: {count_before} rows in silver_volume")
    
    # L3 pattern: delete by key, then insert fresh data
    key = {"week": "2024-01-19", "tier": "NMS_TIER_1"}
    deleted = helper.delete_for_key("silver_volume", key)
    print(f"  Deleted {deleted} rows for key {key}")
    
    new_data = [
        ("2024-01-19", "NMS_TIER_1", 1500000),
        ("2024-01-19", "NMS_TIER_1", 2500000),
        ("2024-01-19", "NMS_TIER_1", 3000000),
    ]
    for row in new_data:
        conn.execute(
            "INSERT INTO silver_volume (week, tier, volume) VALUES (?, ?, ?)",
            row,
        )
    conn.commit()
    
    count_after = conn.execute("SELECT COUNT(*) FROM silver_volume").fetchone()[0]
    print(f"  Inserted {len(new_data)} new rows")
    print(f"  After: {count_after} rows in silver_volume")
    print("  Result: Same final state regardless of how many times run")
    
    # === 6. Real-world: Operation with idempotency ===
    print("\n[6] Real-world: Operation with Idempotency")
    
    def run_operation(conn, helper, week: str, data: list):
        """L3 idempotent operation."""
        key = {"week": week}
        
        # Delete existing
        deleted = helper.delete_for_key("silver_volume", key)
        print(f"    Deleted {deleted} existing records")
        
        # Insert new
        for d in data:
            conn.execute(
                "INSERT INTO silver_volume (week, tier, volume) VALUES (?, ?, ?)",
                (d["week"], d.get("tier", "ALL"), d["volume"]),
            )
        conn.commit()
        print(f"    Inserted {len(data)} new records")
        
        return len(data)
    
    week = "2024-02-01"
    data = [
        {"week": week, "tier": "ALL", "volume": 100},
        {"week": week, "tier": "ALL", "volume": 200},
    ]
    
    # First run
    print("  First run:")
    run_operation(conn, helper, week, data)
    total = conn.execute(
        "SELECT COUNT(*) FROM silver_volume WHERE week = ?", (week,)
    ).fetchone()[0]
    print(f"    DB state: {total} records for week {week}")
    
    # Re-run (should produce same result)
    print("  Re-run (idempotent):")
    run_operation(conn, helper, week, data)
    total = conn.execute(
        "SELECT COUNT(*) FROM silver_volume WHERE week = ?", (week,)
    ).fetchone()[0]
    print(f"    DB state: {total} records for week {week} (unchanged)")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("[OK] Idempotency Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
