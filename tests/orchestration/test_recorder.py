"""Tests for Step Recorder / Replay.

Covers:
- StepRecording creation and serialization
- WorkflowRecording serialization roundtrip (dict, JSON)
- RecordingRunner recording during execution
- Replay with matching and differing outputs
- Edge cases (empty workflows, failed steps)
"""

from __future__ import annotations

import json

import pytest

from spine.orchestration import Step, StepResult, Workflow
from spine.orchestration.recorder import (
    RecordingRunner,
    ReplayResult,
    StepDiff,
    StepRecording,
    WorkflowRecording,
    replay,
)
from spine.orchestration.workflow_runner import WorkflowRunner
from spine.execution.runnable import OperationRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _NoOpRunnable:
    """Minimal Runnable for recorder tests."""

    def submit_operation_sync(self, operation_name, params=None, *, parent_run_id=None, correlation_id=None):
        return OperationRunResult(status="completed")


def _noop_runnable():
    return _NoOpRunnable()

def _ok_handler(ctx, config):
    return StepResult.ok(output={"processed": True, "count": 42})


def _fail_handler(ctx, config):
    return StepResult.fail("intentional failure")


def _param_handler(ctx, config):
    val = ctx.params.get("key", "default")
    return StepResult.ok(output={"key_value": val})


def _make_workflow(name="test.recorder"):
    return Workflow(
        name=name,
        steps=[
            Step.lambda_("step1", _ok_handler),
            Step.lambda_("step2", _param_handler),
            Step.lambda_("step3", _ok_handler),
        ],
    )


# ---------------------------------------------------------------------------
# StepRecording
# ---------------------------------------------------------------------------

class TestStepRecording:
    def test_creation(self):
        r = StepRecording(
            step_name="fetch",
            step_type="operation",
            params_snapshot={"date": "2026-01-15"},
            outputs_snapshot={"rows": 100},
            result_status="completed",
            result_output={"rows": 100},
            duration_ms=123.4,
            timestamp="2026-01-15T00:00:00",
        )
        assert r.step_name == "fetch"
        assert r.step_type == "operation"
        assert r.duration_ms == 123.4
        assert r.error is None

    def test_frozen(self):
        r = StepRecording(
            step_name="x", step_type="lambda",
            params_snapshot={}, outputs_snapshot={},
            result_status="ok", result_output={},
            duration_ms=0.0, timestamp="",
        )
        with pytest.raises(AttributeError):
            r.step_name = "y"

    def test_to_dict(self):
        r = StepRecording(
            step_name="fetch", step_type="operation",
            params_snapshot={"a": 1}, outputs_snapshot={"b": 2},
            result_status="completed", result_output={"b": 2},
            duration_ms=50.0, timestamp="2026-01-15T00:00:00",
            error="boom",
        )
        d = r.to_dict()
        assert d["step_name"] == "fetch"
        assert d["error"] == "boom"
        assert d["result_output"] == {"b": 2}

    def test_to_dict_no_error(self):
        r = StepRecording(
            step_name="x", step_type="lambda",
            params_snapshot={}, outputs_snapshot={},
            result_status="ok", result_output={},
            duration_ms=0.0, timestamp="",
        )
        d = r.to_dict()
        assert "error" not in d

    def test_roundtrip(self):
        original = StepRecording(
            step_name="validate", step_type="lambda",
            params_snapshot={"env": "prod"}, outputs_snapshot={"valid": True},
            result_status="completed", result_output={"valid": True},
            duration_ms=12.5, timestamp="2026-01-15T12:00:00",
        )
        restored = StepRecording.from_dict(original.to_dict())
        assert restored.step_name == original.step_name
        assert restored.params_snapshot == original.params_snapshot
        assert restored.result_output == original.result_output


# ---------------------------------------------------------------------------
# WorkflowRecording
# ---------------------------------------------------------------------------

