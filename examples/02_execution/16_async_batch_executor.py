#!/usr/bin/env python3
"""AsyncBatchExecutor — Bounded Fan-Out for Concurrent Async Operations.

================================================================================
WHY ASYNCBATCHEXECUTOR?
================================================================================

When you need to run 100+ async operations concurrently with bounded
parallelism::

    # BAD: Unbounded — launches 10,000 requests simultaneously
    results = await asyncio.gather(*[fetch(url) for url in urls])
    # → API rate limits, memory exhaustion, connection pool overflow

    # GOOD: Bounded to 10 concurrent with fluent API
    executor = AsyncBatchExecutor(max_concurrency=10)
    executor.add("fetch_10k", params={"cik": "0001318605"})
    executor.add("fetch_10k", params={"cik": "0000320193"})
    # ... add 998 more ...
    result = await executor.run_all()
    # → Max 10 concurrent, rest queued via semaphore

Key properties:
    - **Semaphore-bounded** — Never exceed ``max_concurrency``
    - **Fluent API** — ``.add().add().run_all()`` pattern
    - **Aggregate results** — ``BatchResult`` with success/failure counts
    - **Error isolation** — One failure doesn't cancel others


================================================================================
ARCHITECTURE: SEMAPHORE-BOUNDED FAN-OUT
================================================================================

::

    executor.add(spec_1)                  ┌──── handler(spec_1) ─── ✓
    executor.add(spec_2)    run_all()     ├──── handler(spec_2) ─── ✓
    executor.add(spec_3)  ─────────────►  ├──── handler(spec_3) ─── ✗
    executor.add(spec_4)                  │     ─── queued ───
    executor.add(spec_5)                  ├──── handler(spec_4) ─── ✓
                                          └──── handler(spec_5) ─── ✓
                            Semaphore(3)
                            max 3 concurrent    AsyncBatchResult
                                                total=5, ok=4, failed=1


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/16_async_batch_executor.py

See Also:
    - :mod:`spine.execution` — AsyncBatchExecutor, AsyncBatchItem
    - ``examples/02_execution/11_batch_execution.py`` — Sync batch executor
    - ``examples/02_execution/15_async_local_executor.py`` — Single async executor
"""

import asyncio

from spine.execution import (
    AsyncBatchExecutor,
    AsyncBatchItem,
    AsyncBatchResult,
)


# === Async handlers ===


async def download_page(params: dict) -> dict:
    """Simulate downloading a web page."""
    url = params.get("url", "https://example.com")
    await asyncio.sleep(0.02)
    return {"url": url, "size_kb": 45, "status_code": 200}


async def fetch_filing(params: dict) -> dict:
    """Simulate fetching an SEC filing."""
    accession = params.get("accession", "0000000000-00-000000")
    await asyncio.sleep(0.03)
    return {"accession": accession, "pages": 120, "format": "html"}


async def flaky_download(params: dict) -> dict:
    """Simulate a download that might fail."""
    url = params.get("url", "")
    if "bad" in url:
        raise ConnectionError(f"Failed to connect to {url}")
    await asyncio.sleep(0.01)
    return {"url": url, "ok": True}


