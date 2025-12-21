#!/usr/bin/env python3
"""Step Recorder — capture and replay workflow executions.

Demonstrates the ``RecordingRunner`` wrapper that transparently captures
every step execution (inputs, outputs, timing, status) into a
serializable ``WorkflowRecording``, and the ``replay()`` function
that re-executes with recorded parameters and diffs the results.

Demonstrates:
    1. ``RecordingRunner``     — wraps WorkflowRunner, captures recordings
    2. ``WorkflowRecording``   — serializable execution trace
    3. ``StepRecording``       — per-step snapshot
    4. JSON round-trip         — save and reload recordings
    5. ``replay()``            — re-run and compare
    6. ``ReplayResult``        — diff detection

Architecture::

    RecordingRunner
    ├── wraps WorkflowRunner (delegation)
    ├── execute(workflow, params, handlers)
    │   ├── delegates to inner WorkflowRunner
    │   ├── captures StepRecording per step
    │   └── builds WorkflowRecording
    └── last_recording → WorkflowRecording

    WorkflowRecording
    ├── recordings: list[StepRecording]
    ├── to_json() / from_json()
    └── to_dict() / from_dict()

    replay(recording, handlers)
    ├── re-executes with recorded params
    ├── compares status + output per step
    └── returns ReplayResult(diffs, all_match)

Key Concepts:
    - **Transparent capture**: No changes to workflow or handler code.
    - **JSON round-trip**: Persist recordings for regression/golden tests.
    - **Deterministic replay**: Detects non-determinism, regressions,
      and handler behavior changes via step-level diffing.

See Also:
    - ``01_workflow_basics.py``     — workflow construction
    - ``19_workflow_linter.py``     — static analysis
    - ``21_workflow_visualizer.py`` — visual output
    - :mod:`spine.orchestration.recorder`

Run:
    python examples/04_orchestration/20_step_recorder.py

Expected Output:
    Recording capture with step details, JSON round-trip verification,
    and replay comparison showing matched/mismatched steps.
"""

import json

from spine.execution.runnable import OperationRunResult
from spine.orchestration.step_types import Step
from spine.orchestration.step_result import StepResult
from spine.orchestration.workflow import Workflow
from spine.orchestration.recorder import (
    RecordingRunner,
    WorkflowRecording,
    StepRecording,
    StepDiff,
    ReplayResult,
    replay,
)


class _NoOpRunnable:
    """Minimal Runnable for recording demo."""

    def submit_operation_sync(self, operation_name, params=None, **kw):
        return OperationRunResult(status="completed")


def _success_handler(ctx, config):
    """Simple handler that always succeeds."""
    return StepResult.ok(output={"processed": True, "count": 42})


def _altered_handler(ctx, config):
    """Handler with slightly different output for replay diff demo."""
    return StepResult.ok(output={"processed": False, "count": 999})


def main() -> None:
    # ------------------------------------------------------------------
    # 1. Record a workflow execution
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("1. Record a workflow execution")
    print(f"{'='*60}")

    workflow = Workflow(
        name="etl_operation",
        steps=[
            Step.lambda_("extract", _success_handler),
            Step.lambda_("transform", _success_handler),
            Step.lambda_("load", _success_handler),
        ],
    )

    runner = RecordingRunner(runnable=_NoOpRunnable())
    result = runner.execute(workflow, params={"count": 0})

    print(f"   Workflow result: {result.status}")
    print(f"   Steps executed:  {len(result.step_executions)}")

    recording = runner.last_recording
    assert recording is not None
    print(f"   Recording name:  {recording.workflow_name}")
    print(f"   Step count:      {recording.step_count}")
    print(f"   Total duration:  {recording.total_duration_ms:.1f}ms")

    # ------------------------------------------------------------------
    # 2. Inspect individual step recordings
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("2. Step-level recording details")
    print(f"{'='*60}")

    for rec in recording.recordings:
        print(f"   Step: {rec.step_name}")
        print(f"     Type:     {rec.step_type}")
        print(f"     Status:   {rec.result_status}")
        print(f"     Duration: {rec.duration_ms:.1f}ms")
        print(f"     Output:   {rec.result_output}")
        print()

    # ------------------------------------------------------------------
    # 3. JSON round-trip
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("3. JSON serialization round-trip")
    print(f"{'='*60}")

    json_str = recording.to_json()
    parsed = json.loads(json_str)
    print(f"   JSON keys:      {list(parsed.keys())}")
    print(f"   JSON size:      {len(json_str)} bytes")

    restored = WorkflowRecording.from_json(json_str)
    print(f"   Restored name:  {restored.workflow_name}")
    print(f"   Restored steps: {restored.step_count}")
    assert restored.step_count == recording.step_count
    print("   Round-trip:     OK ✓")

    # ------------------------------------------------------------------
    # 4. Replay with same handlers (should match)
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("4. Replay with same handlers")
    print(f"{'='*60}")

    replay_result = replay(recording, workflow, runnable=_NoOpRunnable())
    print(f"   All match:    {replay_result.all_match}")
    print(f"   Replayed:     {replay_result.replayed_count} steps")
    if replay_result.all_match:
        print("   Deterministic: YES ✓")

    # ------------------------------------------------------------------
    # 5. Replay with altered handler (detect diff)
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("5. Replay with altered handler (diff detection)")
    print(f"{'='*60}")

    altered_workflow = Workflow(
        name="etl_operation",
        steps=[
            Step.lambda_("extract", _altered_handler),
            Step.lambda_("transform", _success_handler),
            Step.lambda_("load", _success_handler),
        ],
    )
    replay_result = replay(recording, altered_workflow, runnable=_NoOpRunnable())
    print(f"   All match:  {replay_result.all_match}")
    print(f"   Mismatches: {len(replay_result.mismatches)}")
    for diff in replay_result.mismatches:
        print(f"     Step '{diff.step_name}' — {diff.field}:")
        print(f"       Expected: {diff.expected}")
        print(f"       Actual:   {diff.actual}")

    # ------------------------------------------------------------------
    # 6. ReplayResult summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("6. Replay summary")
    print(f"{'='*60}")

    print(replay_result.summary())

    # ------------------------------------------------------------------
    # 7. Failed steps tracking
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("7. Recording metadata")
    print(f"{'='*60}")

    print(f"   Workflow:     {recording.workflow_name}")
    print(f"   Params:       {recording.params}")
    print(f"   Failed steps: {recording.failed_steps}")
    print(f"   Started:      {recording.started_at}")
    print(f"   Finished:     {recording.finished_at}")
    print(f"   Status:       {recording.status}")

    print(f"\n{'='*60}")
    print("Done — step recorder example complete")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
