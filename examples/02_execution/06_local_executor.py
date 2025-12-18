#!/usr/bin/env python3
"""LocalExecutor — ThreadPool-Based Execution for I/O-Bound Concurrency.

================================================================================
WHY LOCALEXECUTOR?
================================================================================

LocalExecutor wraps ``concurrent.futures.ThreadPoolExecutor`` to run multiple
tasks concurrently without Celery or external infrastructure::

    # 5 SEC filings downloaded in parallel via thread pool
    executor = LocalExecutor(max_workers=5)
    for cik in ciks:
        dispatcher.submit(WorkSpec(name="fetch_filing", params={"cik": cik}))

Key properties:
    - **Synchronous handlers** — Uses regular ``def``, not ``async def``
    - **True concurrency** for I/O — Threads release the GIL during I/O
    - **Bounded parallelism** — ``max_workers`` prevents resource exhaustion
    - **Zero infrastructure** — No Redis, no RabbitMQ, no Celery

When to use:
    ✓ Downloading multiple files concurrently
    ✓ Parallel database queries (with thread-safe connections)
    ✓ Dev/staging environments without Celery
    ✓ Mixed I/O and light CPU work

When NOT to use:
    ✗ CPU-bound tasks (GIL limits true parallelism)
    ✗ Async handlers (use AsyncLocalExecutor instead)
    ✗ Production scale (use CeleryExecutor for fault tolerance)


================================================================================
ARCHITECTURE: THREAD POOL EXECUTION
================================================================================

::

    ┌──────────┐              ┌──────────────────────────────────┐
    │Dispatcher│  submit(5)   │     ThreadPoolExecutor(max=3)    │
    │          │─────────────►│                                  │
    └──────────┘              │  Thread 1: fetch_filing(CIK_1)  │
                              │  Thread 2: fetch_filing(CIK_2)  │
                              │  Thread 3: fetch_filing(CIK_3)  │
                              │  ─── queued ───                  │
                              │  fetch_filing(CIK_4)            │
                              │  fetch_filing(CIK_5)            │
                              └──────────────────────────────────┘

    Important: Handlers must be SYNCHRONOUS (``def``, not ``async def``)
    because ThreadPoolExecutor wraps them with ``loop.run_in_executor()``.


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/06_local_executor.py

See Also:
    - :mod:`spine.execution.executors` — LocalExecutor
    - ``examples/02_execution/05_memory_executor.py`` — In-process async
    - ``examples/02_execution/15_async_local_executor.py`` — Async alternative
"""
import asyncio
from spine.execution import EventDispatcher, HandlerRegistry, WorkSpec
from spine.execution.executors import LocalExecutor


# === Task handlers (must be synchronous for ThreadPoolExecutor) ===

def cpu_intensive_task(params: dict) -> dict:
    """Simulate a CPU-intensive operation."""
    iterations = params.get("iterations", 1000)
    result = 0
    for i in range(iterations):
        result += i * i
    return {"iterations": iterations, "result": result}


def data_transform(params: dict) -> dict:
    """Transform data in a worker thread."""
    data = params.get("data", [])
    transform = params.get("transform", "upper")
    
    if transform == "upper":
        transformed = [str(d).upper() for d in data]
    elif transform == "reverse":
        transformed = list(reversed(data))
    else:
        transformed = data
    
    return {"original": data, "transformed": transformed}


def isolated_operation(params: dict) -> dict:
    """An operation that runs in thread pool."""
    import os
    import threading
    return {
        "pid": os.getpid(),
        "thread": threading.current_thread().name,
        "params": params,
    }


async def main():
    print("=" * 60)
    print("Local Executor")
    print("=" * 60)
    
    # === 1. Setup with LocalExecutor ===
    print("\n[1] Setup with LocalExecutor")
    
    registry = HandlerRegistry()
    registry.register("task", "cpu_intensive_task", cpu_intensive_task)
    registry.register("task", "data_transform", data_transform)
    registry.register("task", "isolated_operation", isolated_operation)
    
    handlers = {
        "task:cpu_intensive_task": cpu_intensive_task,
        "task:data_transform": data_transform,
        "task:isolated_operation": isolated_operation,
    }
    
    # LocalExecutor with worker configuration
    executor = LocalExecutor(handlers=handlers, max_workers=2)
    dispatcher = EventDispatcher(executor=executor, registry=registry)
    
    print(f"  Executor type: {type(executor).__name__}")
    print(f"  Max workers: 2")
    
    # === 2. Run task in thread pool ===
    print("\n[2] ThreadPool Execution")
    
    run_id = await dispatcher.submit_task("isolated_operation", {"value": "test"})
    # Give thread pool time to execute
    await asyncio.sleep(0.1)
    run = await dispatcher.get_run(run_id)
    
    import os
    current_pid = os.getpid()
    print(f"  Main process PID: {current_pid}")
    if run.result:
        print(f"  Task thread: {run.result.get('thread', 'N/A')}")
        print(f"  Task PID: {run.result.get('pid', 'N/A')}")
    else:
        print(f"  Status: {run.status.value}")
    
    # === 3. Concurrent CPU tasks ===
    print("\n[3] Concurrent CPU Tasks")
    
    # Submit multiple CPU tasks
    run_ids = []
    for i in range(3):
        run_id = await dispatcher.submit_task(
            "cpu_intensive_task",
            {"iterations": 1000 * (i + 1)}
        )
        run_ids.append(run_id)
    
    # Wait for all to complete
    await asyncio.sleep(0.2)
    
    # Collect results
    for i, run_id in enumerate(run_ids):
        run = await dispatcher.get_run(run_id)
        if run.result:
            print(f"  Task {i + 1}: iterations={run.result['iterations']}, result={run.result['result']}")
        else:
            print(f"  Task {i + 1}: status={run.status.value}")
    
    # === 4. Data transformation ===
    print("\n[4] Data Transformation")
    
    spec = WorkSpec(
        kind="task",
        name="data_transform",
        params={"data": ["apple", "banana", "cherry"], "transform": "upper"},
    )
    
    run_id = await dispatcher.submit(spec)
    await asyncio.sleep(0.1)
    run = await dispatcher.get_run(run_id)
    
    if run.result:
        print(f"  Original: {run.result['original']}")
        print(f"  Transformed: {run.result['transformed']}")
    else:
        print(f"  Status: {run.status.value}")
    
    # === 5. Local executor characteristics ===
    print("\n[5] LocalExecutor Characteristics")
    print("  ✓ Non-blocking submission (uses ThreadPoolExecutor)")
    print("  ✓ Configurable worker count")
    print("  ✓ Good for development and small-scale production")
    print("  ✓ No external dependencies (no Celery/Redis)")
    print("  ✗ GIL limits CPU parallelism (use ProcessPoolExecutor for CPU)")
    print("  ✗ Handlers must be synchronous (not async)")
    
    # Cleanup
    executor.pool.shutdown(wait=False)
    
    print("\n" + "=" * 60)
    print("[OK] Local Executor Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
