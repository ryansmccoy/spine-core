#!/usr/bin/env python3
"""AsyncLocalExecutor — Native asyncio Execution Without Thread Overhead.

================================================================================
WHY ASYNCLOCALEXECUTOR?
================================================================================

When your handlers are already ``async def``, using ThreadPool is wasteful::

    # BAD: Wrapping async in thread (unnecessary overhead)
    LocalExecutor → loop.run_in_executor(thread_pool, sync_wrapper(async_fn))

    # GOOD: Run directly on the event loop
    AsyncLocalExecutor → await handler(params)

AsyncLocalExecutor is ideal for I/O-bound work where handlers are natively
async: HTTP requests, database queries, LLM API calls.

Key properties:
    - **Zero thread overhead** — No GIL contention, no thread pool
    - **Natural backpressure** — asyncio handles task scheduling
    - **Easy cancellation** — ``task.cancel()`` works natively
    - **Low memory** — No thread stack per task (2KB vs 8MB)


================================================================================
EXECUTOR SELECTION GUIDE
================================================================================

::

    ┌──────────────────────────────────────────────────────────────────────┐
    │  "What kind of work are you doing?"                                  │
    │                                                                      │
    │  ┌─ I/O-bound + async handlers ──► AsyncLocalExecutor (this one)   │
    │  │                                                                   │
    │  ├─ I/O-bound + sync handlers ───► LocalExecutor (threaded)        │
    │  │                                                                   │
    │  ├─ Quick tests/dev ──────────────► MemoryExecutor                  │
    │  │                                                                   │
    │  ├─ Fan-out many async items ────► AsyncBatchExecutor               │
    │  │                                                                   │
    │  └─ Production scale ────────────► CeleryExecutor                   │
    └──────────────────────────────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/15_async_local_executor.py

See Also:
    - :mod:`spine.execution.executors` — AsyncLocalExecutor
    - ``examples/02_execution/16_async_batch_executor.py`` — Batch fan-out
    - ``examples/02_execution/07_async_patterns.py`` — Async coordination
"""

import asyncio

from spine.execution import EventDispatcher, HandlerRegistry, WorkSpec
from spine.execution.executors import AsyncLocalExecutor


# === Async handlers (native coroutines) ===


async def download_filing(params: dict) -> dict:
    """Simulate downloading an SEC filing."""
    url = params.get("url", "https://sec.gov/filing.txt")
    ticker = params.get("ticker", "AAPL")
    await asyncio.sleep(0.02)  # Simulate HTTP I/O
    return {
        "ticker": ticker,
        "url": url,
        "bytes": 102_400,
        "status": "downloaded",
    }


async def call_llm(params: dict) -> dict:
    """Simulate an async LLM API call."""
    prompt = params.get("prompt", "Summarise this filing")
    await asyncio.sleep(0.03)  # Simulate API latency
    return {
        "prompt_tokens": len(prompt.split()),
        "completion_tokens": 150,
        "summary": f"Summary of: {prompt[:40]}...",
    }


async def query_database(params: dict) -> dict:
    """Simulate an async database query."""
    table = params.get("table", "filings")
    await asyncio.sleep(0.01)  # Simulate DB round-trip
    return {
        "table": table,
        "row_count": 42,
        "query_ms": 12.5,
    }


async def main():
    print("=" * 60)
    print("AsyncLocalExecutor — I/O-Bound Async Execution")
    print("=" * 60)

    # === 1. Setup ===
    print("\n[1] Setup")

    executor = AsyncLocalExecutor(max_concurrency=5)
    executor.register("task", "download_filing", download_filing)
    executor.register("task", "call_llm", call_llm)
    executor.register("task", "query_database", query_database)

    print(f"  Executor: {executor.name}")
    print(f"  Max concurrency: 5 (asyncio.Semaphore)")
    print(f"  Active tasks: {executor.active_count}")

    # === 2. Submit a single task ===
    print("\n[2] Single Task Submission")

    spec = WorkSpec(kind="task", name="download_filing", params={
        "ticker": "MSFT",
        "url": "https://sec.gov/cgi-bin/viewer?action=view&cik=0000789019",
    })
    ref = await executor.submit(spec)
    print(f"  Submitted ref: {ref}")

    status = await executor.get_status(ref)
    print(f"  Status (immediate): {status}")

    # Wait for completion
    final_status = await executor.wait(ref, timeout=5.0)
    print(f"  Status (after wait): {final_status}")

    result = await executor.get_result(ref)
    print(f"  Result: {result}")

    # === 3. Parallel fan-out (semaphore-bounded) ===
    print("\n[3] Parallel Fan-Out (5 tasks, max_concurrency=5)")

    import time
    start = time.perf_counter()

    tickers = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"]
    refs = []
    for ticker in tickers:
        spec = WorkSpec(kind="task", name="download_filing", params={
            "ticker": ticker,
            "url": f"https://sec.gov/filings/{ticker}/10-K.txt",
        })
        ref = await executor.submit(spec)
        refs.append(ref)

    print(f"  Submitted {len(refs)} tasks")
    print(f"  Active tasks: {executor.active_count}")

    # Wait for all
    for ref in refs:
        await executor.wait(ref, timeout=5.0)

    elapsed = time.perf_counter() - start
    print(f"  All completed in {elapsed:.3f}s (concurrent, ~0.02s each)")

    for ref in refs:
        result = await executor.get_result(ref)
        print(f"    {result['ticker']}: {result['bytes']} bytes")

    # === 4. Mixed task types ===
    print("\n[4] Mixed Task Types")

    tasks = [
        WorkSpec(kind="task", name="download_filing", params={"ticker": "NVDA"}),
        WorkSpec(kind="task", name="call_llm", params={"prompt": "Summarise NVDA 10-K"}),
        WorkSpec(kind="task", name="query_database", params={"table": "entities"}),
    ]

    refs = [await executor.submit(spec) for spec in tasks]

    for ref in refs:
        await executor.wait(ref, timeout=5.0)
        status = await executor.get_status(ref)
        result = await executor.get_result(ref)
        print(f"  [{status}] {ref}: {result}")

    # === 5. Cancellation ===
    print("\n[5] Task Cancellation")

    spec = WorkSpec(kind="task", name="call_llm", params={"prompt": "Long analysis..."})
    ref = await executor.submit(spec)
    print(f"  Submitted: {ref}")

    cancelled = await executor.cancel(ref)
    print(f"  Cancelled: {cancelled}")

    await asyncio.sleep(0.05)  # Let cancellation propagate
    status = await executor.get_status(ref)
    print(f"  Status after cancel: {status}")

    # === 6. Characteristics ===
    print("\n[6] AsyncLocalExecutor Characteristics")
    print("  ✓ Native asyncio — no threads, no GIL contention")
    print("  ✓ Semaphore-bounded concurrency")
    print("  ✓ Ideal for I/O-bound work (HTTP, DB, LLM)")
    print("  ✓ Low overhead — coroutines are cheap")
    print("  ✗ CPU-bound work blocks the event loop → use ProcessExecutor")
    print("  ✗ Handlers must be async functions")

    print("\n" + "=" * 60)
    print("[OK] AsyncLocalExecutor Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
