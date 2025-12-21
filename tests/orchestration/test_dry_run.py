"""Tests for spine.orchestration.dry_run — dry-run analysis."""

from __future__ import annotations

import pytest

from spine.orchestration.dry_run import (
    DryRunResult,
    DryRunStep,
    clear_cost_registry,
    dry_run,
    register_cost_estimate,
    register_estimator,
)
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import (
    ExecutionMode,
    Workflow,
    WorkflowExecutionPolicy,
)


def _ok_handler(ctx, config):
    return StepResult.ok(output={"done": True})


def _always_true(ctx):
    return True


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset cost registry before each test."""
    clear_cost_registry()
    yield
    clear_cost_registry()


# ── DryRunStep ───────────────────────────────────────────────────────


class TestDryRunStep:
    """Tests for the DryRunStep data class."""

    def test_frozen_dataclass(self):
        step = DryRunStep(
            step_name="test",
            step_type="lambda",
            order=1,
            estimated_seconds=0.5,
        )
        assert step.step_name == "test"
        assert step.will_execute is True

    def test_notes_tuple(self):
        step = DryRunStep(
            step_name="test",
            step_type="lambda",
            order=1,
            estimated_seconds=0.1,
            notes=("hello", "world"),
        )
        assert len(step.notes) == 2


# ── DryRunResult ─────────────────────────────────────────────────────


class TestDryRunResult:
    """Tests for the DryRunResult model."""

    def test_is_valid_no_issues(self):
        result = DryRunResult(workflow_name="test")
        assert result.is_valid is True

    def test_is_valid_with_issues(self):
        result = DryRunResult(
            workflow_name="test",
            validation_issues=["missing handler"],
        )
        assert result.is_valid is False

    def test_total_estimated_seconds_sequential(self):
        result = DryRunResult(
            workflow_name="test",
            execution_plan=[
                DryRunStep("a", "lambda", 1, 1.0),
                DryRunStep("b", "lambda", 2, 2.0),
                DryRunStep("c", "lambda", 3, 3.0),
            ],
        )
        assert result.total_estimated_seconds == 6.0

    def test_total_estimated_seconds_parallel(self):
        result = DryRunResult(
            workflow_name="test",
            execution_mode="parallel",
            execution_plan=[
                DryRunStep("a", "operation", 1, 5.0),
                DryRunStep("b", "operation", 2, 3.0),
                DryRunStep("c", "operation", 3, 2.0, dependencies=("a", "b")),
            ],
        )
        # Critical path: max(a=5, b=3) + c=2 = 7
        assert result.total_estimated_seconds == 7.0

    def test_step_count(self):
        result = DryRunResult(
            workflow_name="test",
            execution_plan=[
                DryRunStep("a", "lambda", 1, 1.0, will_execute=True),
                DryRunStep("b", "lambda", 2, 1.0, will_execute=False),
            ],
        )
        assert result.step_count == 1

    def test_summary_contains_workflow_name(self):
        result = DryRunResult(workflow_name="my.workflow")
        summary = result.summary()
        assert "my.workflow" in summary

    def test_summary_shows_issues(self):
        result = DryRunResult(
            workflow_name="test",
            validation_issues=["step 'x' has no handler"],
        )
        summary = result.summary()
        assert "VALIDATION ISSUES" in summary
        assert "no handler" in summary


# ── dry_run() function ───────────────────────────────────────────────


class TestDryRun:
    """Tests for the dry_run() analysis function."""

    def test_basic_dry_run(self):
        wf = Workflow(
            name="test.basic",
            steps=[
                Step.lambda_("step_a", _ok_handler),
                Step.operation("step_b", "data.process"),
            ],
        )
        result = dry_run(wf)
        assert result.is_valid
        assert result.step_count == 2
        assert len(result.execution_plan) == 2

    def test_empty_workflow_has_issue(self):
        wf = Workflow(name="test.empty", steps=[])
        result = dry_run(wf)
        assert not result.is_valid
        assert any("no steps" in i for i in result.validation_issues)

    def test_missing_handler_detected(self):
        wf = Workflow(
            name="test.bad",
            steps=[Step.lambda_("broken", None)],
        )
        result = dry_run(wf)
        assert not result.is_valid
        assert any("no handler" in i for i in result.validation_issues)

    def test_missing_operation_name_detected(self):
        wf = Workflow(
            name="test.bad",
            steps=[Step(name="bad_pipe", step_type=StepType.OPERATION)],
        )
        result = dry_run(wf)
        assert not result.is_valid
        assert any("no operation_name" in i for i in result.validation_issues)

    def test_missing_condition_detected(self):
        wf = Workflow(
            name="test.bad",
            steps=[Step(name="bad_choice", step_type=StepType.CHOICE)],
        )
        result = dry_run(wf)
        assert not result.is_valid
        assert any("no condition" in i for i in result.validation_issues)

    def test_custom_cost_estimate(self):
        register_cost_estimate("data.expensive", 30.0)
        wf = Workflow(
            name="test.cost",
            steps=[Step.operation("expensive", "data.expensive")],
        )
        result = dry_run(wf)
        assert result.execution_plan[0].estimated_seconds == 30.0

    def test_custom_estimator(self):
        def my_estimator(step, params):
            return params.get("size", 1) * 2.0

        register_estimator("dynamic", my_estimator)
        wf = Workflow(
            name="test.estimator",
            steps=[Step.lambda_("dynamic", _ok_handler)],
        )
        result = dry_run(wf, params={"size": 5})
        assert result.execution_plan[0].estimated_seconds == 10.0

    def test_wait_step_uses_configured_duration(self):
        wf = Workflow(
            name="test.wait",
            steps=[Step.wait("pause", 60)],
        )
        result = dry_run(wf)
        assert result.execution_plan[0].estimated_seconds == 60.0

    def test_params_merged_with_defaults(self):
        wf = Workflow(
            name="test.defaults",
            steps=[Step.lambda_("a", _ok_handler)],
            defaults={"default_key": "value"},
        )
        result = dry_run(wf, params={"extra": "param"})
        assert result.params_provided["default_key"] == "value"
        assert result.params_provided["extra"] == "param"

    def test_execution_mode_reported(self):
        wf = Workflow(
            name="test.parallel",
            steps=[
                Step.operation("a", "pipe.a"),
                Step.operation("b", "pipe.b"),
            ],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
            ),
        )
        result = dry_run(wf)
        assert result.execution_mode == "parallel"

    def test_unknown_dependency_detected(self):
        """Workflow rejects unknown deps at construction time."""
        with pytest.raises(ValueError, match="nonexistent"):
            Workflow(
                name="test.bad_dep",
                steps=[
                    Step.operation("a", "pipe.a", depends_on=["nonexistent"]),
                ],
            )

    def test_plan_order_matches_step_order(self):
        wf = Workflow(
            name="test.order",
            steps=[
                Step.lambda_("first", _ok_handler),
                Step.lambda_("second", _ok_handler),
                Step.lambda_("third", _ok_handler),
            ],
        )
        result = dry_run(wf)
        orders = [s.order for s in result.execution_plan]
        assert orders == [1, 2, 3]
