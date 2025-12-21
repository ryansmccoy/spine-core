"""SEC Filing Workflow — Multi-step filing processing operation.

WHY THIS EXAMPLE
────────────────
Processing an SEC filing is not a single step — it’s a multi-stage
operation: fetch the raw document, extract text and exhibits, parse
XBRL financial data, run NLP entity extraction, store results, and
notify downstream consumers.  This example shows how spine-core’s
execution primitives orchestrate that entire chain.

ARCHITECTURE
────────────
    ┌───────────┐   ┌──────────────┐
    │   Fetch   │─▶│ Extract Text │────┬──▶ Parse XBRL
    └───────────┘   └──────────────┘    │
                                        ├──▶ Extract Exhibits
                                        │
                                        ▼
                                 ┌──────────────┐
                                 │ NLP Entities │
                                 └──────┬───────┘
                                        │
                                        ▼
                         ┌───────┐   ┌────────┐
                         │ Store │─▶│ Notify │
                         └───────┘   └────────┘

    Text extraction and exhibit extraction run in parallel.
    XBRL parsing has a 10 % simulated failure rate to demonstrate
    error handling and retry patterns.

STEP HANDLERS
─────────────
    Step                Decorator             Output
    ─────────────────── ───────────────────── ──────────────────────
    fetch_filing         @register_step       accession, filing dict
    extract_text         @register_step       sections[], word_count
    extract_exhibits     @register_step       exhibits[], count
    parse_xbrl           @register_step       facts{}, key financials
    extract_entities     @register_step       companies, people, locs
    store_results        @register_step       storage_location, stored_at
    notify_downstream    @register_step       notifications sent

Run: python examples/07_real_world/05_sec_filing_workflow.py

See Also:
    04_feed_ingestion — feed-level ingestion operation
    01_entityspine_integration — entity resolution for filings
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
import random

from spine.execution import (
    EventDispatcher,
    WorkSpec,
    task_spec,
    operation_spec,
    step_spec,
    register_task,
    register_operation,
    register_step,
    HandlerRegistry,
    RunStatus,
)
from spine.execution.executors import MemoryExecutor


# =============================================================================
# SEC FILING PROCESSING WORKFLOW (real use case)
# =============================================================================

# This simulates a filing processing operation that:
# 1. Fetches raw filing from SEC EDGAR
# 2. Extracts text and exhibits
# 3. Parses structured data (XML/XBRL)
# 4. Runs entity extraction
# 5. Stores results
# 6. Notifies downstream systems

# Mock SEC filing data
MOCK_FILINGS = {
    "0000320193-24-000001": {
        "cik": "0000320193",
        "company": "Apple Inc.",
        "form_type": "10-K",
        "filed_date": "2024-10-25",
        "url": "https://www.sec.gov/Archives/edgar/data/320193/...",
    },
    "0000789019-24-000002": {
        "cik": "0000789019",
        "company": "Microsoft Corporation",
        "form_type": "10-Q",
        "filed_date": "2024-10-24",
        "url": "https://www.sec.gov/Archives/edgar/data/789019/...",
    },
}

registry = HandlerRegistry()


# --- Step Handlers ---

@register_step("fetch_filing", registry=registry, description="Fetch raw filing from SEC EDGAR")
async def fetch_filing(params: dict) -> dict:
    """Fetch a filing document from SEC EDGAR."""
    accession = params.get("accession_number")
    
    await asyncio.sleep(0.2)  # Simulate network I/O
    
    filing = MOCK_FILINGS.get(accession)
    if not filing:
        raise ValueError(f"Filing not found: {accession}")
    
    print(f"  📥 Fetched filing {accession} ({filing['form_type']})")
    
    return {
        "accession_number": accession,
        "filing": filing,
        "content_size_kb": random.randint(500, 5000),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


@register_step("extract_text", registry=registry, description="Extract text from HTML/XML")
async def extract_text(params: dict) -> dict:
    """Extract plain text from filing document."""
    accession = params.get("accession_number")
    content_size_kb = params.get("content_size_kb", 1000)
    
    await asyncio.sleep(0.1 * (content_size_kb / 1000))  # Simulate processing
    
    print(f"  📝 Extracted text from {accession}")
    
    return {
        "accession_number": accession,
        "text_extracted": True,
        "sections_found": ["item_1", "item_1a", "item_7", "item_8"],
        "word_count": random.randint(50000, 200000),
    }


@register_step("extract_exhibits", registry=registry, description="Extract exhibits from filing")
async def extract_exhibits(params: dict) -> dict:
    """Extract exhibit documents from filing."""
    accession = params.get("accession_number")
    
    await asyncio.sleep(0.15)
    
    exhibits = [
        {"number": "10.1", "type": "material_contract", "pages": 25},
        {"number": "21.1", "type": "subsidiaries", "pages": 5},
        {"number": "31.1", "type": "certification_302", "pages": 1},
    ]
    
    print(f"  📎 Extracted {len(exhibits)} exhibits from {accession}")
    
    return {
        "accession_number": accession,
        "exhibits": exhibits,
        "exhibit_count": len(exhibits),
    }


@register_step("parse_xbrl", registry=registry, description="Parse XBRL financial data")
async def parse_xbrl(params: dict) -> dict:
    """Parse XBRL-tagged financial data."""
    accession = params.get("accession_number")
    form_type = params.get("form_type", "10-K")
    
    await asyncio.sleep(0.3)  # XBRL parsing is slow
    
    # Simulate occasional parsing failures
    if random.random() < 0.1:  # 10% failure rate
        raise ValueError(f"XBRL parsing failed for {accession}: malformed instance document")
    
    facts = {
        "Assets": {"value": 352583000000, "unit": "USD"},
        "Revenues": {"value": 391035000000, "unit": "USD"},
        "NetIncome": {"value": 96995000000, "unit": "USD"},
    }
    
    print(f"  📊 Parsed XBRL data from {accession} ({len(facts)} facts)")
    
    return {
        "accession_number": accession,
        "facts_extracted": len(facts),
        "key_facts": facts,
        "xbrl_version": "2.1",
    }


@register_step("extract_entities", registry=registry, description="Extract named entities")
async def extract_entities(params: dict) -> dict:
    """Run NLP entity extraction on filing text."""
    accession = params.get("accession_number")
    
    await asyncio.sleep(0.25)
    
    entities = {
        "companies": ["Apple Inc.", "Foxconn", "TSMC"],
        "people": ["Tim Cook", "Luca Maestri"],
        "locations": ["Cupertino", "California", "China"],
        "dates": ["December 31, 2024", "September 2024"],
    }
    
    print(f"  🔍 Extracted entities from {accession}")
    
    return {
        "accession_number": accession,
        "entities": entities,
        "total_entities": sum(len(v) for v in entities.values()),
    }


@register_step("store_results", registry=registry, description="Store processed results")
async def store_results(params: dict) -> dict:
    """Store processed filing data to database."""
    accession = params.get("accession_number")
    results = params.get("results", {})
    
    await asyncio.sleep(0.05)
    
    print(f"  💾 Stored results for {accession}")
    
    return {
        "accession_number": accession,
        "stored": True,
        "storage_location": f"s3://filings/{accession}/processed.json",
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }


@register_step("notify_downstream", registry=registry, description="Notify downstream systems")
async def notify_downstream(params: dict) -> dict:
    """Send notifications to downstream consumers."""
    accession = params.get("accession_number")
    channels = params.get("channels", ["websocket", "kafka"])
    
    await asyncio.sleep(0.02)
    
    for channel in channels:
        print(f"  📨 Notified {channel} about {accession}")
    
    return {
        "accession_number": accession,
        "notified": channels,
        "notification_count": len(channels),
    }


# --- Workflow Operation ---

@register_operation("process_filing", registry=registry, description="Full SEC filing processing workflow")
async def process_filing(params: dict) -> dict:
    """
    Complete filing processing workflow.
    
    Workflow steps:
    1. Fetch raw filing (sequential)
    2. Extract text AND exhibits (parallel)
    3. Parse XBRL if applicable (conditional)
    4. Extract entities from text
    5. Store results
    6. Notify downstream (parallel to next filing)
    """
    accession = params.get("accession_number")
    
    print(f"\n🔄 Processing filing: {accession}")
    
    # Step 1: Fetch filing
    fetch_result = await fetch_filing({"accession_number": accession})
    filing = fetch_result["filing"]
    
    # Step 2: Extract text and exhibits in parallel
    text_task = extract_text({
        "accession_number": accession,
        "content_size_kb": fetch_result["content_size_kb"],
    })
    exhibits_task = extract_exhibits({"accession_number": accession})
    
    text_result, exhibits_result = await asyncio.gather(text_task, exhibits_task)
    
    # Step 3: Parse XBRL (only for 10-K and 10-Q)
    xbrl_result = None
    if filing["form_type"] in ["10-K", "10-Q"]:
        try:
            xbrl_result = await parse_xbrl({
                "accession_number": accession,
                "form_type": filing["form_type"],
            })
        except ValueError as e:
            print(f"  ⚠️ XBRL parsing failed: {e}")
            xbrl_result = {"error": str(e), "facts_extracted": 0}
    
    # Step 4: Extract entities
    entities_result = await extract_entities({"accession_number": accession})
    
    # Step 5: Store results
    combined_results = {
        "fetch": fetch_result,
        "text": text_result,
        "exhibits": exhibits_result,
        "xbrl": xbrl_result,
        "entities": entities_result,
    }
    
    store_result = await store_results({
        "accession_number": accession,
        "results": combined_results,
    })
    
    # Step 6: Notify downstream
    notify_result = await notify_downstream({
        "accession_number": accession,
        "channels": ["websocket", "kafka", "sns"],
    })
    
    print(f"✅ Completed processing: {accession}")
    
    return {
        "accession_number": accession,
        "filing": filing,
        "text_extracted": text_result["word_count"],
        "exhibits_extracted": exhibits_result["exhibit_count"],
        "xbrl_facts": xbrl_result["facts_extracted"] if xbrl_result else 0,
        "entities_extracted": entities_result["total_entities"],
        "storage_location": store_result["storage_location"],
        "notifications_sent": notify_result["notification_count"],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


@register_operation("batch_process_filings", registry=registry, description="Process multiple filings")
async def batch_process_filings(params: dict) -> dict:
    """Process multiple filings with controlled concurrency."""
    accessions = params.get("accession_numbers", [])
    max_concurrent = params.get("max_concurrent", 2)
    
    print(f"\n📦 Batch processing {len(accessions)} filings (max {max_concurrent} concurrent)")
    
    results = []
    errors = []
    
    # Process in batches for concurrency control
    for i in range(0, len(accessions), max_concurrent):
        batch = accessions[i:i + max_concurrent]
        tasks = [process_filing({"accession_number": acc}) for acc in batch]
        
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for acc, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                errors.append({"accession_number": acc, "error": str(result)})
            else:
                results.append(result)
    
    return {
        "processed_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


# =============================================================================
# MAIN DEMONSTRATION
# =============================================================================

async def main():
    """Demonstrate the workflow execution."""
    print("\n" + "=" * 60)
    print("SPINE EXECUTION - WORKFLOW EXAMPLE")
    print("SEC Filing Processing Operation")
    print("=" * 60)
    
    # Build handler map from registry
    handlers = {}
    for kind, name in registry.list_handlers():
        handler = registry.get(kind, name)
        handlers[f"{kind}:{name}"] = handler
    
    # Create executor and dispatcher
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    # --- Demo 1: Single Filing Processing ---
    print("\n📋 Demo 1: Process a single 10-K filing")
    print("-" * 40)
    
    run_id = await dispatcher.submit_operation(
        "process_filing",
        params={"accession_number": "0000320193-24-000001"},
    )
    
    # Wait for completion
    while True:
        run = await dispatcher.get_run(run_id)
        if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
            break
        await asyncio.sleep(0.1)
    
    if run.status == RunStatus.COMPLETED:
        print(f"\n✅ Filing processed successfully!")
        print(f"   Text words: {run.result.get('text_extracted', 0):,}")
        print(f"   XBRL facts: {run.result.get('xbrl_facts', 0)}")
        print(f"   Entities: {run.result.get('entities_extracted', 0)}")
    else:
        print(f"\n❌ Processing failed: {run.error}")
    
    # --- Demo 2: Batch Processing ---
    print("\n\n📋 Demo 2: Batch process multiple filings")
    print("-" * 40)
    
    run_id = await dispatcher.submit_operation(
        "batch_process_filings",
        params={
            "accession_numbers": [
                "0000320193-24-000001",
                "0000789019-24-000002",
            ],
            "max_concurrent": 2,
        },
    )
    
    # Wait for completion
    while True:
        run = await dispatcher.get_run(run_id)
        if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
            break
        await asyncio.sleep(0.1)
    
    if run.status == RunStatus.COMPLETED:
        result = run.result
        print(f"\n✅ Batch processing complete!")
        print(f"   Processed: {result.get('processed_count', 0)} filings")
        print(f"   Errors: {result.get('error_count', 0)}")
    else:
        print(f"\n❌ Batch failed: {run.error}")
    
    # --- Demo 3: Individual Step Execution ---
    print("\n\n📋 Demo 3: Execute individual steps")
    print("-" * 40)
    
    # Submit individual steps
    step_ids = []
    for step_name in ["fetch_filing", "parse_xbrl"]:
        step_id = await dispatcher.submit(
            step_spec(
                step_name,
                params={"accession_number": "0000320193-24-000001", "form_type": "10-K"},
            )
        )
        step_ids.append((step_name, step_id))
    
    # Wait for all steps
    for step_name, step_id in step_ids:
        while True:
            run = await dispatcher.get_run(step_id)
            if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
                break
            await asyncio.sleep(0.1)
        
        status = "✅" if run.status == RunStatus.COMPLETED else "❌"
        print(f"   {status} {step_name}: {run.status.value}")
    
    # --- Show Execution History ---
    print("\n\n📋 Execution History")
    print("-" * 40)
    
    runs = await dispatcher.list_runs(limit=10)
    for run in runs[:5]:
        status_icon = {
            RunStatus.COMPLETED: "✅",
            RunStatus.FAILED: "❌",
            RunStatus.RUNNING: "🔄",
            RunStatus.PENDING: "⏳",
        }.get(run.status, "❓")
        
        duration_ms = (run.duration_seconds or 0) * 1000
        print(f"   {status_icon} {run.kind}:{run.name} - {duration_ms:.0f}ms")
    
    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
