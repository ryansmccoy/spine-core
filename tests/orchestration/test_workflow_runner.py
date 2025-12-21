"""Tests for WorkflowRunner — execution modes, choice branching, error policies.

Covers sequential execution, choice branching, error-policy CONTINUE,
dry-run mode, WorkflowResult serialization, and parallel DAG execution.
Uses a minimal mock Runnable so tests don't depend on EventDispatcher.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from spine.execution.runnable import OperationRunResult, Runnable
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import ErrorPolicy, Step
from spine.orchestration.workflow import ExecutionMode, WorkflowExecutionPolicy, Workflow
from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.workflow_runner import (
    StepExecution,
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class StubRunnable:
    """Minimal Runnable for testing operation steps."""

    def submit_operation_sync(
        self,
        operation_name: str,
        params: dict[str, Any] | None = None,
        partition: dict[str, Any] | None = None,
        context: Any = None,
        **kwargs: Any,
    ) -> OperationRunResult:
        return OperationRunResult(
            run_id="test-run",
            status="completed",
            metrics=params or {},
        )


def _ok_step(ctx: WorkflowContext, config: dict) -> StepResult:
    return StepResult.ok(output={"handled": True})


def _fail_step(ctx: WorkflowContext, config: dict) -> StepResult:
    return StepResult.fail("intentional failure")


def _counter_step(ctx: WorkflowContext, config: dict) -> StepResult:
    n = ctx.get_param("n", 0) + 1
    return StepResult.ok(output={"n": n}, context_updates={"n": n})


# ---------------------------------------------------------------------------
# WorkflowStatus enum
# ---------------------------------------------------------------------------


class TestWorkflowStatus:
    def test_values(self):
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.COMPLETED.value == "completed"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.PARTIAL.value == "partial"


# ---------------------------------------------------------------------------
# Sequential execution
# ---------------------------------------------------------------------------


class TestSequentialExecution:
    def test_single_lambda(self):
        wf = Workflow(name="test.wf", steps=[Step.lambda_("step1", _ok_step)])
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert len(result.completed_steps) == 1
        assert result.context.has_output("step1")

    def test_multi_step(self):
        wf = Workflow(
            name="test.wf",
            steps=[
                Step.lambda_("a", _ok_step),
                Step.lambda_("b", _ok_step),
                Step.lambda_("c", _ok_step),
            ],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert result.completed_steps == ["a", "b", "c"]

    def test_with_params(self):
        def greet(ctx, config):
            name = ctx.get_param("name", "world")
            return StepResult.ok(output={"greeting": f"hello {name}"})

        wf = Workflow(name="test.wf", steps=[Step.lambda_("greet", greet)])
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf, params={"name": "spine"})
        assert result.context.get_output("greet", "greeting") == "hello spine"

    def test_context_updates_flow(self):
        """context_updates from one step are visible to the next."""

        def step_a(ctx, config):
            return StepResult.ok(context_updates={"computed": 42})

        def step_b(ctx, config):
            v = ctx.get_param("computed")
            return StepResult.ok(output={"doubled": v * 2})

        wf = Workflow(
            name="test.wf",
            steps=[Step.lambda_("a", step_a), Step.lambda_("b", step_b)],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.context.get_output("b", "doubled") == 84

    def test_operation_step(self):
        wf = Workflow(
            name="test.wf",
            steps=[Step.operation("ingest", "my.operation", params={"x": 1})],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED

    def test_start_from(self):
        wf = Workflow(
            name="test.wf",
            steps=[
                Step.lambda_("a", _ok_step),
                Step.lambda_("b", _ok_step),
                Step.lambda_("c", _ok_step),
            ],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf, start_from="b")
        assert "a" not in result.completed_steps
        assert "b" in result.completed_steps
        assert "c" in result.completed_steps


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    def test_stop_on_failure(self):
        wf = Workflow(
            name="test.wf",
            steps=[
                Step.lambda_("a", _ok_step),
                Step.lambda_("b", _fail_step),
                Step.lambda_("c", _ok_step),
            ],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED
        assert result.error_step == "b"
        assert "c" not in result.completed_steps

    def test_continue_on_failure(self):
        wf = Workflow(
            name="test.wf",
            steps=[
                Step.lambda_("a", _ok_step),
                Step.lambda_("b", _fail_step, on_error=ErrorPolicy.CONTINUE),
                Step.lambda_("c", _ok_step),
            ],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.PARTIAL
        assert "b" in result.failed_steps
        assert "c" in result.completed_steps


# ---------------------------------------------------------------------------
# Choice branching
# ---------------------------------------------------------------------------


class TestChoiceBranching:
    def test_then_branch(self):
        """Choice condition=True routes to then_step."""
        wf = Workflow(
            name="test.wf",
            steps=[
                Step.choice(
                    "check",
                    condition=lambda ctx: True,
                    then_step="target",
                    else_step="skip_me",
                ),
                Step.lambda_("skip_me", _ok_step),
                Step.lambda_("target", _ok_step),
            ],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert "target" in result.completed_steps

    def test_else_branch(self):
        """Choice condition=False routes to else_step."""
        wf = Workflow(
            name="test.wf",
            steps=[
                Step.choice(
                    "check",
                    condition=lambda ctx: False,
                    then_step="skip_me",
                    else_step="target",
                ),
                Step.lambda_("skip_me", _ok_step),
                Step.lambda_("target", _ok_step),
            ],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert "target" in result.completed_steps

    def test_choice_based_on_params(self):
        """Choice condition uses ctx.params for branching."""
        wf = Workflow(
            name="test.wf",
            steps=[
                Step.choice(
                    "route",
                    condition=lambda ctx: ctx.get_param("valid", False),
                    then_step="process",
                    else_step="reject",
                ),
                Step.lambda_("reject", _ok_step),
                Step.lambda_("process", _ok_step),
            ],
        )
        runner = WorkflowRunner(runnable=StubRunnable())

        # valid=True → process
        r1 = runner.execute(wf, params={"valid": True})
        assert "process" in r1.completed_steps

        # valid=False → reject
        r2 = runner.execute(wf, params={"valid": False})
        assert "reject" in r2.completed_steps


# ---------------------------------------------------------------------------
# Dry-run mode
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_flag(self):
        runner = WorkflowRunner(runnable=StubRunnable(), dry_run=True)
        wf = Workflow(name="test.wf", steps=[Step.lambda_("a", _ok_step)])
        result = runner.execute(wf)
        assert result.context.is_dry_run is True


# ---------------------------------------------------------------------------
# WorkflowResult serialization
# ---------------------------------------------------------------------------


class TestWorkflowResultSerialization:
    def test_to_dict(self):
        wf = Workflow(
            name="test.wf",
            steps=[Step.lambda_("a", _ok_step), Step.lambda_("b", _ok_step)],
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        d = result.to_dict()
        assert d["workflow_name"] == "test.wf"
        assert d["status"] == "completed"
        assert d["completed_steps"] == ["a", "b"]
        assert len(d["step_executions"]) == 2
        assert "started_at" in d
        assert d["duration_seconds"] is not None

    def test_failed_to_dict(self):
        wf = Workflow(name="test.wf", steps=[Step.lambda_("fail", _fail_step)])
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        d = result.to_dict()
        assert d["status"] == "failed"
        assert d["error_step"] == "fail"
        assert d["error"] is not None


# ---------------------------------------------------------------------------
# StepExecution
# ---------------------------------------------------------------------------


class TestStepExecution:
    def test_to_dict(self):
        se = StepExecution(
            step_name="s1",
            step_type="lambda",
            status="completed",
            result=StepResult.ok(output={"k": "v"}),
        )
        d = se.to_dict()
        assert d["step_name"] == "s1"
        assert d["output"]["k"] == "v"

    def test_duration_none_when_incomplete(self):
        se = StepExecution(step_name="s", step_type="lambda", status="running")
        assert se.duration_seconds is None


# ---------------------------------------------------------------------------
# Parallel DAG execution
# ---------------------------------------------------------------------------


class TestParallelExecution:
    def test_independent_steps(self):
        """Steps without dependencies run in parallel."""
        wf = Workflow(
            name="test.parallel",
            steps=[
                Step.lambda_("a", _ok_step, depends_on=[]),
                Step.lambda_("b", _ok_step, depends_on=[]),
                Step.lambda_("c", _ok_step, depends_on=["a", "b"]),
            ],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL, max_concurrency=2
            ),
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert set(result.completed_steps) == {"a", "b", "c"}

    def test_diamond_dag(self):
        """Diamond dependency: a -> b,c -> d."""
        wf = Workflow(
            name="test.diamond",
            steps=[
                Step.lambda_("a", _ok_step),
                Step.lambda_("b", _ok_step, depends_on=["a"]),
                Step.lambda_("c", _ok_step, depends_on=["a"]),
                Step.lambda_("d", _ok_step, depends_on=["b", "c"]),
            ],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL, max_concurrency=4
            ),
        )
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert set(result.completed_steps) == {"a", "b", "c", "d"}
