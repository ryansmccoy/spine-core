"""Tests for workflow serialization: to_dict, from_dict, to_yaml.

Part of Idea #3: Workflow Serialization in IDEAS_ROADMAP.md.
"""

from __future__ import annotations

import pytest
import yaml

from spine.orchestration import (
    Workflow,
    Step,
    StepType,
    StepResult,
)
from spine.orchestration.workflow import (
    ExecutionMode,
    FailurePolicy,
    WorkflowExecutionPolicy,
)
from spine.orchestration.workflow_yaml import WorkflowSpec


# =============================================================================
# Sample handlers for handler_ref tests
# =============================================================================


def sample_handler(ctx, config) -> StepResult:
    """Named handler for testing handler_ref."""
    return StepResult.ok(output={"processed": True})


def sample_condition(ctx) -> bool:
    """Named condition for testing condition_ref."""
    return ctx.get_param("route") == "a"


# =============================================================================
# Step.to_dict() tests
# =============================================================================


class TestStepToDict:
    """Test Step.to_dict() for all step types."""

    def test_pipeline_step_to_dict(self):
        """Pipeline step serializes correctly."""
        step = Step.pipeline("ingest", "finra.ingest", params={"batch_size": 100})
        d = step.to_dict()

        assert d["name"] == "ingest"
        assert d["type"] == "pipeline"
        assert d["pipeline"] == "finra.ingest"
        assert d["config"] == {"batch_size": 100}

    def test_pipeline_step_with_depends_on(self):
        """Pipeline step serializes depends_on."""
        step = Step.pipeline("process", "proc_pipeline", depends_on=["fetch", "validate"])
        d = step.to_dict()

        assert d["depends_on"] == ["fetch", "validate"]

    def test_lambda_step_with_named_handler(self):
        """Lambda step with named handler includes handler_ref."""
        step = Step.lambda_("validate", sample_handler)
        d = step.to_dict()

        assert d["name"] == "validate"
        assert d["type"] == "lambda"
        assert d["handler_ref"] == f"{__name__}:sample_handler"

    def test_lambda_step_with_inline_lambda(self):
        """Lambda step with inline lambda has no handler_ref."""
        step = Step.lambda_("inline", lambda ctx, cfg: StepResult.ok())
        d = step.to_dict()

        assert d["name"] == "inline"
        assert d["type"] == "lambda"
        assert "handler_ref" not in d  # Lambdas can't be serialized

    def test_choice_step_with_named_condition(self):
        """Choice step with named condition includes condition_ref."""
        step = Step.choice("route", sample_condition, "step_a", "step_b")
        d = step.to_dict()

        assert d["name"] == "route"
        assert d["type"] == "choice"
        assert d["then_step"] == "step_a"
        assert d["else_step"] == "step_b"
        assert d["condition_ref"] == f"{__name__}:sample_condition"

    def test_choice_step_with_inline_condition(self):
        """Choice step with inline condition has no condition_ref."""
        step = Step.choice("route", lambda ctx: True, "step_a", "step_b")
        d = step.to_dict()

        assert d["type"] == "choice"
        assert "condition_ref" not in d

    def test_wait_step_to_dict(self):
        """Wait step serializes duration."""
        step = Step.wait("pause", duration_seconds=30)
        d = step.to_dict()

        assert d["name"] == "pause"
        assert d["type"] == "wait"
        assert d["duration_seconds"] == 30

    def test_map_step_to_dict(self):
        """Map step serializes items_path and concurrency."""
        step = Step.map(
            "fan_out",
            items_path="$.data.items",
            iterator_workflow=None,
            max_concurrency=8,
        )
        d = step.to_dict()

        assert d["name"] == "fan_out"
        assert d["type"] == "map"
        assert d["items_path"] == "$.data.items"
        assert d["max_concurrency"] == 8

    def test_step_with_non_default_error_policy(self):
        """Step with CONTINUE error policy serializes it."""
        from spine.orchestration.step_types import ErrorPolicy

        step = Step.pipeline("risky_step", "risky.pipeline")
        step.on_error = ErrorPolicy.CONTINUE
        d = step.to_dict()

        assert d["on_error"] == "continue"


# =============================================================================
# Workflow.to_dict() / from_dict() round-trip tests
# =============================================================================


