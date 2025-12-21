#!/usr/bin/env python3
"""FeedSpine Integration — Using spine-core with FeedSpine.

WHY FEED ABSTRACTION
────────────────────
Financial data comes from dozens of sources — SEC RSS, FINRA OTC,
earnings calendars, news wires.  Each has its own API, format, and
rate limits.  FeedSpine normalises all of them behind a single
collect(feed_name) interface, handling deduplication, sightings,
and incremental collection.

ARCHITECTURE
────────────
    ┌─────────────┐   collect(name)   ┌─────────────┐
    │ spine-core  │───────────────▶│  FeedSpine  │
    │ dispatcher │                │   (mock)    │
    └─────────────┘                └────┬────────┘
                                       │
                                       ▼
                                 {new, duplicates,
                                  records[]}

    Incremental: second call to same feed returns new=0
    because all records were already "collected" on first call.

INGESTION WORKFLOW
──────────────────
    1. collect_feed(name)          → raw records
    2. collect_multiple_feeds([])  → merged records
    3. deduplicate_records([])     → unique records by ID
    4. parallel collection via asyncio.gather()

BEST PRACTICES
──────────────
• Collect feeds in parallel to reduce wall-clock time.
• Always deduplicate when collecting overlapping feeds.
• Use list_feeds() to discover available sources.
• Combine with EntitySpine (01) for enriched ingestion.

Run: python examples/07_real_world/02_feedspine_integration.py

See Also:
    01_entityspine_integration — entity resolution
    03_combined_workflow — feeds + entities together
    04_feed_ingestion — full production-style ingestion
"""
import asyncio
import sys
from pathlib import Path

# Add mock path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spine.execution import EventDispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor
from mock import MockFeedSpine


# === Setup mock FeedSpine ===
feed_spine = MockFeedSpine(latency_ms=10)


# === Task handlers using FeedSpine ===

async def collect_feed(params: dict) -> dict:
    """Collect records from a single feed."""
    feed_name = params.get("feed_name", "")
    
    result = await feed_spine.collect(feed_name)
    
    if result.success:
        return {
            "feed": feed_name,
            "new_records": result.data["new"],
            "duplicates": result.data["duplicates"],
            "records": result.data["records"],
        }
    return {"feed": feed_name, "error": result.error}


async def collect_multiple_feeds(params: dict) -> dict:
    """Collect from multiple feeds."""
    feed_names = params.get("feeds", [])
    
    all_records = []
    feed_stats = {}
    
    for feed_name in feed_names:
        result = await feed_spine.collect(feed_name)
        if result.success:
            all_records.extend(result.data["records"])
            feed_stats[feed_name] = result.data["new"]
    
    return {
        "total_records": len(all_records),
        "by_feed": feed_stats,
        "records": all_records,
    }


async def deduplicate_records(params: dict) -> dict:
    """Deduplicate records across feeds."""
    records = params.get("records", [])
    
    # Simple dedup by ID
    seen_ids = set()
    unique = []
    
    for record in records:
        rid = record.get("id", id(record))
        if rid not in seen_ids:
            seen_ids.add(rid)
            unique.append(record)
    
    return {
        "original_count": len(records),
        "unique_count": len(unique),
        "duplicates_removed": len(records) - len(unique),
        "records": unique,
    }


