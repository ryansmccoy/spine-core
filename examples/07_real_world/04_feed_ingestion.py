"""Feed Ingestion Operation — Production-style feed processing.

WHY THIS EXAMPLE
────────────────
This is a realistic end-to-end ingestion operation that mirrors how
feedspine processes SEC EDGAR and FINRA OTC data.  It demonstrates
every layer of the execution contract: tasks, operations, workflows,
and the deduplication/sighting pattern that prevents re-processing.

ARCHITECTURE
────────────
    ┌─────────────┐  fetch  ┌───────────┐  dedup  ┌─────────┐
    │ SEC / FINRA │──────▶│ Raw Data  │──────▶│ Unique  │
    └─────────────┘        └───────────┘        └────┬────┘
                                                   │ store
                                                   ▼
                                            ┌─────────┐
                                            │ Storage │
                                            └─────────┘

    DEDUPLICATION LOGIC:
    natural_key not in storage  → NEW     → store
    natural_key + same hash     → DUPE    → add_sighting
    natural_key + diff hash     → UPDATE  → re-store

TASK REGISTRY
─────────────
    @register_task / @register_operation / @register_workflow
    • Decorators auto-register handlers with HandlerRegistry.
    • WorkSpec types: task_spec, operation_spec, workflow_spec.
    • MemoryExecutor runs everything in-process for this demo.

Run: python examples/07_real_world/04_feed_ingestion.py

See Also:
    02_feedspine_integration — simplified feed collection
    05_sec_filing_workflow — multi-step SEC filing processing
"""
import asyncio
import random
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any

# Import the unified execution contract
from spine.execution import (
    EventDispatcher,
    WorkSpec,
    task_spec,
    operation_spec,
    workflow_spec,
    step_spec,
    register_task,
    register_operation,
    register_workflow,
    HandlerRegistry,
    RunStatus,
    EventType,
)
from spine.execution.executors import MemoryExecutor


# =============================================================================
# DOMAIN MODELS (simulating feedspine records)
# =============================================================================

@dataclass
class FeedRecord:
    """A record from a feed (SEC filings, FINRA data, etc.)."""
    natural_key: str
    content_hash: str
    source_url: str
    raw_data: dict
    fetched_at: datetime


@dataclass
class ProcessResult:
    """Result of processing a feed record."""
    action: str  # "created", "duplicate", "updated"
    record_id: str | None = None


# =============================================================================
# MOCK DATA SOURCES (simulating real feeds)
# =============================================================================

SEC_RSS_FEED = [
    {"id": "0001193125-26-012345", "form": "10-K", "company": "Apple Inc.", "url": "https://sec.gov/..."},
    {"id": "0001193125-26-012346", "form": "10-Q", "company": "Microsoft Corp.", "url": "https://sec.gov/..."},
    {"id": "0001193125-26-012347", "form": "8-K", "company": "Tesla Inc.", "url": "https://sec.gov/..."},
]

FINRA_OTC_FEED = [
    {"date": "2026-01-15", "symbol": "AAPL", "volume": 1234567, "tier": "NMS_TIER_1"},
    {"date": "2026-01-15", "symbol": "MSFT", "volume": 987654, "tier": "NMS_TIER_1"},
    {"date": "2026-01-15", "symbol": "TSLA", "volume": 567890, "tier": "NMS_TIER_2"},
]


# =============================================================================
# STORAGE (in-memory for example, would be PostgreSQL/DuckDB in production)
# =============================================================================

class InMemoryStorage:
    """Simple in-memory storage simulating a database."""
    
    def __init__(self):
        self.records: dict[str, FeedRecord] = {}
        self.sightings: list[dict] = []
    
    def get_by_natural_key(self, key: str) -> FeedRecord | None:
        return self.records.get(key)
    
    def store(self, record: FeedRecord) -> str:
        self.records[record.natural_key] = record
        return record.natural_key
    
    def add_sighting(self, natural_key: str, source: str):
        self.sightings.append({
            "natural_key": natural_key,
            "source": source,
            "seen_at": datetime.now(timezone.utc),
        })


# Global storage instance (would be injected in real app)
storage = InMemoryStorage()


# =============================================================================
# TASK HANDLERS (the actual work units)
# =============================================================================

# Create a registry for this example
registry = HandlerRegistry()


@register_task("fetch_sec_rss", registry=registry, description="Fetch SEC RSS feed")
async def fetch_sec_rss(params: dict) -> dict:
    """Fetch records from SEC RSS feed."""
    # Simulate network latency
    await asyncio.sleep(0.1)
    
    records = []
    for item in SEC_RSS_FEED:
        record = FeedRecord(
            natural_key=item["id"],
            content_hash=f"sha256:{hash(str(item))}",
            source_url=item["url"],
            raw_data=item,
            fetched_at=datetime.now(timezone.utc),
        )
        records.append(record.__dict__)
    
    return {
        "source": "sec_rss",
        "record_count": len(records),
        "records": records,
    }


