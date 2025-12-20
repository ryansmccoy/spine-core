#!/usr/bin/env python3
"""Mock Runtime Adapters — test doubles for edge-case simulation.

Demonstrates five specialised ``BaseRuntimeAdapter`` implementations for
testing error handling, timeout logic, retry strategies, state-machine
transitions, and latency injection without real container infrastructure.

Demonstrates:
    1. ``FailingAdapter``   — always raises a configured JobError
    2. ``SlowAdapter``      — configurable latency injection
    3. ``FlakeyAdapter``    — probabilistic success/failure with counters
    4. ``SequenceAdapter``  — scripted state progression
    5. ``LatencyAdapter``   — decorator wrapping another adapter

Architecture::

    BaseRuntimeAdapter  (abstract)
    ├── StubRuntimeAdapter    (existing — auto-succeed/fail)
    ├── FailingAdapter        (always raises JobError)
    ├── SlowAdapter           (submit_delay, status_delay)
    ├── FlakeyAdapter         (success_rate + seeded RNG)
    ├── SequenceAdapter       (states=["pending","running","succeeded"])
    └── LatencyAdapter        (wraps inner adapter + delay)

    Usage:
        adapter = FlakeyAdapter(success_rate=0.7, seed=42)
        ref = await adapter.submit(spec)   # ~70% success
        status = await adapter.status(ref)  # check outcome

Key Concepts:
    - **FailingAdapter**: Test error-category routing and retry decisions.
    - **SlowAdapter**: Test timeout handling and poll-loop behavior.
    - **FlakeyAdapter**: Test circuit breakers and resilience patterns.
    - **SequenceAdapter**: Test multi-state transitions and polling.
    - **LatencyAdapter**: Compose with any adapter to add network delay.

See Also:
    - ``02_stub_adapter.py`` (category 13) — basic StubRuntimeAdapter
    - ``20_job_engine_lifecycle.py``        — JobEngine integration
    - :mod:`spine.execution.runtimes.mock_adapters`

Run:
    python examples/13_runtimes/04_mock_adapters.py

Expected Output:
    Each adapter section shows its behavior — deterministic failures,
    delays, probabilistic outcomes, state sequences, and latency wrapping.
"""

import asyncio

from spine.execution.runtimes._types import ContainerJobSpec, ErrorCategory, JobError
from spine.execution.runtimes._base import StubRuntimeAdapter
from spine.execution.runtimes.mock_adapters import (
    FailingAdapter,
    SlowAdapter,
    FlakeyAdapter,
    SequenceAdapter,
    LatencyAdapter,
)


def _make_spec(name: str = "test-job") -> ContainerJobSpec:
    return ContainerJobSpec(name=name, image="busybox:latest")


async def _run() -> None:
    # ------------------------------------------------------------------
    # 1. FailingAdapter — deterministic errors
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("1. FailingAdapter — always raises JobError")
    print(f"{'='*60}")

    adapter = FailingAdapter(category=ErrorCategory.OOM, message="Out of memory")
    try:
        await adapter.submit(_make_spec("oom-job"))
    except JobError as e:
        print(f"   Caught: {e.category.value} — {e.message}")
        print(f"   Retryable: {e.retryable}")

    health = await adapter.health()
    print(f"   Health: healthy={health.healthy}, message={health.message}")

    # ------------------------------------------------------------------
    # 2. SlowAdapter — latency injection
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("2. SlowAdapter — configurable delays")
    print(f"{'='*60}")

    adapter = SlowAdapter(submit_delay=0.3, status_delay=0.05, auto_succeed=True)
    import time

    t0 = time.monotonic()
    ref = await adapter.submit(_make_spec("slow-job"))
    elapsed = time.monotonic() - t0
    print(f"   Submit took: {elapsed:.2f}s (configured: 0.30s)")
    print(f"   Job ref:     {ref}")

    status = await adapter.status(ref)
    print(f"   Status:      {status.state} (exit_code={status.exit_code})")

    # ------------------------------------------------------------------
    # 3. FlakeyAdapter — probabilistic failures
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("3. FlakeyAdapter — probabilistic success/failure")
    print(f"{'='*60}")

    adapter = FlakeyAdapter(success_rate=0.6, seed=42)
    successes, failures = 0, 0
    for i in range(20):
        try:
            await adapter.submit(_make_spec(f"flakey-{i}"))
            successes += 1
        except JobError:
            failures += 1

    print(f"   Total:     {adapter.submit_count}")
    print(f"   Successes: {adapter.success_count} ({adapter.success_count/adapter.submit_count:.0%})")
    print(f"   Failures:  {adapter.failure_count} ({adapter.failure_count/adapter.submit_count:.0%})")
    print(f"   Target rate: 60%")

    # ------------------------------------------------------------------
    # 4. SequenceAdapter — scripted state transitions
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("4. SequenceAdapter — scripted state machine")
    print(f"{'='*60}")

    adapter = SequenceAdapter(states=["pending", "running", "running", "succeeded"])
    ref = await adapter.submit(_make_spec("seq-job"))

    for i in range(5):
        status = await adapter.status(ref)
        print(f"   Poll {i+1}: state={status.state}, exit_code={status.exit_code}")

    # ------------------------------------------------------------------
    # 5. LatencyAdapter — decorator pattern
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("5. LatencyAdapter — wraps another adapter with delay")
    print(f"{'='*60}")

    inner = StubRuntimeAdapter()
    adapter = LatencyAdapter(inner=inner, latency=0.2)
    print(f"   Runtime name: {adapter.runtime_name}")

    t0 = time.monotonic()
    ref = await adapter.submit(_make_spec("latency-job"))
    elapsed = time.monotonic() - t0
    print(f"   Submit took:  {elapsed:.2f}s (delay=0.20s + inner)")
    print(f"   Job ref:      {ref}")

    health = await adapter.health()
    print(f"   Health:       healthy={health.healthy}")

    # ------------------------------------------------------------------
    # 6. Multiple jobs on SequenceAdapter
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("6. Multiple independent jobs on SequenceAdapter")
    print(f"{'='*60}")

    adapter = SequenceAdapter(states=["pending", "running", "succeeded"])
    ref_a = await adapter.submit(_make_spec("job-a"))
    ref_b = await adapter.submit(_make_spec("job-b"))

    sa1 = await adapter.status(ref_a)
    sb1 = await adapter.status(ref_b)
    print(f"   Job A poll 1: {sa1.state}")
    print(f"   Job B poll 1: {sb1.state}")

    sa2 = await adapter.status(ref_a)
    print(f"   Job A poll 2: {sa2.state}")
    print(f"   Job B still:  {sb1.state}")

    print(f"\n{'='*60}")
    print("Done — mock adapters example complete")
    print(f"{'='*60}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
