#!/usr/bin/env python3
"""Combined Workflow — Using EntitySpine and FeedSpine together.

WHY COMBINED WORKFLOWS
──────────────────────
Raw feed records (SEC filings, news) contain tickers and CIKs but
lack normalised entity context.  By combining FeedSpine collection
with EntitySpine resolution, you build enriched records that join
across data sources — "all 10-K filings for companies in the
technology sector filed this week."

ARCHITECTURE
────────────
    ┌─────────────┐   parallel   ┌─────────────┐
    │ EntitySpine │◀──────────┤ Dispatcher  │
    └──────┬──────┘   gather   └──────┬──────┘
           │                          │
           ▼                          ▼
    entity + filings         ┌─────────────┐
           │                │  FeedSpine  │
           │                └──────┬──────┘
           │                       │ records
           ▼                       ▼
    ┌─────────────────────────────┐
    │  enrich_feed_items()          │
    │  record.entity = resolved     │
    └─────────────┬───────────────┘
                  │
                  ▼
    ┌─────────────────────────────┐
    │  filter_by_sector(industry)   │
    └─────────────────────────────┘

WORKFLOW STAGES
───────────────
    1. Parallel gather: entity + filings + news + SEC feed
    2. Enrich: attach entity data to each feed record
    3. Filter: select records by sector / industry
    4. Aggregate: combine entity + filing + feed views

Run: python examples/07_real_world/03_combined_workflow.py

See Also:
    01_entityspine_integration — entity resolution details
    02_feedspine_integration — feed collection details
"""
import asyncio
import sys
from pathlib import Path

# Add mock path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spine.execution import EventDispatcher, HandlerRegistry, WorkSpec
from spine.execution.executors import MemoryExecutor
from mock import MockEntitySpine, MockFeedSpine


# === Setup mocks ===
entity_spine = MockEntitySpine(latency_ms=10)
feed_spine = MockFeedSpine(latency_ms=10)


# === Entity tasks ===

async def resolve_entity(params: dict) -> dict:
    """Resolve a ticker to full entity details."""
    ticker = params.get("ticker", "")
    result = await entity_spine.resolve_by_ticker(ticker)
    
    if result.success:
        return {"resolved": True, "entity": result.data}
    return {"resolved": False, "ticker": ticker}


async def get_entity_filings(params: dict) -> dict:
    """Get filings for an entity."""
    cik = params.get("cik", "")
    form_type = params.get("form_type")
    limit = params.get("limit", 10)
    
    result = await entity_spine.get_filings(cik, form_type=form_type, limit=limit)
    
    if result.success:
        return {"cik": cik, "filings": result.data}
    return {"cik": cik, "filings": []}


# === Feed tasks ===

async def collect_news_feed(params: dict) -> dict:
    """Collect news feed items."""
    result = await feed_spine.collect("news")
    
    if result.success:
        return {"feed": "news", "records": result.data["records"]}
    return {"feed": "news", "records": []}


async def collect_sec_feed(params: dict) -> dict:
    """Collect SEC filings feed."""
    result = await feed_spine.collect("sec_filings")
    
    if result.success:
        return {"feed": "sec_filings", "records": result.data["records"]}
    return {"feed": "sec_filings", "records": []}


# === Combined tasks ===

async def enrich_feed_items(params: dict) -> dict:
    """Enrich feed items with entity data."""
    records = params.get("records", [])
    
    enriched = []
    for record in records:
        # Try to extract ticker from record
        ticker = record.get("ticker") or record.get("symbol")
        
        if ticker:
            result = await entity_spine.resolve_by_ticker(ticker)
            if result.success:
                record["entity"] = result.data
                record["enriched"] = True
            else:
                record["enriched"] = False
        else:
            record["enriched"] = False
        
        enriched.append(record)
    
    enriched_count = sum(1 for r in enriched if r.get("enriched"))
    return {
        "total": len(enriched),
        "enriched_count": enriched_count,
        "records": enriched,
    }


