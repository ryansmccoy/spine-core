"""Tests for workflow_runner.py and workflow_context.py to boost coverage."""
from __future__ import annotations

import pytest

from spine.orchestration.step_result import ErrorCategory, QualityMetrics, StepResult
from spine.orchestration.step_types import ErrorPolicy, Step, StepType
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow import WorkflowExecutionPolicy
from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.workflow_runner import (
    StepExecution,
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
    get_workflow_runner,
)


# =============================================================================
# WorkflowContext
# =============================================================================


class TestWorkflowContext:
    """Test WorkflowContext creation and mutation."""

    def test_create_basic(self):
        ctx = WorkflowContext.create(workflow_name="test")
        assert ctx.workflow_name == "test"
        assert ctx.params == {}
        assert ctx.outputs == {}
        assert ctx.run_id  # Non-empty

    def test_create_with_params(self):
        ctx = WorkflowContext.create(
            workflow_name="test",
            params={"key": "value"},
            partition={"tier": "1"},
            batch_id="batch-1",
            run_id="run-123",
            dry_run=True,
        )
        assert ctx.params == {"key": "value"}
        assert ctx.partition == {"tier": "1"}
        assert ctx.run_id == "run-123"
        assert ctx.is_dry_run

    def test_with_output_immutable(self):
        ctx = WorkflowContext.create(workflow_name="test")
        ctx2 = ctx.with_output("step1", {"count": 42})
        assert ctx.outputs == {}  # Original unchanged
        assert ctx2.outputs == {"step1": {"count": 42}}

    def test_with_params_immutable(self):
        ctx = WorkflowContext.create(workflow_name="test", params={"a": 1})
        ctx2 = ctx.with_params({"b": 2})
        assert ctx.params == {"a": 1}
        assert ctx2.params == {"a": 1, "b": 2}

    def test_with_metadata_immutable(self):
        ctx = WorkflowContext.create(workflow_name="test")
        ctx2 = ctx.with_metadata({"extra": "info"})
        assert "extra" not in ctx.metadata
        assert ctx2.metadata["extra"] == "info"

    def test_get_param(self):
        ctx = WorkflowContext.create(workflow_name="test", params={"k": "v"})
        assert ctx.get_param("k") == "v"
        assert ctx.get_param("missing", "default") == "default"

    def test_get_output_key(self):
        ctx = WorkflowContext.create(workflow_name="test")
        ctx = ctx.with_output("step1", {"count": 42, "name": "test"})
        assert ctx.get_output("step1", "count") == 42
        assert ctx.get_output("step1", "missing", 0) == 0

    def test_get_output_full(self):
        ctx = WorkflowContext.create(workflow_name="test")
        ctx = ctx.with_output("step1", {"count": 42})
        assert ctx.get_output("step1") == {"count": 42}

    def test_get_output_missing_step(self):
        ctx = WorkflowContext.create(workflow_name="test")
        assert ctx.get_output("nonexistent") is None
        assert ctx.get_output("nonexistent", default="fallback") == "fallback"

    def test_has_output(self):
        ctx = WorkflowContext.create(workflow_name="test")
        assert not ctx.has_output("step1")
        ctx = ctx.with_output("step1", {"data": True})
        assert ctx.has_output("step1")

    def test_execution_id(self):
        ctx = WorkflowContext.create(workflow_name="test")
        assert ctx.execution_id  # Non-empty

    def test_batch_id(self):
        ctx = WorkflowContext.create(workflow_name="test", batch_id="b1")
        assert ctx.batch_id == "b1"

    def test_from_dict(self):
        data = {
            "run_id": "r1",
            "workflow_name": "test",
            "params": {"x": 1},
            "outputs": {"s1": {"v": 2}},
            "partition": {"tier": "A"},
            "started_at": "2026-01-01T00:00:00+00:00",
            "metadata": {"dry_run": True},
            "execution": {
                "execution_id": "e1",
                "batch_id": "b1",
            },
        }
        ctx = WorkflowContext.from_dict(data)
        assert ctx.run_id == "r1"
        assert ctx.workflow_name == "test"
        assert ctx.params == {"x": 1}
        assert ctx.outputs == {"s1": {"v": 2}}
        assert ctx.is_dry_run

    def test_from_dict_minimal(self):
        ctx = WorkflowContext.from_dict({})
        assert ctx.workflow_name == ""
        assert ctx.params == {}


# =============================================================================
# StepExecution
# =============================================================================


class TestStepExecution:
    """Test StepExecution dataclass."""

    def test_duration_seconds(self):
        from datetime import UTC, datetime, timedelta

        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = start + timedelta(seconds=5.5)
        se = StepExecution(
            step_name="s",
            step_type="lambda",
            status="completed",
            started_at=start,
            completed_at=end,
        )
        assert se.duration_seconds == pytest.approx(5.5)

    def test_duration_seconds_incomplete(self):
        se = StepExecution(step_name="s", step_type="lambda", status="running")
        assert se.duration_seconds is None

    def test_to_dict(self):
        from datetime import UTC, datetime

        start = datetime(2026, 1, 1, tzinfo=UTC)
        result = StepResult.ok(output={"k": "v"})
        se = StepExecution(
            step_name="s",
            step_type="pipeline",
            status="completed",
            started_at=start,
            completed_at=start,
            result=result,
        )
        d = se.to_dict()
        assert d["step_name"] == "s"
        assert d["output"] == {"k": "v"}

    def test_to_dict_no_result(self):
        se = StepExecution(step_name="s", step_type="lambda", status="failed", error="boom")
        d = se.to_dict()
        assert d["output"] is None


