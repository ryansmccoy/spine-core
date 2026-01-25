#!/usr/bin/env python3
"""FeedSpine Pipeline Example - Real Market Data Feed Ingestion.

Run: python examples/ecosystem/01_feedspine_pipeline.py
"""
import asyncio
from datetime import datetime
from typing import Any

from spine.execution import Dispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor


async def fetch_otc_quotes(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch OTC Markets quotes."""
    symbols = params.get("symbols", ["AAPL", "MSFT"])
    await asyncio.sleep(0.01)
    quotes = [{"symbol": s, "bid": 150.0 + i, "ask": 150.05 + i} for i, s in enumerate(symbols)]
    return {"quotes": quotes, "count": len(quotes)}


async def validate_quotes(params: dict[str, Any]) -> dict[str, Any]:
    """Validate quotes for data quality."""
    quotes = params.get("quotes", [])
    valid = [q for q in quotes if abs(q.get("ask", 0) - q.get("bid", 0)) <= 1.0]
    return {"valid_quotes": valid, "valid_count": len(valid)}


async def run_feed_pipeline(params: dict[str, Any]) -> dict[str, Any]:
    """Full feed ingestion pipeline."""
    symbols = params.get("symbols", ["AAPL", "MSFT", "GOOGL"])
    fetch_result = await fetch_otc_quotes({"symbols": symbols})
    validation_result = await validate_quotes({"quotes": fetch_result["quotes"]})
    return {"pipeline": "feed_ingestion", "status": "completed", 
            "stats": {"fetched": fetch_result["count"], "valid": validation_result["valid_count"]}}


async def main():
    print("=" * 70)
    print("FeedSpine Pipeline Example")
    print("Using spine-core Unified Execution Contract")
    print("=" * 70)
    
    # Build handler map for MemoryExecutor
    handlers = {
        "task:fetch_otc_quotes": fetch_otc_quotes,
        "task:validate_quotes": validate_quotes,
        "pipeline:feed_ingestion": run_feed_pipeline,
    }
    
    # Create registry for metadata
    registry = HandlerRegistry()
    registry.register("task", "fetch_otc_quotes", fetch_otc_quotes, tags={"domain": "feedspine"})
    registry.register("task", "validate_quotes", validate_quotes, tags={"domain": "feedspine"})
    registry.register("pipeline", "feed_ingestion", run_feed_pipeline, tags={"domain": "feedspine"})
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    print("\n[1] Submitting task: fetch_otc_quotes")
    run_id = await dispatcher.submit_task("fetch_otc_quotes", {"symbols": ["AAPL", "MSFT", "NVDA"]})
    run = await dispatcher.get_run(run_id)
    print(f"  Status: {run.status.value}, Quotes: {run.result.get('count')}")
    
    print("\n[2] Submitting pipeline: feed_ingestion")
    pipeline_run_id = await dispatcher.submit_pipeline("feed_ingestion", {"symbols": ["AAPL", "MSFT"]})
    pipeline_run = await dispatcher.get_run(pipeline_run_id)
    print(f"  Status: {pipeline_run.status.value}, Stats: {pipeline_run.result.get('stats')}")
    
    print("\n" + "=" * 70)
    print("[OK] FeedSpine Example Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