class TestWorkflowToDict:
    """Test Workflow.to_dict()."""

    def test_minimal_workflow_to_dict(self):
        """Minimal workflow serializes correctly."""
        workflow = Workflow(
            name="test.workflow",
            steps=[Step.pipeline("step1", "pipeline1")],
        )
        d = workflow.to_dict()

        assert d["name"] == "test.workflow"
        assert d["version"] == 1
        assert len(d["steps"]) == 1
        assert d["steps"][0]["name"] == "step1"

    def test_workflow_with_all_fields_to_dict(self):
        """Workflow with all fields serializes correctly."""
        workflow = Workflow(
            name="etl.daily",
            steps=[
                Step.pipeline("fetch", "fetcher"),
                Step.pipeline("transform", "transformer", depends_on=["fetch"]),
            ],
            domain="etl.sec",
            description="Daily SEC ETL workflow",
            version=3,
            defaults={"date": "2026-01-15"},
            tags=["production", "daily"],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
                max_concurrency=8,
                timeout_seconds=3600,
                on_failure=FailurePolicy.CONTINUE,
            ),
        )
        d = workflow.to_dict()

        assert d["name"] == "etl.daily"
        assert d["domain"] == "etl.sec"
        assert d["description"] == "Daily SEC ETL workflow"
        assert d["version"] == 3
        assert d["defaults"] == {"date": "2026-01-15"}
        assert d["tags"] == ["production", "daily"]
        assert d["execution_policy"]["mode"] == "parallel"
        assert d["execution_policy"]["max_concurrency"] == 8
        assert d["execution_policy"]["timeout_seconds"] == 3600
        assert d["execution_policy"]["on_failure"] == "continue"

    def test_workflow_omits_default_execution_policy(self):
        """Workflow with default execution_policy doesn't include it."""
        workflow = Workflow(
            name="simple",
            steps=[Step.pipeline("step1", "p1")],
        )
        d = workflow.to_dict()

        assert "execution_policy" not in d


class TestWorkflowFromDict:
    """Test Workflow.from_dict()."""

    def test_round_trip_pipeline_workflow(self):
        """Pipeline-only workflow round-trips through dict."""
        original = Workflow(
            name="etl.workflow",
            steps=[
                Step.pipeline("fetch", "fetcher"),
                Step.pipeline("process", "processor", depends_on=["fetch"]),
            ],
            domain="etl",
            version=2,
            defaults={"env": "production"},
        )

        d = original.to_dict()
        restored = Workflow.from_dict(d)

        assert restored.name == original.name
        assert restored.domain == original.domain
        assert restored.version == original.version
        assert restored.defaults == original.defaults
        assert len(restored.steps) == 2
        assert restored.steps[0].name == "fetch"
        assert restored.steps[1].depends_on == ("fetch",)

    def test_from_dict_with_lambda_handler_ref(self):
        """Lambda step with handler_ref resolves correctly."""
        d = {
            "name": "test.workflow",
            "version": 1,
            "steps": [
                {
                    "name": "validate",
                    "type": "lambda",
                    "handler_ref": f"{__name__}:sample_handler",
                },
            ],
        }
        workflow = Workflow.from_dict(d)

        assert workflow.steps[0].step_type == StepType.LAMBDA
        assert workflow.steps[0].handler is sample_handler

    def test_from_dict_with_choice_condition_ref(self):
        """Choice step with condition_ref resolves correctly."""
        d = {
            "name": "test.workflow",
            "version": 1,
            "steps": [
                {
                    "name": "route",
                    "type": "choice",
                    "condition_ref": f"{__name__}:sample_condition",
                    "then_step": "step_a",
                    "else_step": "step_b",
                },
                {"name": "step_a", "type": "pipeline", "pipeline": "pa"},
                {"name": "step_b", "type": "pipeline", "pipeline": "pb"},
            ],
        }
        workflow = Workflow.from_dict(d)

        assert workflow.steps[0].step_type == StepType.CHOICE
        assert workflow.steps[0].condition is sample_condition

    def test_from_dict_with_wait_step(self):
        """Wait step deserializes correctly."""
        d = {
            "name": "test.workflow",
            "version": 1,
            "steps": [
                {"name": "pause", "type": "wait", "duration_seconds": 60},
            ],
        }
        workflow = Workflow.from_dict(d)

        assert workflow.steps[0].step_type == StepType.WAIT
        assert workflow.steps[0].duration_seconds == 60

    def test_from_dict_with_map_step(self):
        """Map step deserializes correctly."""
        d = {
            "name": "test.workflow",
            "version": 1,
            "steps": [
                {
                    "name": "fan_out",
                    "type": "map",
                    "items_path": "$.items",
                    "iterator_workflow": "child.workflow",
                    "max_concurrency": 16,
                },
            ],
        }
        workflow = Workflow.from_dict(d)

        assert workflow.steps[0].step_type == StepType.MAP
        assert workflow.steps[0].items_path == "$.items"
        assert workflow.steps[0].iterator_workflow == "child.workflow"
        assert workflow.steps[0].max_concurrency == 16

    def test_from_dict_with_execution_policy(self):
        """Execution policy deserializes correctly."""
        d = {
            "name": "test.workflow",
            "version": 1,
            "steps": [{"name": "s1", "type": "pipeline", "pipeline": "p1"}],
            "execution_policy": {
                "mode": "parallel",
                "max_concurrency": 12,
                "timeout_seconds": 7200,
                "on_failure": "continue",
            },
        }
        workflow = Workflow.from_dict(d)

        assert workflow.execution_policy.mode == ExecutionMode.PARALLEL
        assert workflow.execution_policy.max_concurrency == 12
        assert workflow.execution_policy.timeout_seconds == 7200
        assert workflow.execution_policy.on_failure == FailurePolicy.CONTINUE

    def test_from_dict_with_invalid_handler_ref(self):
        """Invalid handler_ref creates placeholder handler."""
        d = {
            "name": "test.workflow",
            "version": 1,
            "steps": [
                {
                    "name": "bad_ref",
                    "type": "lambda",
                    "handler_ref": "nonexistent.module:missing_fn",
                },
            ],
        }
        workflow = Workflow.from_dict(d)

        # Should succeed - creates placeholder handler
        assert workflow.steps[0].step_type == StepType.LAMBDA
        assert workflow.steps[0].handler is not None

    def test_from_dict_unknown_step_type_raises(self):
        """Unknown step type raises ValueError."""
        d = {
            "name": "test.workflow",
            "version": 1,
            "steps": [{"name": "weird", "type": "quantum_teleport"}],
        }
        with pytest.raises(ValueError, match="Unknown step type"):
            Workflow.from_dict(d)


