#!/usr/bin/env python3
"""JobEngine — unified entry-point for job submission and lifecycle management.

================================================================================
WHY JobEngine?
================================================================================

Direct adapter calls scatter routing, validation, and tracking across call
sites.  ``JobEngine`` is the **single facade** that:

1. Routes specs to the correct runtime via ``RuntimeAdapterRouter``
2. Validates specs against adapter capabilities via ``SpecValidator``
3. Records executions in the ``ExecutionLedger`` for audit
4. Returns structured ``SubmitResult`` with spec hashing
5. Supports idempotent submissions via ``idempotency_key``

::

    User Code
        │
        ▼
    ┌──────────┐     ┌──────────────┐     ┌───────────────┐
    │ JobEngine│────▸│ SpecValidator│────▸│ RuntimeAdapter │
    │          │     └──────────────┘     └───────────────┘
    │          │────▸│ AdapterRouter│
    │          │     └──────────────┘
    │          │────▸│   Ledger     │
    │          │     └──────────────┘
    └──────────┘


================================================================================
WHAT THIS EXAMPLE DEMONSTRATES
================================================================================

::

    1  Engine construction — wire router + ledger + validator
    2  Job submission — spec → SubmitResult
    3  Status polling loop — wait for completion
    4  Cancellation — cancel via engine
    5  Log retrieval — stream logs through engine
    6  Idempotent re-submit — same key returns same result
    7  Job listing — list_jobs()
    8  Cleanup — resource release


================================================================================
RUN IT
================================================================================

::

    python examples/02_execution/20_job_engine_lifecycle.py

See Also:
    - ``19_local_process_adapter.py`` — Adapter-level API
    - ``21_runtime_router.py`` — Multi-adapter routing
    - ``src/spine/execution/runtimes/engine.py`` — Implementation
"""

import asyncio
import sqlite3

from spine.execution.runtimes import (
    ContainerJobSpec,
    JobEngine,
    RuntimeAdapterRouter,
    SpecValidator,
    StubRuntimeAdapter,
    SubmitResult,
)
from spine.execution.ledger import ExecutionLedger


# ── Section 1: Engine construction ────────────────────────────────────────

def build_engine():
    """Wire up the three dependencies and construct a JobEngine."""
    print("=" * 70)
    print("SECTION 1 — Engine Construction")
    print("=" * 70)

    # 1) Router — manages runtime adapters
    router = RuntimeAdapterRouter()

    # 2) Ledger — records execution history (in-memory SQLite)
    conn = sqlite3.connect(":memory:")
    from spine.core.schema import create_core_tables
    create_core_tables(conn)
    ledger = ExecutionLedger(conn)

    # 3) Validator — pre-submit spec checks
    validator = SpecValidator()

    # 4) Register a stub adapter (auto-succeeds, no real process)
    stub = StubRuntimeAdapter(auto_succeed=True)
    router.register(stub)

    # 5) Build the engine
    engine = JobEngine(router=router, ledger=ledger, validator=validator)

    print(f"  Router:     {router.list_runtimes()}")
    print(f"  Default:    {router.default_name}")
    print(f"  Engine:     {engine}")
    print("  ✓ Engine assembled\n")

    return engine, router, ledger, stub


# ── Section 2: Job submission ─────────────────────────────────────────────

def demo_submit(engine):
    """Submit a job spec and inspect the SubmitResult."""
    print("=" * 70)
    print("SECTION 2 — Job Submission")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="data-processor",
        image="python:3.12-slim",
        command=["python", "-c", "print('processing')"],
        timeout_seconds=300,
        labels={"team": "data-eng", "stage": "staging"},
    )

    async def run():
        result: SubmitResult = await engine.submit(spec)
        print(f"  execution_id: {result.execution_id}")
        print(f"  external_ref: {result.external_ref}")
        print(f"  runtime:      {result.runtime}")
        print(f"  spec_hash:    {result.spec_hash}")

        assert result.runtime == "stub"
        assert result.spec_hash  # Non-empty hash
        print("  ✓ Job submitted\n")
        return result

    return asyncio.run(run())


# ── Section 3: Status polling loop ────────────────────────────────────────

