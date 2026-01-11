"""
Tests for spine.orchestration.models module.

Tests cover:
- PipelineStep creation and serialization
- PipelineGroup creation and validation
- ExecutionPolicy factories and validation
- ExecutionPlan structure
- PlannedStep dataclass
"""

import pytest

from spine.orchestration.models import (
    PipelineStep,
    PipelineGroup,
    ExecutionPolicy,
    ExecutionMode,
    FailurePolicy,
    ExecutionPlan,
    PlannedStep,
    GroupRunStatus,
)


class TestPipelineStep:
    """Tests for PipelineStep dataclass."""

    def test_step_creation_minimal(self):
        """Test minimal step creation."""
        step = PipelineStep("ingest", "finra.ingest_week")
        
        assert step.name == "ingest"
        assert step.pipeline == "finra.ingest_week"
        assert step.depends_on == ()
        assert step.params == {}

    def test_step_with_dependencies(self):
        """Test step with dependencies."""
        step = PipelineStep("normalize", "finra.normalize", depends_on=["ingest"])
        
        assert step.depends_on == ("ingest",)

    def test_step_with_multiple_dependencies(self):
        """Test step with multiple dependencies."""
        step = PipelineStep("merge", "pipeline.merge", depends_on=["source1", "source2"])
        
        assert set(step.depends_on) == {"source1", "source2"}

    def test_step_with_params(self):
        """Test step with parameters."""
        step = PipelineStep("ingest", "finra.ingest", params={"tier": "NMS_TIER_1"})
        
        assert step.params == {"tier": "NMS_TIER_1"}

    def test_step_depends_on_normalized_to_tuple(self):
        """Test that depends_on list is normalized to tuple."""
        step = PipelineStep("test", "pipeline", depends_on=["a", "b"])
        
        assert isinstance(step.depends_on, tuple)

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
        """Test step serialization to dict."""
        step = PipelineStep("normalize", "finra.normalize", depends_on=["ingest"])
        
        d = step.to_dict()
        
        assert d["name"] == "normalize"
        assert d["pipeline"] == "finra.normalize"
        assert d["depends_on"] == ["ingest"]


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

    def test_invalid_max_concurrency_raises(self):
        """Test that invalid max_concurrency raises error."""
        with pytest.raises(ValueError):
            ExecutionPolicy(max_concurrency=0)
        
        with pytest.raises(ValueError):
            ExecutionPolicy(max_concurrency=-1)


class TestPipelineGroup:
    """Tests for PipelineGroup dataclass."""

    def test_group_creation_minimal(self):
        """Test minimal group creation."""
        group = PipelineGroup(
            name="test.minimal",
            steps=[PipelineStep("a", "pipeline.a")],
        )
        
        assert group.name == "test.minimal"
        assert len(group.steps) == 1

    def test_group_with_domain(self):
        """Test group with domain."""
        group = PipelineGroup(
            name="finra.weekly",
            domain="finra.otc_transparency",
            steps=[PipelineStep("a", "pipeline.a")],
        )
        
        assert group.domain == "finra.otc_transparency"

    def test_group_step_names_property(self):
        """Test step_names property."""
        group = PipelineGroup(
            name="test.multi",
            steps=[
                PipelineStep("step_a", "pipeline.a"),
                PipelineStep("step_b", "pipeline.b"),
                PipelineStep("step_c", "pipeline.c"),
            ],
        )
        
        assert group.step_names == ["step_a", "step_b", "step_c"]

    def test_group_get_step(self):
        """Test get_step method."""
        group = PipelineGroup(
            name="test.get",
            steps=[
                PipelineStep("step_a", "pipeline.a"),
                PipelineStep("step_b", "pipeline.b"),
            ],
        )
        
        step = group.get_step("step_b")
        assert step is not None
        assert step.name == "step_b"
        
        assert group.get_step("nonexistent") is None

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

    def test_group_to_dict(self, simple_linear_group):
        """Test group serialization."""
        d = simple_linear_group.to_dict()
        
        assert d["name"] == "test.simple_linear"
        assert d["domain"] == "test"
        assert len(d["steps"]) == 3


class TestPlannedStep:
    """Tests for PlannedStep dataclass."""

    def test_planned_step_creation(self):
        """Test PlannedStep creation."""
        step = PlannedStep(
            step_name="ingest",
            pipeline_name="finra.ingest",
            params={"tier": "NMS_TIER_1"},
            depends_on=(),
            sequence_order=0,
        )
        
        assert step.step_name == "ingest"
        assert step.pipeline_name == "finra.ingest"
        assert step.params["tier"] == "NMS_TIER_1"
        assert step.sequence_order == 0


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


class TestGroupRunStatus:
    """Tests for GroupRunStatus enum."""

    def test_status_values(self):
        """Test all status values exist."""
        assert GroupRunStatus.PENDING.value == "pending"
        assert GroupRunStatus.RUNNING.value == "running"
        assert GroupRunStatus.COMPLETED.value == "completed"
        assert GroupRunStatus.FAILED.value == "failed"
        assert GroupRunStatus.CANCELLED.value == "cancelled"


class TestFailurePolicy:
    """Tests for FailurePolicy enum."""

    def test_failure_policy_values(self):
        """Test failure policy values."""
        assert FailurePolicy.STOP.value == "stop"
        assert FailurePolicy.CONTINUE.value == "continue"


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_execution_mode_values(self):
        """Test execution mode values."""
        assert ExecutionMode.SEQUENTIAL.value == "sequential"
        assert ExecutionMode.PARALLEL.value == "parallel"
