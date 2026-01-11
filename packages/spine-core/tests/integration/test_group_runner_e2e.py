"""
End-to-end integration tests for GroupRunner with real pipelines.

These tests verify that orchestration works correctly with the actual
spine-framework components (registry, dispatcher, pipeline base classes).
"""

from datetime import datetime

import pytest

from spine.framework import (
    Pipeline,
    PipelineResult,
    PipelineStatus,
    register_pipeline,
    clear_registry,
)
from spine.framework.dispatcher import reset_dispatcher
from spine.orchestration import (
    PipelineGroup,
    PipelineStep,
    ExecutionPolicy,
    ExecutionMode,
    FailurePolicy,
    PlanResolver,
    GroupRunner,
    GroupExecutionStatus,
    StepStatus,
    register_group,
    clear_group_registry,
)


# =============================================================================
# Test Pipelines (registered with framework)
# =============================================================================


class FetchDataPipeline(Pipeline):
    """Test pipeline that simulates data fetching."""

    name = "test.fetch_data"
    description = "Fetches data from source"

    def run(self) -> PipelineResult:
        started_at = datetime.now()
        # Simulate successful fetch
        source = self.params.get("source", "default")
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(),
            metrics={"source": source, "rows": 100},
        )


class TransformDataPipeline(Pipeline):
    """Test pipeline that simulates data transformation."""

    name = "test.transform_data"
    description = "Transforms fetched data"

    def run(self) -> PipelineResult:
        started_at = datetime.now()
        mode = self.params.get("mode", "standard")
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(),
            metrics={"mode": mode, "rows": 100},
        )


class LoadDataPipeline(Pipeline):
    """Test pipeline that simulates data loading."""

    name = "test.load_data"
    description = "Loads transformed data"

    def run(self) -> PipelineResult:
        started_at = datetime.now()
        target = self.params.get("target", "default_table")
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(),
            metrics={"target": target, "rows": 100},
        )


class FailingPipeline(Pipeline):
    """Test pipeline that always fails."""

    name = "test.failing_pipeline"
    description = "Always fails for testing"

    def run(self) -> PipelineResult:
        started_at = datetime.now()
        raise RuntimeError("Simulated pipeline failure")


class ConditionalPipeline(Pipeline):
    """Test pipeline that fails based on parameter."""

    name = "test.conditional_pipeline"
    description = "Fails based on should_fail parameter"

    def run(self) -> PipelineResult:
        started_at = datetime.now()
        if self.params.get("should_fail", False):
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(),
                error="Conditional failure triggered",
            )
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(),
        )


class ValidateDataPipeline(Pipeline):
    """Test pipeline that simulates data validation."""

    name = "test.validate_data"
    description = "Validates data quality"

    def run(self) -> PipelineResult:
        started_at = datetime.now()
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(),
            metrics={"rows_validated": 100, "errors": 0},
        )


class PersistDataPipeline(Pipeline):
    """Test pipeline that simulates data persistence."""

    name = "test.persist_data"
    description = "Persists data to storage"

    def run(self) -> PipelineResult:
        started_at = datetime.now()
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(),
            metrics={"rows_persisted": 100},
        )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def setup_test_registry():
    """Register test pipelines and clean up after each test."""
    # Clear registries
    clear_registry()
    clear_group_registry()
    reset_dispatcher()

    # Register test pipelines
    register_pipeline("test.fetch_data")(FetchDataPipeline)
    register_pipeline("test.transform_data")(TransformDataPipeline)
    register_pipeline("test.load_data")(LoadDataPipeline)
    register_pipeline("test.failing_pipeline")(FailingPipeline)
    register_pipeline("test.conditional_pipeline")(ConditionalPipeline)
    register_pipeline("test.validate_data")(ValidateDataPipeline)
    register_pipeline("test.persist_data")(PersistDataPipeline)

    yield

    # Clean up
    clear_registry()
    clear_group_registry()
    reset_dispatcher()


# =============================================================================
# Tests
# =============================================================================


