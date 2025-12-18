#!/usr/bin/env python3
"""MemoryExecutor — In-Process Async Execution for Development and Testing.

================================================================================
WHY MEMORYEXECUTOR?
================================================================================

MemoryExecutor runs tasks directly in the current process via asyncio.
No external services, no threads, no serialization overhead::

    ┌──────────┐   submit    ┌──────────────┐   asyncio.run   ┌─────────┐
    │  Client  │────────────►│   Dispatcher │───────────────►│ Handler │
    │          │             │              │  (same process) │  (async)│
    └──────────┘             └──────────────┘                └─────────┘

When to use:
    ✓ Unit tests (fast, no infrastructure)
    ✓ Development (immediate feedback)
    ✓ Simple automation scripts
    ✓ Low-latency single-process pipelines

When NOT to use:
    ✗ CPU-bound work (blocks the event loop)
    ✗ Multi-worker parallelism (use LocalExecutor or Celery)
    ✗ Production workloads needing fault tolerance


================================================================================
EXECUTOR COMPARISON
================================================================================

::

    ┌──────────────────┬─────────────┬──────────────┬──────────────────────┐
    │ Executor         │ Concurrency │ Isolation    │ Best For             │
    ├──────────────────┼─────────────┼──────────────┼──────────────────────┤
    │ MemoryExecutor   │ async/await │ None (in-proc)│ Tests, dev, scripts │
    │ AsyncLocalExec   │ asyncio     │ None         │ I/O-bound async work│
    │ LocalExecutor    │ ThreadPool  │ Thread       │ I/O + light CPU     │
    │ CeleryExecutor   │ Worker pool │ Process/host │ Production scale    │
    └──────────────────┴─────────────┴──────────────┴──────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/05_memory_executor.py

See Also:
    - :mod:`spine.execution.executors` — MemoryExecutor, LocalExecutor
    - ``examples/02_execution/06_local_executor.py`` — ThreadPool executor
    - ``examples/02_execution/15_async_local_executor.py`` — Async executor
"""
import asyncio
from spine.execution import EventDispatcher, HandlerRegistry, WorkSpec
from spine.execution.executors import MemoryExecutor


# === Task handlers ===

async def process_data(params: dict) -> dict:
    """Process some data in memory."""
    data = params.get("data", [])
    processed = [item.upper() if isinstance(item, str) else item * 2 
                 for item in data]
    return {"original": data, "processed": processed}


async def compute_result(params: dict) -> dict:
    """Compute a result."""
    x = params.get("x", 0)
    y = params.get("y", 0)
    op = params.get("op", "add")
    
    operations = {
        "add": x + y,
        "subtract": x - y,
        "multiply": x * y,
        "divide": x / y if y != 0 else None,
    }
    
    return {"result": operations.get(op), "operation": op}


async def fetch_mock_data(params: dict) -> dict:
    """Simulate fetching data (with mock delay)."""
    await asyncio.sleep(0.01)  # Simulate network call
    return {
        "ticker": params.get("ticker", "UNKNOWN"),
        "price": 123.45,
        "volume": 1000000,
    }


async def main():
    print("=" * 60)
    print("Memory Executor")
    print("=" * 60)
    
    # === 1. Basic setup ===
    print("\n[1] Basic Setup")
    
    registry = HandlerRegistry()
    registry.register("task", "process_data", process_data)
    registry.register("task", "compute_result", compute_result)
    registry.register("task", "fetch_mock_data", fetch_mock_data)
    
    # Handler map for executor
    handlers = {
        "task:process_data": process_data,
        "task:compute_result": compute_result,
        "task:fetch_mock_data": fetch_mock_data,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    print(f"  Executor type: {type(executor).__name__}")
    print(f"  Registered handlers: {len(handlers)}")
    
    # === 2. Run single task ===
    print("\n[2] Single Task Execution")
    
    run_id = await dispatcher.submit_task("process_data", {"data": ["hello", "world"]})
    run = await dispatcher.get_run(run_id)
    
    print(f"  Status: {run.status.value}")
    print(f"  Result: {run.result}")
    
    # === 3. Run multiple tasks in parallel ===
    print("\n[3] Parallel Execution")
    
    # Submit multiple tasks at once
    run_ids = await asyncio.gather(
        dispatcher.submit_task("compute_result", {"x": 10, "y": 5, "op": "add"}),
        dispatcher.submit_task("compute_result", {"x": 10, "y": 5, "op": "multiply"}),
        dispatcher.submit_task("fetch_mock_data", {"ticker": "AAPL"}),
    )
    
    print(f"  Submitted {len(run_ids)} tasks in parallel")
    
    # Get all results
    for run_id in run_ids:
        run = await dispatcher.get_run(run_id)
        print(f"  - {run.spec.name}: {run.result}")
    
    # === 4. Memory executor characteristics ===
    print("\n[4] Memory Executor Characteristics")
    print("  ✓ In-process execution (no IPC overhead)")
    print("  ✓ Direct async/await support")
    print("  ✓ Shared memory access")
    print("  ✓ Immediate result availability")
    print("  ✗ No parallelism for CPU-bound tasks (single thread)")
    print("  ✗ No persistence across restarts")
    
    # === 5. WorkSpec submission ===
    print("\n[5] WorkSpec Submission")
    
    spec = WorkSpec(
        kind="task",
        name="process_data",
        params={"data": [1, 2, 3]},
        metadata={"source": "example"},
    )
    
    run_id = await dispatcher.submit(spec)
    run = await dispatcher.get_run(run_id)
    
    print(f"  Original: {run.result['original']}")
    print(f"  Processed: {run.result['processed']}")
    
    print("\n" + "=" * 60)
    print("[OK] Memory Executor Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