# =============================================================================
# Workflow.to_yaml() tests
# =============================================================================


class TestWorkflowToYaml:
    """Test Workflow.to_yaml()."""

    def test_to_yaml_produces_valid_yaml(self):
        """to_yaml produces parseable YAML."""
        workflow = Workflow(
            name="test.workflow",
            steps=[Step.pipeline("step1", "pipeline1")],
        )
        yaml_str = workflow.to_yaml()

        # Should be valid YAML
        data = yaml.safe_load(yaml_str)
        assert data["apiVersion"] == "spine.io/v1"
        assert data["kind"] == "Workflow"

    def test_to_yaml_includes_metadata(self):
        """to_yaml includes all metadata fields."""
        workflow = Workflow(
            name="etl.daily",
            domain="finance",
            version=5,
            description="Daily finance ETL",
            tags=["production", "etl"],
            steps=[Step.pipeline("run", "main_pipeline")],
        )
        yaml_str = workflow.to_yaml()
        data = yaml.safe_load(yaml_str)

        meta = data["metadata"]
        assert meta["name"] == "etl.daily"
        assert meta["domain"] == "finance"
        assert meta["version"] == 5
        assert meta["description"] == "Daily finance ETL"
        assert meta["tags"] == ["production", "etl"]

    def test_to_yaml_includes_spec(self):
        """to_yaml includes spec section with steps."""
        workflow = Workflow(
            name="test",
            steps=[
                Step.pipeline("a", "pa"),
                Step.pipeline("b", "pb", depends_on=["a"]),
            ],
            defaults={"env": "dev"},
        )
        yaml_str = workflow.to_yaml()
        data = yaml.safe_load(yaml_str)

        spec = data["spec"]
        assert spec["defaults"] == {"env": "dev"}
        assert len(spec["steps"]) == 2
        assert spec["steps"][0]["name"] == "a"

    def test_to_yaml_includes_policy(self):
        """to_yaml includes non-default policy."""
        workflow = Workflow(
            name="parallel",
            steps=[Step.pipeline("s1", "p1")],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
                max_concurrency=16,
            ),
        )
        yaml_str = workflow.to_yaml()
        data = yaml.safe_load(yaml_str)

        policy = data["spec"]["policy"]
        assert policy["execution"] == "parallel"
        assert policy["max_concurrency"] == 16

    def test_to_yaml_round_trip_via_workflowspec(self):
        """to_yaml output can be parsed by WorkflowSpec.from_yaml()."""
        original = Workflow(
            name="roundtrip",
            domain="test",
            steps=[
                Step.pipeline("fetch", "fetcher"),
                Step.pipeline("process", "processor", depends_on=["fetch"]),
            ],
        )
        yaml_str = original.to_yaml()

        # Parse with WorkflowSpec
        spec = WorkflowSpec.from_yaml(yaml_str)
        restored = spec.to_workflow()

        assert restored.name == original.name
        assert restored.domain == original.domain
        assert len(restored.steps) == 2
        assert restored.steps[1].depends_on == ("fetch",)


# =============================================================================
# WorkflowSpec.from_workflow() tests
# =============================================================================


