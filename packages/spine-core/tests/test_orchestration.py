"""
Tests for spine.orchestration module.

Covers:
- Models (PipelineGroup, PipelineStep, ExecutionPolicy)
- Registry (register, get, list, clear)
- Planner (DAG validation, topological sort, parameter merging)
- Loader (YAML parsing)
"""

import pytest
from datetime import datetime

from spine.orchestration import (
    # Models
    PipelineGroup,
    PipelineStep,
    ExecutionPolicy,
    FailurePolicy,
    ExecutionPlan,
    PlannedStep,
    GroupRunStatus,
    # Exceptions
    GroupError,
    GroupNotFoundError,
    CycleDetectedError,
    PlanResolutionError,
    StepNotFoundError,
    InvalidGroupSpecError,
    # Registry
    register_group,
    get_group,
    list_groups,
    clear_group_registry,
    group_exists,
    # Planner
    PlanResolver,
)
from spine.orchestration.models import ExecutionMode
from spine.orchestration.exceptions import DependencyError


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    clear_group_registry()
    yield
    clear_group_registry()


@pytest.fixture
def simple_group():
    """A simple linear group: A -> B -> C."""
    return PipelineGroup(
        name="test.simple",
        domain="test",
        steps=[
            PipelineStep("step_a", "pipeline.a"),
            PipelineStep("step_b", "pipeline.b", depends_on=["step_a"]),
            PipelineStep("step_c", "pipeline.c", depends_on=["step_b"]),
        ],
    )


@pytest.fixture
def diamond_group():
    """
    Diamond dependency pattern:
        A
       / \\
      B   C
       \\ /
        D
    """
    return PipelineGroup(
        name="test.diamond",
        domain="test",
        steps=[
            PipelineStep("step_a", "pipeline.a"),
            PipelineStep("step_b", "pipeline.b", depends_on=["step_a"]),
            PipelineStep("step_c", "pipeline.c", depends_on=["step_a"]),
            PipelineStep("step_d", "pipeline.d", depends_on=["step_b", "step_c"]),
        ],
    )


@pytest.fixture
def parallel_group():
    """Group with independent steps (no dependencies)."""
    return PipelineGroup(
        name="test.parallel",
        domain="test",
        steps=[
            PipelineStep("step_a", "pipeline.a"),
            PipelineStep("step_b", "pipeline.b"),
            PipelineStep("step_c", "pipeline.c"),
        ],
        policy=ExecutionPolicy.parallel(max_concurrency=3),
    )


# =============================================================================
# Model Tests
# =============================================================================


class TestPipelineStep:
    """Tests for PipelineStep dataclass."""

    def test_step_creation(self):
        """Test basic step creation."""
        step = PipelineStep("ingest", "finra.ingest_week")
        assert step.name == "ingest"
        assert step.pipeline == "finra.ingest_week"
        assert step.depends_on == ()
        assert step.params == {}

    def test_step_with_dependencies(self):
        """Test step with dependencies."""
        step = PipelineStep("normalize", "finra.normalize", depends_on=["ingest"])
        assert step.depends_on == ("ingest",)

    def test_step_with_params(self):
        """Test step with parameters."""
        step = PipelineStep("ingest", "finra.ingest", params={"tier": "NMS_TIER_1"})
        assert step.params == {"tier": "NMS_TIER_1"}

    def test_step_from_dict(self):
        """Test creating step from dictionary."""
        data = {
            "name": "aggregate",
            "pipeline": "finra.aggregate",
            "depends_on": ["normalize"],
            "params": {"force": True},
        }
        step = PipelineStep.from_dict(data)
        assert step.name == "aggregate"
        assert step.pipeline == "finra.aggregate"
        assert step.depends_on == ("normalize",)
        assert step.params == {"force": True}

    def test_step_to_dict(self):
        """Test step serialization."""
        step = PipelineStep("normalize", "finra.normalize", depends_on=["ingest"])
        d = step.to_dict()
        assert d["name"] == "normalize"
        assert d["pipeline"] == "finra.normalize"
        assert d["depends_on"] == ["ingest"]

    def test_step_depends_on_normalized_to_tuple(self):
        """Test that depends_on list is normalized to tuple."""
        step = PipelineStep("test", "pipeline", depends_on=["a", "b"])
        assert isinstance(step.depends_on, tuple)


