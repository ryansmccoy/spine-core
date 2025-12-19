"""Tests for spine.orchestration.testing — test harness utilities."""

from __future__ import annotations

import pytest

from spine.execution.runnable import PipelineRunResult
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
    make_context,
    make_runner,
    make_workflow,
)
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_runner import WorkflowRunner, WorkflowStatus


def _ok_handler(ctx, config):
    return StepResult.ok(output={"value": 42})


def _fail_handler(ctx, config):
    return StepResult.fail("Something broke")


# ── StubRunnable ─────────────────────────────────────────────────────


class TestStubRunnable:
    """Tests for StubRunnable."""

    def test_always_succeeds(self):
        stub = StubRunnable()
        result = stub.submit_pipeline_sync("any.pipeline")
        assert result.succeeded

    def test_tracks_calls(self):
        stub = StubRunnable()
        stub.submit_pipeline_sync("pipe.a", params={"x": 1})
        stub.submit_pipeline_sync("pipe.b")
        assert len(stub.calls) == 2
        assert stub.calls[0]["pipeline_name"] == "pipe.a"
        assert stub.calls[0]["params"] == {"x": 1}

    def test_custom_outputs(self):
        stub = StubRunnable(outputs={"pipe.a": {"rows": 100}})
        result = stub.submit_pipeline_sync("pipe.a")
        assert result.metrics == {"rows": 100}

    def test_unknown_pipeline_empty_metrics(self):
        stub = StubRunnable(outputs={"pipe.a": {"rows": 100}})
        result = stub.submit_pipeline_sync("pipe.unknown")
        assert result.metrics == {}


# ── FailingRunnable ──────────────────────────────────────────────────


class TestFailingRunnable:
    """Tests for FailingRunnable."""

    def test_always_fails(self):
        failing = FailingRunnable(error="Connection refused")
        result = failing.submit_pipeline_sync("any.pipeline")
        assert not result.succeeded
        assert result.error == "Connection refused"

    def test_selective_failure(self):
        failing = FailingRunnable(
            error="broken",
            fail_pipelines={"pipe.bad"},
        )
        bad = failing.submit_pipeline_sync("pipe.bad")
        good = failing.submit_pipeline_sync("pipe.good")
        assert not bad.succeeded
        assert good.succeeded

    def test_tracks_calls(self):
        failing = FailingRunnable()
        failing.submit_pipeline_sync("pipe.a")
        assert len(failing.calls) == 1


# ── ScriptedRunnable ─────────────────────────────────────────────────


class TestScriptedRunnable:
    """Tests for ScriptedRunnable."""

    def test_returns_scripted_results(self):
        scripted = ScriptedRunnable(scripts={
            "pipe.ok": PipelineRunResult(status="completed", metrics={"x": 1}),
            "pipe.fail": PipelineRunResult(status="failed", error="boom"),
        })
        ok = scripted.submit_pipeline_sync("pipe.ok")
        fail = scripted.submit_pipeline_sync("pipe.fail")
        assert ok.succeeded
        assert ok.metrics == {"x": 1}
        assert not fail.succeeded
        assert fail.error == "boom"

    def test_unscripted_succeeds(self):
        scripted = ScriptedRunnable()
        result = scripted.submit_pipeline_sync("pipe.unknown")
        assert result.succeeded

    def test_tracks_calls(self):
        scripted = ScriptedRunnable()
        scripted.submit_pipeline_sync("pipe.a")
        assert len(scripted.calls) == 1


# ── Assertion helpers ────────────────────────────────────────────────


