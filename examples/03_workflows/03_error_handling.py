#!/usr/bin/env python3
"""Error Handling - Managing failures in workflows.

This example demonstrates error handling patterns:
- Basic try/except
- Retries with backoff
- Fallback handlers
- Partial failure handling

Run: python examples/03_workflows/03_error_handling.py
"""
import asyncio
import random
from spine.execution import Dispatcher, HandlerRegistry, RunStatus
from spine.execution.executors import MemoryExecutor


# === Task handlers with various failure modes ===

async def reliable_task(params: dict) -> dict:
    """A task that always succeeds."""
    return {"status": "success", "data": params}


async def flaky_task(params: dict) -> dict:
    """A task that sometimes fails."""
    failure_rate = params.get("failure_rate", 0.5)
    
    if random.random() < failure_rate:
        raise RuntimeError("Random failure occurred")
    
    return {"status": "success", "attempts": params.get("attempt", 1)}


async def failing_task(params: dict) -> dict:
    """A task that always fails."""
    raise ValueError("This task always fails")


async def timeout_task(params: dict) -> dict:
    """A task that might timeout."""
    delay = params.get("delay", 1.0)
    await asyncio.sleep(delay)
    return {"status": "completed", "delay": delay}


async def fallback_task(params: dict) -> dict:
    """A fallback when primary fails."""
    return {"status": "fallback_used", "original_error": params.get("error")}


async def main():
    print("=" * 60)
    print("Error Handling")
    print("=" * 60)
    
    # === Setup ===
    registry = HandlerRegistry()
    registry.register("task", "reliable", reliable_task)
    registry.register("task", "flaky", flaky_task)
    registry.register("task", "failing", failing_task)
    registry.register("task", "timeout", timeout_task)
    registry.register("task", "fallback", fallback_task)
    
    handlers = {
        "task:reliable": reliable_task,
        "task:flaky": flaky_task,
        "task:failing": failing_task,
        "task:timeout": timeout_task,
        "task:fallback": fallback_task,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    # === 1. Basic error detection ===
    print("\n[1] Basic Error Detection")
    
    run_id = await dispatcher.submit_task("failing", {})
    run = await dispatcher.get_run(run_id)
    
    print(f"  Status: {run.status.value}")
    print(f"  Error: {run.error}")
    print(f"  Error Type: {run.error_type}")
    
    if run.status == RunStatus.FAILED:
        print("  → Task failed, need to handle error")
    
    # === 2. Retry with backoff ===
    print("\n[2] Retry with Backoff")
    
    async def retry_with_backoff(task_name: str, params: dict, max_retries: int = 3):
        """Retry a task with exponential backoff."""
        for attempt in range(1, max_retries + 1):
            run_id = await dispatcher.submit_task(task_name, {**params, "attempt": attempt})
            run = await dispatcher.get_run(run_id)
            
            if run.status == RunStatus.COMPLETED:
                print(f"    Attempt {attempt}: SUCCESS")
                return run.result
            
            print(f"    Attempt {attempt}: FAILED - {run.error}")
            
            if attempt < max_retries:
                wait_time = 0.1 * (2 ** (attempt - 1))  # Exponential backoff
                print(f"    Waiting {wait_time:.2f}s before retry...")
                await asyncio.sleep(wait_time)
        
        raise RuntimeError(f"All {max_retries} attempts failed")
    
    try:
        # Set low failure rate for demo
        result = await retry_with_backoff("flaky", {"failure_rate": 0.3}, max_retries=5)
        print(f"  Final result: {result}")
    except RuntimeError as e:
        print(f"  All retries exhausted: {e}")
    
    # === 3. Fallback pattern ===
    print("\n[3] Fallback Pattern")
    
    async def with_fallback(primary_task: str, fallback_task: str, params: dict):
        """Try primary task, use fallback on failure."""
        run_id = await dispatcher.submit_task(primary_task, params)
        run = await dispatcher.get_run(run_id)
        
        if run.status == RunStatus.COMPLETED:
            print(f"    Primary task succeeded")
            return run.result
        
        print(f"    Primary failed: {run.error}")
        print(f"    Using fallback...")
        
        fallback_id = await dispatcher.submit_task(fallback_task, {
            "error": run.error,
            "original_params": params,
        })
        fallback_run = await dispatcher.get_run(fallback_id)
        return fallback_run.result
    
    result = await with_fallback("failing", "fallback", {"data": "important"})
    print(f"  Result: {result}")
    
    # === 4. Partial failure handling ===
    print("\n[4] Partial Failure Handling")
    
    tasks = [
        ("reliable", {"id": 1}),
        ("failing", {"id": 2}),
        ("reliable", {"id": 3}),
        ("failing", {"id": 4}),
        ("reliable", {"id": 5}),
    ]
    
    # Submit all tasks
    run_ids = []
    for task_name, params in tasks:
        run_id = await dispatcher.submit_task(task_name, params)
        run_ids.append((task_name, params, run_id))
    
    # Collect results, handling failures
    successes = []
    failures = []
    
    for task_name, params, run_id in run_ids:
        run = await dispatcher.get_run(run_id)
        if run.status == RunStatus.COMPLETED:
            successes.append({"task": task_name, "params": params, "result": run.result})
        else:
            failures.append({"task": task_name, "params": params, "error": run.error})
    
    print(f"  Total tasks: {len(tasks)}")
    print(f"  Successes: {len(successes)}")
    print(f"  Failures: {len(failures)}")
    
    if failures:
        print("  Failed tasks:")
        for f in failures:
            print(f"    - {f['task']} (id={f['params']['id']}): {f['error']}")
    
    # === 5. Error aggregation ===
    print("\n[5] Error Aggregation")
    
    all_runs = await dispatcher.list_runs(limit=100)
    
    # Group by status
    by_status = {}
    for run in all_runs:
        status = run.status.value
        by_status.setdefault(status, []).append(run)
    
    print("  Run statistics:")
    for status, runs in sorted(by_status.items()):
        print(f"    {status}: {len(runs)}")
    
    # For detailed error analysis, fetch full RunRecord for failed runs
    failed_runs = by_status.get("failed", [])
    if failed_runs:
        print("  Failed run IDs:")
        for run_summary in failed_runs[:3]:  # Show first 3
            full_run = await dispatcher.get_run(run_summary.run_id)
            et = full_run.error_type or "unknown"
            print(f"    - {run_summary.run_id[:8]}... ({et})")
    
    print("\n" + "=" * 60)
    print("[OK] Error Handling Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
