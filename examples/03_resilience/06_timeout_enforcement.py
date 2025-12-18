#!/usr/bin/env python3
"""Timeout Enforcement — Deadlines and timeouts for reliable execution.

WHY TIMEOUTS MATTER
───────────────────
A pipeline without timeouts can hang indefinitely on a stalled network
call, a deadlocked database, or an unexpectedly large dataset.  One
hung worker blocks its thread/slot, reducing cluster throughput — and
if every worker hangs, the entire pipeline stalls.  Explicit timeouts
turn hangs into catchable exceptions with clear diagnostics.

ARCHITECTURE
────────────
    ┌────────────────────── Deadline Stack ──────────────────────┐
    │                                                            │
    │  with_deadline(10s, "outer")                               │
    │    │                                                       │
    │    ├── with_deadline(2s, "inner")   ← shortest wins        │
    │    │     │                                                  │
    │    │     └── check_deadline()  ← raises if inner expired   │
    │    │                                                       │
    │    └── get_remaining_deadline()  ← outer still active      │
    │                                                            │
    └────────────────────────────────────────────────────────────┘

    Deadlines nest via context-local storage.  The innermost
    (shortest) deadline governs.  When it exits, the outer
    deadline resumes.

TIMEOUT API SUMMARY
───────────────────
    API                      Type            Purpose
    ──────────────────────── ─────────────── ────────────────────────
    with_deadline(secs)      context mgr     Scoped deadline
    @timeout(secs)           decorator       Function-level timeout
    run_with_timeout(fn, s)  helper          One-shot timeout call
    check_deadline()         assertion       Raise if past deadline
    get_remaining_deadline() query           Seconds left (or None)
    DeadlineContext          dataclass       deadline, elapsed, remaining

TimeoutExpired EXCEPTION
────────────────────────
    TimeoutExpired(timeout, operation)
        .timeout    → float   (seconds allowed)
        .operation  → str     (what was running)
        inherits    → TimeoutError (stdlib)

    Being a stdlib TimeoutError subclass means existing
    `except TimeoutError` handlers catch it automatically.

BEST PRACTICES
──────────────
• Set timeouts at every network boundary (API calls, DB queries).
• Use nested deadlines to enforce per-step and per-pipeline limits.
• Call check_deadline() inside long loops to fail fast.
• Prefer @timeout decorator for simple function-level limits.
• Combine with RetryStrategy — set total deadline > sum of retries.

Run: python examples/03_resilience/06_timeout_enforcement.py

See Also:
    01_retry_strategies — bound total retry time with a deadline
    02_circuit_breaker — trip breaker after repeated timeouts
"""
import time

from spine.execution.timeout import (
    DeadlineContext,
    TimeoutExpired,
    check_deadline,
    get_remaining_deadline,
    run_with_timeout,
    timeout,
    with_deadline,
)


def main():
    print("=" * 60)
    print("Timeout Enforcement Examples")
    print("=" * 60)

    # === 1. Basic deadline context ===
    print("\n[1] Basic Deadline Context (with_deadline)")

    with with_deadline(5.0, "quick_operation") as ctx:
        time.sleep(0.01)
        print(f"  Operation completed")
        print(f"  Time remaining: {ctx.remaining():.2f}s")
        print(f"  Elapsed: {ctx.elapsed:.4f}s")
        print(f"  Expired: {ctx.is_expired()}")

    # === 2. Timeout exception ===
    print("\n[2] Timeout Raises TimeoutExpired")

    try:
        with with_deadline(0.05, "slow_operation"):
            time.sleep(0.2)
    except TimeoutExpired as e:
        print(f"  Caught: {e}")
        print(f"  Timeout was: {e.timeout}s")
        print(f"  Operation: {e.operation}")
        print(f"  Inherits TimeoutError: {isinstance(e, TimeoutError)}")

    # === 3. Nested deadlines ===
    print("\n[3] Nested Deadlines (shortest wins)")

    with with_deadline(10.0, "outer") as outer_ctx:
        print(f"  Outer remaining: {outer_ctx.remaining():.1f}s")

        with with_deadline(2.0, "inner") as inner_ctx:
            remaining = get_remaining_deadline()
            print(f"  Inner remaining: {remaining:.1f}s (inner deadline active)")

        remaining = get_remaining_deadline()
        print(f"  After inner exits: {remaining:.1f}s (outer deadline active)")

    # === 4. Timeout decorator ===
    print("\n[4] Timeout Decorator (@timeout)")

    @timeout(5.0)
    def fast_function():
        """A fast function that completes within the timeout."""
        time.sleep(0.01)
        return "completed"

    result = fast_function()
    print(f"  fast_function() = {result}")
    print(f"  Preserves __name__: {fast_function.__name__}")
    print(f"  Preserves __doc__: {fast_function.__doc__}")

    @timeout(0.05, operation="slow_task")
    def slow_function():
        time.sleep(0.2)
        return "never reached"

    try:
        slow_function()
    except TimeoutExpired as e:
        print(f"  slow_function() raised: {e.operation} timed out")

    # === 5. run_with_timeout helper ===
    print("\n[5] run_with_timeout Helper")

    def add(a, b, c=0):
        return a + b + c

    result = run_with_timeout(add, timeout_seconds=5.0, args=(1, 2), kwargs={"c": 3})
    print(f"  add(1, 2, c=3) = {result}")

    try:
        run_with_timeout(
            time.sleep, timeout_seconds=0.05,
            args=(1.0,), operation="long_sleep",
        )
    except TimeoutExpired as e:
        print(f"  time.sleep(1.0) timed out after {e.timeout}s")

    # === 6. check_deadline helper ===
    print("\n[6] check_deadline() - Manual Deadline Checks")

    outside = get_remaining_deadline()
    print(f"  Outside context: get_remaining_deadline() = {outside}")

    with with_deadline(5.0, "manual_check"):
        check_deadline()  # No raise — plenty of time
        print(f"  check_deadline() passed (not expired)")

    # === 7. DeadlineContext attributes ===
    print("\n[7] DeadlineContext Attributes")

    ctx = DeadlineContext(
        deadline=time.monotonic() + 30.0,
        timeout_seconds=30.0,
        operation="example_op",
    )
    print(f"  operation: {ctx.operation}")
    print(f"  timeout_seconds: {ctx.timeout_seconds}")
    print(f"  remaining: {ctx.remaining():.1f}s")
    print(f"  is_expired: {ctx.is_expired()}")

    print("\n" + "=" * 60)
    print("All timeout enforcement examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