# =============================================================================
# WorkflowResult
# =============================================================================


class TestWorkflowResult:
    """Test WorkflowResult dataclass."""

    def test_completed_steps(self):
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        wr = WorkflowResult(
            workflow_name="test",
            run_id="r1",
            status=WorkflowStatus.COMPLETED,
            context=WorkflowContext.create(workflow_name="test"),
            started_at=now,
            completed_at=now,
            step_executions=[
                StepExecution(step_name="s1", step_type="lambda", status="completed"),
                StepExecution(step_name="s2", step_type="pipeline", status="failed"),
                StepExecution(step_name="s3", step_type="lambda", status="completed"),
            ],
        )
        assert wr.completed_steps == ["s1", "s3"]
        assert wr.failed_steps == ["s2"]
        assert wr.total_steps == 3

    def test_duration(self):
        from datetime import UTC, datetime, timedelta

        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = start + timedelta(seconds=10)
        wr = WorkflowResult(
            workflow_name="test",
            run_id="r1",
            status=WorkflowStatus.COMPLETED,
            context=WorkflowContext.create(workflow_name="test"),
            started_at=start,
            completed_at=end,
        )
        assert wr.duration_seconds == pytest.approx(10.0)

    def test_duration_none_when_incomplete(self):
        from datetime import UTC, datetime

        wr = WorkflowResult(
            workflow_name="test",
            run_id="r1",
            status=WorkflowStatus.RUNNING,
            context=WorkflowContext.create(workflow_name="test"),
            started_at=datetime.now(UTC),
        )
        assert wr.duration_seconds is None

    def test_to_dict(self):
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        wr = WorkflowResult(
            workflow_name="test",
            run_id="r1",
            status=WorkflowStatus.FAILED,
            context=WorkflowContext.create(workflow_name="test"),
            started_at=now,
            completed_at=now,
            error_step="bad_step",
            error="something broke",
        )
        d = wr.to_dict()
        assert d["status"] == "failed"
        assert d["error_step"] == "bad_step"
        assert d["error"] == "something broke"


# =============================================================================
# WorkflowRunner
# =============================================================================


