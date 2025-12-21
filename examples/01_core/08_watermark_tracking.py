#!/usr/bin/env python3
"""Watermark Store — Cursor-based progress tracking for incremental operations.

Demonstrates spine-core's watermark primitives:
1. Creating watermarks for domain/source/partition triples
2. Advancing watermarks (forward-only / monotonic)
3. In-memory store vs SQLite-backed store
4. Listing all watermarks and detecting gaps
5. Deleting stale watermarks

Real-World Context:
    An EDGAR crawl processes 10-K, 10-Q, 8-K, and 20-F filing types.
    After ingesting 50,000 filings, the operation crashes.  Without
    watermarks, you'd re-crawl everything from scratch — wasting hours
    and burning API rate limits.  With watermarks, each filing type has
    a high-water mark (e.g. "2025-09-30T00:00:00Z") and the operation
    resumes exactly where it left off.

    Gap detection finds filing types with no watermark at all — "we
    have 10-K, 10-Q, and 8-K watermarks but no 20-F" — which feeds
    directly into BackfillPlan for structured recovery.

Run: python examples/01_core/08_watermark_tracking.py
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add examples directory to path for _db import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import get_demo_connection, load_env
from spine.core.watermarks import Watermark, WatermarkGap, WatermarkStore


def main():
    print("=" * 60)
    print("Watermark Store — Incremental Operation Cursors")
    print("=" * 60)

    # ── 1. In-memory store ──────────────────────────────────────
    print("\n--- 1. In-memory WatermarkStore ---")
    store = WatermarkStore()
    print(f"  Backend: in-memory")

    # ── 2. Advance (creates if missing) ─────────────────────────
    print("\n--- 2. Advance watermarks ---")
    w1 = store.advance(
        domain="sec_filings",
        source="edgar",
        partition_key="10-K",
        high_water="2025-06-15T00:00:00Z",
    )
    print(f"  Domain:      {w1.domain}")
    print(f"  Source:       {w1.source}")
    print(f"  Partition:   {w1.partition_key}")
    print(f"  High water:  {w1.high_water}")
    print(f"  Low water:   {w1.low_water}")

    # ── 3. Advance again (forward-only) ─────────────────────────
    print("\n--- 3. Forward-only advance ---")
    w2 = store.advance(
        domain="sec_filings",
        source="edgar",
        partition_key="10-K",
        high_water="2025-09-30T00:00:00Z",
    )
    print(f"  New high water:  {w2.high_water}")
    print(f"  Low water kept:  {w2.low_water}")

    # Try to move backward — forward-only, so stale value is ignored
    print("\n  Attempting backward advance...")
    w3 = store.advance(
        domain="sec_filings",
        source="edgar",
        partition_key="10-K",
        high_water="2025-01-01T00:00:00Z",
    )
    print(f"  High water unchanged: {w3.high_water}  (stale value ignored)")

    # ── 4. Multiple partitions ──────────────────────────────────
    print("\n--- 4. Multiple partitions ---")
    store.advance("sec_filings", "edgar", "10-Q", "2025-08-01T00:00:00Z")
    store.advance("sec_filings", "edgar", "8-K", "2025-09-15T00:00:00Z")
    store.advance("prices", "vendor_a", "daily", "2025-09-30T00:00:00Z")

    all_wm = store.list_all()
    print(f"  Total watermarks: {len(all_wm)}")
    for wm in all_wm:
        print(f"    {wm.domain}/{wm.source}/{wm.partition_key} → {wm.high_water}")

    # ── 5. Get a specific watermark ─────────────────────────────
    print("\n--- 5. Get specific watermark ---")
    wm = store.get("sec_filings", "edgar", "10-K")
    if wm:
        print(f"  Found: {wm.domain}/{wm.partition_key} → {wm.high_water}")
    missing = store.get("prices", "vendor_b", "daily")
    print(f"  Missing watermark returns: {missing}")

    # ── 6. Gap detection ────────────────────────────────────────
    print("\n--- 6. Gap detection ---")
    expected = ["10-K", "10-Q", "8-K", "20-F"]  # 20-F is missing
    gaps = store.list_gaps("sec_filings", "edgar", expected)
    print(f"  Expected partitions: {expected}")
    print(f"  Gaps found: {len(gaps)}")
    for gap in gaps:
        print(f"    {gap.partition_key}: {gap.gap_start} → {gap.gap_end}")

    # ── 7. SQLite-backed store ──────────────────────────────────
    print("\n--- 7. SQLite-backed store ---")
    # Load .env and get connection (in-memory or persistent based on config)
    load_env()
    conn, info = get_demo_connection()
    # core_watermarks table is created automatically by get_demo_connection()
    print(f"  Backend: {'persistent' if info.persistent else 'in-memory'}")
    db_store = WatermarkStore(conn=conn)
    db_store.advance("filings", "edgar", "10-K", "2025-12-31T00:00:00Z")
    result = db_store.get("filings", "edgar", "10-K")
    print(f"  SQLite watermark: {result.high_water if result else 'missing'}")
    print(f"  Persisted to DB: True")

    # Verify it survives a new store instance on same connection
    db_store2 = WatermarkStore(conn=conn)
    result2 = db_store2.get("filings", "edgar", "10-K")
    print(f"  Survives reload: {result2 is not None}")
    conn.close()

    # ── 8. Delete a watermark ───────────────────────────────────
    print("\n--- 8. Delete watermark ---")
    before = len(store.list_all())
    store.delete("prices", "vendor_a", "daily")
    after = len(store.list_all())
    print(f"  Before: {before} watermarks")
    print(f"  After:  {after} watermarks")

    print("\n" + "=" * 60)
    print("[OK] Watermark store example complete")


if __name__ == "__main__":
    main()