class TestExecutionPolicy:
    """Tests for ExecutionPolicy dataclass."""

    def test_default_policy(self):
        """Test default policy values."""
        policy = ExecutionPolicy()
        assert policy.mode == ExecutionMode.SEQUENTIAL
        assert policy.max_concurrency == 4
        assert policy.on_failure == FailurePolicy.STOP
        assert policy.timeout_minutes is None

    def test_sequential_factory(self):
        """Test sequential policy factory."""
        policy = ExecutionPolicy.sequential(on_failure=FailurePolicy.CONTINUE)
        assert policy.mode == ExecutionMode.SEQUENTIAL
        assert policy.on_failure == FailurePolicy.CONTINUE

    def test_parallel_factory(self):
        """Test parallel policy factory."""
        policy = ExecutionPolicy.parallel(max_concurrency=8)
        assert policy.mode == ExecutionMode.PARALLEL
        assert policy.max_concurrency == 8

    def test_invalid_max_concurrency(self):
        """Test that invalid max_concurrency raises error."""
        with pytest.raises(ValueError):
            ExecutionPolicy(max_concurrency=0)


class TestPipelineGroup:
    """Tests for PipelineGroup dataclass."""

    def test_group_creation(self, simple_group):
        """Test basic group creation."""
        assert simple_group.name == "test.simple"
        assert simple_group.domain == "test"
        assert len(simple_group.steps) == 3

    def test_group_step_names(self, simple_group):
        """Test step_names property."""
        assert simple_group.step_names == ["step_a", "step_b", "step_c"]

    def test_group_get_step(self, simple_group):
        """Test get_step method."""
        step = simple_group.get_step("step_b")
        assert step is not None
        assert step.name == "step_b"

        assert simple_group.get_step("nonexistent") is None

    def test_duplicate_step_names_rejected(self):
        """Test that duplicate step names raise error."""
        with pytest.raises(ValueError, match="Duplicate step names"):
            PipelineGroup(
                name="test.duplicate",
                steps=[
                    PipelineStep("ingest", "pipeline.a"),
                    PipelineStep("ingest", "pipeline.b"),  # Duplicate!
                ],
            )

    def test_group_from_dict_flat(self):
        """Test creating group from flat dictionary."""
        data = {
            "name": "test.flat",
            "domain": "test",
            "steps": [
                {"name": "a", "pipeline": "pipeline.a"},
                {"name": "b", "pipeline": "pipeline.b", "depends_on": ["a"]},
            ],
        }
        group = PipelineGroup.from_dict(data)
        assert group.name == "test.flat"
        assert len(group.steps) == 2

    def test_group_from_dict_yaml_format(self):
        """Test creating group from YAML-style nested dictionary."""
        data = {
            "apiVersion": "spine.io/v1",
            "kind": "PipelineGroup",
            "metadata": {
                "name": "test.yaml",
                "domain": "test",
                "version": 2,
            },
            "spec": {
                "pipelines": [
                    {"name": "a", "pipeline": "pipeline.a"},
                    {"name": "b", "pipeline": "pipeline.b", "depends_on": ["a"]},
                ],
                "policy": {
                    "execution": "parallel",
                    "max_concurrency": 2,
                },
            },
        }
        group = PipelineGroup.from_dict(data)
        assert group.name == "test.yaml"
        assert group.version == 2
        assert group.policy.mode == ExecutionMode.PARALLEL
        assert group.policy.max_concurrency == 2

    def test_group_to_dict(self, simple_group):
        """Test group serialization."""
        d = simple_group.to_dict()
        assert d["name"] == "test.simple"
        assert d["domain"] == "test"
        assert len(d["steps"]) == 3


# =============================================================================
# Registry Tests
# =============================================================================


