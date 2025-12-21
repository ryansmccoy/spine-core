#!/usr/bin/env python3
"""EntitySpine Integration — Using spine-core with EntitySpine.

WHY ENTITY RESOLUTION
─────────────────────
SEC filings use CIKs, market data uses tickers, and FINRA uses
MPIDs.  Without a unified entity resolver, joining across these
data sources requires brittle manual mapping tables.  EntitySpine
provides a single API: give it any identifier and get back a
canonical entity record with all cross-references.

ARCHITECTURE
────────────
    ┌─────────────┐   resolve_by_ticker   ┌─────────────┐
    │ spine-core  │───────────────────▶│ EntitySpine │
    │ dispatcher │                    │   (mock)    │
    └──────┬──────┘   resolve_by_cik    └────┬────────┘
           │       ───────────────────▶     │
           │       get_filings             │
           │       ───────────────────▶     │
           ▼                               ▼
    ┌─────────────┐               ┌─────────────┐
    │   Entity    │               │  Filings   │
    │ {ticker,   │               │ [{form,    │
    │  cik, name,│               │   filed}]  │
    │  sic_desc} │               └─────────────┘
    └─────────────┘

    This example uses MockEntitySpine.  In production, replace
    with the real EntitySpine client pointing at the entity API.

TASKS DEMONSTRATED
──────────────────
    Task              Input          Output
    ───────────────── ────────────── ───────────────────────
    resolve_ticker    {ticker}       {entity} or {error}
    resolve_cik       {cik}          {entity} or {error}
    get_filings       {cik, form}    [{form, filed, ...}]
    batch_resolve     {tickers[]}    [{resolved, entity}]

Run: python examples/07_real_world/01_entityspine_integration.py

See Also:
    02_feedspine_integration — feed collection via FeedSpine
    03_combined_workflow — EntitySpine + FeedSpine together
"""
import asyncio
import sys
from pathlib import Path

# Add mock path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spine.execution import EventDispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor
from mock import MockEntitySpine


# === Setup mock EntitySpine ===
entity_spine = MockEntitySpine(latency_ms=10)


# === Task handlers using EntitySpine ===

async def resolve_ticker(params: dict) -> dict:
    """Resolve a ticker symbol to entity details."""
    ticker = params.get("ticker", "")
    result = await entity_spine.resolve_by_ticker(ticker)
    
    if result.success:
        return {"resolved": True, "entity": result.data}
    return {"resolved": False, "error": result.error}


async def resolve_cik(params: dict) -> dict:
    """Resolve a CIK to entity details."""
    cik = params.get("cik", "")
    result = await entity_spine.resolve_by_cik(cik)
    
    if result.success:
        return {"resolved": True, "entity": result.data}
    return {"resolved": False, "error": result.error}


async def get_filings(params: dict) -> dict:
    """Get filings for a CIK."""
    cik = params.get("cik", "")
    form_type = params.get("form_type")
    limit = params.get("limit", 10)
    
    result = await entity_spine.get_filings(cik, form_type=form_type, limit=limit)
    
    if result.success:
        return {
            "cik": cik,
            "filing_count": len(result.data),
            "filings": result.data,
        }
    return {"cik": cik, "error": result.error}


async def batch_resolve(params: dict) -> dict:
    """Resolve multiple tickers in batch."""
    tickers = params.get("tickers", [])
    
    results = []
    for ticker in tickers:
        result = await entity_spine.resolve_by_ticker(ticker)
        if result.success:
            results.append({"ticker": ticker, "resolved": True, "entity": result.data})
        else:
            results.append({"ticker": ticker, "resolved": False})
    
    return {
        "total": len(tickers),
        "resolved": len([r for r in results if r["resolved"]]),
        "results": results,
    }