@register_task("fetch_finra_otc", registry=registry, description="Fetch FINRA OTC data")
async def fetch_finra_otc(params: dict) -> dict:
    """Fetch FINRA OTC transparency data."""
    date = params.get("date", "2026-01-15")
    tier = params.get("tier")
    
    await asyncio.sleep(0.1)
    
    data = FINRA_OTC_FEED
    if tier:
        data = [r for r in data if r["tier"] == tier]
    
    records = []
    for item in data:
        record = FeedRecord(
            natural_key=f"{item['date']}:{item['symbol']}",
            content_hash=f"sha256:{hash(str(item))}",
            source_url=f"https://finra.org/otc/{item['date']}",
            raw_data=item,
            fetched_at=datetime.now(timezone.utc),
        )
        records.append(record.__dict__)
    
    return {
        "source": "finra_otc",
        "date": date,
        "tier": tier,
        "record_count": len(records),
        "records": records,
    }


@register_task("deduplicate", registry=registry, description="Deduplicate records")
async def deduplicate(params: dict) -> dict:
    """Deduplicate records against storage."""
    records = params.get("records", [])
    
    new_records = []
    duplicates = []
    updates = []
    
    for record_dict in records:
        natural_key = record_dict["natural_key"]
        content_hash = record_dict["content_hash"]
        
        existing = storage.get_by_natural_key(natural_key)
        
        if existing is None:
            new_records.append(record_dict)
        elif existing.content_hash == content_hash:
            duplicates.append(natural_key)
            storage.add_sighting(natural_key, record_dict.get("source_url", "unknown"))
        else:
            updates.append(record_dict)
    
    return {
        "new_count": len(new_records),
        "duplicate_count": len(duplicates),
        "update_count": len(updates),
        "new_records": new_records,
        "updates": updates,
    }


@register_task("store_records", registry=registry, description="Store records in database")
async def store_records(params: dict) -> dict:
    """Store new records in the database."""
    records = params.get("records", [])
    
    stored_ids = []
    for record_dict in records:
        record = FeedRecord(
            natural_key=record_dict["natural_key"],
            content_hash=record_dict["content_hash"],
            source_url=record_dict["source_url"],
            raw_data=record_dict["raw_data"],
            fetched_at=datetime.fromisoformat(record_dict["fetched_at"]) if isinstance(record_dict["fetched_at"], str) else record_dict["fetched_at"],
        )
        record_id = storage.store(record)
        stored_ids.append(record_id)
    
    return {
        "stored_count": len(stored_ids),
        "record_ids": stored_ids,
    }


@register_task("notify_new_records", registry=registry, description="Send notifications")
async def notify_new_records(params: dict) -> dict:
    """Send notifications for new records (Slack, email, etc.)."""
    record_ids = params.get("record_ids", [])
    channel = params.get("channel", "default")
    
    # Simulate notification
    await asyncio.sleep(0.05)
    
    print(f"  📬 Notified {channel}: {len(record_ids)} new records")
    
    return {
        "notified": True,
        "channel": channel,
        "record_count": len(record_ids),
    }


# =============================================================================
# operation HANDLERS (composed from tasks)
# =============================================================================

@register_operation("ingest_sec_filings", registry=registry, description="Full SEC filing ingestion")
async def ingest_sec_filings(params: dict) -> dict:
    """Complete operation: fetch → dedupe → store → notify."""
    # This would normally use the dispatcher to run sub-tasks
    # For this example, we call handlers directly
    
    fetch_result = await fetch_sec_rss(params)
    dedup_result = await deduplicate({"records": fetch_result["records"]})
    store_result = await store_records({"records": dedup_result["new_records"]})
    
    if store_result["stored_count"] > 0:
        await notify_new_records({
            "record_ids": store_result["record_ids"],
            "channel": "sec-filings",
        })
    
    return {
        "fetched": fetch_result["record_count"],
        "new": store_result["stored_count"],
        "duplicates": dedup_result["duplicate_count"],
        "updates": dedup_result["update_count"],
    }


@register_operation("ingest_finra_otc", registry=registry, description="FINRA OTC data ingestion")
async def ingest_finra_otc(params: dict) -> dict:
    """Ingest FINRA OTC transparency data."""
    fetch_result = await fetch_finra_otc(params)
    dedup_result = await deduplicate({"records": fetch_result["records"]})
    store_result = await store_records({"records": dedup_result["new_records"]})
    
    return {
        "date": params.get("date"),
        "tier": params.get("tier"),
        "fetched": fetch_result["record_count"],
        "new": store_result["stored_count"],
        "duplicates": dedup_result["duplicate_count"],
    }


# =============================================================================
# MAIN EXAMPLE
# =============================================================================

