#!/usr/bin/env python3
"""LocalProcessAdapter — run container specs as local subprocesses.

================================================================================
WHY LocalProcessAdapter?
================================================================================

Docker is not always available — CI runners, restricted servers, dev machines
without Docker Desktop.  ``LocalProcessAdapter`` implements the full
``RuntimeAdapter`` lifecycle (submit / status / cancel / logs / cleanup/
artifacts) using ``asyncio.create_subprocess_exec``, so workflows work
locally with **zero container runtime**.

::

    ContainerJobSpec field     │ Local equivalent
    ──────────────────────────┼───────────────────────────
    image                      │ ignored (runs host binary)
    command + args             │ subprocess argv
    env                        │ os.environ overlay
    working_dir                │ subprocess cwd
    timeout_seconds            │ asyncio.wait_for + kill
    artifacts_dir              │ local directory listing


================================================================================
WHAT THIS EXAMPLE DEMONSTRATES
================================================================================

::

    1  Basic submit + status — run "python -c 'print(...)'"
    2  Log capture — stdout / stderr collection
    3  Timeout enforcement — SIGKILL on deadline exceeded
    4  Cancellation — SIGTERM → SIGKILL escalation
    5  Capability reporting — what local execution supports
    6  Health check — always-healthy (no daemon)
    7  Environment variables — spec.env overlay + SPINE_RUNTIME marker
    8  Artifacts — list files written to artifacts_dir
    9  Command-not-found error handling

================================================================================
RUN IT
================================================================================

::

    python examples/02_execution/19_local_process_adapter.py

See Also:
    - ``18_hot_reload_adapter.py`` — Config hot-reload wrapper
    - ``examples/04_orchestration/14_container_runnable.py`` — Workflow bridge
    - ``src/spine/execution/runtimes/local_process.py`` — Implementation
"""

import asyncio
import sys

from spine.execution.runtimes import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    LocalProcessAdapter,
)


# ── Section 1: Basic submit + status ──────────────────────────────────────

def demo_basic_submit():
    """Submit a simple Python command and check its status."""
    print("=" * 70)
    print("SECTION 1 — Basic Submit + Status")
    print("=" * 70)

    adapter = LocalProcessAdapter()

    spec = ContainerJobSpec(
        name="hello-world",
        image="ignored",  # No image needed for local runs
        command=[sys.executable, "-c", "print('Hello from LocalProcessAdapter!')"],
        timeout_seconds=10,
    )

    async def run():
        ref = await adapter.submit(spec)
        print(f"  Submitted:    ref={ref}")

        # Wait briefly for process to finish
        await asyncio.sleep(0.5)

        status = await adapter.status(ref)
        print(f"  State:        {status.state}")
        print(f"  Exit code:    {status.exit_code}")
        print(f"  Started at:   {status.started_at}")
        print(f"  Finished at:  {status.finished_at}")
        assert status.state == "succeeded", f"Expected succeeded, got {status.state}"
        print("  ✓ Job completed successfully\n")

    asyncio.run(run())


# ── Section 2: Log capture ────────────────────────────────────────────────

def demo_log_capture():
    """Capture stdout and stderr from a subprocess."""
    print("=" * 70)
    print("SECTION 2 — Log Capture (stdout + stderr)")
    print("=" * 70)

    adapter = LocalProcessAdapter()

    script = """
import sys
print("Line 1: stdout message")
print("Line 2: another stdout line")
print("Line 3: warning message", file=sys.stderr)
print("Line 4: done")
"""

    spec = ContainerJobSpec(
        name="log-demo",
        image="ignored",
        command=[sys.executable, "-c", script],
        timeout_seconds=10,
    )

    async def run():
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)

        # Collect all log lines
        lines = []
        async for line in adapter.logs(ref):
            lines.append(line)
            print(f"  LOG: {line}")

        print(f"\n  Total lines captured: {len(lines)}")

        # Tail: get last 2 lines
        tail_lines = []
        async for line in adapter.logs(ref, tail=2):
            tail_lines.append(line)
        print(f"  Last 2 lines (tail): {tail_lines}")
        print("  ✓ Logs captured\n")

    asyncio.run(run())


