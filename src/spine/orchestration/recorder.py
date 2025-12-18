"""Step Recorder / Replay — capture and replay workflow executions.

Records every step's inputs, outputs, and timing during a workflow
execution.  Recordings can be serialized to JSON for persistence and
replayed later for regression testing or debugging.

Architecture::

    RecordingRunner (wraps WorkflowRunner)
    ├── execute(workflow, params)
    │   ├── before each step → snapshot params/context
    │   ├── execute step (delegate to inner runner)
    │   └── after each step → capture result + timing
    │       → StepRecording
    └── last_recording → WorkflowRecording
        ├── to_dict() / to_json()
        ├── from_dict() / from_json()
        └── replay(workflow) → ReplayResult
            ├── diffs: list[StepDiff]
            └── all_match → bool

    StepRecording (frozen)
    ├── step_name, step_type
    ├── params_snapshot (before)
    ├── outputs_snapshot (after)
    ├── result (StepResult)
    ├── duration_ms
    └── error (optional)

Example::

    from spine.orchestration.recorder import RecordingRunner
    from spine.orchestration import Workflow, Step, StepResult

    def validate(ctx, config):
        return StepResult.ok(output={"valid": True})

    workflow = Workflow(
        name="test.pipeline",
        steps=[
            Step.pipeline("fetch", "data.fetch"),
            Step.lambda_("validate", validate),
        ],
    )

    # Record
    recorder = RecordingRunner()
    result = recorder.execute(workflow, params={"date": "2026-01-15"})
    recording = recorder.last_recording

    # Save
    json_str = recording.to_json()

    # Replay later
    loaded = WorkflowRecording.from_json(json_str)
    replay_result = replay(loaded, workflow)
    assert replay_result.all_match

See Also:
    spine.orchestration.playground — interactive step-by-step execution
    spine.orchestration.linter — static workflow analysis
"""

from __future__ import annotations

import copy
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from spine.execution.runnable import Runnable, PipelineRunResult
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.workflow_runner import (
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recording data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StepRecording:
    """Immutable record of a single step execution.

    Attributes:
        step_name: Name of the step that was executed.
        step_type: Type of the step (LAMBDA, PIPELINE, etc.).
        params_snapshot: Copy of workflow params *before* this step ran.
        outputs_snapshot: Copy of context outputs *after* this step ran.
        result_status: Status string from the StepResult.
        result_output: Output dict from the StepResult (if any).
        duration_ms: Wall-clock time in milliseconds.
        timestamp: ISO-format UTC timestamp of capture.
        error: Error message if the step failed.
    """

    step_name: str
    step_type: str
    params_snapshot: dict[str, Any]
    outputs_snapshot: dict[str, Any]
    result_status: str
    result_output: dict[str, Any]
    duration_ms: float
    timestamp: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        d: dict[str, Any] = {
            "step_name": self.step_name,
            "step_type": self.step_type,
            "params_snapshot": self.params_snapshot,
            "outputs_snapshot": self.outputs_snapshot,
            "result_status": self.result_status,
            "result_output": self.result_output,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }
        if self.error:
            d["error"] = self.error
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepRecording:
        """Deserialize from a plain dictionary."""
        return cls(
            step_name=data["step_name"],
            step_type=data["step_type"],
            params_snapshot=data.get("params_snapshot", {}),
            outputs_snapshot=data.get("outputs_snapshot", {}),
            result_status=data.get("result_status", "unknown"),
            result_output=data.get("result_output", {}),
            duration_ms=data.get("duration_ms", 0.0),
            timestamp=data.get("timestamp", ""),
            error=data.get("error"),
        )


@dataclass
class WorkflowRecording:
    """Complete recording of a workflow execution.

    Attributes:
        workflow_name: Name of the workflow that was recorded.
        recordings: Ordered list of step recordings.
        params: Initial workflow params.
        started_at: ISO-format UTC timestamp when execution began.
        finished_at: ISO-format UTC timestamp when execution ended.
        status: Final workflow status string.
    """

    workflow_name: str
    recordings: list[StepRecording] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    status: str = ""

    @property
    def step_count(self) -> int:
        """Number of recorded steps."""
        return len(self.recordings)

    @property
    def total_duration_ms(self) -> float:
        """Sum of all step durations."""
        return sum(r.duration_ms for r in self.recordings)

    @property
    def failed_steps(self) -> list[StepRecording]:
        """Steps that failed during recording."""
        return [r for r in self.recordings if r.error is not None]

    def get_recording(self, step_name: str) -> StepRecording | None:
        """Get recording for a specific step by name."""
        for r in self.recordings:
            if r.step_name == step_name:
                return r
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "workflow_name": self.workflow_name,
            "params": self.params,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "recordings": [r.to_dict() for r in self.recordings],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowRecording:
        """Deserialize from a plain dictionary."""
        return cls(
            workflow_name=data["workflow_name"],
            params=data.get("params", {}),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            status=data.get("status", ""),
            recordings=[StepRecording.from_dict(r) for r in data.get("recordings", [])],
        )

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_json(cls, json_str: str) -> WorkflowRecording:
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(json_str))