async def main():
    """Run the feed ingestion example."""
    print("\n" + "=" * 60)
    print("SPINE EXECUTION - FEED INGESTION EXAMPLE")
    print("=" * 60)
    
    # Create executor with our handlers
    executor = MemoryExecutor(handlers=registry.to_executor_handlers())
    
    # Create dispatcher
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    # -----------------------------------------------------------------
    # Example 1: Submit individual tasks
    # -----------------------------------------------------------------
    print("\n📥 Example 1: Submit Individual Tasks")
    print("-" * 40)
    
    # Fetch SEC RSS
    run_id = await dispatcher.submit_task("fetch_sec_rss", {})
    run = await dispatcher.get_run(run_id)
    print(f"  Task: fetch_sec_rss")
    print(f"  Run ID: {run_id[:8]}...")
    print(f"  Status: {run.status.value}")
    
    # Fetch FINRA OTC with params
    run_id = await dispatcher.submit_task(
        "fetch_finra_otc",
        {"date": "2026-01-15", "tier": "NMS_TIER_1"},
        priority="high",
    )
    run = await dispatcher.get_run(run_id)
    print(f"  Task: fetch_finra_otc (tier=NMS_TIER_1)")
    print(f"  Run ID: {run_id[:8]}...")
    print(f"  Status: {run.status.value}")
    
    # -----------------------------------------------------------------
    # Example 2: Submit operations
    # -----------------------------------------------------------------
    print("\n📊 Example 2: Submit Operations")
    print("-" * 40)
    
    # Run SEC ingestion operation
    run_id = await dispatcher.submit_operation("ingest_sec_filings", {})
    run = await dispatcher.get_run(run_id)
    print(f"  Operation: ingest_sec_filings")
    print(f"  Run ID: {run_id[:8]}...")
    print(f"  Status: {run.status.value}")
    
    # Run FINRA OTC operation
    run_id = await dispatcher.submit_operation(
        "ingest_finra_otc",
        {"date": "2026-01-15"},
        lane="backfill",
    )
    run = await dispatcher.get_run(run_id)
    print(f"  Operation: ingest_finra_otc (lane=backfill)")
    print(f"  Run ID: {run_id[:8]}...")
    print(f"  Status: {run.status.value}")
    
    # -----------------------------------------------------------------
    # Example 3: Idempotency
    # -----------------------------------------------------------------
    print("\n🔒 Example 3: Idempotency Key")
    print("-" * 40)
    
    # Submit with idempotency key
    run_id_1 = await dispatcher.submit_task(
        "fetch_sec_rss",
        {},
        idempotency_key="sec-rss-2026-01-15",
    )
    
    # Submit again with same key - should return same run
    run_id_2 = await dispatcher.submit_task(
        "fetch_sec_rss",
        {},
        idempotency_key="sec-rss-2026-01-15",
    )
    
    print(f"  First submission: {run_id_1[:8]}...")
    print(f"  Second submission: {run_id_2[:8]}...")
    print(f"  Same run? {run_id_1 == run_id_2}")
    
    # -----------------------------------------------------------------
    # Example 4: Query runs
    # -----------------------------------------------------------------
    print("\n🔍 Example 4: Query Runs")
    print("-" * 40)
    
    # List all task runs
    task_runs = await dispatcher.list_runs(kind="task")
    print(f"  Total task runs: {len(task_runs)}")
    
    # List all operation runs
    operation_runs = await dispatcher.list_runs(kind="operation")
    print(f"  Total operation runs: {len(operation_runs)}")
    
    # List by name
    sec_runs = await dispatcher.list_runs(name="fetch_sec_rss")
    print(f"  fetch_sec_rss runs: {len(sec_runs)}")
    
    # -----------------------------------------------------------------
    # Example 5: Event history
    # -----------------------------------------------------------------
    print("\n📜 Example 5: Event History")
    print("-" * 40)
    
    # Get events for a run
    events = await dispatcher.get_events(run_id_1)
    print(f"  Run {run_id_1[:8]}... events:")
    for event in events:
        print(f"    - {event.event_type} at {event.timestamp.strftime('%H:%M:%S')}")
    
    # -----------------------------------------------------------------
    # Example 6: Storage state
    # -----------------------------------------------------------------
    print("\n💾 Example 6: Storage State")
    print("-" * 40)
    print(f"  Records in storage: {len(storage.records)}")
    print(f"  Sightings logged: {len(storage.sightings)}")
    
    for key, record in list(storage.records.items())[:3]:
        print(f"    - {key}: {record.raw_data.get('company', record.raw_data.get('symbol', 'N/A'))}")
    
    # -----------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------
    print("\n" + "=" * 60)
    print("✅ EXAMPLE COMPLETE")
    print("=" * 60)
    
    all_runs = await dispatcher.list_runs()
    print(f"\nTotal runs executed: {len(all_runs)}")
    print(f"Handlers registered: {len(registry.list_handlers())}")
    print(f"  - Tasks: {len(registry.list_handlers(kind='task'))}")
    print(f"  - Operations: {len(registry.list_handlers(kind='operation'))}")


if __name__ == "__main__":
    asyncio.run(main())
