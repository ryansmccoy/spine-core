"""
Integration tests for orchestration workflows.

These tests verify end-to-end behavior of the orchestration system,
from YAML loading through planning and execution.

Marked as integration tests - may be slower and involve file I/O.
"""

import pytest
from pathlib import Path

from spine.orchestration import (
    PipelineGroup,
    PipelineStep,
    ExecutionPolicy,
    FailurePolicy,
    register_group,
    get_group,
    group_exists,
    clear_group_registry,
)
from spine.orchestration.planner import PlanResolver
from spine.orchestration.loader import load_group_from_yaml


pytestmark = pytest.mark.integration


class TestFullOrchestrationWorkflow:
    """End-to-end integration tests for orchestration."""

    def test_python_dsl_to_plan(self):
        """Test complete workflow: define -> register -> resolve."""
        # Define group using Python DSL
        group = PipelineGroup(
            name="integration.python_dsl",
            domain="integration_test",
            description="Test Python DSL workflow",
            version=1,
            defaults={"week_ending": "2026-01-03"},
            steps=[
                PipelineStep("ingest", "test.ingest"),
                PipelineStep("normalize", "test.normalize", depends_on=["ingest"]),
                PipelineStep(
                    "aggregate",
                    "test.aggregate",
                    depends_on=["normalize"],
                    params={"force": True},
                ),
            ],
            policy=ExecutionPolicy.sequential(on_failure=FailurePolicy.STOP),
        )

        # Register
        register_group(group)
        assert group_exists("integration.python_dsl")

        # Retrieve
        retrieved = get_group("integration.python_dsl")
        assert retrieved.domain == "integration_test"

        # Resolve (without pipeline validation)
        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(
            retrieved,
            params={"tier": "NMS_TIER_1"},
        )

        # Verify plan
        assert plan.group_name == "integration.python_dsl"
        assert plan.step_count == 3

        # Verify topological order
        step_order = [s.step_name for s in plan.steps]
        assert step_order.index("ingest") < step_order.index("normalize")
        assert step_order.index("normalize") < step_order.index("aggregate")

        # Verify parameter merging
        ingest_step = plan.get_step("ingest")
        assert ingest_step.params["week_ending"] == "2026-01-03"
        assert ingest_step.params["tier"] == "NMS_TIER_1"

        aggregate_step = plan.get_step("aggregate")
        assert aggregate_step.params["force"] is True  # Step-level param preserved

    def test_yaml_to_plan(self, yaml_fixtures_dir):
        """Test complete workflow: YAML file -> parse -> register -> resolve."""
        # Load from YAML
        yaml_path = yaml_fixtures_dir / "sample_group.yaml"
        group = load_group_from_yaml(yaml_path)

        # Verify parsing
        assert group.name == "finra.weekly_refresh"
        assert group.domain == "finra.otc_transparency"
        assert len(group.steps) == 4

        # Register
        register_group(group)
        assert group_exists("finra.weekly_refresh")

        # Resolve
        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(
            group,
            params={"week_ending": "2026-01-03"},
        )

        # Verify execution order (linear chain)
        step_order = [s.step_name for s in plan.steps]
        assert step_order == ["ingest", "normalize", "aggregate", "rolling"]

        # Verify defaults were applied
        for step in plan.steps:
            assert step.params["tier"] == "NMS_TIER_1"

    def test_diamond_dependency_resolution(self, yaml_fixtures_dir):
        """Test diamond pattern resolves correctly from YAML."""
        yaml_path = yaml_fixtures_dir / "diamond_group.yaml"
        group = load_group_from_yaml(yaml_path)

        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(group)

        step_order = [s.step_name for s in plan.steps]

        # Verify topological constraints
        assert step_order[0] == "step_a"  # A must be first
        assert step_order[-1] == "step_d"  # D must be last

        # B and C must come between A and D
        b_idx = step_order.index("step_b")
        c_idx = step_order.index("step_c")
        assert 0 < b_idx < 3
        assert 0 < c_idx < 3

    def test_parallel_group_from_yaml(self, yaml_fixtures_dir):
        """Test parallel group loading and resolution."""
        yaml_path = yaml_fixtures_dir / "parallel_group.yaml"
        group = load_group_from_yaml(yaml_path)

        # Verify policy was parsed
        assert group.policy.max_concurrency == 4
        assert group.policy.on_failure == FailurePolicy.CONTINUE

        # Resolve
        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(group)

        # All steps should be present
        assert plan.step_count == 4

        # Defaults should be applied
        for step in plan.steps:
            assert step.params.get("batch_size") == 1000

    def test_invalid_yaml_cycle_detection(self, yaml_fixtures_dir):
        """Test that cycle in YAML is detected during resolution."""
        yaml_path = yaml_fixtures_dir / "invalid_cycle.yaml"
        group = load_group_from_yaml(yaml_path)

        resolver = PlanResolver(validate_pipelines=False)

        from spine.orchestration.exceptions import CycleDetectedError

        with pytest.raises(CycleDetectedError):
            resolver.resolve(group)


class TestParameterPropagation:
    """Integration tests for parameter handling across the workflow."""

    def test_parameters_flow_through_workflow(self):
        """Test that parameters flow correctly from run to planned steps."""
        group = PipelineGroup(
            name="integration.params",
            defaults={
                "env": "production",
                "debug": False,
            },
            steps=[
                PipelineStep("step1", "pipeline.a", params={"debug": True}),
                PipelineStep("step2", "pipeline.b", depends_on=["step1"]),
            ],
        )

        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(
            group,
            params={"run_id": "test-123", "env": "staging"},
        )

        # step1: debug=True (step override), env=staging (run override)
        step1 = plan.get_step("step1")
        assert step1.params["debug"] is True  # Step param wins
        assert step1.params["env"] == "staging"  # Run param overrides default
        assert step1.params["run_id"] == "test-123"  # Run param added

        # step2: debug=False (default), env=staging (run override)
        step2 = plan.get_step("step2")
        assert step2.params["debug"] is False  # Default
        assert step2.params["env"] == "staging"  # Run param
        assert step2.params["run_id"] == "test-123"  # Run param


class TestBatchIdHandling:
    """Integration tests for batch ID generation and propagation."""

    def test_auto_generated_batch_id(self):
        """Test that batch_id is auto-generated with group name."""
        group = PipelineGroup(
            name="integration.batch_test",
            steps=[PipelineStep("a", "pipeline.a")],
        )

        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(group)

        assert plan.batch_id is not None
        assert "integration.batch_test" in plan.batch_id

    def test_custom_batch_id_preserved(self):
        """Test that custom batch_id is preserved."""
        group = PipelineGroup(
            name="integration.custom_batch",
            steps=[PipelineStep("a", "pipeline.a")],
        )

        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(group, batch_id="my-custom-batch-id-12345")

        assert plan.batch_id == "my-custom-batch-id-12345"

    def test_batch_id_unique_per_resolve(self):
        """Test that each resolve generates a unique batch_id."""
        group = PipelineGroup(
            name="integration.unique_batch",
            steps=[PipelineStep("a", "pipeline.a")],
        )

        resolver = PlanResolver(validate_pipelines=False)
        plan1 = resolver.resolve(group)
        plan2 = resolver.resolve(group)

        assert plan1.batch_id != plan2.batch_id