def demo_status_poll(engine, result):
    """Poll status until the job completes."""
    print("=" * 70)
    print("SECTION 3 — Status Polling")
    print("=" * 70)

    async def run():
        for attempt in range(5):
            status = await engine.status(result.execution_id)
            print(f"  Poll {attempt + 1}: state={status.state}")
            if status.state in ("succeeded", "failed", "cancelled"):
                break
            await asyncio.sleep(0.1)

        print(f"  Final state:  {status.state}")
        print(f"  Exit code:    {status.exit_code}")
        print("  ✓ Status polling complete\n")
        return status

    return asyncio.run(run())


# ── Section 4: Cancellation ───────────────────────────────────────────────

def demo_cancel(engine):
    """Submit a job and cancel it."""
    print("=" * 70)
    print("SECTION 4 — Cancellation")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="long-runner",
        image="python:3.12",
        command=["sleep", "3600"],
        timeout_seconds=3600,
    )

    async def run():
        result = await engine.submit(spec)
        print(f"  Submitted:    {result.execution_id}")

        cancelled = await engine.cancel(result.execution_id)
        print(f"  Cancelled:    {cancelled}")

        status = await engine.status(result.execution_id)
        print(f"  Final state:  {status.state}")
        print("  ✓ Cancellation complete\n")

    asyncio.run(run())


# ── Section 5: Log retrieval ──────────────────────────────────────────────

def demo_logs(engine, result):
    """Stream logs through the engine facade."""
    print("=" * 70)
    print("SECTION 5 — Log Retrieval")
    print("=" * 70)

    async def run():
        lines = []
        async for line in engine.logs(result.execution_id):
            lines.append(line)
            print(f"  LOG: {line}")

        print(f"  Total lines: {len(lines)}")
        print("  ✓ Logs retrieved\n")

    asyncio.run(run())


# ── Section 6: Idempotent re-submit ───────────────────────────────────────

def demo_idempotency(engine):
    """Submit the same spec twice with an idempotency key."""
    print("=" * 70)
    print("SECTION 6 — Idempotent Re-Submit")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="idempotent-job",
        image="python:3.12",
        command=["echo", "hello"],
        timeout_seconds=60,
        idempotency_key="unique-key-001",
    )

    async def run():
        r1 = await engine.submit(spec)
        r2 = await engine.submit(spec)

        print(f"  First submit:  execution_id={r1.execution_id}")
        print(f"  Second submit: execution_id={r2.execution_id}")
        print(f"  Same result:   {r1.execution_id == r2.execution_id}")
        assert r1.execution_id == r2.execution_id, "Idempotency violation!"
        print("  ✓ Idempotent re-submit returned same result\n")

    asyncio.run(run())


# ── Section 7: Job listing ────────────────────────────────────────────────

def demo_list_jobs(engine):
    """List all recorded executions via the ledger."""
    print("=" * 70)
    print("SECTION 7 — Job Listing")
    print("=" * 70)

    jobs = engine.list_jobs()
    print(f"  Total jobs tracked: {len(jobs)}")
    for j in jobs[:5]:  # Show first 5
        print(f"    {j.id[:12]}...  status={j.status.value}  workflow={j.workflow}")
    print("  ✓ Jobs listed\n")


# ── Section 8: Cleanup ────────────────────────────────────────────────────

def demo_cleanup(engine, result):
    """Release resources for a completed job."""
    print("=" * 70)
    print("SECTION 8 — Cleanup")
    print("=" * 70)

    async def run():
        await engine.cleanup(result.execution_id)
        print(f"  Cleaned up:   {result.execution_id}")
        print("  ✓ Resources released\n")

    asyncio.run(run())


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    engine, router, ledger, stub = build_engine()
    result = demo_submit(engine)
    demo_status_poll(engine, result)
    demo_cancel(engine)
    demo_logs(engine, result)
    demo_idempotency(engine)
    demo_list_jobs(engine)
    demo_cleanup(engine, result)
    print(f"  StubRuntimeAdapter stats:")
    print(f"    submit_count:  {stub.submit_count}")
    print(f"    cancel_count:  {stub.cancel_count}")
    print(f"    cleanup_count: {stub.cleanup_count}")
    print()
    print("=" * 70)
    print("ALL SECTIONS PASSED ✓")
    print("=" * 70)