# ---------------------------------------------------------------------------
# Step diff (for replay comparison)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StepDiff:
    """Difference between recorded and replayed step output.

    Attributes:
        step_name: Name of the step.
        field: The field that differs (e.g. ``"result_output.valid"``).
        expected: Value from the recording.
        actual: Value from the replay.
    """

    step_name: str
    field: str
    expected: Any
    actual: Any

    @property
    def matched(self) -> bool:
        """True if expected == actual."""
        return self.expected == self.actual

    def __str__(self) -> str:
        status = "MATCH" if self.matched else "DIFF"
        return f"[{status}] {self.step_name}.{self.field}: expected={self.expected!r}, actual={self.actual!r}"


@dataclass
class ReplayResult:
    """Result of replaying a recording against a workflow.

    Attributes:
        workflow_name: Name of the workflow.
        diffs: All differences found.
        replayed_count: Number of steps that were replayed.
    """

    workflow_name: str
    diffs: list[StepDiff] = field(default_factory=list)
    replayed_count: int = 0

    @property
    def all_match(self) -> bool:
        """True if no differences were found."""
        return all(d.matched for d in self.diffs) if self.diffs else self.replayed_count > 0

    @property
    def mismatches(self) -> list[StepDiff]:
        """Only the diffs that don't match."""
        return [d for d in self.diffs if not d.matched]

    def summary(self) -> str:
        """One-line summary."""
        status = "MATCH" if self.all_match else "MISMATCH"
        return f"{status}: {self.workflow_name} — {self.replayed_count} steps, {len(self.mismatches)} differences"


# ---------------------------------------------------------------------------
# RecordingRunner — wraps WorkflowRunner to capture step I/O
# ---------------------------------------------------------------------------

