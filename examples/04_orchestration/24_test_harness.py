#!/usr/bin/env python3
"""Test Harness — utilities for testing workflows.

Demonstrates the test harness module for writing concise, expressive
workflow tests with test doubles, assertion helpers, and factories.

Demonstrates:
    1. ``StubRunnable``             — always-succeeds test double
    2. ``FailingRunnable``          — always-fails test double
    3. ``ScriptedRunnable``         — pre-configured responses
    4. ``assert_workflow_completed`` — assertion helper
    5. ``assert_step_output``       — output value checking
    6. ``make_workflow``            — quick workflow factory
    7. ``make_runner``              — quick runner factory

Architecture::

    Test Doubles:
      StubRunnable          → always succeeds
      FailingRunnable       → always fails
      ScriptedRunnable      → scripted per-operation results

    Assertions:
      assert_workflow_completed(result)
      assert_workflow_failed(result, step=...)
      assert_step_output(result, step, key, value)
      assert_step_count(result, n)
      assert_no_failures(result)

    Factories:
      make_workflow(*handlers)   → Workflow from functions
      make_runner(runnable)      → WorkflowRunner with defaults

Key Concepts:
    - Test doubles replace real ``Runnable`` backends.
    - Assertion helpers provide clear error messages.
    - Factories minimise boilerplate in tests.

See Also:
    - ``01_workflow_basics.py``    — workflow construction
    - ``22_composition_operators.py`` — build testable workflows
    - :mod:`spine.orchestration.testing`

Run:
    python examples/04_orchestration/24_test_harness.py

Expected Output:
    Demonstrations of test doubles, assertions, and workflow testing
    patterns with clear pass/fail indicators.
"""

from spine.execution.runnable import OperationRunResult
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step
from spine.orchestration.testing import (
    FailingRunnable,
    ScriptedRunnable,
    StubRunnable,
    WorkflowAssertionError,
    assert_no_failures,
    assert_step_count,
    assert_step_output,
    assert_steps_ran,
    assert_workflow_completed,
    assert_workflow_failed,
    make_runner,
    make_workflow,
)
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_runner import WorkflowRunner


def main() -> None:
    # ------------------------------------------------------------------
    # 1. StubRunnable — always succeeds
    # ------------------------------------------------------------------
    print("=" * 60)
    print("1. StubRunnable — Always Succeeds")
    print("=" * 60)

    stub = StubRunnable(outputs={"data.fetch": {"rows": 100}})
    runner = WorkflowRunner(runnable=stub)

    wf = Workflow(
        name="test.stub",
        steps=[Step.operation("fetch", "data.fetch")],
    )
    result = runner.execute(wf)
    print(f"  Status: {result.status.value}")
    print(f"  Calls tracked: {len(stub.calls)}")
    print(f"  Operation called: {stub.calls[0]['operation_name']}")
    print()

    # ------------------------------------------------------------------
    # 2. FailingRunnable — always fails
    # ------------------------------------------------------------------
    print("=" * 60)
    print("2. FailingRunnable — Simulated Failures")
    print("=" * 60)

    failing = FailingRunnable(error="Connection timeout")
    runner = WorkflowRunner(runnable=failing)
    result = runner.execute(wf)
    print(f"  Status: {result.status.value}")
    print(f"  Error: {result.error}")
    print()

    # ------------------------------------------------------------------
    # 3. ScriptedRunnable — per-operation responses
    # ------------------------------------------------------------------
    print("=" * 60)
    print("3. ScriptedRunnable — Scripted Responses")
    print("=" * 60)

    scripted = ScriptedRunnable(scripts={
        "data.fetch": OperationRunResult(status="completed", metrics={"rows": 42}),
        "data.store": OperationRunResult(status="failed", error="Disk full"),
    })
    print(f"  fetch result: {scripted.submit_operation_sync('data.fetch').status}")
    print(f"  store result: {scripted.submit_operation_sync('data.store').status}")
    print()

    # ------------------------------------------------------------------
    # 4. make_workflow — quick factory
    # ------------------------------------------------------------------
    print("=" * 60)
    print("4. make_workflow() — Quick Workflow Factory")
    print("=" * 60)

    wf = make_workflow(
        lambda ctx, cfg: StepResult.ok(output={"count": 10}),
        lambda ctx, cfg: StepResult.ok(output={"processed": True}),
    )
    print(f"  Name: {wf.name}")
    print(f"  Steps: {[s.name for s in wf.steps]}")
    print()

    # ------------------------------------------------------------------
    # 5. Assertion helpers — pass case
    # ------------------------------------------------------------------
    print("=" * 60)
    print("5. Assertion Helpers — Passing")
    print("=" * 60)

    runner = make_runner()
    result = runner.execute(wf)

    assert_workflow_completed(result)
    print("  assert_workflow_completed: PASS")

    assert_step_count(result, 2)
    print("  assert_step_count(2): PASS")

    assert_no_failures(result)
    print("  assert_no_failures: PASS")

    assert_step_output(result, "step_1", "count", 10)
    print("  assert_step_output(step_1, count, 10): PASS")

    assert_steps_ran(result, "step_1", "step_2")
    print("  assert_steps_ran(step_1, step_2): PASS")
    print()

    # ------------------------------------------------------------------
    # 6. Assertion helpers — failure detection
    # ------------------------------------------------------------------
    print("=" * 60)
    print("6. Assertion Helpers — Failure Detection")
    print("=" * 60)

    fail_wf = make_workflow(
        lambda ctx, cfg: StepResult.fail("Something broke"),
    )
    result = runner.execute(fail_wf)

    assert_workflow_failed(result, step="step_1")
    print("  assert_workflow_failed(step_1): PASS")

    assert_workflow_failed(result, error_contains="broke")
    print("  assert_workflow_failed(error_contains='broke'): PASS")

    # Test that wrong assertion raises
    try:
        assert_workflow_completed(result)
        print("  ERROR: should have raised!")
    except WorkflowAssertionError as e:
        print(f"  WorkflowAssertionError caught: {e.args[0][:50]}...")
    print()

    print("All test harness examples completed successfully!")


if __name__ == "__main__":
    main()