class TestGroupRunnerBasicExecution:
    """Test basic group execution scenarios."""

    def test_execute_simple_linear_group(self):
        """Test executing a simple linear group (A -> B -> C)."""
        group = PipelineGroup(
            name="test.simple_linear",
            domain="test",
            steps=[
                PipelineStep(name="fetch", pipeline="test.fetch_data"),
                PipelineStep(
                    name="transform",
                    pipeline="test.transform_data",
                    depends_on=["fetch"],
                ),
                PipelineStep(
                    name="load",
                    pipeline="test.load_data",
                    depends_on=["transform"],
                ),
            ],
        )
        register_group(group)

        # Resolve and execute
        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # Verify success
        assert result.status == GroupExecutionStatus.COMPLETED
        assert result.successful_steps == 3
        assert result.failed_steps == 0
        assert result.skipped_steps == 0

        # Verify execution order
        step_names = [s.step_name for s in result.step_executions]
        assert step_names == ["fetch", "transform", "load"]

        # All steps should be completed
        for step_exec in result.step_executions:
            assert step_exec.status == StepStatus.COMPLETED
            assert step_exec.result is not None
            assert step_exec.result.status == PipelineStatus.COMPLETED

    def test_execute_with_parameter_merging(self):
        """Test that parameters are correctly merged and passed to pipelines."""
        group = PipelineGroup(
            name="test.with_params",
            domain="test",
            steps=[
                PipelineStep(
                    name="fetch",
                    pipeline="test.fetch_data",
                    params={"source": "step_override"},
                ),
            ],
            defaults={"source": "group_default", "batch_size": 100},
        )
        register_group(group)

        # Resolve with runtime params
        resolver = PlanResolver()
        plan = resolver.resolve(group, params={"source": "runtime_override"})

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.COMPLETED

        # The step should have received the step-level override
        step_exec = result.get_step_execution("fetch")
        assert step_exec is not None
        assert step_exec.result.metrics["source"] == "step_override"

    def test_execute_parallel_steps(self):
        """Test steps with no dependencies can execute (currently sequential)."""
        group = PipelineGroup(
            name="test.parallel",
            domain="test",
            steps=[
                PipelineStep(name="fetch_a", pipeline="test.fetch_data"),
                PipelineStep(name="fetch_b", pipeline="test.fetch_data"),
                PipelineStep(name="fetch_c", pipeline="test.fetch_data"),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.COMPLETED
        assert result.successful_steps == 3


class TestGroupRunnerFailureHandling:
    """Test failure handling with different policies."""

    def test_stop_on_failure(self):
        """Test STOP policy halts execution and skips remaining steps."""
        group = PipelineGroup(
            name="test.stop_on_failure",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
                PipelineStep(
                    name="step2_fails",
                    pipeline="test.failing_pipeline",
                    depends_on=["step1"],
                ),
                PipelineStep(
                    name="step3",
                    pipeline="test.load_data",
                    depends_on=["step2_fails"],
                ),
            ],
            policy=ExecutionPolicy.sequential(on_failure=FailurePolicy.STOP),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # Overall status should be FAILED
        assert result.status == GroupExecutionStatus.FAILED

        # Verify step statuses
        step1 = result.get_step_execution("step1")
        step2 = result.get_step_execution("step2_fails")
        step3 = result.get_step_execution("step3")

        assert step1.status == StepStatus.COMPLETED
        assert step2.status == StepStatus.FAILED
        assert step3.status == StepStatus.SKIPPED

        assert result.successful_steps == 1
        assert result.failed_steps == 1
        assert result.skipped_steps == 1

    def test_continue_on_failure(self):
        """Test CONTINUE policy continues with independent steps."""
        group = PipelineGroup(
            name="test.continue_on_failure",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
                PipelineStep(
                    name="step2_fails",
                    pipeline="test.failing_pipeline",
                    depends_on=["step1"],
                ),
                # step3 depends on step2, so should be skipped
                PipelineStep(
                    name="step3",
                    pipeline="test.load_data",
                    depends_on=["step2_fails"],
                ),
            ],
            policy=ExecutionPolicy.sequential(on_failure=FailurePolicy.CONTINUE),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # Overall status should be PARTIAL (some succeeded, some failed)
        assert result.status == GroupExecutionStatus.PARTIAL

        # step3 should be SKIPPED because its dependency failed
        step1 = result.get_step_execution("step1")
        step2 = result.get_step_execution("step2_fails")
        step3 = result.get_step_execution("step3")

        assert step1.status == StepStatus.COMPLETED
        assert step2.status == StepStatus.FAILED
        assert step3.status == StepStatus.SKIPPED

    def test_continue_allows_independent_steps(self):
        """Test CONTINUE policy allows independent branches to run."""
        group = PipelineGroup(
            name="test.independent_branches",
            domain="test",
            steps=[
                # Root step
                PipelineStep(name="root", pipeline="test.fetch_data"),
                # Branch A - will fail
                PipelineStep(
                    name="branch_a",
                    pipeline="test.failing_pipeline",
                    depends_on=["root"],
                ),
                # Branch B - should still run (independent of branch_a)
                PipelineStep(
                    name="branch_b",
                    pipeline="test.transform_data",
                    depends_on=["root"],
                ),
                # Merge - depends on both, should be skipped
                PipelineStep(
                    name="merge",
                    pipeline="test.load_data",
                    depends_on=["branch_a", "branch_b"],
                ),
            ],
            policy=ExecutionPolicy.sequential(on_failure=FailurePolicy.CONTINUE),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.PARTIAL

        # Verify statuses
        assert result.get_step_execution("root").status == StepStatus.COMPLETED
        assert result.get_step_execution("branch_a").status == StepStatus.FAILED
        assert result.get_step_execution("branch_b").status == StepStatus.COMPLETED
        # merge is skipped because branch_a failed
        assert result.get_step_execution("merge").status == StepStatus.SKIPPED


class TestGroupRunnerDiamondDependency:
    """Test diamond-shaped dependency patterns."""

    def test_diamond_dependency_pattern(self):
        """Test A -> B, C -> D pattern (diamond)."""
        #     A
        #    / \
        #   B   C
        #    \ /
        #     D
        group = PipelineGroup(
            name="test.diamond",
            domain="test",
            steps=[
                PipelineStep(name="A", pipeline="test.fetch_data"),
                PipelineStep(
                    name="B",
                    pipeline="test.transform_data",
                    depends_on=["A"],
                ),
                PipelineStep(
                    name="C",
                    pipeline="test.transform_data",
                    depends_on=["A"],
                ),
                PipelineStep(
                    name="D",
                    pipeline="test.load_data",
                    depends_on=["B", "C"],
                ),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.COMPLETED
        assert result.successful_steps == 4

        # Verify A runs first
        step_names = [s.step_name for s in result.step_executions]
        assert step_names[0] == "A"
        # B and C run after A (order between them may vary)
        assert set(step_names[1:3]) == {"B", "C"}
        # D runs last
        assert step_names[3] == "D"


class TestGroupRunnerEdgeCases:
    """Test edge cases and error conditions."""

    def test_single_step_group(self):
        """Test group with only one step."""
        group = PipelineGroup(
            name="test.single",
            domain="test",
            steps=[
                PipelineStep(name="only", pipeline="test.fetch_data"),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.COMPLETED
        assert result.total_steps == 1

    def test_all_steps_fail(self):
        """Test when all steps fail."""
        group = PipelineGroup(
            name="test.all_fail",
            domain="test",
            steps=[
                PipelineStep(name="fail1", pipeline="test.failing_pipeline"),
            ],
            policy=ExecutionPolicy.sequential(on_failure=FailurePolicy.CONTINUE),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.status == GroupExecutionStatus.FAILED
        assert result.successful_steps == 0
        assert result.failed_steps == 1

    def test_batch_id_propagation(self):
        """Test that batch_id is propagated to all steps."""
        group = PipelineGroup(
            name="test.batch_id",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
                PipelineStep(
                    name="step2",
                    pipeline="test.transform_data",
                    depends_on=["step1"],
                ),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        custom_batch_id = "custom_batch_123"
        plan = resolver.resolve(group, batch_id=custom_batch_id)

        runner = GroupRunner()
        result = runner.execute(plan)

        assert result.batch_id == custom_batch_id
        assert result.status == GroupExecutionStatus.COMPLETED

    def test_duration_tracking(self):
        """Test that duration is tracked correctly."""
        group = PipelineGroup(
            name="test.timing",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # Overall duration should be tracked
        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0

        # Step duration should be tracked
        step = result.get_step_execution("step1")
        assert step.duration_seconds is not None
        assert step.duration_seconds >= 0

    def test_result_serialization(self):
        """Test that results can be serialized to dict."""
        group = PipelineGroup(
            name="test.serialize",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
            ],
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # Should serialize without error
        result_dict = result.to_dict()

        assert result_dict["group_name"] == "test.serialize"
        assert result_dict["status"] == "completed"
        assert len(result_dict["step_executions"]) == 1
        assert result_dict["step_executions"][0]["step_name"] == "step1"


class TestGroupRunnerParallelExecution:
    """Tests for parallel execution mode using ThreadPoolExecutor."""

    def test_parallel_independent_steps(self):
        """Test parallel execution of independent steps."""
        from spine.orchestration.models import ExecutionMode, ExecutionPolicy

        group = PipelineGroup(
            name="test.parallel_independent",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
                PipelineStep(name="step2", pipeline="test.transform_data"),
                PipelineStep(name="step3", pipeline="test.validate_data"),
            ],
            policy=ExecutionPolicy(
                mode=ExecutionMode.PARALLEL, max_concurrency=3
            ),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # All should complete successfully
        assert result.status == GroupExecutionStatus.COMPLETED
        assert len(result.step_executions) == 3
        for step_exec in result.step_executions:
            assert step_exec.status == StepStatus.COMPLETED

    def test_parallel_with_dependencies(self):
        """Test parallel execution respects dependencies."""
        from spine.orchestration.models import ExecutionMode, ExecutionPolicy

        # Diamond pattern: step1 -> step2, step3 -> step4
        group = PipelineGroup(
            name="test.parallel_diamond",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
                PipelineStep(
                    name="step2", pipeline="test.transform_data", depends_on=["step1"]
                ),
                PipelineStep(
                    name="step3", pipeline="test.validate_data", depends_on=["step1"]
                ),
                PipelineStep(
                    name="step4", pipeline="test.persist_data", depends_on=["step2", "step3"]
                ),
            ],
            policy=ExecutionPolicy(
                mode=ExecutionMode.PARALLEL, max_concurrency=4
            ),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # All should complete
        assert result.status == GroupExecutionStatus.COMPLETED
        assert len(result.step_executions) == 4

        # Verify execution order respects dependencies
        step_order = {
            ex.step_name: i for i, ex in enumerate(result.step_executions)
        }
        # step1 must complete before step2 and step3
        # step2 and step3 must complete before step4
        assert step_order["step1"] < step_order["step4"]

    def test_parallel_stop_on_failure(self):
        """Test STOP policy in parallel mode."""
        from spine.orchestration.models import (
            ExecutionMode,
            ExecutionPolicy,
            FailurePolicy,
        )

        group = PipelineGroup(
            name="test.parallel_stop",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.failing_pipeline"),
                PipelineStep(name="step2", pipeline="test.fetch_data"),
                PipelineStep(
                    name="step3", pipeline="test.transform_data", depends_on=["step1"]
                ),
            ],
            policy=ExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
                on_failure=FailurePolicy.STOP,
                max_concurrency=2,
            ),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # Group should fail
        assert result.status == GroupExecutionStatus.FAILED

        # step1 failed, step3 depends on it so should be skipped
        step1 = result.get_step_execution("step1")
        step3 = result.get_step_execution("step3")
        assert step1.status == StepStatus.FAILED
        assert step3.status == StepStatus.SKIPPED

    def test_parallel_continue_on_failure(self):
        """Test CONTINUE policy in parallel mode."""
        from spine.orchestration.models import (
            ExecutionMode,
            ExecutionPolicy,
            FailurePolicy,
        )

        group = PipelineGroup(
            name="test.parallel_continue",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.failing_pipeline"),
                PipelineStep(name="step2", pipeline="test.fetch_data"),
                PipelineStep(name="step3", pipeline="test.transform_data"),
            ],
            policy=ExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
                on_failure=FailurePolicy.CONTINUE,
                max_concurrency=3,
            ),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # Group should be partial (some failed, some succeeded)
        assert result.status == GroupExecutionStatus.PARTIAL

        # step1 failed, but step2 and step3 should succeed
        step1 = result.get_step_execution("step1")
        step2 = result.get_step_execution("step2")
        step3 = result.get_step_execution("step3")
        assert step1.status == StepStatus.FAILED
        assert step2.status == StepStatus.COMPLETED
        assert step3.status == StepStatus.COMPLETED

    def test_parallel_max_concurrency(self):
        """Test that max_concurrency limits concurrent execution."""
        from spine.orchestration.models import ExecutionMode, ExecutionPolicy

        group = PipelineGroup(
            name="test.parallel_concurrency",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
                PipelineStep(name="step2", pipeline="test.transform_data"),
                PipelineStep(name="step3", pipeline="test.validate_data"),
                PipelineStep(name="step4", pipeline="test.persist_data"),
            ],
            policy=ExecutionPolicy(
                mode=ExecutionMode.PARALLEL, max_concurrency=2
            ),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # All should complete (concurrency just limits parallelism)
        assert result.status == GroupExecutionStatus.COMPLETED
        assert len(result.step_executions) == 4

    def test_parallel_defaults_to_sequential_for_chain(self):
        """Test that a linear chain in parallel mode still works correctly."""
        from spine.orchestration.models import ExecutionMode, ExecutionPolicy

        # Linear chain: each step depends on previous
        group = PipelineGroup(
            name="test.parallel_chain",
            domain="test",
            steps=[
                PipelineStep(name="step1", pipeline="test.fetch_data"),
                PipelineStep(
                    name="step2", pipeline="test.transform_data", depends_on=["step1"]
                ),
                PipelineStep(
                    name="step3", pipeline="test.validate_data", depends_on=["step2"]
                ),
            ],
            policy=ExecutionPolicy(
                mode=ExecutionMode.PARALLEL, max_concurrency=3
            ),
        )
        register_group(group)

        resolver = PlanResolver()
        plan = resolver.resolve(group)

        runner = GroupRunner()
        result = runner.execute(plan)

        # All should complete in order
        assert result.status == GroupExecutionStatus.COMPLETED

        # Verify order
        step_names = [ex.step_name for ex in result.step_executions]
        assert step_names == ["step1", "step2", "step3"]