async def main():
    print("=" * 60)
    print("AsyncBatchExecutor — Fan-Out Batch Execution")
    print("=" * 60)

    # === 1. Basic batch ===
    print("\n[1] Basic Batch (3 items)")

    batch = AsyncBatchExecutor(max_concurrency=10)
    batch.add("page_1", download_page, {"url": "https://sec.gov/filings"})
    batch.add("page_2", download_page, {"url": "https://finra.org/data"})
    batch.add("page_3", download_page, {"url": "https://edgar.sec.gov"})

    result = await batch.run_all()

    print(f"  Batch ID: {result.batch_id[:12]}...")
    print(f"  Total: {result.total}")
    print(f"  Succeeded: {result.succeeded}")
    print(f"  Failed: {result.failed}")
    print(f"  Duration: {result.duration_seconds:.3f}s")

    for item in result.items:
        print(f"    [{item.status}] {item.name}: {item.result}")

    # === 2. Fluent chaining ===
    print("\n[2] Fluent Chaining (.add().add().run_all())")

    result = await (
        AsyncBatchExecutor(max_concurrency=5)
        .add("filing_1", fetch_filing, {"accession": "0000320193-24-000001"})
        .add("filing_2", fetch_filing, {"accession": "0000789019-24-000001"})
        .add("filing_3", fetch_filing, {"accession": "0001318605-24-000001"})
        .add("filing_4", fetch_filing, {"accession": "0001652044-24-000001"})
        .run_all()
    )

    print(f"  Batch: {result.succeeded}/{result.total} succeeded")
    print(f"  Duration: {result.duration_seconds:.3f}s")

    # === 3. Handling partial failures ===
    print("\n[3] Partial Failure Handling")

    batch = AsyncBatchExecutor(max_concurrency=5)
    batch.add("good_1", flaky_download, {"url": "https://good-server.com/data"})
    batch.add("bad_1", flaky_download, {"url": "https://bad-server.com/fail"})
    batch.add("good_2", flaky_download, {"url": "https://good-server.com/more"})
    batch.add("bad_2", flaky_download, {"url": "https://bad-server.com/nope"})
    batch.add("good_3", flaky_download, {"url": "https://good-server.com/last"})

    result = await batch.run_all()

    print(f"  Total: {result.total}")
    print(f"  Succeeded: {result.succeeded}")
    print(f"  Failed: {result.failed}")

    for item in result.items:
        if item.status == "completed":
            print(f"    ✓ {item.name}: OK")
        else:
            print(f"    ✗ {item.name}: {item.error}")

    # === 4. Concurrency control ===
    print("\n[4] Concurrency Control (20 items, max_concurrency=3)")

    import time

    async def slow_task(params: dict) -> dict:
        await asyncio.sleep(0.05)
        return {"id": params.get("id")}

    batch = AsyncBatchExecutor(max_concurrency=3)
    for i in range(20):
        batch.add(f"task_{i:02d}", slow_task, {"id": i})

    print(f"  Items queued: {batch.item_count}")

    start = time.perf_counter()
    result = await batch.run_all()
    elapsed = time.perf_counter() - start

    # With 20 tasks at 0.05s each and max_concurrency=3:
    # Sequential: 1.0s, Fully parallel: 0.05s, Bounded(3): ~0.35s
    print(f"  Duration: {elapsed:.3f}s")
    print(f"  Succeeded: {result.succeeded}/{result.total}")
    print(f"  (Sequential would be ~1.0s, fully parallel ~0.05s)")

    # === 5. Result serialisation ===
    print("\n[5] Result Serialisation (.to_dict())")

    result_dict = result.to_dict()
    print(f"  Keys: {list(result_dict.keys())}")
    print(f"  batch_id: {result_dict['batch_id'][:12]}...")
    print(f"  succeeded: {result_dict['succeeded']}")
    print(f"  failed: {result_dict['failed']}")
    print(f"  items (first 3):")
    for item in result_dict["items"][:3]:
        print(f"    {item['name']}: {item['status']} ({item['duration_seconds']:.3f}s)")

    # === 6. Per-item timing ===
    print("\n[6] Per-Item Timing")

    batch = AsyncBatchExecutor(max_concurrency=5)
    batch.add("fast", download_page, {"url": "https://fast.com"})
    batch.add("medium", fetch_filing, {"accession": "0000320193-24-000001"})

    result = await batch.run_all()

    for item in result.items:
        dur = f"{item.duration_seconds:.3f}s" if item.duration_seconds else "N/A"
        print(f"  {item.name}: {dur}")

    # === Comparison ===
    print("\n[Comparison] When to use which executor")
    print("  AsyncBatchExecutor:")
    print("    ✓ Fan-out N items with bounded concurrency")
    print("    ✓ Fluent .add().add().run_all() API")
    print("    ✓ Per-item error isolation")
    print("    ✓ Best for: bulk downloads, API crawling, batch LLM calls")
    print()
    print("  AsyncLocalExecutor:")
    print("    ✓ Long-lived executor with persistent handler registry")
    print("    ✓ submit/wait/cancel lifecycle per task")
    print("    ✓ Best for: server-mode execution engine")
    print()
    print("  BatchExecutor (sync, 02_execution/11):")
    print("    ✓ Thread-based with ExecutionLedger persistence")
    print("    ✓ Best for: DB-tracked batch runs with retry")

    print("\n" + "=" * 60)
    print("[OK] AsyncBatchExecutor Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
