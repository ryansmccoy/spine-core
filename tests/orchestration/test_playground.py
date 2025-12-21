"""Tests for Idea #5 — Workflow Playground.

Covers:
- load / reset
- step-by-step execution
- peek / run_to / run_all
- step_back (undo)
- set_param / set_params
- context inspection between steps
- summary generation
- dry-run mode (no runnable)
- all step types
"""

from __future__ import annotations

import pytest

from spine.orchestration import Step, StepResult, Workflow
from spine.orchestration.playground import StepSnapshot, WorkflowPlayground


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _noop_handler(ctx, config):
    return StepResult.ok(output={"handled": True})


def _fail_handler(ctx, config):
    return StepResult.fail("intentional failure")


def _param_handler(ctx, config):
    val = ctx.params.get("key", "missing")
    return StepResult.ok(output={"key_value": val})


def _condition_true(ctx):
    return True


def _condition_param(ctx):
    return ctx.params.get("flag", False)


def _make_workflow(steps=None, name="test.playground"):
    if steps is None:
        steps = [
            Step.lambda_("step1", _noop_handler),
            Step.lambda_("step2", _noop_handler),
            Step.lambda_("step3", _noop_handler),
        ]
    return Workflow(name=name, steps=steps)


# ---------------------------------------------------------------------------
# Load / Reset
# ---------------------------------------------------------------------------

class TestLoadReset:
    def test_load_initializes_state(self):
        pg = WorkflowPlayground()
        wf = _make_workflow()
        pg.load(wf, params={"env": "test"})

        assert pg.workflow is wf
        assert pg.context is not None
        assert pg.context.params["env"] == "test"
        assert pg.current_step_index == 0
        assert not pg.is_complete
        assert len(pg.remaining_steps) == 3

    def test_reset_restores_initial_state(self):
        pg = WorkflowPlayground()
        wf = _make_workflow()
        pg.load(wf, params={"key": "val"})
        pg.step()
        pg.step()

        pg.reset()
        assert pg.current_step_index == 0
        assert len(pg.history) == 0
        assert not pg.is_complete

    def test_no_workflow_raises(self):
        pg = WorkflowPlayground()
        with pytest.raises(RuntimeError, match="No workflow loaded"):
            pg.step()

    def test_reset_without_load_raises(self):
        pg = WorkflowPlayground()
        with pytest.raises(RuntimeError, match="No workflow loaded"):
            pg.reset()


# ---------------------------------------------------------------------------
# Step-by-step execution
# ---------------------------------------------------------------------------

