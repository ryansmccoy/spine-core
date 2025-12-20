#!/usr/bin/env python3
"""StubRuntimeAdapter — injectable test double for unit testing.

================================================================================
WHY StubRuntimeAdapter?
================================================================================

Testing Job Engine logic without real subprocesses or containers requires
a controllable test double.  ``StubRuntimeAdapter`` provides:

- Auto-succeed or auto-fail modes
- Injectable failure points (submit, cancel, health)
- Call counters (submit_count, cancel_count, cleanup_count)
- Predictable behavior for deterministic tests

This adapter is used throughout spine-core's own test suite and
is the recommended way to test any code that interacts with the
Job Engine.

::

    StubRuntimeAdapter
    ├── auto_succeed=True    → submit() always succeeds
    ├── fail_submit=True     → submit() always raises JobError
    ├── fail_cancel=True     → cancel() always raises JobError
    ├── fail_health=True     → health_check() returns unhealthy
    └── Counters: submit_count, cancel_count, cleanup_count


================================================================================
WHAT THIS EXAMPLE DEMONSTRATES
================================================================================

::

    1  Auto-succeed mode — jobs complete immediately
    2  Auto-fail submit — simulate submission failures
    3  Auto-fail cancel — simulate cancel failures
    4  Auto-fail health — simulate unhealthy runtime
    5  Call counters — verify interaction counts
    6  Capabilities and constraints — stub feature flags
    7  Integration with JobEngine — full engine test with stubs


================================================================================
RUN IT
================================================================================

::

    python examples/13_runtimes/02_stub_adapter.py

See Also:
    - ``02_execution/20_job_engine_lifecycle.py`` — Engine with StubRuntimeAdapter
    - ``src/spine/execution/runtimes/_base.py`` — Implementation
"""

import asyncio
import sqlite3

from spine.execution.runtimes import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    StubRuntimeAdapter,
    RuntimeAdapterRouter,
    JobEngine,
    SpecValidator,
)
from spine.execution.ledger import ExecutionLedger
from spine.core.schema import create_core_tables


def _make_spec(name="test-job"):
    return ContainerJobSpec(
        name=name, image="python:3.12",
        command=["echo", "hello"],
        timeout_seconds=60,
    )


# ── Section 1: Auto-succeed mode ─────────────────────────────────────────

def demo_auto_succeed():
    """Jobs auto-complete with success."""
    print("=" * 70)
    print("SECTION 1 — Auto-Succeed Mode")
    print("=" * 70)

    stub = StubRuntimeAdapter(auto_succeed=True)
    print(f"  runtime_name:  {stub.runtime_name}")
    print(f"  auto_succeed:  {stub.auto_succeed}")

    async def run():
        ref = await stub.submit(_make_spec())
        print(f"  Submitted:     ref={ref}")

        status = await stub.status(ref)
        print(f"  Status:        state={status.state}")
        assert status.state == "succeeded"
        print("  ✓ Auto-succeed works\n")

    asyncio.run(run())
    return stub


# ── Section 2: Submit failure injection ───────────────────────────────────

def demo_fail_submit():
    """Inject a submit failure."""
    print("=" * 70)
    print("SECTION 2 — Submit Failure Injection")
    print("=" * 70)

    stub = StubRuntimeAdapter()
    stub.fail_submit = True

    async def run():
        try:
            await stub.submit(_make_spec())
            print("  ERROR: Should have raised!")
        except JobError as err:
            print(f"  Category:  {err.category}")
            print(f"  Message:   {err.message}")
            print(f"  Retryable: {err.retryable}")
            assert err.category == ErrorCategory.RUNTIME_UNAVAILABLE
            print("  ✓ Submit failure injected correctly\n")

    asyncio.run(run())


# ── Section 3: Cancel failure injection ───────────────────────────────────

def demo_fail_cancel():
    """Inject a cancel failure."""
    print("=" * 70)
    print("SECTION 3 — Cancel Failure Injection")
    print("=" * 70)

    stub = StubRuntimeAdapter(auto_succeed=False)
    stub.fail_cancel = True

    async def run():
        ref = await stub.submit(_make_spec())
        print(f"  Submitted:  ref={ref}")

        try:
            result = await stub.cancel(ref)
            assert result is False, "cancel() should return False when fail_cancel=True"
            print("  ✓ Cancel returned False as expected\n")
        except JobError as err:
            print(f"  Category:  {err.category}")
            print(f"  Message:   {err.message}")
            print("  ✓ Cancel failure injected correctly\n")

    asyncio.run(run())


