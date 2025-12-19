"""Tests for Workflow Visualizer — Mermaid, ASCII, and summary output.

Covers:
- Mermaid output for sequential, DAG, and choice workflows
- ASCII output formatting
- Summary metadata dict
- Edge cases (empty, single-step, large workflows)
- Direction and style options
"""

from __future__ import annotations

import pytest

from spine.orchestration import Step, StepResult, Workflow
from spine.orchestration.visualizer import (
    visualize_ascii,
    visualize_mermaid,
    visualize_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _noop(ctx, config):
    return StepResult.ok()


def _cond_true(ctx):
    return True


def _make_sequential():
    """Simple 3-step sequential workflow."""
    return Workflow(
        name="test.sequential",
        steps=[
            Step.pipeline("extract", "data.extract"),
            Step.lambda_("transform", _noop),
            Step.pipeline("load", "data.load"),
        ],
    )


def _make_dag():
    """DAG workflow with dependencies."""
    return Workflow(
        name="test.dag",
        steps=[
            Step.pipeline("fetch_a", "source.a"),
            Step.pipeline("fetch_b", "source.b"),
            Step.lambda_("merge", _noop, depends_on=("fetch_a", "fetch_b")),
            Step.pipeline("store", "data.store", depends_on=("merge",)),
        ],
    )


def _make_choice():
    """Workflow with a choice step."""
    return Workflow(
        name="test.choice",
        steps=[
            Step.pipeline("ingest", "data.ingest"),
            Step.choice("route", condition=_cond_true, then_step="process", else_step="reject"),
            Step.lambda_("process", _noop),
            Step.lambda_("reject", _noop),
        ],
    )


# ---------------------------------------------------------------------------
# Mermaid
# ---------------------------------------------------------------------------

class TestVisualizeMermaid:
    def test_sequential_output(self):
        wf = _make_sequential()
        mermaid = visualize_mermaid(wf)

        assert "graph TD" in mermaid
        assert "extract" in mermaid
        assert "transform" in mermaid
        assert "load" in mermaid
        # Sequential edges
        assert "extract --> transform" in mermaid
        assert "transform --> load" in mermaid

    def test_dag_output(self):
        wf = _make_dag()
        mermaid = visualize_mermaid(wf)

        assert "graph TD" in mermaid
        # DAG edges from depends_on
        assert "fetch_a --> merge" in mermaid
        assert "fetch_b --> merge" in mermaid
        assert "merge --> store" in mermaid

    def test_choice_output(self):
        wf = _make_choice()
        mermaid = visualize_mermaid(wf)

        assert "route" in mermaid
        assert "true" in mermaid
        assert "false" in mermaid

    def test_direction_lr(self):
        wf = _make_sequential()
        mermaid = visualize_mermaid(wf, direction="LR")
        assert "graph LR" in mermaid

    def test_pipeline_label(self):
        wf = _make_sequential()
        mermaid = visualize_mermaid(wf)
        # Pipeline nodes show pipeline name in label
        assert "data.extract" in mermaid

    def test_lambda_shape(self):
        wf = Workflow(name="test", steps=[Step.lambda_("fn", _noop)])
        mermaid = visualize_mermaid(wf)
        # Lambda uses rounded shape: name("label")
        assert 'fn("fn")' in mermaid

    def test_no_styles(self):
        wf = _make_sequential()
        mermaid = visualize_mermaid(wf, include_styles=False)
        assert "style" not in mermaid

    def test_with_styles(self):
        wf = _make_sequential()
        mermaid = visualize_mermaid(wf, include_styles=True)
        assert "style" in mermaid
        assert "fill:" in mermaid

    def test_title(self):
        wf = _make_sequential()
        mermaid = visualize_mermaid(wf, title="My Workflow")
        assert "title: My Workflow" in mermaid

    def test_single_step(self):
        wf = Workflow(name="test", steps=[Step.pipeline("only", "single.step")])
        mermaid = visualize_mermaid(wf)
        assert "only" in mermaid
        # No edges for single step
        assert "-->" not in mermaid


# ---------------------------------------------------------------------------
# ASCII
# ---------------------------------------------------------------------------

class TestVisualizeAscii:
    def test_sequential_output(self):
        wf = _make_sequential()
        ascii_out = visualize_ascii(wf)

        assert "test.sequential" in ascii_out
        assert "extract" in ascii_out
        assert "transform" in ascii_out
        assert "load" in ascii_out
        # Box drawing characters
        assert "\u250c" in ascii_out  # ┌
        assert "\u2514" in ascii_out  # └
        # Arrow
        assert "\u25b6" in ascii_out  # ▶

    def test_dag_output(self):
        wf = _make_dag()
        ascii_out = visualize_ascii(wf)

        assert "DAG" in ascii_out
        assert "fetch_a" in ascii_out
        assert "merge" in ascii_out
        assert "depends_on" in ascii_out

    def test_empty_workflow(self):
        wf = Workflow.__new__(Workflow)
        wf.name = "empty"
        wf.steps = []
        wf.domain = ""
        wf.description = ""
        wf.version = 1
        wf.defaults = {}
        wf.tags = []
        from spine.orchestration.workflow import WorkflowExecutionPolicy
        wf.execution_policy = WorkflowExecutionPolicy()

        ascii_out = visualize_ascii(wf)
        assert "empty" in ascii_out

    def test_single_step(self):
        wf = Workflow(name="test", steps=[Step.lambda_("only", _noop)])
        ascii_out = visualize_ascii(wf)
        assert "only" in ascii_out

    def test_type_indicators(self):
        wf = Workflow(
            name="test.types",
            steps=[
                Step.pipeline("pipe", "my.pipeline"),
                Step.lambda_("func", _noop),
            ],
        )
        ascii_out = visualize_ascii(wf)
        assert "[P]" in ascii_out  # Pipeline indicator
        assert "[\u03bb]" in ascii_out  # Lambda indicator (λ)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestVisualizeSummary:
    def test_sequential_summary(self):
        wf = _make_sequential()
        summary = visualize_summary(wf)

        assert summary["workflow_name"] == "test.sequential"
        assert summary["step_count"] == 3
        assert summary["edge_count"] == 2  # Sequential: n-1 edges
        assert summary["has_branches"] is False
        assert summary["has_dependencies"] is False
        assert summary["max_depth"] == 3
        assert summary["tier"] == "basic"
        assert "data.extract" in summary["pipeline_names"]
        assert "data.load" in summary["pipeline_names"]

    def test_dag_summary(self):
        wf = _make_dag()
        summary = visualize_summary(wf)

        assert summary["step_count"] == 4
        assert summary["has_dependencies"] is True
        assert summary["edge_count"] == 3  # 3 depends_on edges
        assert summary["max_depth"] >= 3  # fetch → merge → store

    def test_step_types(self):
        wf = _make_sequential()
        summary = visualize_summary(wf)
        assert "pipeline" in summary["step_types"]
        assert "lambda" in summary["step_types"]
        assert summary["step_types"]["pipeline"] == 2
        assert summary["step_types"]["lambda"] == 1

    def test_critical_path_sequential(self):
        wf = _make_sequential()
        summary = visualize_summary(wf)
        assert summary["critical_path"] == ["extract", "transform", "load"]

    def test_critical_path_dag(self):
        wf = _make_dag()
        summary = visualize_summary(wf)
        path = summary["critical_path"]
        # Critical path goes through one of fetch_a/fetch_b → merge → store
        assert "merge" in path
        assert "store" in path
        assert len(path) == 3

    def test_empty_summary(self):
        wf = Workflow.__new__(Workflow)
        wf.name = "empty"
        wf.steps = []
        wf.domain = ""
        wf.description = ""
        wf.version = 1
        wf.defaults = {}
        wf.tags = []
        from spine.orchestration.workflow import WorkflowExecutionPolicy
        wf.execution_policy = WorkflowExecutionPolicy()

        summary = visualize_summary(wf)
        assert summary["step_count"] == 0
        assert summary["max_depth"] == 0
        assert summary["critical_path"] == []

    def test_choice_workflow_summary(self):
        wf = _make_choice()
        summary = visualize_summary(wf)
        assert summary["has_branches"] is True
        assert "choice" in summary["step_types"]

    def test_tier_detection(self):
        wf = _make_choice()
        summary = visualize_summary(wf)
        assert summary["tier"] == "intermediate"  # Choice steps = intermediate