class TestAssertions:
    """Tests for assertion helper functions."""

    def _make_completed_result(self) -> WorkflowResult:
        from spine.orchestration.workflow_runner import StepExecution, WorkflowResult
        from datetime import datetime, UTC

        return WorkflowResult(
            workflow_name="test.wf",
            run_id="run-1",
            status=WorkflowStatus.COMPLETED,
            context=make_context(),
            started_at=datetime.now(UTC),
            step_executions=[
                StepExecution(
                    step_name="step_1",
                    step_type="lambda",
                    status="completed",
                    result=StepResult.ok(output={"count": 42}),
                ),
                StepExecution(
                    step_name="step_2",
                    step_type="pipeline",
                    status="completed",
                    result=StepResult.ok(output={"saved": True}),
                ),
            ],
        )

    def _make_failed_result(self) -> WorkflowResult:
        from spine.orchestration.workflow_runner import StepExecution, WorkflowResult
        from datetime import datetime, UTC

        return WorkflowResult(
            workflow_name="test.wf",
            run_id="run-2",
            status=WorkflowStatus.FAILED,
            context=make_context(),
            started_at=datetime.now(UTC),
            error_step="step_1",
            error="Connection refused",
            step_executions=[
                StepExecution(
                    step_name="step_1",
                    step_type="pipeline",
                    status="failed",
                    error="Connection refused",
                ),
            ],
        )

    def test_assert_workflow_completed_passes(self):
        assert_workflow_completed(self._make_completed_result())

    def test_assert_workflow_completed_fails(self):
        with pytest.raises(WorkflowAssertionError, match="COMPLETED"):
            assert_workflow_completed(self._make_failed_result())

    def test_assert_workflow_failed_passes(self):
        assert_workflow_failed(self._make_failed_result())

    def test_assert_workflow_failed_with_step(self):
        assert_workflow_failed(self._make_failed_result(), step="step_1")

    def test_assert_workflow_failed_wrong_step(self):
        with pytest.raises(WorkflowAssertionError, match="step_1"):
            assert_workflow_failed(self._make_failed_result(), step="step_2")

    def test_assert_workflow_failed_error_contains(self):
        assert_workflow_failed(
            self._make_failed_result(),
            error_contains="Connection",
        )

    def test_assert_workflow_failed_on_completed(self):
        with pytest.raises(WorkflowAssertionError, match="FAILED"):
            assert_workflow_failed(self._make_completed_result())

    def test_assert_step_output(self):
        assert_step_output(self._make_completed_result(), "step_1", "count", 42)

    def test_assert_step_output_missing_key(self):
        with pytest.raises(WorkflowAssertionError, match="missing key"):
            assert_step_output(self._make_completed_result(), "step_1", "nonexistent", 0)

    def test_assert_step_output_wrong_value(self):
        with pytest.raises(WorkflowAssertionError, match="expected 99"):
            assert_step_output(self._make_completed_result(), "step_1", "count", 99)

    def test_assert_step_output_missing_step(self):
        with pytest.raises(WorkflowAssertionError, match="not found"):
            assert_step_output(self._make_completed_result(), "nonexistent", "x", 0)

    def test_assert_step_count(self):
        assert_step_count(self._make_completed_result(), 2)

    def test_assert_step_count_wrong(self):
        with pytest.raises(WorkflowAssertionError, match="Expected 5"):
            assert_step_count(self._make_completed_result(), 5)

    def test_assert_no_failures(self):
        assert_no_failures(self._make_completed_result())

    def test_assert_no_failures_with_failure(self):
        with pytest.raises(WorkflowAssertionError, match="no failures"):
            assert_no_failures(self._make_failed_result())

    def test_assert_steps_ran(self):
        assert_steps_ran(self._make_completed_result(), "step_1", "step_2")

    def test_assert_steps_ran_missing(self):
        with pytest.raises(WorkflowAssertionError, match="not executed"):
            assert_steps_ran(self._make_completed_result(), "step_1", "nonexistent")


# ── Factory helpers ──────────────────────────────────────────────────


class TestFactories:
    """Tests for factory helper functions."""

    def test_make_workflow(self):
        wf = make_workflow(_ok_handler, _ok_handler)
        assert wf.name == "test.workflow"
        assert len(wf.steps) == 2
        assert wf.steps[0].name == "step_1"
        assert wf.steps[1].name == "step_2"

    def test_make_context(self):
        ctx = make_context(params={"key": "val"})
        assert ctx.params["key"] == "val"

    def test_make_runner_default(self):
        runner = make_runner()
        assert isinstance(runner, WorkflowRunner)

    def test_make_runner_custom_runnable(self):
        stub = StubRunnable()
        runner = make_runner(runnable=stub)
        assert runner.runnable is stub

    def test_make_runner_dry_run(self):
        runner = make_runner(dry_run=True)
        assert runner._dry_run is True


# ── Integration: use test harness to run a workflow ──────────────────


class TestIntegration:
    """Integration test using the test harness for a real workflow."""

    def test_full_workflow_with_harness(self):
        wf = make_workflow(
            lambda ctx, cfg: StepResult.ok(output={"count": 10}),
            lambda ctx, cfg: StepResult.ok(output={"processed": True}),
        )
        runner = make_runner()
        result = runner.execute(wf)

        assert_workflow_completed(result)
        assert_step_count(result, 2)
        assert_no_failures(result)
        assert_step_output(result, "step_1", "count", 10)
        assert_step_output(result, "step_2", "processed", True)
        assert_steps_ran(result, "step_1", "step_2")

    def test_failing_workflow_with_harness(self):
        wf = make_workflow(_fail_handler)
        runner = make_runner()
        result = runner.execute(wf)

        assert_workflow_failed(result, step="step_1")