class RecordingRunner:
    """Workflow runner that records every step's inputs and outputs.

    Wraps a ``WorkflowRunner`` (delegation pattern) and intercepts
    each step execution to capture ``StepRecording`` objects.

    Parameters
    ----------
    runnable
        Any object implementing the ``Runnable`` protocol
        (typically ``EventDispatcher`` or a test stub).
    runner
        Optional pre-configured ``WorkflowRunner`` to delegate to.
        If both ``runnable`` and ``runner`` are provided, ``runner``
        takes precedence.

    Example::

        from spine.execution.runnable import PipelineRunResult

        class StubRunnable:
            def submit_pipeline_sync(self, pipeline_name, params=None, **kw):
                return PipelineRunResult(status="completed")

        recorder = RecordingRunner(runnable=StubRunnable())
        result = recorder.execute(workflow, params={"key": "val"})
        recording = recorder.last_recording
        print(recording.to_json())
    """

    def __init__(
        self,
        runnable: Runnable | None = None,
        runner: WorkflowRunner | None = None,
    ) -> None:
        if runner is not None:
            self._runner = runner
        elif runnable is not None:
            self._runner = WorkflowRunner(runnable=runnable)
        else:
            raise TypeError(
                "RecordingRunner requires either 'runnable' or 'runner' argument"
            )
        self._last_recording: WorkflowRecording | None = None

    @property
    def last_recording(self) -> WorkflowRecording | None:
        """The recording from the most recent ``execute()`` call."""
        return self._last_recording

    def execute(self, workflow: Workflow, params: dict[str, Any] | None = None) -> WorkflowResult:
        """Execute the workflow and record all step executions.

        Parameters
        ----------
        workflow
            The workflow to execute.
        params
            Initial parameters passed to the workflow.

        Returns
        -------
        WorkflowResult
            The standard workflow result from the inner runner.
        """
        params = params or {}
        recording = WorkflowRecording(
            workflow_name=workflow.name,
            params=copy.deepcopy(params),
            started_at=datetime.now(UTC).isoformat(),
        )

        # Execute workflow normally
        result = self._runner.execute(workflow, params=params)

        # Build recordings from step executions in the result
        for step_exec in result.step_executions:
            step_type_str = step_exec.step_type if isinstance(step_exec.step_type, str) else str(step_exec.step_type)

            # Capture outputs from StepResult if available
            outputs_snapshot: dict[str, Any] = {}
            if step_exec.result and step_exec.result.output:
                raw = step_exec.result.output
                outputs_snapshot = copy.deepcopy(raw) if isinstance(raw, dict) else {"_value": raw}

            # Convert duration_seconds to duration_ms
            duration_ms = 0.0
            if step_exec.duration_seconds is not None:
                duration_ms = step_exec.duration_seconds * 1000.0

            step_recording = StepRecording(
                step_name=step_exec.step_name,
                step_type=step_type_str,
                params_snapshot=copy.deepcopy(params),
                outputs_snapshot=outputs_snapshot,
                result_status=step_exec.status,
                result_output=outputs_snapshot,
                duration_ms=duration_ms,
                timestamp=datetime.now(UTC).isoformat(),
                error=step_exec.error,
            )
            recording.recordings.append(step_recording)

        recording.finished_at = datetime.now(UTC).isoformat()
        recording.status = result.status.value if isinstance(result.status, WorkflowStatus) else str(result.status)
        self._last_recording = recording

        logger.debug(
            "recorded %s: %d steps, status=%s",
            workflow.name,
            recording.step_count,
            recording.status,
        )
        return result


# ---------------------------------------------------------------------------
# Replay — compare a recording against a fresh execution
# ---------------------------------------------------------------------------

def replay(recording: WorkflowRecording, workflow: Workflow,
           runnable: Runnable | None = None,
           runner: WorkflowRunner | None = None) -> ReplayResult:
    """Replay a recorded workflow and compare outputs.

    Re-executes the workflow with the recorded params and compares
    each step's result_output against the recording.

    Parameters
    ----------
    recording
        The original recording to compare against.
    workflow
        The workflow to re-execute (may have updated handlers).
    runnable
        A ``Runnable`` for creating the internal ``WorkflowRunner``.
    runner
        Optional pre-configured ``WorkflowRunner`` to use for replay.

    Returns
    -------
    ReplayResult
        Comparison of recorded vs. replayed outputs.
    """
    replay_runner = RecordingRunner(runnable=runnable, runner=runner)
    replay_runner.execute(workflow, params=copy.deepcopy(recording.params))
    replayed = replay_runner.last_recording

    result = ReplayResult(workflow_name=workflow.name)

    if replayed is None:
        return result

    result.replayed_count = replayed.step_count

    # Compare each step's result_output
    for original in recording.recordings:
        replayed_step = replayed.get_recording(original.step_name)

        if replayed_step is None:
            result.diffs.append(
                StepDiff(
                    step_name=original.step_name,
                    field="existence",
                    expected="present",
                    actual="missing",
                )
            )
            continue

        # Compare result status
        result.diffs.append(
            StepDiff(
                step_name=original.step_name,
                field="result_status",
                expected=original.result_status,
                actual=replayed_step.result_status,
            )
        )

        # Compare result output keys
        for key in set(list(original.result_output.keys()) + list(replayed_step.result_output.keys())):
            result.diffs.append(
                StepDiff(
                    step_name=original.step_name,
                    field=f"result_output.{key}",
                    expected=original.result_output.get(key, "<missing>"),
                    actual=replayed_step.result_output.get(key, "<missing>"),
                )
            )

    logger.debug("replay %s: %s", workflow.name, result.summary())
    return result