class TestWorkflowRecording:
    def test_creation(self):
        wr = WorkflowRecording(workflow_name="test.wf", params={"a": 1})
        assert wr.workflow_name == "test.wf"
        assert wr.step_count == 0
        assert wr.total_duration_ms == 0.0
        assert wr.failed_steps == []

    def test_step_count_and_duration(self):
        wr = WorkflowRecording(
            workflow_name="test",
            recordings=[
                StepRecording("s1", "lambda", {}, {}, "ok", {}, 10.0, ""),
                StepRecording("s2", "lambda", {}, {}, "ok", {}, 20.0, ""),
            ],
        )
        assert wr.step_count == 2
        assert wr.total_duration_ms == 30.0

    def test_failed_steps(self):
        wr = WorkflowRecording(
            workflow_name="test",
            recordings=[
                StepRecording("s1", "lambda", {}, {}, "ok", {}, 10.0, ""),
                StepRecording("s2", "lambda", {}, {}, "failed", {}, 5.0, "", error="boom"),
            ],
        )
        assert len(wr.failed_steps) == 1
        assert wr.failed_steps[0].step_name == "s2"

    def test_get_recording(self):
        wr = WorkflowRecording(
            workflow_name="test",
            recordings=[
                StepRecording("alpha", "lambda", {}, {}, "ok", {}, 1.0, ""),
                StepRecording("beta", "lambda", {}, {}, "ok", {}, 2.0, ""),
            ],
        )
        assert wr.get_recording("alpha") is not None
        assert wr.get_recording("alpha").step_name == "alpha"
        assert wr.get_recording("gamma") is None

    def test_to_dict_roundtrip(self):
        wr = WorkflowRecording(
            workflow_name="test.roundtrip",
            params={"env": "staging"},
            started_at="2026-01-15T00:00:00",
            finished_at="2026-01-15T00:01:00",
            status="completed",
            recordings=[
                StepRecording("s1", "lambda", {"env": "staging"}, {"done": True}, "completed", {"done": True}, 100.0, "2026-01-15T00:00:30"),
            ],
        )
        restored = WorkflowRecording.from_dict(wr.to_dict())
        assert restored.workflow_name == wr.workflow_name
        assert restored.params == wr.params
        assert restored.step_count == 1
        assert restored.recordings[0].step_name == "s1"

    def test_json_roundtrip(self):
        wr = WorkflowRecording(
            workflow_name="test.json",
            params={"key": "val"},
            status="completed",
            recordings=[
                StepRecording("a", "operation", {}, {}, "ok", {"x": 1}, 50.0, ""),
            ],
        )
        json_str = wr.to_json()
        parsed = json.loads(json_str)
        assert parsed["workflow_name"] == "test.json"

        restored = WorkflowRecording.from_json(json_str)
        assert restored.workflow_name == "test.json"
        assert restored.recordings[0].result_output == {"x": 1}


# ---------------------------------------------------------------------------
# StepDiff
# ---------------------------------------------------------------------------

class TestStepDiff:
    def test_match(self):
        d = StepDiff(step_name="s1", field="result_status", expected="ok", actual="ok")
        assert d.matched is True

    def test_mismatch(self):
        d = StepDiff(step_name="s1", field="result_status", expected="ok", actual="failed")
        assert d.matched is False

    def test_str_match(self):
        d = StepDiff(step_name="s1", field="x", expected=1, actual=1)
        assert "MATCH" in str(d)

    def test_str_diff(self):
        d = StepDiff(step_name="s1", field="x", expected=1, actual=2)
        assert "DIFF" in str(d)


# ---------------------------------------------------------------------------
# ReplayResult
# ---------------------------------------------------------------------------

class TestReplayResult:
    def test_empty_no_match(self):
        r = ReplayResult(workflow_name="test", replayed_count=0)
        assert r.all_match is False  # No steps replayed

    def test_all_match_true(self):
        r = ReplayResult(
            workflow_name="test",
            replayed_count=2,
            diffs=[
                StepDiff("s1", "status", "ok", "ok"),
                StepDiff("s2", "status", "ok", "ok"),
            ],
        )
        assert r.all_match is True
        assert len(r.mismatches) == 0

    def test_mismatches(self):
        r = ReplayResult(
            workflow_name="test",
            replayed_count=2,
            diffs=[
                StepDiff("s1", "status", "ok", "ok"),
                StepDiff("s2", "status", "ok", "failed"),
            ],
        )
        assert r.all_match is False
        assert len(r.mismatches) == 1

    def test_summary(self):
        r = ReplayResult(workflow_name="test.wf", replayed_count=3)
        assert "test.wf" in r.summary()


