"""Tests for spine.orchestration workflow modules."""

import pytest

from spine.orchestration import (
    Workflow,
    WorkflowContext,
    Step,
    StepType,
    StepResult,
    WorkflowRunner,
    WorkflowStatus,
)
from spine.core.errors import OperationError


class TestStep:
    """Test Step creation."""

    def test_create_operation_step(self):
        """Create operation step."""
        step = Step.operation("ingest", "finra.ingest")
        assert step.name == "ingest"
        assert step.step_type == StepType.OPERATION
        assert step.operation_name == "finra.ingest"

    def test_create_lambda_step(self):
        """Create lambda step."""
        fn = lambda ctx, cfg: StepResult.ok()
        step = Step.lambda_("validate", fn)
        assert step.name == "validate"
        assert step.step_type == StepType.LAMBDA
        assert step.handler == fn

    def test_create_choice_step(self):
        """Create choice step."""
        condition = lambda ctx: True
        step = Step.choice("route", condition, "step_a", "step_b")
        assert step.name == "route"
        assert step.step_type == StepType.CHOICE
        assert step.then_step == "step_a"
        assert step.else_step == "step_b"


class TestWorkflow:
    """Test Workflow creation and validation."""

    def test_create_minimal_workflow(self):
        """Create workflow with minimal fields."""
        workflow = Workflow(
            name="test.workflow",
            steps=[
                Step.operation("step1", "operation1"),
            ],
        )
        assert workflow.name == "test.workflow"
        assert len(workflow.steps) == 1

    def test_create_workflow_with_multiple_steps(self):
        """Create workflow with multiple steps."""
        workflow = Workflow(
            name="test.workflow",
            steps=[
                Step.operation("ingest", "ingest_operation"),
                Step.lambda_("validate", lambda ctx, cfg: StepResult.ok()),
                Step.operation("process", "process_operation"),
            ],
        )
        assert len(workflow.steps) == 3
        assert workflow.steps[0].name == "ingest"
        assert workflow.steps[1].name == "validate"
        assert workflow.steps[2].name == "process"

    def test_workflow_validates_unique_step_names(self):
        """Workflow validates step names are unique."""
        with pytest.raises(ValueError, match="Duplicate step name"):
            Workflow(
                name="test.workflow",
                steps=[
                    Step.operation("step1", "operation1"),
                    Step.operation("step1", "operation2"),  # Duplicate
                ],
            )

    def test_workflow_with_domain(self):
        """Create workflow with domain."""
        workflow = Workflow(
            name="finra.weekly",
            domain="finra.otc_transparency",
            steps=[Step.operation("ingest", "finra.ingest")],
        )
        assert workflow.domain == "finra.otc_transparency"

    def test_workflow_with_defaults(self):
        """Create workflow with default parameters."""
        workflow = Workflow(
            name="test.workflow",
            steps=[Step.operation("step1", "operation1")],
            defaults={"date": "2026-01-12", "env": "prod"},
        )
        assert workflow.defaults["date"] == "2026-01-12"


class TestWorkflowContext:
    """Test WorkflowContext."""

    def test_create_empty_context(self):
        """Create empty context."""
        ctx = WorkflowContext()
        assert ctx.params == {}
        assert ctx.outputs == {}

    def test_create_context_with_params(self):
        """Create context with parameters."""
        ctx = WorkflowContext(params={"date": "2026-01-12"})
        assert ctx.get_param("date") == "2026-01-12"

    def test_get_param_with_default(self):
        """Get parameter with default value."""
        ctx = WorkflowContext()
        assert ctx.get_param("missing", "default") == "default"

    def test_with_output_returns_new_context(self):
        """with_output returns new context with output."""
        ctx = WorkflowContext()
        new_ctx = ctx.with_output("step1", {"count": 100})
        
        # Original unchanged
        assert ctx.outputs == {}
        # New has output
        assert new_ctx.get_output("step1", "count") == 100

    def test_get_output_with_default(self):
        """Get output with default value."""
        ctx = WorkflowContext()
        assert ctx.get_output("step1", "result", "default") == "default"

    def test_chained_with_output(self):
        """Chain multiple with_output calls."""
        ctx = WorkflowContext()
        ctx = ctx.with_output("step1", {"count": 100})
        ctx = ctx.with_output("step1", {"status": "success"})
        
        # Later output replaces earlier for same step
        assert ctx.get_output("step1", "status") == "success"
        # But count is gone since entire output was replaced
        assert ctx.get_output("step1", "count") is None

    def test_context_from_create(self):
        """Create context via factory method."""
        ctx = WorkflowContext.create(
            workflow_name="test.workflow",
            params={"date": "2026-01-12"},
        )
        assert ctx.workflow_name == "test.workflow"
        assert ctx.get_param("date") == "2026-01-12"

    def test_context_isolation(self):
        """Outputs are isolated per step."""
        ctx = WorkflowContext()
        ctx = ctx.with_output("step1", {"result": "value1"})
        ctx = ctx.with_output("step2", {"result": "value2"})
        
        assert ctx.get_output("step1", "result") == "value1"
        assert ctx.get_output("step2", "result") == "value2"