class TestStep:
    def test_step_returns_snapshot(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        snap = pg.step()

        assert isinstance(snap, StepSnapshot)
        assert snap.step_name == "step1"
        assert snap.status == "completed"
        assert snap.step_index == 0
        assert snap.duration_ms >= 0

    def test_step_advances_index(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())

        pg.step()
        assert pg.current_step_index == 1

        pg.step()
        assert pg.current_step_index == 2

    def test_step_accumulates_context(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())

        pg.step()
        assert "step1" in pg.context.outputs

        pg.step()
        assert "step2" in pg.context.outputs

    def test_step_on_complete_raises(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        pg.run_all()

        with pytest.raises(RuntimeError, match="All steps already executed"):
            pg.step()

    def test_failed_step(self):
        wf = Workflow(name="fail.test", steps=[
            Step.lambda_("bad", _fail_handler),
        ])
        pg = WorkflowPlayground()
        pg.load(wf)
        snap = pg.step()

        assert snap.status == "failed"
        assert snap.error is not None

    def test_snapshot_captures_context_before_after(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow(), params={"init": 1})
        snap = pg.step()

        assert "init" in snap.context_before["params"]
        assert "step1" in snap.context_after["outputs"]


# ---------------------------------------------------------------------------
# Peek
# ---------------------------------------------------------------------------

class TestPeek:
    def test_peek_returns_next_step(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())

        step = pg.peek()
        assert step is not None
        assert step.name == "step1"

    def test_peek_does_not_advance(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())

        pg.peek()
        assert pg.current_step_index == 0

    def test_peek_returns_none_when_complete(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        pg.run_all()

        assert pg.peek() is None


# ---------------------------------------------------------------------------
# Run-to / Run-all
# ---------------------------------------------------------------------------

class TestRunTo:
    def test_run_to_stops_at_named_step(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        snaps = pg.run_to("step2")

        assert len(snaps) == 2
        assert snaps[-1].step_name == "step2"
        assert pg.current_step_index == 2

    def test_run_to_unknown_step_raises(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())

        with pytest.raises(ValueError, match="not found"):
            pg.run_to("nonexistent")

    def test_run_all(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        snaps = pg.run_all()

        assert len(snaps) == 3
        assert pg.is_complete


# ---------------------------------------------------------------------------
# Step-back (undo)
# ---------------------------------------------------------------------------

class TestStepBack:
    def test_step_back_rewinds(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        pg.step()
        pg.step()

        undone = pg.step_back()
        assert undone is not None
        assert undone.step_name == "step2"
        assert pg.current_step_index == 1
        assert "step2" not in pg.context.outputs

    def test_step_back_then_re_execute(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        pg.step()
        pg.step()

        pg.step_back()
        snap = pg.step()  # re-execute step2
        assert snap.step_name == "step2"
        assert pg.current_step_index == 2

    def test_step_back_at_start_returns_none(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())

        result = pg.step_back()
        assert result is None


# ---------------------------------------------------------------------------
# Parameter modification
# ---------------------------------------------------------------------------

class TestSetParam:
    def test_set_param(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow(), params={"key": "original"})

        pg.set_param("key", "modified")
        assert pg.context.params["key"] == "modified"

    def test_set_params(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())

        pg.set_params({"a": 1, "b": 2})
        assert pg.context.params["a"] == 1
        assert pg.context.params["b"] == 2

    def test_set_param_affects_next_step(self):
        wf = Workflow(name="param.test", steps=[
            Step.lambda_("read", _param_handler),
        ])
        pg = WorkflowPlayground()
        pg.load(wf, params={"key": "initial"})

        pg.set_param("key", "changed")
        snap = pg.step()
        assert snap.result.output["key_value"] == "changed"

    def test_set_param_without_load_raises(self):
        pg = WorkflowPlayground()
        with pytest.raises(RuntimeError, match="No workflow loaded"):
            pg.set_param("key", "val")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_structure(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        pg.step()

        s = pg.summary()
        assert s["workflow"] == "test.playground"
        assert s["total_steps"] == 3
        assert s["executed"] == 1
        assert s["remaining"] == 2
        assert s["is_complete"] is False
        assert len(s["history"]) == 1
        assert s["history"][0]["step"] == "step1"


# ---------------------------------------------------------------------------
# All step types
# ---------------------------------------------------------------------------

class TestStepTypes:
    def test_operation_dry_run(self):
        wf = Workflow(name="dry", steps=[
            Step.operation("p1", "my.operation"),
        ])
        pg = WorkflowPlayground()  # No runnable → dry run
        pg.load(wf)
        snap = pg.step()

        assert snap.status == "completed"
        assert snap.result.output["_dry_run"] is True
        assert snap.result.output["operation"] == "my.operation"

    def test_wait_step_instant(self):
        wf = Workflow(name="wait", steps=[
            Step.wait("pause", 300),
        ])
        pg = WorkflowPlayground()
        pg.load(wf)
        snap = pg.step()

        assert snap.status == "completed"
        assert snap.result.output["_wait_skipped"] is True
        assert snap.result.output["duration_seconds"] == 300

    def test_choice_step_true(self):
        wf = Workflow(name="choice", steps=[
            Step.lambda_("a", _noop_handler),
            Step.lambda_("b", _noop_handler),
            Step.choice("branch", _condition_true, "a", "b"),
        ])
        pg = WorkflowPlayground()
        pg.load(wf)
        pg.step()  # step a
        pg.step()  # step b
        snap = pg.step()  # choice step

        assert snap.status == "completed"
        assert snap.result.output["branch"] == "a"
        assert snap.result.output["condition_result"] is True

    def test_choice_step_with_param(self):
        wf = Workflow(name="choice", steps=[
            Step.lambda_("yes", _noop_handler),
            Step.lambda_("no", _noop_handler),
            Step.choice("branch", _condition_param, "yes", "no"),
        ])
        pg = WorkflowPlayground()
        pg.load(wf, params={"flag": True})
        pg.step()  # yes
        pg.step()  # no
        snap = pg.step()  # choice

        assert snap.result.output["branch"] == "yes"

    def test_map_step_preview(self):
        wf = Workflow(name="map", steps=[
            Step.map("fan", "items", "sub.wf", 8),
        ])
        pg = WorkflowPlayground()
        pg.load(wf)
        snap = pg.step()

        assert snap.status == "completed"
        assert snap.result.output["_map_preview"] is True
        assert snap.result.output["items_path"] == "items"
        assert snap.result.output["max_concurrency"] == 8


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestHistory:
    def test_history_accumulates(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        pg.run_all()

        assert len(pg.history) == 3
        names = [s.step_name for s in pg.history]
        assert names == ["step1", "step2", "step3"]

    def test_history_is_copy(self):
        pg = WorkflowPlayground()
        pg.load(_make_workflow())
        pg.step()

        h1 = pg.history
        pg.step()
        h2 = pg.history

        assert len(h1) == 1
        assert len(h2) == 2  # original not mutated
