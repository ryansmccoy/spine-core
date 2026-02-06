#!/usr/bin/env python3
"""Run Lifecycle - Understanding run states and transitions.

This example demonstrates the RunRecord lifecycle: how runs move
through states (pending → running → completed/failed).

Run: python examples/01_basics/04_run_lifecycle.py
"""
import asyncio
from spine.execution import Dispatcher, HandlerRegistry, RunStatus
from spine.execution.executors import MemoryExecutor


# === Handlers with different outcomes ===

async def successful_task(params: dict) -> dict:
    """A task that succeeds."""
    await asyncio.sleep(0.01)
    return {"status": "success", "data": params.get("data", "default")}


async def failing_task(params: dict) -> dict:
    """A task that raises an error."""
    await asyncio.sleep(0.01)
    raise ValueError("Simulated failure for demonstration")


async def slow_task(params: dict) -> dict:
    """A task that takes time."""
    delay = params.get("delay", 0.1)
    await asyncio.sleep(delay)
    return {"status": "completed", "delay": delay}


async def main():
    print("=" * 60)
    print("Run Lifecycle")
    print("=" * 60)
    
    # === Setup ===
    registry = HandlerRegistry()
    registry.register("task", "successful_task", successful_task)
    registry.register("task", "failing_task", failing_task)
    registry.register("task", "slow_task", slow_task)
    
    handlers = {
        "task:successful_task": successful_task,
        "task:failing_task": failing_task,
        "task:slow_task": slow_task,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    # === 1. Successful run lifecycle ===
    print("\n[1] Successful Run")
    run_id = await dispatcher.submit_task("successful_task", {"data": "test"})
    run = await dispatcher.get_run(run_id)
    
    print(f"  Run ID: {run_id[:8]}...")
    print(f"  Status: {run.status.value}")
    print(f"  Created At: {run.created_at}")
    print(f"  Completed At: {run.completed_at}")
    duration = run.duration_seconds if run.duration_seconds is not None else 0.0
    print(f"  Duration: {duration:.3f}s")
    print(f"  Result: {run.result}")
    
    # === 2. Failed run lifecycle ===
    print("\n[2] Failed Run")
    run_id2 = await dispatcher.submit_task("failing_task", {})
    run2 = await dispatcher.get_run(run_id2)
    
    print(f"  Status: {run2.status.value}")
    print(f"  Error: {run2.error}")
    print(f"  Error Type: {run2.error_type}")
    
    # === 3. Run status values ===
    print("\n[3] All Run Status Values")
    for status in RunStatus:
        print(f"  - {status.value}: {status.name}")
    
    # === 4. Filter runs by status ===
    print("\n[4] Filter by Status")
    all_runs = await dispatcher.list_runs(limit=100)
    
    completed = [r for r in all_runs if r.status == RunStatus.COMPLETED]
    failed = [r for r in all_runs if r.status == RunStatus.FAILED]
    
    print(f"  Completed: {len(completed)}")
    print(f"  Failed: {len(failed)}")
    
    # === 5. Run timing information ===
    print("\n[5] Run Timing")
    run_id3 = await dispatcher.submit_task("slow_task", {"delay": 0.05})
    run3 = await dispatcher.get_run(run_id3)
    
    print(f"  Created: {run3.created_at.isoformat()}")
    print(f"  Started: {run3.started_at.isoformat() if run3.started_at else 'N/A'}")
    print(f"  Completed: {run3.completed_at.isoformat() if run3.completed_at else 'N/A'}")
    duration3 = run3.duration_seconds if run3.duration_seconds is not None else 0.0
    print(f"  Duration: {duration3:.4f}s")
    
    # === 6. Run metadata ===
    print("\n[6] Run Metadata")
    from spine.execution import WorkSpec
    
    spec = WorkSpec(
        kind="task",
        name="successful_task",
        params={"data": "with_metadata"},
        metadata={"source": "example", "priority": "high"},
        trigger_source="manual",
    )
    run_id4 = await dispatcher.submit(spec)
    run4 = await dispatcher.get_run(run_id4)
    
    print(f"  Spec Kind: {run4.spec.kind}")
    print(f"  Spec Name: {run4.spec.name}")
    print(f"  Trigger Source: {run4.spec.trigger_source}")
    print(f"  Metadata: {run4.spec.metadata}")
    
    print("\n" + "=" * 60)
    print("[OK] Run Lifecycle Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