class TestWorkflowSpecFromWorkflow:
    """Test WorkflowSpec.from_workflow()."""

    def test_from_workflow_creates_valid_spec(self):
        """from_workflow creates valid Pydantic model."""
        workflow = Workflow(
            name="spec.test",
            domain="testing",
            steps=[Step.pipeline("s1", "p1")],
        )
        spec = WorkflowSpec.from_workflow(workflow)

        assert spec.metadata.name == "spec.test"
        assert spec.metadata.domain == "testing"
        assert len(spec.spec.steps) == 1
        assert spec.spec.steps[0].name == "s1"

    def test_from_workflow_preserves_policy(self):
        """from_workflow preserves execution policy."""
        workflow = Workflow(
            name="policy.test",
            steps=[Step.pipeline("s1", "p1")],
            execution_policy=WorkflowExecutionPolicy(
                mode=ExecutionMode.PARALLEL,
                max_concurrency=10,
                on_failure=FailurePolicy.CONTINUE,
            ),
        )
        spec = WorkflowSpec.from_workflow(workflow)

        assert spec.spec.policy.execution == "parallel"
        assert spec.spec.policy.max_concurrency == 10
        assert spec.spec.policy.on_failure == "continue"

    def test_from_workflow_round_trip(self):
        """from_workflow + to_workflow round-trip."""
        original = Workflow(
            name="roundtrip.spec",
            domain="test",
            version=3,
            description="Round trip test",
            steps=[
                Step.pipeline("a", "pa", params={"x": 1}),
                Step.pipeline("b", "pb", depends_on=["a"]),
            ],
            defaults={"key": "value"},
            tags=["test", "roundtrip"],
        )
        spec = WorkflowSpec.from_workflow(original)
        restored = spec.to_workflow()

        assert restored.name == original.name
        assert restored.domain == original.domain
        assert restored.version == original.version
        assert restored.description == original.description
        assert len(restored.steps) == 2
        assert restored.steps[0].config == {"x": 1}
        assert restored.steps[1].depends_on == ("a",)
        assert restored.defaults == {"key": "value"}
        assert restored.tags == ["test", "roundtrip"]

    def test_from_workflow_with_non_pipeline_steps(self):
        """Non-pipeline steps serialize properly in WorkflowSpec."""
        workflow = Workflow(
            name="mixed",
            steps=[
                Step.pipeline("p1", "pipeline1"),
                Step.lambda_("l1", lambda ctx, cfg: StepResult.ok()),
            ],
        )
        spec = WorkflowSpec.from_workflow(workflow)

        # Lambda is preserved as type="lambda"
        assert spec.spec.steps[1].type == "lambda"
        assert spec.spec.steps[1].pipeline is None


# =============================================================================
# Handler ref utilities tests
# =============================================================================


class TestHandlerRef:
    """Test _callable_ref and resolve_callable_ref."""

    def test_callable_ref_for_named_function(self):
        """Named function returns module:qualname ref."""
        from spine.orchestration.step_types import _callable_ref

        ref = _callable_ref(sample_handler)
        assert ref == f"{__name__}:sample_handler"

    def test_callable_ref_for_lambda(self):
        """Lambda returns None."""
        from spine.orchestration.step_types import _callable_ref

        ref = _callable_ref(lambda x: x)
        assert ref is None

    def test_callable_ref_for_builtin(self):
        """Built-in may return a ref."""
        from spine.orchestration.step_types import _callable_ref

        ref = _callable_ref(len)
        # Built-ins return 'builtins:len' in Python 3.x
        assert ref is None or ref == "builtins:len"

    def test_resolve_callable_ref_success(self):
        """resolve_callable_ref imports named function."""
        from spine.orchestration.step_types import resolve_callable_ref

        ref = f"{__name__}:sample_handler"
        fn = resolve_callable_ref(ref)
        assert fn is sample_handler

    def test_resolve_callable_ref_imports_from_spine(self):
        """resolve_callable_ref can import from spine modules."""
        from spine.orchestration.step_types import resolve_callable_ref

        ref = "spine.orchestration:StepResult"
        cls = resolve_callable_ref(ref)
        assert cls is StepResult

    def test_resolve_callable_ref_invalid_module(self):
        """resolve_callable_ref raises for invalid module."""
        from spine.orchestration.step_types import resolve_callable_ref

        with pytest.raises(ImportError):
            resolve_callable_ref("nonexistent_module_xyz:func")

    def test_resolve_callable_ref_invalid_attr(self):
        """resolve_callable_ref raises for invalid attribute."""
        from spine.orchestration.step_types import resolve_callable_ref

        with pytest.raises(AttributeError):
            resolve_callable_ref(f"{__name__}:nonexistent_function_xyz")

    def test_resolve_callable_ref_missing_colon(self):
        """resolve_callable_ref raises for malformed ref."""
        from spine.orchestration.step_types import resolve_callable_ref

        with pytest.raises((ValueError, TypeError)):
            resolve_callable_ref("no_colon_here")
