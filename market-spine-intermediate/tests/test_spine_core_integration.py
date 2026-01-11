"""
Tests for spine-core orchestration integration.

Verifies that:
1. Intermediate pipelines can be adapted to spine-core interface
2. PipelineGroups can orchestrate intermediate pipelines
3. GroupRunner executes adapted pipelines correctly
"""

import pytest

from spine.framework import clear_registry, register_pipeline
from spine.orchestration import clear_group_registry

from market_spine.orchestration import (
    adapt_pipeline,
    PipelineGroup,
    PipelineStep,
    PlanResolver,
    GroupRunner,
    GroupExecutionStatus,
    StepStatus,
    register_group,
)
from market_spine.pipelines.base import Pipeline as IntermediatePipeline


# =============================================================================
# Test Pipelines (intermediate-style)
# =============================================================================


class SimplePipeline(IntermediatePipeline):
    """Simple test pipeline."""

    name = "test.simple"
    description = "Simple test pipeline"

    def execute(self, params):
        return {"message": "success", "value": params.get("value", 42)}


class FailingPipeline(IntermediatePipeline):
    """Pipeline that always fails."""

    name = "test.failing"
    description = "Always fails"

    def execute(self, params):
        raise RuntimeError("Intentional failure")


class DependentPipeline(IntermediatePipeline):
    """Pipeline that uses output from previous step."""

    name = "test.dependent"
    description = "Uses previous step output"

    def execute(self, params):
        prev_value = params.get("prev_value", 0)
        return {"result": prev_value * 2}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_registries():
    """Clean spine-core registries before/after each test."""
    clear_registry()
    clear_group_registry()
    yield
    clear_registry()
    clear_group_registry()


@pytest.fixture
def register_test_pipelines():
    """Register adapted test pipelines with spine-core."""
    # Adapt intermediate pipelines to spine-core interface
    AdaptedSimple = adapt_pipeline(SimplePipeline)
    AdaptedFailing = adapt_pipeline(FailingPipeline)
    AdaptedDependent = adapt_pipeline(DependentPipeline)

    # Register with spine-core
    register_pipeline("test.simple")(AdaptedSimple)
    register_pipeline("test.failing")(AdaptedFailing)
    register_pipeline("test.dependent")(AdaptedDependent)


# =============================================================================
# Tests: Pipeline Adaptation
# =============================================================================


class TestPipelineAdaptation:
    """Test that intermediate pipelines can be adapted to spine-core."""

    def test_adapt_preserves_name_and_description(self):
        """Adapted pipeline should preserve name and description."""
        Adapted = adapt_pipeline(SimplePipeline)

        assert Adapted.name == "test.simple"
        assert Adapted.description == "Simple test pipeline"

    def test_adapted_pipeline_can_run(self):
        """Adapted pipeline should execute via run() method."""
        Adapted = adapt_pipeline(SimplePipeline)

        # Create instance with params (spine-core pattern)
        pipeline = Adapted(params={"value": 100})
        result = pipeline.run()

        assert result.status.value == "completed"
        assert result.metrics["value"] == 100
        assert result.metrics["message"] == "success"

    def test_adapted_pipeline_handles_failure(self):
        """Adapted pipeline should catch errors and return failed status."""
        Adapted = adapt_pipeline(FailingPipeline)

        pipeline = Adapted(params={})
        result = pipeline.run()

        assert result.status.value == "failed"
        assert "Intentional failure" in result.error


# =============================================================================
# Tests: Group Orchestration
# =============================================================================


class TestGroupOrchestration:
    """Test spine-core GroupRunner with intermediate pipelines."""

    def test_simple_group_execution(self, register_test_pipelines):
        """Execute a simple group with one step."""
        group = PipelineGroup(
            name="test.simple_group",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.simple"),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group, params={"value": 99})

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.COMPLETED
        assert result.successful_steps == 1
        assert result.failed_steps == 0

    def test_multi_step_group(self, register_test_pipelines):
        """Execute a group with multiple steps."""
        group = PipelineGroup(
            name="test.multi_step",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.simple"),
                PipelineStep(
                    name="step2", pipeline="test.dependent", depends_on=["step1"]
                ),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.COMPLETED
        assert result.successful_steps == 2

        # Verify execution order
        step_names = [s.step_name for s in result.step_executions]
        assert step_names == ["step1", "step2"]

    def test_group_with_failure(self, register_test_pipelines):
        """Group should handle step failures correctly."""
        group = PipelineGroup(
            name="test.failure_group",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.failing"),
                PipelineStep(
                    name="step2", pipeline="test.simple", depends_on=["step1"]
                ),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # Group should fail
        assert result.status == GroupExecutionStatus.FAILED

        # step1 failed, step2 should be skipped
        step1 = result.get_step_execution("step1")
        step2 = result.get_step_execution("step2")

        assert step1.status == StepStatus.FAILED
        assert step2.status == StepStatus.SKIPPED


# =============================================================================
# Tests: Parallel Execution
# =============================================================================


class TestParallelExecution:
    """Test parallel execution with adapted pipelines."""

    def test_parallel_independent_steps(self, register_test_pipelines):
        """Parallel execution of independent steps."""
        from market_spine.orchestration import ExecutionMode, ExecutionPolicy

        group = PipelineGroup(
            name="test.parallel",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.simple"),
                PipelineStep(name="step2", pipeline="test.simple"),
                PipelineStep(name="step3", pipeline="test.simple"),
            ],
            policy=ExecutionPolicy(mode=ExecutionMode.PARALLEL, max_concurrency=3),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.COMPLETED
        assert result.successful_steps == 3
