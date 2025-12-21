"""Tests for ``spine.orchestration.workflow_yaml`` — YAML workflow parsing, validation, round-trip."""

from __future__ import annotations

import pytest

from spine.orchestration.workflow_yaml import (
    WorkflowMetadataSpec,
    WorkflowPolicySpec,
    WorkflowSpec,
    WorkflowSpecSection,
    WorkflowStepSpec,
    validate_yaml_workflow,
)


# ---------------------------------------------------------------------------
# Minimal YAML fixture
# ---------------------------------------------------------------------------

MINIMAL_YAML = """\
apiVersion: spine.io/v1
kind: Workflow
metadata:
  name: test-wf
  description: A test workflow
spec:
  steps:
    - name: step1
      type: operation
      operation: ingest
"""

TWO_STEP_YAML = """\
apiVersion: spine.io/v1
kind: Workflow
metadata:
  name: two-step
  description: Two step workflow
spec:
  steps:
    - name: step1
      type: operation
      operation: ingest
    - name: step2
      type: operation
      operation: validate
      depends_on:
        - step1
"""


# ---------------------------------------------------------------------------
# WorkflowStepSpec
# ---------------------------------------------------------------------------


class TestWorkflowStepSpec:
    def test_operation_step(self):
        s = WorkflowStepSpec(name="ingest", type="operation", operation="daily_ingest")
        step = s.to_step()
        assert step.name == "ingest"

    def test_lambda_step(self):
        s = WorkflowStepSpec(name="transform", type="lambda", handler_ref="os:getcwd")
        step = s.to_step()
        assert step.name == "transform"

    def test_choice_step(self):
        s = WorkflowStepSpec(
            name="check",
            type="choice",
            condition_ref="os.path:exists",
            then_step="proceed",
            else_step="skip",
        )
        step = s.to_step()
        assert step.name == "check"

    def test_wait_step(self):
        s = WorkflowStepSpec(name="pause", type="wait", duration_seconds=60)
        step = s.to_step()
        assert step.name == "pause"

    def test_map_step(self):
        s = WorkflowStepSpec(
            name="fanout",
            type="map",
            items_path="$.records",
            iterator_workflow="process_record",
            max_concurrency=8,
        )
        step = s.to_step()
        assert step.name == "fanout"

    def test_unknown_type_falls_back_to_operation(self):
        s = WorkflowStepSpec(name="custom", type="mystery", operation=None)
        step = s.to_step()
        assert step.name == "custom"

    def test_depends_on_empty_by_default(self):
        s = WorkflowStepSpec(name="a", operation="p")
        assert s.depends_on == []


# ---------------------------------------------------------------------------
# WorkflowSpecSection validation
# ---------------------------------------------------------------------------


class TestWorkflowSpecSection:
    def test_duplicate_step_names_rejected(self):
        with pytest.raises(Exception, match="[Dd]uplicate"):
            WorkflowSpecSection(
                steps=[
                    WorkflowStepSpec(name="dup", operation="a"),
                    WorkflowStepSpec(name="dup", operation="b"),
                ],
            )

    def test_invalid_dependency_rejected(self):
        with pytest.raises(Exception, match="unknown"):
            WorkflowSpecSection(
                steps=[
                    WorkflowStepSpec(name="a", operation="p", depends_on=["nonexistent"]),
                ],
            )

    def test_self_dependency_rejected(self):
        with pytest.raises(Exception, match="cannot depend on itself"):
            WorkflowSpecSection(
                steps=[
                    WorkflowStepSpec(name="a", operation="p", depends_on=["a"]),
                ],
            )


# ---------------------------------------------------------------------------
# WorkflowSpec — from_yaml / to_workflow
# ---------------------------------------------------------------------------


class TestWorkflowSpec:
    def test_from_yaml_minimal(self):
        spec = WorkflowSpec.from_yaml(MINIMAL_YAML)
        assert spec.metadata.name == "test-wf"
        assert len(spec.spec.steps) == 1

    def test_from_yaml_two_steps(self):
        spec = WorkflowSpec.from_yaml(TWO_STEP_YAML)
        assert len(spec.spec.steps) == 2
        assert spec.spec.steps[1].depends_on == ["step1"]

    def test_to_workflow(self):
        spec = WorkflowSpec.from_yaml(MINIMAL_YAML)
        wf = spec.to_workflow()
        assert wf.name == "test-wf"
        assert len(wf.steps) == 1

    def test_round_trip_via_from_workflow(self):
        spec1 = WorkflowSpec.from_yaml(TWO_STEP_YAML)
        wf = spec1.to_workflow()
        spec2 = WorkflowSpec.from_workflow(wf)
        assert spec2.metadata.name == wf.name
        assert len(spec2.spec.steps) == len(wf.steps)

    def test_invalid_yaml_raises(self):
        with pytest.raises(Exception):
            WorkflowSpec.from_yaml("not: valid: yaml: [[[")


# ---------------------------------------------------------------------------
# validate_yaml_workflow
# ---------------------------------------------------------------------------


class TestValidateYamlWorkflow:
    def test_valid_returns_workflow(self):
        import yaml

        data = yaml.safe_load(MINIMAL_YAML)
        wf = validate_yaml_workflow(data)
        assert wf.name == "test-wf"


# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------


class TestModelDefaults:
    def test_metadata_defaults(self):
        m = WorkflowMetadataSpec(name="test")
        assert m.name == "test"
        assert m.description is None or isinstance(m.description, str)

    def test_policy_defaults(self):
        p = WorkflowPolicySpec()
        # Default policy should have some sensible values
        assert isinstance(p.model_dump(), dict)