# ── Section 3: Timeout enforcement ────────────────────────────────────────

def demo_timeout():
    """Demonstrate timeout killing a long-running process."""
    print("=" * 70)
    print("SECTION 3 — Timeout Enforcement")
    print("=" * 70)

    adapter = LocalProcessAdapter()

    # Sleep for 60s but timeout after 1s
    spec = ContainerJobSpec(
        name="timeout-test",
        image="ignored",
        command=[sys.executable, "-c", "import time; time.sleep(60)"],
        timeout_seconds=1,
    )

    async def run():
        ref = await adapter.submit(spec)
        print(f"  Submitted:    ref={ref}")
        print(f"  Timeout:      {spec.timeout_seconds}s")

        # Wait for timeout to trigger
        await asyncio.sleep(2)

        status = await adapter.status(ref)
        print(f"  State:        {status.state}")
        print(f"  Exit code:    {status.exit_code}")
        assert status.state == "failed", f"Expected failed, got {status.state}"
        print("  ✓ Process killed after timeout\n")

    asyncio.run(run())


# ── Section 4: Cancellation ───────────────────────────────────────────────

def demo_cancel():
    """Cancel a running process (SIGTERM → SIGKILL)."""
    print("=" * 70)
    print("SECTION 4 — Cancellation (SIGTERM → SIGKILL)")
    print("=" * 70)

    adapter = LocalProcessAdapter(kill_timeout_seconds=1.0)

    spec = ContainerJobSpec(
        name="cancellable-job",
        image="ignored",
        command=[sys.executable, "-c", "import time; time.sleep(300)"],
        timeout_seconds=300,
    )

    async def run():
        ref = await adapter.submit(spec)
        print(f"  Submitted:    ref={ref}")

        # Let it start
        await asyncio.sleep(0.3)
        status = await adapter.status(ref)
        print(f"  Running:      state={status.state}")

        # Cancel it
        cancelled = await adapter.cancel(ref)
        print(f"  Cancelled:    {cancelled}")

        status = await adapter.status(ref)
        print(f"  Final state:  {status.state}")
        assert status.state == "cancelled", f"Expected cancelled, got {status.state}"
        print("  ✓ Process cancelled cleanly\n")

    asyncio.run(run())


# ── Section 5: Capability reporting ───────────────────────────────────────

def demo_capabilities():
    """Show what LocalProcessAdapter supports and doesn't."""
    print("=" * 70)
    print("SECTION 5 — Capability Reporting")
    print("=" * 70)

    adapter = LocalProcessAdapter()
    caps = adapter.capabilities

    print(f"  supports_gpu:             {caps.supports_gpu}")
    print(f"  supports_volumes:         {caps.supports_volumes}")
    print(f"  supports_sidecars:        {caps.supports_sidecars}")
    print(f"  supports_init_containers: {caps.supports_init_containers}")
    print(f"  supports_log_streaming:   {caps.supports_log_streaming}")
    print(f"  supports_artifacts:       {caps.supports_artifacts}")
    print(f"  supports_exec_into:       {caps.supports_exec_into}")
    print(f"  supports_spot:            {caps.supports_spot}")

    assert caps.supports_artifacts is True
    assert caps.supports_gpu is False
    print("  ✓ Capabilities match expectations\n")


# ── Section 6: Health check ───────────────────────────────────────────────

