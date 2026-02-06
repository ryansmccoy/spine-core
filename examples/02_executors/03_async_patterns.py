#!/usr/bin/env python3
"""Async Patterns - Using spine-core with async/await.

This example demonstrates various async patterns for efficient
task execution and coordination.

Run: python examples/02_executors/03_async_patterns.py
"""
import asyncio
from spine.execution import Dispatcher, HandlerRegistry, WorkSpec
from spine.execution.executors import MemoryExecutor


# === Task handlers ===

async def fetch_entity(params: dict) -> dict:
    """Simulate fetching entity data."""
    ticker = params.get("ticker", "UNKNOWN")
    await asyncio.sleep(0.01)  # Simulate I/O
    return {"ticker": ticker, "name": f"{ticker} Corp", "sector": "Technology"}


async def fetch_filings(params: dict) -> dict:
    """Simulate fetching filings."""
    ticker = params.get("ticker", "UNKNOWN")
    await asyncio.sleep(0.02)  # Simulate I/O
    return {
        "ticker": ticker,
        "filings": [f"{ticker}-10K-2024", f"{ticker}-10Q-2024Q1"],
    }


async def fetch_price(params: dict) -> dict:
    """Simulate fetching price data."""
    ticker = params.get("ticker", "UNKNOWN")
    await asyncio.sleep(0.01)  # Simulate I/O
    return {"ticker": ticker, "price": 150.25, "change": 2.5}


async def aggregate_data(params: dict) -> dict:
    """Aggregate data from multiple sources."""
    return {
        "entity": params.get("entity", {}),
        "filings": params.get("filings", []),
        "price": params.get("price", {}),
    }


# === Setup ===

def setup_dispatcher():
    """Create and configure dispatcher."""
    registry = HandlerRegistry()
    registry.register("task", "fetch_entity", fetch_entity)
    registry.register("task", "fetch_filings", fetch_filings)
    registry.register("task", "fetch_price", fetch_price)
    registry.register("task", "aggregate_data", aggregate_data)
    
    handlers = {
        "task:fetch_entity": fetch_entity,
        "task:fetch_filings": fetch_filings,
        "task:fetch_price": fetch_price,
        "task:aggregate_data": aggregate_data,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    return Dispatcher(executor=executor, registry=registry)


async def main():
    print("=" * 60)
    print("Async Patterns")
    print("=" * 60)
    
    dispatcher = setup_dispatcher()
    
    # === 1. Sequential execution ===
    print("\n[1] Sequential Execution")
    import time
    
    start = time.perf_counter()
    
    run1 = await dispatcher.submit_task("fetch_entity", {"ticker": "AAPL"})
    result1 = (await dispatcher.get_run(run1)).result
    
    run2 = await dispatcher.submit_task("fetch_filings", {"ticker": "AAPL"})
    result2 = (await dispatcher.get_run(run2)).result
    
    run3 = await dispatcher.submit_task("fetch_price", {"ticker": "AAPL"})
    result3 = (await dispatcher.get_run(run3)).result
    
    elapsed = time.perf_counter() - start
    print(f"  Sequential time: {elapsed:.4f}s")
    print(f"  Results: entity={result1['name']}, filings={len(result2['filings'])}, price=${result3['price']}")
    
    # === 2. Parallel execution with gather ===
    print("\n[2] Parallel Execution (asyncio.gather)")
    
    start = time.perf_counter()
    
    # Submit all tasks at once
    run_ids = await asyncio.gather(
        dispatcher.submit_task("fetch_entity", {"ticker": "MSFT"}),
        dispatcher.submit_task("fetch_filings", {"ticker": "MSFT"}),
        dispatcher.submit_task("fetch_price", {"ticker": "MSFT"}),
    )
    
    # Get all results
    results = await asyncio.gather(*[
        dispatcher.get_run(run_id) for run_id in run_ids
    ])
    
    elapsed = time.perf_counter() - start
    print(f"  Parallel time: {elapsed:.4f}s (faster!)")
    print(f"  Results collected: {len(results)}")
    
    # === 3. Fan-out pattern (one-to-many) ===
    print("\n[3] Fan-Out Pattern")
    
    tickers = ["AAPL", "MSFT", "GOOG", "AMZN"]
    
    # Submit tasks for all tickers
    run_ids = await asyncio.gather(*[
        dispatcher.submit_task("fetch_entity", {"ticker": t})
        for t in tickers
    ])
    
    # Collect results
    runs = await asyncio.gather(*[
        dispatcher.get_run(run_id) for run_id in run_ids
    ])
    
    for run in runs:
        print(f"  - {run.result['ticker']}: {run.result['name']}")
    
    # === 4. Fan-in pattern (many-to-one) ===
    print("\n[4] Fan-In Pattern")
    
    ticker = "NVDA"
    
    # Fetch multiple data types in parallel
    entity_id, filings_id, price_id = await asyncio.gather(
        dispatcher.submit_task("fetch_entity", {"ticker": ticker}),
        dispatcher.submit_task("fetch_filings", {"ticker": ticker}),
        dispatcher.submit_task("fetch_price", {"ticker": ticker}),
    )
    
    entity = (await dispatcher.get_run(entity_id)).result
    filings = (await dispatcher.get_run(filings_id)).result
    price = (await dispatcher.get_run(price_id)).result
    
    # Aggregate into single result
    agg_id = await dispatcher.submit_task("aggregate_data", {
        "entity": entity,
        "filings": filings["filings"],
        "price": price,
    })
    aggregated = (await dispatcher.get_run(agg_id)).result
    
    print(f"  Aggregated data for {ticker}:")
    print(f"    Entity: {aggregated['entity']['name']}")
    print(f"    Filings: {len(aggregated['filings'])} items")
    print(f"    Price: ${aggregated['price']['price']}")
    
    # === 5. Batched processing ===
    print("\n[5] Batched Processing")
    
    all_tickers = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"]
    batch_size = 3
    
    async def process_batch(batch):
        run_ids = await asyncio.gather(*[
            dispatcher.submit_task("fetch_entity", {"ticker": t})
            for t in batch
        ])
        runs = await asyncio.gather(*[
            dispatcher.get_run(rid) for rid in run_ids
        ])
        return [r.result for r in runs]
    
    all_results = []
    for i in range(0, len(all_tickers), batch_size):
        batch = all_tickers[i:i + batch_size]
        print(f"  Processing batch: {batch}")
        batch_results = await process_batch(batch)
        all_results.extend(batch_results)
    
    print(f"  Total processed: {len(all_results)}")
    
    # === 6. Error handling in parallel ===
    print("\n[6] Error Handling in Parallel")
    
    async def safe_fetch(ticker):
        """Fetch with error handling."""
        try:
            run_id = await dispatcher.submit_task("fetch_entity", {"ticker": ticker})
            run = await dispatcher.get_run(run_id)
            return {"success": True, "data": run.result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    results = await asyncio.gather(*[
        safe_fetch(t) for t in ["AAPL", "MSFT", "INVALID"]
    ])
    
    successes = sum(1 for r in results if r["success"])
    print(f"  Successes: {successes}/{len(results)}")
    
    print("\n" + "=" * 60)
    print("[OK] Async Patterns Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