class TestWorkflowRunnerLambda:
    """Test WorkflowRunner with lambda steps."""

    def test_simple_lambda_workflow(self, noop_runnable):
        def step1(ctx, config):
            return StepResult.ok(output={"value": 1})

        def step2(ctx, config):
            prev = ctx.get_output("s1", "value", 0)
            return StepResult.ok(output={"value": prev + 1})

        wf = Workflow(
            name="test",
            steps=[
                Step.lambda_("s1", handler=step1),
                Step.lambda_("s2", handler=step2),
            ],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert len(result.completed_steps) == 2
        assert result.context.get_output("s2", "value") == 2

    def test_lambda_failure_stops(self, noop_runnable):
        def fail_step(ctx, config):
            return StepResult.fail("broken")

        def never_run(ctx, config):
            return StepResult.ok()

        wf = Workflow(
            name="test",
            steps=[
                Step.lambda_("s1", handler=fail_step),
                Step.lambda_("s2", handler=never_run),
            ],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED
        assert result.error_step == "s1"
        assert result.error == "broken"
        assert len(result.step_executions) == 1

    def test_lambda_failure_continue(self, noop_runnable):
        def fail_step(ctx, config):
            return StepResult.fail("broken")

        def ok_step(ctx, config):
            return StepResult.ok()

        wf = Workflow(
            name="test",
            steps=[
                Step.lambda_("s1", handler=fail_step, on_error=ErrorPolicy.CONTINUE),
                Step.lambda_("s2", handler=ok_step),
            ],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.PARTIAL
        assert len(result.step_executions) == 2

    def test_lambda_no_handler(self, noop_runnable):
        step = Step(name="bad", step_type=StepType.LAMBDA)
        wf = Workflow.__new__(Workflow)
        wf.name = "test"
        wf.steps = [step]
        wf.domain = ""
        wf.description = ""
        wf.version = 1
        wf.defaults = {}
        wf.tags = []
        wf.execution_policy = WorkflowExecutionPolicy()
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED

    def test_lambda_exception_caught(self, noop_runnable):
        def explode(ctx, config):
            raise RuntimeError("boom")

        wf = Workflow(
            name="test",
            steps=[Step.lambda_("s1", handler=explode)],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED
        assert "boom" in result.error

    def test_context_updates_merged(self, noop_runnable):
        def step(ctx, config):
            return StepResult.ok(context_updates={"new_key": "new_value"})

        wf = Workflow(
            name="test",
            steps=[Step.lambda_("s1", handler=step)],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf, params={"existing": "value"})
        assert result.context.get_param("new_key") == "new_value"
        assert result.context.get_param("existing") == "value"


class TestWorkflowRunnerPipeline:
    """Test pipeline step execution."""

    def test_dry_run_pipeline(self, noop_runnable):
        wf = Workflow(
            name="test",
            steps=[Step.pipeline("s1", "my.pipeline")],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.get_output("s1", "dry_run") is True

    def test_pipeline_no_name(self, noop_runnable):
        step = Step(name="bad", step_type=StepType.PIPELINE)
        wf = Workflow.__new__(Workflow)
        wf.name = "test"
        wf.steps = [step]
        wf.domain = ""
        wf.description = ""
        wf.version = 1
        wf.defaults = {}
        wf.tags = []
        wf.execution_policy = WorkflowExecutionPolicy()
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED


class TestWorkflowRunnerChoice:
    """Test choice step execution."""

    def test_choice_then_branch(self, noop_runnable):
        def ok_step(ctx, config):
            return StepResult.ok(output={"reached": True})

        wf = Workflow(
            name="test",
            steps=[
                Step.lambda_("setup", handler=lambda ctx, cfg: StepResult.ok()),
                Step.pipeline("target_a", "p.a"),
                Step.pipeline("target_b", "p.b"),
                Step.choice(
                    "pick",
                    condition=lambda ctx: True,
                    then_step="target_a",
                    else_step="target_b",
                ),
            ],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED

    def test_choice_no_condition(self, noop_runnable):
        step = Step(name="bad", step_type=StepType.CHOICE)
        wf = Workflow.__new__(Workflow)
        wf.name = "test"
        wf.steps = [step]
        wf.domain = ""
        wf.description = ""
        wf.version = 1
        wf.defaults = {}
        wf.tags = []
        wf.execution_policy = WorkflowExecutionPolicy()
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED

    def test_choice_condition_exception(self, noop_runnable):
        def bad_cond(ctx):
            raise ValueError("bad condition")

        step = Step.choice("pick", condition=bad_cond, then_step="a")
        wf = Workflow.__new__(Workflow)
        wf.name = "test"
        wf.steps = [step]
        wf.domain = ""
        wf.description = ""
        wf.version = 1
        wf.defaults = {}
        wf.tags = []
        wf.execution_policy = WorkflowExecutionPolicy()
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED


class TestWorkflowRunnerAdvanced:
    """Test advanced features."""

    def test_start_from(self, noop_runnable):
        call_log = []

        def step_fn(name):
            def fn(ctx, config):
                call_log.append(name)
                return StepResult.ok()
            return fn

        wf = Workflow(
            name="test",
            steps=[
                Step.lambda_("s1", handler=step_fn("s1")),
                Step.lambda_("s2", handler=step_fn("s2")),
                Step.lambda_("s3", handler=step_fn("s3")),
            ],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf, start_from="s2")
        assert result.status == WorkflowStatus.COMPLETED
        assert call_log == ["s2", "s3"]  # s1 skipped

    def test_start_from_invalid_raises(self, noop_runnable):
        from spine.orchestration.exceptions import GroupError

        wf = Workflow(name="test", steps=[Step.lambda_("s1", handler=lambda c, cfg: StepResult.ok())])
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        with pytest.raises(GroupError, match="Start step not found"):
            runner.execute(wf, start_from="nonexistent")

    def test_map_step_returns_fail(self, noop_runnable):
        step = Step.map("m", items_path="items", iterator_workflow="w")
        wf = Workflow.__new__(Workflow)
        wf.name = "test"
        wf.steps = [step]
        wf.domain = ""
        wf.description = ""
        wf.version = 1
        wf.defaults = {}
        wf.tags = []
        wf.execution_policy = WorkflowExecutionPolicy()
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.FAILED

    def test_wait_step_dry_run(self, noop_runnable):
        wf = Workflow(
            name="test",
            steps=[Step.wait("w", duration_seconds=0)],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED

    def test_with_existing_context(self, noop_runnable):
        ctx = WorkflowContext.create(
            workflow_name="test",
            params={"existing": True},
        )

        def check(ctx, config):
            assert ctx.get_param("existing") is True
            return StepResult.ok()

        wf = Workflow(
            name="test",
            steps=[Step.lambda_("s1", handler=check)],
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf, context=ctx)
        assert result.status == WorkflowStatus.COMPLETED

    def test_workflow_defaults_merged(self, noop_runnable):
        def check(ctx, config):
            assert ctx.get_param("default_key") == "default_value"
            return StepResult.ok()

        wf = Workflow(
            name="test",
            steps=[Step.lambda_("s1", handler=check)],
            defaults={"default_key": "default_value"},
        )
        runner = WorkflowRunner(noop_runnable, dry_run=True)
        result = runner.execute(wf)
        assert result.status == WorkflowStatus.COMPLETED


class TestGetWorkflowRunner:
    """Test factory function."""

    def test_get_workflow_runner(self, noop_runnable):
        runner = get_workflow_runner(noop_runnable, dry_run=True)
        assert isinstance(runner, WorkflowRunner)