def demo_health():
    """Health check — always healthy (no external daemon)."""
    print("=" * 70)
    print("SECTION 6 — Health Check")
    print("=" * 70)

    adapter = LocalProcessAdapter()

    async def run():
        health = await adapter.health()
        print(f"  Healthy:      {health.healthy}")
        print(f"  Runtime:      {health.runtime}")
        print(f"  Version:      {health.version}")
        print(f"  Message:      {health.message}")
        print(f"  Latency:      {health.latency_ms}ms")
        assert health.healthy is True
        print("  ✓ Health check passed\n")

    asyncio.run(run())


# ── Section 7: Environment variables ──────────────────────────────────────

def demo_env_vars():
    """Pass environment variables to the subprocess."""
    print("=" * 70)
    print("SECTION 7 — Environment Variables")
    print("=" * 70)

    # inherit_env=False: ONLY spec.env is passed (plus SPINE_RUNTIME/SPINE_JOB_NAME)
    adapter = LocalProcessAdapter(inherit_env=False)

    script = """
import os
for k in sorted(os.environ):
    print(f"{k}={os.environ[k]}")
"""

    spec = ContainerJobSpec(
        name="env-test",
        image="ignored",
        command=[sys.executable, "-c", script],
        env={"MY_API_KEY": "secret-123", "DEBUG": "true"},
        timeout_seconds=10,
    )

    async def run():
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)

        lines = []
        async for line in adapter.logs(ref):
            lines.append(line)

        # Check that our env vars are present
        env_dict = {}
        for line in lines:
            if "=" in line:
                k, v = line.split("=", 1)
                env_dict[k] = v
                print(f"  ENV: {k}={v}")

        assert env_dict.get("MY_API_KEY") == "secret-123"
        assert env_dict.get("SPINE_RUNTIME") == "local"
        assert env_dict.get("SPINE_JOB_NAME") == "env-test"
        print("  ✓ Environment variables propagated\n")

    asyncio.run(run())


# ── Section 8: Command-not-found error ────────────────────────────────────

def demo_command_not_found():
    """Demonstrate structured error for missing commands."""
    print("=" * 70)
    print("SECTION 8 — Command-Not-Found Error Handling")
    print("=" * 70)

    adapter = LocalProcessAdapter()

    spec = ContainerJobSpec(
        name="bad-command",
        image="ignored",
        command=["nonexistent_program_xyz_12345"],
        timeout_seconds=5,
    )

    async def run():
        try:
            await adapter.submit(spec)
            print("  ERROR: Should have raised JobError")
        except JobError as err:
            print(f"  Category:     {err.category}")
            print(f"  Message:      {err.message}")
            print(f"  Retryable:    {err.retryable}")
            print(f"  Runtime:      {err.runtime}")
            assert err.category == ErrorCategory.NOT_FOUND
            assert err.retryable is False
            print("  ✓ Command-not-found handled correctly\n")

    asyncio.run(run())


# ── Section 9: Cleanup ────────────────────────────────────────────────────

def demo_cleanup():
    """Clean up resources after job completion."""
    print("=" * 70)
    print("SECTION 9 — Cleanup")
    print("=" * 70)

    adapter = LocalProcessAdapter()

    spec = ContainerJobSpec(
        name="cleanup-test",
        image="ignored",
        command=[sys.executable, "-c", "print('done')"],
        timeout_seconds=10,
    )

    async def run():
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)

        status_before = await adapter.status(ref)
        print(f"  Before cleanup: state={status_before.state}")

        # Cleanup
        await adapter.cleanup(ref)
        print("  Cleanup called")

        # Status still queryable after cleanup
        status_after = await adapter.status(ref)
        print(f"  After cleanup:  state={status_after.state}")
        print("  ✓ Cleanup successful (status still queryable)\n")

    asyncio.run(run())


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_basic_submit()
    demo_log_capture()
    demo_timeout()
    demo_cancel()
    demo_capabilities()
    demo_health()
    demo_env_vars()
    demo_command_not_found()
    demo_cleanup()
    print("=" * 70)
    print("ALL SECTIONS PASSED ✓")
    print("=" * 70)