# ── Section 4: Health failure injection ───────────────────────────────────

def demo_fail_health():
    """Inject an unhealthy health check."""
    print("=" * 70)
    print("SECTION 4 — Health Failure Injection")
    print("=" * 70)

    stub = StubRuntimeAdapter()
    stub.fail_health = True

    async def run():
        health = await stub.health()
        print(f"  Healthy:   {health.healthy}")
        print(f"  Runtime:   {health.runtime}")
        print(f"  Message:   {health.message}")
        assert health.healthy is False
        print("  ✓ Unhealthy health check injected\n")

    asyncio.run(run())


# ── Section 5: Call counters ──────────────────────────────────────────────

def demo_call_counters():
    """Track how many times each operation was called."""
    print("=" * 70)
    print("SECTION 5 — Call Counters")
    print("=" * 70)

    stub = StubRuntimeAdapter(auto_succeed=True)

    async def run():
        # Submit 3 times
        refs = []
        for i in range(3):
            ref = await stub.submit(_make_spec(f"job-{i}"))
            refs.append(ref)

        # Cancel 1
        await stub.cancel(refs[0])

        # Cleanup 2
        await stub.cleanup(refs[1])
        await stub.cleanup(refs[2])

        print(f"  submit_count:  {stub.submit_count}")
        print(f"  cancel_count:  {stub.cancel_count}")
        print(f"  cleanup_count: {stub.cleanup_count}")

        assert stub.submit_count == 3
        assert stub.cancel_count == 1
        assert stub.cleanup_count == 2
        print("  ✓ Counters accurate\n")

    asyncio.run(run())


# ── Section 6: Capabilities ──────────────────────────────────────────────

def demo_capabilities():
    """Inspect stub adapter capabilities."""
    print("=" * 70)
    print("SECTION 6 — Stub Capabilities & Constraints")
    print("=" * 70)

    stub = StubRuntimeAdapter()
    caps = stub.capabilities
    constraints = stub.constraints

    print(f"  supports_gpu:             {caps.supports_gpu}")
    print(f"  supports_volumes:         {caps.supports_volumes}")
    print(f"  supports_sidecars:        {caps.supports_sidecars}")
    print(f"  supports_init_containers: {caps.supports_init_containers}")
    print(f"  supports_log_streaming:   {caps.supports_log_streaming}")
    print(f"  supports_artifacts:       {caps.supports_artifacts}")
    print(f"  constraints:              {constraints}")
    print("  ✓ Capabilities inspected\n")


# ── Section 7: Full engine test with stubs ────────────────────────────────

def demo_engine_integration():
    """Wire StubRuntimeAdapter into a full JobEngine for testing."""
    print("=" * 70)
    print("SECTION 7 — Full Engine Test with Stubs")
    print("=" * 70)

    stub = StubRuntimeAdapter(auto_succeed=True)
    router = RuntimeAdapterRouter()
    router.register(stub)

    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    ledger = ExecutionLedger(conn)
    validator = SpecValidator()

    engine = JobEngine(router=router, ledger=ledger, validator=validator)

    async def run():
        # Submit
        result = await engine.submit(_make_spec("engine-test"))
        print(f"  Submitted:   {result.execution_id[:12]}... runtime={result.runtime}")

        # Status
        status = await engine.status(result.execution_id)
        print(f"  Status:      {status.state}")

        # Logs
        log_lines = []
        async for line in engine.logs(result.execution_id):
            log_lines.append(line)
        print(f"  Log lines:   {len(log_lines)}")

        # Cleanup
        await engine.cleanup(result.execution_id)
        print(f"  Cleaned up:  ✓")

        # Verify counters
        print(f"\n  Stub stats:")
        print(f"    submit_count:  {stub.submit_count}")
        print(f"    cleanup_count: {stub.cleanup_count}")
        assert stub.submit_count == 1
        print("  ✓ Full engine test passed\n")

    asyncio.run(run())


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_auto_succeed()
    demo_fail_submit()
    demo_fail_cancel()
    demo_fail_health()
    demo_call_counters()
    demo_capabilities()
    demo_engine_integration()
    print("=" * 70)
    print("ALL SECTIONS PASSED ✓")
    print("=" * 70)
