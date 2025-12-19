"""Test Harness — utilities for testing workflows.

WHY
───
Testing workflows requires creating ``Runnable`` doubles, setting up
context, and asserting on step results.  This module provides
off-the-shelf helpers so test code is concise and expressive.

ARCHITECTURE
────────────
::

    Test doubles:
      StubRunnable              → always succeeds (configurable outputs)
      FailingRunnable           → always fails (configurable error)
      ScriptedRunnable          → returns pre-configured results per pipeline

    Assertion helpers:
      assert_workflow_completed(result)
      assert_workflow_failed(result, step=None)
      assert_step_output(result, step_name, key, value)
      assert_step_count(result, expected)
      assert_no_failures(result)

    Factories:
      make_workflow(*handlers)  → quick workflow from plain functions
      make_context(params)      → create a WorkflowContext
      make_runner(runnable)     → WorkflowRunner with defaults

BEST PRACTICES
──────────────
- Use ``StubRunnable`` for workflows that only have lambda steps.
- Use ``ScriptedRunnable`` to test specific pipeline result handling.
- Prefer ``assert_workflow_completed()`` over manual status checks.

Related modules:
    conftest.py (tests/orchestration/) — internal _NoOpRunnable
    workflow_runner.py                 — the runner under test
    step_result.py                     — StepResult assertions

Example::

    from spine.orchestration.testing import (
        StubRunnable,
        assert_workflow_completed,
        make_workflow,
    )

    def test_simple_workflow():
        wf = make_workflow(lambda ctx, cfg: {"count": 42})
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert_workflow_completed(result)
        assert_step_output(result, "step_1", "count", 42)
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from spine.execution.runnable import PipelineRunResult, Runnable
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.workflow_runner import (
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
)


# ---------------------------------------------------------------------------
# Test doubles (Runnable implementations for testing)
# ---------------------------------------------------------------------------


class StubRunnable:
    """Runnable that always returns success.

    Optionally returns pre-configured output for specific pipelines.

    Parameters
    ----------
    outputs
        Mapping of ``pipeline_name → metrics dict`` to return on
        success.  Pipelines not in the map return empty metrics.

    Example::

        runnable = StubRunnable(outputs={"data.fetch": {"rows": 100}})
        runner = WorkflowRunner(runnable=runnable)
    """

    def __init__(self, outputs: dict[str, dict[str, Any]] | None = None) -> None:
        self._outputs = outputs or {}
        self.calls: list[dict[str, Any]] = []

    def submit_pipeline_sync(
        self,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        *,
        parent_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PipelineRunResult:
        self.calls.append({
            "pipeline_name": pipeline_name,
            "params": params,
            "parent_run_id": parent_run_id,
            "correlation_id": correlation_id,
        })
        metrics = self._outputs.get(pipeline_name, {})
        return PipelineRunResult(
            status="completed",
            metrics=metrics,
            run_id=f"stub-{uuid.uuid4().hex[:8]}",
        )


class FailingRunnable:
    """Runnable that always returns failure.

    Parameters
    ----------
    error
        Error message to include in the result.
    fail_pipelines
        If set, only these pipelines fail — others succeed.

    Example::

        runnable = FailingRunnable(error="Connection refused")
    """

    def __init__(
        self,
        error: str = "Simulated failure",
        fail_pipelines: set[str] | None = None,
    ) -> None:
        self._error = error
        self._fail_pipelines = fail_pipelines
        self.calls: list[dict[str, Any]] = []

    def submit_pipeline_sync(
        self,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        *,
        parent_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PipelineRunResult:
        self.calls.append({
            "pipeline_name": pipeline_name,
            "params": params,
        })
        if self._fail_pipelines is None or pipeline_name in self._fail_pipelines:
            return PipelineRunResult(
                status="failed",
                error=self._error,
            )
        return PipelineRunResult(status="completed")


class ScriptedRunnable:
    """Runnable that returns pre-configured results per pipeline.

    Each pipeline can be assigned a specific ``PipelineRunResult``.
    Unregistered pipelines return a default success.

    Parameters
    ----------
    scripts
        Mapping of ``pipeline_name → PipelineRunResult``.

    Example::

        runnable = ScriptedRunnable(scripts={
            "data.fetch": PipelineRunResult(status="completed", metrics={"rows": 42}),
            "data.store": PipelineRunResult(status="failed", error="Disk full"),
        })
    """

    def __init__(
        self,
        scripts: dict[str, PipelineRunResult] | None = None,
    ) -> None:
        self._scripts = scripts or {}
        self.calls: list[dict[str, Any]] = []

    def submit_pipeline_sync(
        self,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        *,
        parent_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PipelineRunResult:
        self.calls.append({
            "pipeline_name": pipeline_name,
            "params": params,
        })
        if pipeline_name in self._scripts:
            return self._scripts[pipeline_name]
        return PipelineRunResult(status="completed")


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


class WorkflowAssertionError(AssertionError):
    """Raised when a workflow assertion fails.

    Provides contextual information about the workflow result.
    """

    def __init__(self, message: str, result: WorkflowResult) -> None:
        self.result = result
        super().__init__(f"{message}\n  Workflow: {result.workflow_name}\n  Status: {result.status.value}")


def assert_workflow_completed(result: WorkflowResult) -> None:
    """Assert that a workflow completed successfully.

    Raises
    ------
    WorkflowAssertionError
        If the workflow status is not ``COMPLETED``.
    """
    if result.status != WorkflowStatus.COMPLETED:
        raise WorkflowAssertionError(
            f"Expected COMPLETED, got {result.status.value}"
            + (f" (error at '{result.error_step}': {result.error})" if result.error else ""),
            result,
        )


def assert_workflow_failed(
    result: WorkflowResult,
    step: str | None = None,
    error_contains: str | None = None,
) -> None:
    """Assert that a workflow failed.

    Parameters
    ----------
    result
        The workflow result.
    step
        Expected failing step name (optional).
    error_contains
        Substring expected in the error message (optional).

    Raises
    ------
    WorkflowAssertionError
        If the workflow did not fail, or failed at a different step.
    """
    if result.status not in (WorkflowStatus.FAILED, WorkflowStatus.PARTIAL):
        raise WorkflowAssertionError(
            f"Expected FAILED or PARTIAL, got {result.status.value}",
            result,
        )
    if step and result.error_step != step:
        raise WorkflowAssertionError(
            f"Expected failure at '{step}', got '{result.error_step}'",
            result,
        )
    if error_contains and result.error and error_contains not in result.error:
        raise WorkflowAssertionError(
            f"Expected error containing '{error_contains}', got: {result.error}",
            result,
        )


def assert_step_output(
    result: WorkflowResult,
    step_name: str,
    key: str,
    expected: Any,
) -> None:
    """Assert that a step produced a specific output value.

    Parameters
    ----------
    result
        The workflow result.
    step_name
        Name of the step to check.
    key
        Output key to inspect.
    expected
        Expected value.

    Raises
    ------
    WorkflowAssertionError
        If the step is missing or the output doesn't match.
    """
    for step_exec in result.step_executions:
        if step_exec.step_name == step_name:
            if step_exec.result is None:
                raise WorkflowAssertionError(
                    f"Step '{step_name}' has no result",
                    result,
                )
            output = step_exec.result.output or {}
            if key not in output:
                raise WorkflowAssertionError(
                    f"Step '{step_name}' output missing key '{key}'. "
                    f"Available keys: {list(output.keys())}",
                    result,
                )
            actual = output[key]
            if actual != expected:
                raise WorkflowAssertionError(
                    f"Step '{step_name}' output['{key}']: "
                    f"expected {expected!r}, got {actual!r}",
                    result,
                )
            return

    raise WorkflowAssertionError(
        f"Step '{step_name}' not found in results. "
        f"Available: {[s.step_name for s in result.step_executions]}",
        result,
    )


def assert_step_count(result: WorkflowResult, expected: int) -> None:
    """Assert the number of executed steps.

    Parameters
    ----------
    result
        The workflow result.
    expected
        Expected number of step executions.

    Raises
    ------
    WorkflowAssertionError
        If the count doesn't match.
    """
    actual = result.total_steps
    if actual != expected:
        raise WorkflowAssertionError(
            f"Expected {expected} steps, got {actual}",
            result,
        )


def assert_no_failures(result: WorkflowResult) -> None:
    """Assert that no steps failed.

    Raises
    ------
    WorkflowAssertionError
        If any step has status ``'failed'``.
    """
    failures = result.failed_steps
    if failures:
        raise WorkflowAssertionError(
            f"Expected no failures, got {len(failures)}: {failures}",
            result,
        )


def assert_steps_ran(result: WorkflowResult, *step_names: str) -> None:
    """Assert that specific steps were executed.

    Parameters
    ----------
    result
        The workflow result.
    *step_names
        Step names that must appear in executions.

    Raises
    ------
    WorkflowAssertionError
        If any named step is missing.
    """
    executed = {s.step_name for s in result.step_executions}
    missing = set(step_names) - executed
    if missing:
        raise WorkflowAssertionError(
            f"Steps not executed: {sorted(missing)}. "
            f"Executed: {sorted(executed)}",
            result,
        )


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_workflow(
    *handlers: Callable[..., Any],
    name: str = "test.workflow",
    domain: str = "test",
) -> Workflow:
    """Create a quick test workflow from plain functions.

    Each handler becomes a ``Step.from_function()`` step named
    ``step_1``, ``step_2``, etc.

    Parameters
    ----------
    *handlers
        Callable functions. Each receives ``(ctx, config)`` or plain
        kwargs (adapted via ``Step.from_function``).
    name
        Workflow name.
    domain
        Domain tag.

    Returns
    -------
    Workflow
        A workflow with lambda steps.

    Example::

        wf = make_workflow(
            lambda ctx, cfg: StepResult.ok(output={"a": 1}),
            lambda ctx, cfg: StepResult.ok(output={"b": 2}),
        )
    """
    steps = [
        Step.lambda_(f"step_{i + 1}", handler)
        for i, handler in enumerate(handlers)
    ]
    return Workflow(name=name, steps=steps, domain=domain)


def make_context(
    params: dict[str, Any] | None = None,
    workflow_name: str = "test.workflow",
) -> WorkflowContext:
    """Create a WorkflowContext for testing.

    Parameters
    ----------
    params
        Input parameters.
    workflow_name
        Workflow name.

    Returns
    -------
    WorkflowContext
        A fresh context.
    """
    return WorkflowContext.create(
        workflow_name=workflow_name,
        params=params or {},
    )


def make_runner(
    runnable: Any | None = None,
    dry_run: bool = False,
) -> WorkflowRunner:
    """Create a WorkflowRunner with optional defaults.

    Parameters
    ----------
    runnable
        A ``Runnable`` implementation. Defaults to ``StubRunnable()``.
    dry_run
        Whether to run in dry-run mode.

    Returns
    -------
    WorkflowRunner
        A configured runner.
    """
    if runnable is None:
        runnable = StubRunnable()
    return WorkflowRunner(runnable=runnable, dry_run=dry_run)