async def main():
    print("=" * 60)
    print("FeedSpine Integration")
    print("=" * 60)
    
    # === Setup ===
    registry = HandlerRegistry()
    registry.register("task", "collect_feed", collect_feed)
    registry.register("task", "collect_multiple_feeds", collect_multiple_feeds)
    registry.register("task", "deduplicate_records", deduplicate_records)
    
    handlers = {
        "task:collect_feed": collect_feed,
        "task:collect_multiple_feeds": collect_multiple_feeds,
        "task:deduplicate_records": deduplicate_records,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    # === 1. Collect single feed ===
    print("\n[1] Collect Single Feed")
    
    run_id = await dispatcher.submit_task("collect_feed", {
        "feed_name": "sec_filings",
    })
    run = await dispatcher.get_run(run_id)
    
    print(f"  Feed: {run.result['feed']}")
    print(f"  New records: {run.result['new_records']}")
    
    for record in run.result.get("records", [])[:3]:
        print(f"    - {record.get('title', record.get('id', 'Unknown'))}")
    
    # === 2. Collect multiple feeds ===
    print("\n[2] Collect Multiple Feeds")
    
    run_id = await dispatcher.submit_task("collect_multiple_feeds", {
        "feeds": ["sec_filings", "earnings", "news"],
    })
    run = await dispatcher.get_run(run_id)
    
    print(f"  Total records: {run.result['total_records']}")
    print("  By feed:")
    for feed, count in run.result["by_feed"].items():
        print(f"    - {feed}: {count}")
    
    # === 3. List available feeds ===
    print("\n[3] Available Feeds")
    
    feeds_result = await feed_spine.list_feeds()
    if feeds_result.success:
        for feed in feeds_result.data:
            name = feed["name"]
            count = feed["record_count"]
            print(f"  {name}: {count} records")
    
    # === 4. Parallel feed collection ===
    print("\n[4] Parallel Feed Collection")
    
    feeds = ["sec_filings", "earnings", "news"]
    
    # Submit all in parallel
    run_ids = await asyncio.gather(*[
        dispatcher.submit_task("collect_feed", {"feed_name": f})
        for f in feeds
    ])
    
    # Collect results
    all_records = []
    for run_id in run_ids:
        run = await dispatcher.get_run(run_id)
        all_records.extend(run.result.get("records", []))
    
    print(f"  Collected {len(all_records)} total records from {len(feeds)} feeds")
    
    # === 5. Deduplication workflow ===
    print("\n[5] Deduplication Workflow")
    
    # Reset tracking for this test
    feed_spine._collected_ids.clear()
    
    # Collect with potential duplicates (second call sees all as duplicates)
    run_id = await dispatcher.submit_task("collect_multiple_feeds", {
        "feeds": ["sec_filings", "sec_filings", "news"],  # Intentional duplicate
    })
    collection_run = await dispatcher.get_run(run_id)
    
    # Deduplicate
    dedup_id = await dispatcher.submit_task("deduplicate_records", {
        "records": collection_run.result["records"],
    })
    dedup_run = await dispatcher.get_run(dedup_id)
    
    print(f"  Original: {dedup_run.result['original_count']}")
    print(f"  After dedup: {dedup_run.result['unique_count']}")
    print(f"  Duplicates removed: {dedup_run.result['duplicates_removed']}")
    
    # === 6. Full ingestion workflow ===
    print("\n[6] Full Ingestion Workflow")
    
    # Reset for clean run
    feed_spine._collected_ids.clear()
    
    async def run_ingestion(feeds: list) -> dict:
        """Complete ingestion workflow with deduplication."""
        # Step 1: Collect from all feeds
        r1 = await dispatcher.submit_task("collect_multiple_feeds", {
            "feeds": feeds,
        })
        collection = (await dispatcher.get_run(r1)).result
        
        # Step 2: Deduplicate
        r2 = await dispatcher.submit_task("deduplicate_records", {
            "records": collection["records"],
        })
        deduped = (await dispatcher.get_run(r2)).result
        
        return {
            "feeds_processed": len(feeds),
            "raw_records": collection["total_records"],
            "unique_records": deduped["unique_count"],
            "duplicates": deduped["duplicates_removed"],
        }
    
    result = await run_ingestion(
        feeds=["sec_filings", "earnings", "news"],
    )
    
    print(f"  Feeds processed: {result['feeds_processed']}")
    print(f"  Raw records: {result['raw_records']}")
    print(f"  Unique records: {result['unique_records']}")
    
    # === 7. API statistics ===
    print("\n[7] Mock API Statistics")
    print(f"  Total API calls: {feed_spine._call_count}")
    
    print("\n" + "=" * 60)
    print("[OK] FeedSpine Integration Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
