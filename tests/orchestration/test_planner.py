"""
Tests for spine.orchestration.planner module.

Tests cover:
- PlanResolver initialization
- DAG resolution and topological sort
- Cycle detection
- Dependency validation
- Parameter merging precedence
- Batch ID generation
"""

import pytest
from pathlib import Path

from spine.orchestration import (
    PipelineGroup,
    PipelineStep,
    ExecutionPolicy,
    FailurePolicy,
)
from spine.orchestration.planner import PlanResolver
from spine.orchestration.exceptions import (
    CycleDetectedError,
    DependencyError,
    PlanResolutionError,
)
from spine.orchestration.models import ExecutionMode


class TestPlanResolverInit:
    """Tests for PlanResolver initialization."""

    def test_resolver_default_validates_pipelines(self):
        """Test default resolver validates pipelines."""
        resolver = PlanResolver()
        assert resolver.validate_pipelines is True

    def test_resolver_can_skip_validation(self):
        """Test resolver can skip pipeline validation."""
        resolver = PlanResolver(validate_pipelines=False)
        assert resolver.validate_pipelines is False


class TestBasicResolution:
    """Tests for basic plan resolution."""

    @pytest.fixture
    def resolver(self):
        """Create resolver without pipeline validation."""
        return PlanResolver(validate_pipelines=False)

    def test_resolve_simple_linear(self, resolver, simple_linear_group):
        """Test resolving simple linear group A -> B -> C."""
        plan = resolver.resolve(simple_linear_group)

        assert plan.group_name == "test.simple_linear"
        assert len(plan.steps) == 3

        # Verify topological order
        step_order = [s.step_name for s in plan.steps]
        assert step_order.index("step_a") < step_order.index("step_b")
        assert step_order.index("step_b") < step_order.index("step_c")

    def test_resolve_diamond(self, resolver, diamond_dependency_group):
        """Test resolving diamond dependency pattern."""
        plan = resolver.resolve(diamond_dependency_group)

        step_order = [s.step_name for s in plan.steps]

        # A must be first
        assert step_order[0] == "step_a"

        # D must be last
        assert step_order[-1] == "step_d"

        # B and C must be between A and D
        b_idx = step_order.index("step_b")
        c_idx = step_order.index("step_c")
        assert 0 < b_idx < 3
        assert 0 < c_idx < 3

    def test_resolve_parallel_independent(self, resolver, parallel_independent_group):
        """Test resolving group with no dependencies."""
        plan = resolver.resolve(parallel_independent_group)

        # All steps should be present
        assert len(plan.steps) == 3

        # All steps have sequence_order assigned
        for step in plan.steps:
            assert step.sequence_order is not None

    def test_batch_id_auto_generated(self, resolver, simple_linear_group):
        """Test that batch_id is auto-generated."""
        plan = resolver.resolve(simple_linear_group)

        assert plan.batch_id is not None
        assert "group_test.simple_linear" in plan.batch_id

    def test_custom_batch_id(self, resolver, simple_linear_group):
        """Test using custom batch_id."""
        plan = resolver.resolve(simple_linear_group, batch_id="custom_batch_123")

        assert plan.batch_id == "custom_batch_123"

    def test_sequence_order_assigned(self, resolver, simple_linear_group):
        """Test that sequence_order is correctly assigned."""
        plan = resolver.resolve(simple_linear_group)

        orders = [s.sequence_order for s in plan.steps]
        assert orders == [0, 1, 2]


class TestCycleDetection:
    """Tests for cycle detection in dependency graphs."""

    @pytest.fixture
    def resolver(self):
        return PlanResolver(validate_pipelines=False)

    def test_simple_cycle_detected(self, resolver):
        """Test detection of A -> B -> A cycle."""
        group = PipelineGroup(
            name="test.cycle",
            steps=[
                PipelineStep("a", "pipeline.a", depends_on=["b"]),
                PipelineStep("b", "pipeline.b", depends_on=["a"]),
            ],
        )

        with pytest.raises(CycleDetectedError) as exc_info:
            resolver.resolve(group)

        assert len(exc_info.value.cycle) >= 2

    def test_self_cycle_detected(self, resolver):
        """Test detection of self-referential dependency."""
        group = PipelineGroup(
            name="test.self_cycle",
            steps=[
                PipelineStep("a", "pipeline.a", depends_on=["a"]),
            ],
        )

        with pytest.raises(CycleDetectedError):
            resolver.resolve(group)

    def test_long_cycle_detected(self, resolver):
        """Test detection of A -> B -> C -> A cycle."""
        group = PipelineGroup(
            name="test.long_cycle",
            steps=[
                PipelineStep("a", "pipeline.a", depends_on=["c"]),
                PipelineStep("b", "pipeline.b", depends_on=["a"]),
                PipelineStep("c", "pipeline.c", depends_on=["b"]),
            ],
        )

        with pytest.raises(CycleDetectedError):
            resolver.resolve(group)

    def test_cycle_with_additional_steps(self, resolver):
        """Test cycle detection when cycle is part of larger graph."""
        group = PipelineGroup(
            name="test.partial_cycle",
            steps=[
                PipelineStep("entry", "pipeline.entry"),
                PipelineStep("a", "pipeline.a", depends_on=["entry", "c"]),
                PipelineStep("b", "pipeline.b", depends_on=["a"]),
                PipelineStep("c", "pipeline.c", depends_on=["b"]),
            ],
        )

        with pytest.raises(CycleDetectedError):
            resolver.resolve(group)