class TestGroupRegistry:
    """Tests for group registry functions."""

    def test_register_group(self, simple_group):
        """Test registering a group."""
        register_group(simple_group)
        assert group_exists("test.simple")

    def test_get_group(self, simple_group):
        """Test getting a registered group."""
        register_group(simple_group)
        retrieved = get_group("test.simple")
        assert retrieved.name == simple_group.name

    def test_get_nonexistent_group(self):
        """Test getting a non-existent group raises error."""
        with pytest.raises(GroupNotFoundError):
            get_group("nonexistent.group")

    def test_list_groups(self, simple_group, diamond_group):
        """Test listing registered groups."""
        register_group(simple_group)
        register_group(diamond_group)
        names = list_groups()
        assert "test.simple" in names
        assert "test.diamond" in names

    def test_list_groups_by_domain(self):
        """Test filtering groups by domain."""
        register_group(PipelineGroup(name="domain1.group", domain="domain1", steps=[
            PipelineStep("a", "pipeline.a"),
        ]))
        register_group(PipelineGroup(name="domain2.group", domain="domain2", steps=[
            PipelineStep("a", "pipeline.a"),
        ]))

        domain1_groups = list_groups(domain="domain1")
        assert "domain1.group" in domain1_groups
        assert "domain2.group" not in domain1_groups

    def test_duplicate_registration_rejected(self, simple_group):
        """Test that registering same name twice raises error."""
        register_group(simple_group)
        with pytest.raises(ValueError, match="already registered"):
            register_group(simple_group)

    def test_clear_registry(self, simple_group):
        """Test clearing the registry."""
        register_group(simple_group)
        assert group_exists("test.simple")

        clear_group_registry()
        assert not group_exists("test.simple")

    def test_register_as_decorator(self):
        """Test using register_group as a decorator."""

        @register_group
        def my_group():
            return PipelineGroup(
                name="test.decorated",
                steps=[PipelineStep("a", "pipeline.a")],
            )

        assert group_exists("test.decorated")


# =============================================================================
# Planner Tests
# =============================================================================


class TestPlanResolver:
    """Tests for PlanResolver class."""

    @pytest.fixture
    def resolver(self):
        """Create resolver with pipeline validation disabled."""
        return PlanResolver(validate_pipelines=False)

    def test_resolve_simple_group(self, resolver, simple_group):
        """Test resolving a simple linear group."""
        plan = resolver.resolve(simple_group)

        assert plan.group_name == "test.simple"
        assert len(plan.steps) == 3

        # Check topological order: A before B before C
        step_order = [s.step_name for s in plan.steps]
        assert step_order.index("step_a") < step_order.index("step_b")
        assert step_order.index("step_b") < step_order.index("step_c")

    def test_resolve_diamond_group(self, resolver, diamond_group):
        """Test resolving diamond dependency pattern."""
        plan = resolver.resolve(diamond_group)

        step_order = [s.step_name for s in plan.steps]

        # A must come first
        assert step_order[0] == "step_a"

        # D must come last
        assert step_order[-1] == "step_d"

        # B and C can be in any order, but both after A and before D
        assert step_order.index("step_b") < step_order.index("step_d")
        assert step_order.index("step_c") < step_order.index("step_d")

    def test_resolve_parallel_group(self, resolver, parallel_group):
        """Test resolving group with no dependencies."""
        plan = resolver.resolve(parallel_group)

        # All steps have no dependencies, order should match definition
        step_order = [s.step_name for s in plan.steps]
        assert step_order == ["step_a", "step_b", "step_c"]

    def test_batch_id_generated(self, resolver, simple_group):
        """Test that batch_id is auto-generated."""
        plan = resolver.resolve(simple_group)
        assert plan.batch_id is not None
        assert "group_test.simple" in plan.batch_id

    def test_custom_batch_id(self, resolver, simple_group):
        """Test using custom batch_id."""
        plan = resolver.resolve(simple_group, batch_id="custom_batch_123")
        assert plan.batch_id == "custom_batch_123"

    def test_sequence_order_assigned(self, resolver, simple_group):
        """Test that sequence_order is correctly assigned."""
        plan = resolver.resolve(simple_group)

        orders = [s.sequence_order for s in plan.steps]
        assert orders == [0, 1, 2]


class TestCycleDetection:
    """Tests for cycle detection in dependency graphs."""

    @pytest.fixture
    def resolver(self):
        return PlanResolver(validate_pipelines=False)

    def test_simple_cycle_detected(self, resolver):
        """Test detection of simple A -> B -> A cycle."""
        group = PipelineGroup(
            name="test.cycle",
            steps=[
                PipelineStep("a", "pipeline.a", depends_on=["b"]),
                PipelineStep("b", "pipeline.b", depends_on=["a"]),
            ],
        )

        with pytest.raises(CycleDetectedError) as exc_info:
            resolver.resolve(group)

        # Cycle should be reported
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
        """Test detection of longer cycle: A -> B -> C -> A."""
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
        assert params["b"] == "run_b"       # Run params override default
        assert params["c"] == "step_c"      # Step params override run params


# =============================================================================
# ExecutionPlan Tests
# =============================================================================