class TestStepResult:
    """Test StepResult."""

    def test_create_ok_result(self):
        """Create successful result."""
        result = StepResult.ok()
        assert result.success is True
        assert result.error is None

    def test_create_ok_result_with_output(self):
        """Create successful result with output."""
        result = StepResult.ok(output={"count": 100})
        assert result.success is True
        assert result.output == {"count": 100}

    def test_create_fail_result(self):
        """Create failed result."""
        result = StepResult.fail("Validation failed")
        assert result.success is False
        assert result.error == "Validation failed"

    def test_create_fail_result_with_category(self):
        """Create failed result with error category."""
        from spine.orchestration.step_result import ErrorCategory
        
        result = StepResult.fail("Step failed", category=ErrorCategory.DATA_QUALITY)
        assert result.success is False
        assert result.error_category == "DATA_QUALITY"

    def test_create_skip_result(self):
        """Create skipped result via ok with next_step."""
        # Skip is represented by success=True with custom output
        result = StepResult.ok(output={"skipped": True, "reason": "Condition not met"})
        assert result.success is True
        assert result.output["skipped"] is True


class TestWorkflowRunner:
    """Test WorkflowRunner execution."""

    def test_run_simple_workflow(self, noop_runnable):
        """Run workflow with lambda steps."""
        executed_steps = []
        
        def step1(ctx, config):
            executed_steps.append("step1")
            return StepResult.ok(output={"value": 10})
        
        def step2(ctx, config):
            executed_steps.append("step2")
            prev_value = ctx.get_output("step1", "value")
            return StepResult.ok(output={"value": prev_value * 2})
        
        workflow = Workflow(
            name="test.workflow",
            steps=[
                Step.lambda_("step1", step1),
                Step.lambda_("step2", step2),
            ],
        )
        
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(workflow)
        
        assert result.status == WorkflowStatus.COMPLETED
        assert executed_steps == ["step1", "step2"]
        assert result.context.get_output("step2", "value") == 20

    def test_run_workflow_with_params(self, noop_runnable):
        """Run workflow with parameters."""
        def step_fn(ctx, config):
            date = ctx.get_param("date")
            return StepResult.ok(output={"date": date})
        
        workflow = Workflow(
            name="test.workflow",
            steps=[Step.lambda_("step1", step_fn)],
        )
        
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(workflow, params={"date": "2026-01-12"})
        
        assert result.status == WorkflowStatus.COMPLETED
        assert result.context.get_output("step1", "date") == "2026-01-12"

    def test_workflow_stops_on_failure(self, noop_runnable):
        """Workflow stops when step fails."""
        executed_steps = []
        
        def step1(ctx, config):
            executed_steps.append("step1")
            return StepResult.ok()
        
        def step2(ctx, config):
            executed_steps.append("step2")
            return StepResult.fail("Step 2 failed")
        
        def step3(ctx, config):
            executed_steps.append("step3")
            return StepResult.ok()
        
        workflow = Workflow(
            name="test.workflow",
            steps=[
                Step.lambda_("step1", step1),
                Step.lambda_("step2", step2),
                Step.lambda_("step3", step3),
            ],
        )
        
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(workflow)
        
        assert result.status == WorkflowStatus.FAILED
        assert executed_steps == ["step1", "step2"]  # step3 not executed
        assert "step2" in result.failed_steps

    def test_workflow_result_tracks_completed_steps(self, noop_runnable):
        """Workflow result tracks completed steps."""
        workflow = Workflow(
            name="test.workflow",
            steps=[
                Step.lambda_("step1", lambda ctx, cfg: StepResult.ok()),
                Step.lambda_("step2", lambda ctx, cfg: StepResult.ok()),
            ],
        )
        
        runner = WorkflowRunner(runnable=noop_runnable)
        result = runner.execute(workflow)
        
        assert "step1" in result.completed_steps
        assert "step2" in result.completed_steps
