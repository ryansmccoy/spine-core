"""Tests for workflow.py to boost coverage from 34% to ~90%."""
from __future__ import annotations

import pytest

from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import Workflow


class TestWorkflowConstruction:
    """Test Workflow creation and validation."""

    def test_basic_workflow(self):
        wf = Workflow(name="test", steps=[Step.pipeline("s1", "p1")])
        assert wf.name == "test"
        assert len(wf.steps) == 1

    def test_defaults(self):
        wf = Workflow(name="test", steps=[])
        assert wf.domain == ""
        assert wf.description == ""
        assert wf.version == 1
        assert wf.defaults == {}
        assert wf.tags == []

    def test_duplicate_step_names_raises(self):
        with pytest.raises(ValueError, match="Duplicate step name"):
            Workflow(
                name="bad",
                steps=[
                    Step.pipeline("dup", "p1"),
                    Step.pipeline("dup", "p2"),
                ],
            )

    def test_choice_unknown_then_step_raises(self):
        with pytest.raises(ValueError, match="references unknown then_step"):
            Workflow(
                name="bad",
                steps=[
                    Step.choice("pick", condition=lambda ctx: True, then_step="nope"),
                ],
            )

    def test_choice_unknown_else_step_raises(self):
        with pytest.raises(ValueError, match="references unknown else_step"):
            Workflow(
                name="bad",
                steps=[
                    Step.pipeline("ok_step", "p1"),
                    Step.choice(
                        "pick",
                        condition=lambda ctx: True,
                        then_step="ok_step",
                        else_step="missing",
                    ),
                ],
            )

    def test_valid_choice_references(self):
        wf = Workflow(
            name="ok",
            steps=[
                Step.pipeline("a", "p1"),
                Step.pipeline("b", "p2"),
                Step.choice("pick", condition=lambda ctx: True, then_step="a", else_step="b"),
            ],
        )
        assert len(wf.steps) == 3


class TestWorkflowAccessors:
    """Test accessor methods."""

    @pytest.fixture()
    def wf(self):
        return Workflow(
            name="test.wf",
            domain="test",
            steps=[
                Step.pipeline("ingest", "my.ingest"),
                Step.lambda_("validate", lambda ctx, cfg: None),
                Step.pipeline("load", "my.load"),
            ],
        )

    def test_get_step_found(self, wf):
        step = wf.get_step("validate")
        assert step is not None
        assert step.name == "validate"

    def test_get_step_not_found(self, wf):
        assert wf.get_step("nonexistent") is None

    def test_step_names(self, wf):
        assert wf.step_names() == ["ingest", "validate", "load"]

    def test_step_index_found(self, wf):
        assert wf.step_index("load") == 2

    def test_step_index_not_found(self, wf):
        assert wf.step_index("nonexistent") == -1


class TestWorkflowTierAnalysis:
    """Test tier analysis methods."""

    def test_basic_tier(self):
        wf = Workflow(name="t", steps=[Step.pipeline("s", "p")])
        assert wf.required_tier() == "basic"

    def test_intermediate_tier(self):
        wf = Workflow(
            name="t",
            steps=[
                Step.pipeline("a", "p1"),
                Step.pipeline("b", "p2"),
                Step.choice("c", condition=lambda ctx: True, then_step="a", else_step="b"),
            ],
        )
        assert wf.required_tier() == "intermediate"

    def test_advanced_tier(self):
        wf = Workflow(
            name="t",
            steps=[
                Step.pipeline("a", "p"),
                Step.wait("w", duration_seconds=5),
            ],
        )
        assert wf.required_tier() == "advanced"

    def test_has_choice_steps(self):
        wf = Workflow(
            name="t",
            steps=[
                Step.pipeline("a", "p"),
                Step.pipeline("b", "q"),
                Step.choice("c", condition=lambda ctx: True, then_step="a"),
            ],
        )
        assert wf.has_choice_steps()

    def test_has_no_choice_steps(self):
        wf = Workflow(name="t", steps=[Step.pipeline("a", "p")])
        assert not wf.has_choice_steps()

    def test_has_lambda_steps(self):
        wf = Workflow(name="t", steps=[Step.lambda_("a", lambda c, cfg: None)])
        assert wf.has_lambda_steps()

    def test_has_no_lambda_steps(self):
        wf = Workflow(name="t", steps=[Step.pipeline("a", "p")])
        assert not wf.has_lambda_steps()

    def test_has_pipeline_steps(self):
        wf = Workflow(name="t", steps=[Step.pipeline("a", "p")])
        assert wf.has_pipeline_steps()

    def test_has_no_pipeline_steps(self):
        wf = Workflow(name="t", steps=[Step.lambda_("a", lambda c, cfg: None)])
        assert not wf.has_pipeline_steps()

    def test_pipeline_names(self):
        wf = Workflow(
            name="t",
            steps=[
                Step.pipeline("a", "p1"),
                Step.lambda_("b", lambda c, cfg: None),
                Step.pipeline("c", "p2"),
            ],
        )
        assert wf.pipeline_names() == ["p1", "p2"]


class TestWorkflowSerialization:
    """Test to_dict/from_dict round-trip."""

    def test_to_dict_minimal(self):
        wf = Workflow(name="t", steps=[Step.pipeline("s", "p")])
        d = wf.to_dict()
        assert d["name"] == "t"
        assert d["version"] == 1
        assert len(d["steps"]) == 1
        assert "domain" not in d  # empty strings excluded

    def test_to_dict_full(self):
        wf = Workflow(
            name="full",
            steps=[Step.pipeline("s", "p")],
            domain="test.domain",
            description="A test workflow",
            version=2,
            defaults={"key": "value"},
            tags=["tag1", "tag2"],
        )
        d = wf.to_dict()
        assert d["domain"] == "test.domain"
        assert d["description"] == "A test workflow"
        assert d["defaults"] == {"key": "value"}
        assert d["tags"] == ["tag1", "tag2"]

    def test_from_dict_pipeline(self):
        data = {
            "name": "loaded",
            "domain": "test",
            "version": 3,
            "description": "From dict",
            "defaults": {"k": "v"},
            "tags": ["t1"],
            "steps": [
                {"name": "s1", "type": "pipeline", "pipeline": "my.pipeline", "config": {"x": 1}},
            ],
        }
        wf = Workflow.from_dict(data)
        assert wf.name == "loaded"
        assert wf.domain == "test"
        assert wf.version == 3
        assert wf.description == "From dict"
        assert wf.defaults == {"k": "v"}
        assert wf.tags == ["t1"]
        assert len(wf.steps) == 1
        assert wf.steps[0].pipeline_name == "my.pipeline"

    def test_from_dict_choice_supported(self):
        data = {
            "name": "choice_ok",
            "steps": [
                {"name": "a", "type": "pipeline", "pipeline": "pa"},
                {"name": "b", "type": "pipeline", "pipeline": "pb"},
                {"name": "c", "type": "choice", "then_step": "a", "else_step": "b"},
            ],
        }
        wf = Workflow.from_dict(data)
        assert wf.steps[2].step_type.value == "choice"

    def test_from_dict_unknown_type_raises(self):
        data = {
            "name": "bad",
            "steps": [{"name": "x", "type": "alien"}],
        }
        with pytest.raises(ValueError, match="Unknown step type"):
            Workflow.from_dict(data)