class TestExecutionPlan:
    """Tests for ExecutionPlan dataclass."""

    def test_plan_step_count(self):
        """Test step_count property."""
        plan = ExecutionPlan(
            group_name="test",
            group_version=1,
            batch_id="batch_123",
            steps=[
                PlannedStep("a", "pipeline.a", {}, (), 0),
                PlannedStep("b", "pipeline.b", {}, ("a",), 1),
            ],
            policy=ExecutionPolicy(),
        )
        assert plan.step_count == 2

    def test_plan_get_step(self):
        """Test get_step method."""
        plan = ExecutionPlan(
            group_name="test",
            group_version=1,
            batch_id="batch_123",
            steps=[
                PlannedStep("a", "pipeline.a", {}, (), 0),
                PlannedStep("b", "pipeline.b", {}, ("a",), 1),
            ],
            policy=ExecutionPolicy(),
        )

        step = plan.get_step("a")
        assert step is not None
        assert step.pipeline_name == "pipeline.a"

        assert plan.get_step("nonexistent") is None

    def test_plan_to_dict(self):
        """Test plan serialization."""
        plan = ExecutionPlan(
            group_name="test",
            group_version=1,
            batch_id="batch_123",
            steps=[PlannedStep("a", "pipeline.a", {"key": "value"}, (), 0)],
            policy=ExecutionPolicy.parallel(max_concurrency=2),
            params={"tier": "OTC"},
        )

        d = plan.to_dict()
        assert d["group_name"] == "test"
        assert d["batch_id"] == "batch_123"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["params"] == {"key": "value"}
        assert d["policy"]["execution"] == "parallel"
        assert d["params"]["tier"] == "OTC"


# =============================================================================
# Integration Tests
# =============================================================================


class TestOrchestrationIntegration:
    """End-to-end integration tests."""

    def test_full_workflow(self):
        """Test complete workflow: define -> register -> resolve."""
        # Define group using Python DSL
        group = PipelineGroup(
            name="integration.full_workflow",
            domain="integration_test",
            description="Test the full workflow",
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
        assert group_exists("integration.full_workflow")

        # Retrieve
        retrieved = get_group("integration.full_workflow")
        assert retrieved.domain == "integration_test"

        # Resolve (without pipeline validation)
        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(
            retrieved,
            params={"tier": "NMS_TIER_1"},
        )

        # Verify plan
        assert plan.group_name == "integration.full_workflow"
        assert plan.step_count == 3

        # Verify parameter merging
        ingest_step = plan.get_step("ingest")
        assert ingest_step.params["week_ending"] == "2026-01-03"
        assert ingest_step.params["tier"] == "NMS_TIER_1"

        aggregate_step = plan.get_step("aggregate")
        assert aggregate_step.params["force"] is True  # Step-level param preserved

    def test_from_yaml_format(self):
        """Test creating group from YAML-like data structure."""
        yaml_data = {
            "apiVersion": "spine.io/v1",
            "kind": "PipelineGroup",
            "metadata": {
                "name": "finra.weekly_refresh",
                "domain": "finra.otc_transparency",
                "version": 1,
                "description": "Weekly FINRA data refresh",
            },
            "spec": {
                "defaults": {
                    "tier": "NMS_TIER_1",
                },
                "pipelines": [
                    {"name": "ingest", "pipeline": "finra.otc_transparency.ingest_week"},
                    {
                        "name": "normalize",
                        "pipeline": "finra.otc_transparency.normalize_week",
                        "depends_on": ["ingest"],
                    },
                    {
                        "name": "aggregate",
                        "pipeline": "finra.otc_transparency.aggregate_week",
                        "depends_on": ["normalize"],
                    },
                    {
                        "name": "rolling",
                        "pipeline": "finra.otc_transparency.compute_rolling",
                        "depends_on": ["aggregate"],
                    },
                ],
                "policy": {
                    "execution": "sequential",
                    "on_failure": "stop",
                },
            },
        }

        group = PipelineGroup.from_dict(yaml_data)
        assert group.name == "finra.weekly_refresh"
        assert group.domain == "finra.otc_transparency"
        assert len(group.steps) == 4
        assert group.defaults["tier"] == "NMS_TIER_1"

        # Resolve
        resolver = PlanResolver(validate_pipelines=False)
        plan = resolver.resolve(group, params={"week_ending": "2026-01-03"})

        # Verify order
        step_order = [s.step_name for s in plan.steps]
        assert step_order == ["ingest", "normalize", "aggregate", "rolling"]