async def main():
    print("=" * 60)
    print("EntitySpine Integration")
    print("=" * 60)
    
    # === Setup ===
    registry = HandlerRegistry()
    registry.register("task", "resolve_ticker", resolve_ticker)
    registry.register("task", "resolve_cik", resolve_cik)
    registry.register("task", "get_filings", get_filings)
    registry.register("task", "batch_resolve", batch_resolve)
    
    handlers = {
        "task:resolve_ticker": resolve_ticker,
        "task:resolve_cik": resolve_cik,
        "task:get_filings": get_filings,
        "task:batch_resolve": batch_resolve,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    # === 1. Resolve single ticker ===
    print("\n[1] Resolve Single Ticker")
    
    run_id = await dispatcher.submit_task("resolve_ticker", {"ticker": "AAPL"})
    run = await dispatcher.get_run(run_id)
    
    if run.result.get("resolved"):
        entity = run.result["entity"]
        print(f"  Ticker: AAPL")
        print(f"  Name: {entity['name']}")
        print(f"  CIK: {entity['cik']}")
        print(f"  Industry: {entity.get('sic_description', 'N/A')}")
    
    # === 2. Resolve by CIK ===
    print("\n[2] Resolve by CIK")
    
    run_id = await dispatcher.submit_task("resolve_cik", {"cik": "0000789019"})
    run = await dispatcher.get_run(run_id)
    
    if run.result.get("resolved"):
        entity = run.result["entity"]
        print(f"  CIK: 0000789019")
        print(f"  Resolved to: {entity['ticker']} - {entity['name']}")
    
    # === 3. Get filings ===
    print("\n[3] Get Filings")
    
    # First resolve MSFT to get CIK
    msft_result = await entity_spine.resolve_by_ticker("MSFT")
    msft_cik = msft_result.data["cik"] if msft_result.success else "0000789019"
    
    run_id = await dispatcher.submit_task("get_filings", {
        "cik": msft_cik,
        "form_type": "10-K",
        "limit": 3,
    })
    run = await dispatcher.get_run(run_id)
    
    print(f"  Found {run.result['filing_count']} filings for MSFT:")
    for filing in run.result.get("filings", []):
        print(f"    - {filing.get('form', 'N/A')} ({filing.get('filed', 'N/A')})")
    
    # === 4. Batch resolution ===
    print("\n[4] Batch Resolution")
    
    run_id = await dispatcher.submit_task("batch_resolve", {
        "tickers": ["AAPL", "MSFT", "GOOG", "INVALID", "AMZN"],
    })
    run = await dispatcher.get_run(run_id)
    
    print(f"  Total: {run.result['total']}")
    print(f"  Resolved: {run.result['resolved']}")
    
    for r in run.result["results"]:
        status = "✓" if r["resolved"] else "✗"
        print(f"    {status} {r['ticker']}")
    
    # === 5. Workflow: Full entity analysis ===
    print("\n[5] Entity Analysis Workflow")
    
    async def analyze_entity(ticker: str) -> dict:
        """Full entity analysis workflow."""
        # Step 1: Resolve ticker
        r1 = await dispatcher.submit_task("resolve_ticker", {"ticker": ticker})
        entity_run = await dispatcher.get_run(r1)
        
        if not entity_run.result.get("resolved"):
            return {"error": f"Could not resolve {ticker}"}
        
        entity = entity_run.result["entity"]
        cik = entity["cik"]
        
        # Step 2: Get filings using CIK
        r2 = await dispatcher.submit_task("get_filings", {
            "cik": cik,
            "limit": 5,
        })
        filings_run = await dispatcher.get_run(r2)
        
        return {
            "ticker": ticker,
            "entity": entity,
            "filing_count": filings_run.result.get("filing_count", 0),
            "recent_filings": filings_run.result.get("filings", [])[:3],
        }
    
    analysis = await analyze_entity("NVDA")
    print(f"  Entity: {analysis['entity']['name']}")
    print(f"  Industry: {analysis['entity'].get('sic_description', 'N/A')}")
    print(f"  Total filings: {analysis['filing_count']}")
    
    # === 6. API statistics ===
    print("\n[6] Mock API Statistics")
    print(f"  Total API calls: {entity_spine._call_count}")
    
    print("\n" + "=" * 60)
    print("[OK] EntitySpine Integration Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
