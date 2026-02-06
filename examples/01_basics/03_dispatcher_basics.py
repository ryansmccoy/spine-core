#!/usr/bin/env python3
"""Dispatcher Basics - Submitting and tracking work.

This example demonstrates the Dispatcher, which is the main entry
point for submitting tasks, pipelines, and workflows.

Run: python examples/01_basics/03_dispatcher_basics.py
"""
import asyncio
from spine.execution import Dispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor


# === Define handlers ===

async def fetch_quote(params: dict) -> dict:
    """Fetch a stock quote."""
    symbol = params.get("symbol", "AAPL")
    await asyncio.sleep(0.01)  # Simulate API call
    return {
        "symbol": symbol,
        "price": 185.50,
        "volume": 45_000_000,
    }


async def analyze_quote(params: dict) -> dict:
    """Analyze a stock quote."""
    symbol = params.get("symbol", "AAPL")
    await asyncio.sleep(0.01)
    return {
        "symbol": symbol,
        "recommendation": "hold",
        "confidence": 0.75,
    }


async def main():
    print("=" * 60)
    print("Dispatcher Basics")
    print("=" * 60)
    
    # === Setup ===
    registry = HandlerRegistry()
    registry.register("task", "fetch_quote", fetch_quote)
    registry.register("task", "analyze_quote", analyze_quote)
    
    # Build handler map for MemoryExecutor
    handlers = {
        "task:fetch_quote": fetch_quote,
        "task:analyze_quote": analyze_quote,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    # === 1. Submit a task ===
    print("\n[1] Submit Task")
    run_id = await dispatcher.submit_task("fetch_quote", {"symbol": "MSFT"})
    print(f"  Submitted run_id: {run_id}")
    
    # === 2. Get run status ===
    print("\n[2] Get Run Status")
    run = await dispatcher.get_run(run_id)
    print(f"  Status: {run.status.value}")
    print(f"  Result: {run.result}")
    
    # === 3. Submit another task ===
    print("\n[3] Submit Another Task")
    run_id2 = await dispatcher.submit_task("analyze_quote", {"symbol": "NVDA"})
    run2 = await dispatcher.get_run(run_id2)
    print(f"  Task: analyze_quote")
    print(f"  Status: {run2.status.value}")
    print(f"  Result: {run2.result}")
    
    # === 4. List recent runs ===
    print("\n[4] List Recent Runs")
    runs = await dispatcher.list_runs(limit=10)
    print(f"  Total runs: {len(runs)}")
    for r in runs:
        print(f"    - {r.name}: {r.status.value}")
    
    # === 5. Submit with WorkSpec directly ===
    print("\n[5] Submit with WorkSpec")
    from spine.execution import WorkSpec
    
    spec = WorkSpec(
        kind="task",
        name="fetch_quote",
        params={"symbol": "GOOGL"},
        metadata={"priority_reason": "earnings"},
    )
    run_id3 = await dispatcher.submit(spec)
    run3 = await dispatcher.get_run(run_id3)
    print(f"  WorkSpec submitted: {spec.name}")
    print(f"  Result: {run3.result}")
    
    print("\n" + "=" * 60)
    print("[OK] Dispatcher Basics Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