# ---------------------------------------------------------------------------
# RecordingRunner
# ---------------------------------------------------------------------------

class TestRecordingRunner:
    def test_records_execution(self):
        recorder = RecordingRunner(runnable=_noop_runnable())
        wf = _make_workflow()
        result = recorder.execute(wf, params={"key": "value"})

        assert recorder.last_recording is not None
        rec = recorder.last_recording
        assert rec.workflow_name == "test.recorder"
        assert rec.step_count == 3
        assert rec.params == {"key": "value"}
        assert rec.status == "completed"
        assert rec.started_at != ""
        assert rec.finished_at != ""

    def test_records_step_details(self):
        recorder = RecordingRunner(runnable=_noop_runnable())
        wf = _make_workflow()
        recorder.execute(wf, params={"key": "hello"})

        rec = recorder.last_recording
        step1 = rec.get_recording("step1")
        assert step1 is not None
        assert step1.step_name == "step1"
        assert step1.duration_ms >= 0

    def test_records_params(self):
        recorder = RecordingRunner(runnable=_noop_runnable())
        wf = _make_workflow()
        recorder.execute(wf, params={"key": "test_val"})

        rec = recorder.last_recording
        assert rec.params == {"key": "test_val"}

    def test_no_recording_before_execute(self):
        recorder = RecordingRunner(runnable=_noop_runnable())
        assert recorder.last_recording is None

    def test_overwrites_previous_recording(self):
        recorder = RecordingRunner(runnable=_noop_runnable())
        wf = _make_workflow()

        recorder.execute(wf, params={"run": 1})
        first = recorder.last_recording

        recorder.execute(wf, params={"run": 2})
        second = recorder.last_recording

        assert first is not second
        assert second.params == {"run": 2}

    def test_serialization_roundtrip(self):
        recorder = RecordingRunner(runnable=_noop_runnable())
        wf = _make_workflow()
        recorder.execute(wf, params={"env": "test"})

        rec = recorder.last_recording
        json_str = rec.to_json()
        restored = WorkflowRecording.from_json(json_str)

        assert restored.workflow_name == rec.workflow_name
        assert restored.step_count == rec.step_count
        assert restored.params == rec.params

    def test_custom_runner(self):
        inner = WorkflowRunner(runnable=_noop_runnable())
        recorder = RecordingRunner(runner=inner)
        wf = _make_workflow()
        result = recorder.execute(wf, params={})

        assert recorder.last_recording is not None
        assert recorder.last_recording.step_count == 3


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

class TestReplay:
    def test_replay_same_handlers_match(self):
        recorder = RecordingRunner(runnable=_noop_runnable())
        wf = _make_workflow()
        recorder.execute(wf, params={"key": "val"})
        recording = recorder.last_recording

        result = replay(recording, wf, runnable=_noop_runnable())
        assert result.replayed_count == 3
        # All status diffs should match since same handlers
        status_diffs = [d for d in result.diffs if d.field == "result_status"]
        assert all(d.matched for d in status_diffs)

    def test_replay_different_handler_detects_diff(self):
        # Record with ok handler
        recorder = RecordingRunner(runnable=_noop_runnable())
        wf = _make_workflow()
        recorder.execute(wf, params={"key": "val"})
        recording = recorder.last_recording

        # Replay with different handler
        def different_handler(ctx, config):
            return StepResult.ok(output={"processed": False, "count": 0})

        wf_v2 = Workflow(
            name="test.recorder",
            steps=[
                Step.lambda_("step1", different_handler),
                Step.lambda_("step2", _param_handler),
                Step.lambda_("step3", _ok_handler),
            ],
        )
        result = replay(recording, wf_v2, runnable=_noop_runnable())
        # step1 output changed: processed True→False, count 42→0
        step1_diffs = [d for d in result.diffs if d.step_name == "step1" and not d.matched]
        assert len(step1_diffs) > 0

    def test_replay_result_summary(self):
        recorder = RecordingRunner(runnable=_noop_runnable())
        wf = _make_workflow()
        recorder.execute(wf, params={})
        recording = recorder.last_recording

        result = replay(recording, wf, runnable=_noop_runnable())
        summary = result.summary()
        assert "test.recorder" in summary
        assert "3 steps" in summary