class TestDependencyValidation:
    """Tests for dependency validation."""

    @pytest.fixture
    def resolver(self):
        return PlanResolver(validate_pipelines=False)

    def test_missing_dependency_detected(self, resolver):
        """Test that missing dependency raises error."""
        group = PipelineGroup(
            name="test.missing_dep",
            steps=[
                PipelineStep("a", "pipeline.a", depends_on=["nonexistent"]),
            ],
        )

        with pytest.raises(DependencyError) as exc_info:
            resolver.resolve(group)

        assert "nonexistent" in exc_info.value.missing_deps

    def test_multiple_missing_dependencies(self, resolver):
        """Test multiple missing dependencies reported."""
        group = PipelineGroup(
            name="test.multi_missing",
            steps=[
                PipelineStep("a", "pipeline.a", depends_on=["missing1", "missing2"]),
            ],
        )

        with pytest.raises(DependencyError) as exc_info:
            resolver.resolve(group)

        missing = exc_info.value.missing_deps
        assert "missing1" in missing
        assert "missing2" in missing


class TestParameterMerging:
    """Tests for parameter merging precedence."""

    @pytest.fixture
    def resolver(self):
        return PlanResolver(validate_pipelines=False)

    def test_defaults_applied(self, resolver):
        """Test that group defaults are applied."""
        group = PipelineGroup(
            name="test.defaults",
            defaults={"tier": "NMS_TIER_1", "force": False},
            steps=[PipelineStep("a", "pipeline.a")],
        )

        plan = resolver.resolve(group)

        assert plan.steps[0].params["tier"] == "NMS_TIER_1"
        assert plan.steps[0].params["force"] is False

    def test_run_params_override_defaults(self, resolver):
        """Test that run params override defaults."""
        group = PipelineGroup(
            name="test.override",
            defaults={"tier": "NMS_TIER_1", "force": False},
            steps=[PipelineStep("a", "pipeline.a")],
        )

        plan = resolver.resolve(group, params={"tier": "OTC"})

        assert plan.steps[0].params["tier"] == "OTC"
        assert plan.steps[0].params["force"] is False  # Default preserved

    def test_step_params_override_all(self, resolver):
        """Test that step params override everything."""
        group = PipelineGroup(
            name="test.step_override",
            defaults={"tier": "NMS_TIER_1"},
            steps=[
                PipelineStep("a", "pipeline.a", params={"tier": "NMS_TIER_2"}),
            ],
        )

        plan = resolver.resolve(group, params={"tier": "OTC"})

        # Step params win over both defaults and run params
        assert plan.steps[0].params["tier"] == "NMS_TIER_2"

    def test_full_precedence_chain(self, resolver):
        """Test complete precedence: defaults < run_params < step_params."""
        group = PipelineGroup(
            name="test.precedence",
            defaults={
                "a": "default_a",
                "b": "default_b",
                "c": "default_c",
            },
            steps=[
                PipelineStep("s1", "pipeline.a", params={"c": "step_c"}),
            ],
        )

        plan = resolver.resolve(group, params={"b": "run_b", "c": "run_c"})

        params = plan.steps[0].params
        assert params["a"] == "default_a"  # Only in defaults
        assert params["b"] == "run_b"  # Run params override default
        assert params["c"] == "step_c"  # Step params override run params


class TestComplexGraphs:
    """Tests for complex dependency graphs."""

    @pytest.fixture
    def resolver(self):
        return PlanResolver(validate_pipelines=False)

    def test_multiple_roots(self, resolver):
        """Test graph with multiple root nodes (no dependencies)."""
        group = PipelineGroup(
            name="test.multi_root",
            steps=[
                PipelineStep("root1", "pipeline.a"),
                PipelineStep("root2", "pipeline.b"),
                PipelineStep("middle", "pipeline.c", depends_on=["root1", "root2"]),
                PipelineStep("end", "pipeline.d", depends_on=["middle"]),
            ],
        )

        plan = resolver.resolve(group)

        step_order = [s.step_name for s in plan.steps]

        # Both roots must come before middle
        assert step_order.index("root1") < step_order.index("middle")
        assert step_order.index("root2") < step_order.index("middle")

        # Middle must come before end
        assert step_order.index("middle") < step_order.index("end")

    def test_wide_graph(self, resolver):
        """Test graph with many parallel branches."""
        group = PipelineGroup(
            name="test.wide",
            steps=[
                PipelineStep("start", "pipeline.start"),
                PipelineStep("branch1", "pipeline.b1", depends_on=["start"]),
                PipelineStep("branch2", "pipeline.b2", depends_on=["start"]),
                PipelineStep("branch3", "pipeline.b3", depends_on=["start"]),
                PipelineStep("branch4", "pipeline.b4", depends_on=["start"]),
                PipelineStep("end", "pipeline.end", depends_on=[
                    "branch1", "branch2", "branch3", "branch4"
                ]),
            ],
        )

        plan = resolver.resolve(group)

        step_order = [s.step_name for s in plan.steps]

        # Start must be first
        assert step_order[0] == "start"

        # End must be last
        assert step_order[-1] == "end"

        # All branches must be in the middle
        for branch in ["branch1", "branch2", "branch3", "branch4"]:
            idx = step_order.index(branch)
            assert 0 < idx < len(step_order) - 1