async def filter_by_sector(params: dict) -> dict:
    """Filter records by entity industry (SIC description)."""
    records = params.get("records", [])
    target_industry = params.get("industry", "")
    
    filtered = [
        r for r in records
        if target_industry.lower() in r.get("entity", {}).get("sic_description", "").lower()
    ]
    
    return {
        "original_count": len(records),
        "filtered_count": len(filtered),
        "industry": target_industry,
        "records": filtered,
    }


async def main():
    print("=" * 60)
    print("Combined Workflow: EntitySpine + FeedSpine")
    print("=" * 60)
    
    # === Setup ===
    registry = HandlerRegistry()
    registry.register("task", "resolve_entity", resolve_entity)
    registry.register("task", "get_entity_filings", get_entity_filings)
    registry.register("task", "collect_news_feed", collect_news_feed)
    registry.register("task", "collect_sec_feed", collect_sec_feed)
    registry.register("task", "enrich_feed_items", enrich_feed_items)
    registry.register("task", "filter_by_sector", filter_by_sector)
    
    handlers = {
        "task:resolve_entity": resolve_entity,
        "task:get_entity_filings": get_entity_filings,
        "task:collect_news_feed": collect_news_feed,
        "task:collect_sec_feed": collect_sec_feed,
        "task:enrich_feed_items": enrich_feed_items,
        "task:filter_by_sector": filter_by_sector,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    # === 1. Parallel data gathering ===
    print("\n[1] Parallel Data Gathering")
    print("  Collecting from entity and feed sources simultaneously...")
    
    # Resolve entity first to get CIK
    aapl = await entity_spine.resolve_by_ticker("AAPL")
    aapl_cik = aapl.data["cik"] if aapl.success else "0000320193"
    
    # Run entity resolution and feed collection in parallel
    entity_id, filings_id, news_id, sec_id = await asyncio.gather(
        dispatcher.submit_task("resolve_entity", {"ticker": "AAPL"}),
        dispatcher.submit_task("get_entity_filings", {"cik": aapl_cik, "limit": 5}),
        dispatcher.submit_task("collect_news_feed", {}),
        dispatcher.submit_task("collect_sec_feed", {}),
    )
    
    # Get results
    entity_run = await dispatcher.get_run(entity_id)
    filings_run = await dispatcher.get_run(filings_id)
    news_run = await dispatcher.get_run(news_id)
    sec_run = await dispatcher.get_run(sec_id)
    
    print(f"  Entity: {entity_run.result['entity']['name']}")
    print(f"  Entity filings: {len(filings_run.result['filings'])}")
    print(f"  News items: {len(news_run.result['records'])}")
    print(f"  SEC feed items: {len(sec_run.result['records'])}")
    
    # === 2. Feed enrichment workflow ===
    print("\n[2] Feed Enrichment Workflow")
    print("  Step 1: Collect feed → Step 2: Enrich with entity data")
    
    # Reset feed tracking
    feed_spine._collected_ids.clear()
    
    # Step 1: Collect
    collect_id = await dispatcher.submit_task("collect_sec_feed", {})
    collected = (await dispatcher.get_run(collect_id)).result
    print(f"  Collected {len(collected['records'])} SEC records")
    
    # Step 2: Enrich
    enrich_id = await dispatcher.submit_task("enrich_feed_items", {
        "records": collected["records"],
    })
    enriched = (await dispatcher.get_run(enrich_id)).result
    print(f"  Enriched {enriched['enriched_count']}/{enriched['total']} records")
    
    # === 3. Sector-Filtered Workflow ===
    print("\n[3] Sector-Filtered Workflow")
    print("  Collect → Enrich → Filter by sector")
    
    # Reset for clean run
    feed_spine._collected_ids.clear()
    
    # Collect and enrich
    c_id = await dispatcher.submit_task("collect_sec_feed", {})
    collected = (await dispatcher.get_run(c_id)).result
    
    e_id = await dispatcher.submit_task("enrich_feed_items", {
        "records": collected["records"],
    })
    enriched = (await dispatcher.get_run(e_id)).result
    
    # Filter by industry
    f_id = await dispatcher.submit_task("filter_by_sector", {
        "records": enriched["records"],
        "industry": "Software",
    })
    filtered = (await dispatcher.get_run(f_id)).result
    
    print(f"  Original: {filtered['original_count']}")
    print(f"  Software industry: {filtered['filtered_count']}")
    
    # === 4. Multi-entity research ===
    print("\n[4] Multi-Entity Research")
    
    tickers = ["AAPL", "MSFT", "GOOG"]
    
    async def research_entity(ticker: str) -> dict:
        """Research a single entity."""
        # Resolve
        r1 = await dispatcher.submit_task("resolve_entity", {"ticker": ticker})
        entity = (await dispatcher.get_run(r1)).result
        
        if not entity.get("resolved"):
            return {"ticker": ticker, "error": "Not found"}
        
        cik = entity["entity"]["cik"]
        
        # Get filings
        r2 = await dispatcher.submit_task("get_entity_filings", {
            "cik": cik,
            "form_type": "10-K",
            "limit": 3,
        })
        filings = (await dispatcher.get_run(r2)).result
        
        return {
            "ticker": ticker,
            "name": entity["entity"]["name"],
            "industry": entity["entity"].get("sic_description", "N/A"),
            "recent_10ks": len(filings["filings"]),
        }
    
    # Research all entities in parallel
    research_results = await asyncio.gather(*[
        research_entity(t) for t in tickers
    ])
    
    for result in research_results:
        if "error" in result:
            print(f"  {result['ticker']}: ERROR - {result['error']}")
        else:
            print(f"  {result['ticker']}: {result['name']} ({result['industry']}) - {result['recent_10ks']} 10-Ks")
    
    # === 5. Complete data pipeline ===
    print("\n[5] Complete Data Pipeline")
    
    # Reset for clean run
    feed_spine._collected_ids.clear()
    
    async def run_data_pipeline(tickers: list) -> dict:
        """
        Complete pipeline:
        1. Resolve all entities
        2. Collect feed data
        3. Enrich with entity data
        4. Aggregate results
        """
        # Step 1: Resolve entities
        entity_ids = await asyncio.gather(*[
            dispatcher.submit_task("resolve_entity", {"ticker": t})
            for t in tickers
        ])
        entities = {}
        for run_id in entity_ids:
            run = await dispatcher.get_run(run_id)
            if run.result.get("resolved"):
                ticker = run.result["entity"]["ticker"]
                entities[ticker] = run.result["entity"]
        
        # Step 2: Collect feeds
        news_id, sec_id = await asyncio.gather(
            dispatcher.submit_task("collect_news_feed", {}),
            dispatcher.submit_task("collect_sec_feed", {}),
        )
        news = (await dispatcher.get_run(news_id)).result["records"]
        sec = (await dispatcher.get_run(sec_id)).result["records"]
        
        # Step 3: Enrich
        all_records = news + sec
        enrich_id = await dispatcher.submit_task("enrich_feed_items", {
            "records": all_records,
        })
        enriched = (await dispatcher.get_run(enrich_id)).result
        
        return {
            "entities_resolved": len(entities),
            "total_records": len(all_records),
            "enriched_records": enriched["enriched_count"],
            "entities": list(entities.keys()),
        }
    
    pipeline_result = await run_data_pipeline(
        tickers=["AAPL", "MSFT", "GOOG", "AMZN", "NVDA"],
    )
    
    print(f"  Entities resolved: {pipeline_result['entities_resolved']}")
    print(f"  Total records: {pipeline_result['total_records']}")
    print(f"  Enriched: {pipeline_result['enriched_records']}")
    print(f"  Covered tickers: {pipeline_result['entities']}")
    
    # === 6. API statistics ===
    print("\n[6] Combined API Statistics")
    
    print(f"  EntitySpine calls: {entity_spine._call_count}")
    print(f"  FeedSpine calls: {feed_spine._call_count}")
    print(f"  Total API calls: {entity_spine._call_count + feed_spine._call_count}")
    
    print("\n" + "=" * 60)
    print("[OK] Combined Workflow Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
