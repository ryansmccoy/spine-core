"""Workflow Playground — interactive step-by-step workflow executor.

Allows developers to execute workflows one step at a time, inspect
context between steps, modify parameters on the fly, and replay
individual steps.  Ideal for notebooks, debugging, and development.

Architecture::

    WorkflowPlayground
    ├── load(workflow)       → sets up step queue
    ├── step()               → executes next step, returns StepSnapshot
    ├── step_back()          → rewinds to previous context snapshot
    ├── peek()               → shows next step without executing
    ├── run_to(step_name)    → executes up to a named step
    ├── run_all()            → executes remaining steps
    ├── set_param(k, v)      → modifies context params on the fly
    ├── context              → current WorkflowContext
    ├── history              → list of StepSnapshot objects
    └── reset()              → restarts from beginning

Example::

    from spine.orchestration.playground import WorkflowPlayground
    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="debug.workflow",
        steps=[
            Step.operation("fetch", "my.fetcher"),
            Step.lambda_("validate", validate_fn),
            Step.operation("store", "my.store"),
        ],
    )

    pg = WorkflowPlayground()
    pg.load(workflow, params={"date": "2026-01-15"})

    # Step through one at a time
    snap = pg.step()          # executes "fetch"
    print(snap.result)        # inspect output
    print(pg.context.outputs) # see accumulated outputs

    pg.set_param("override", True)  # modify params
    snap = pg.step()          # executes "validate" with modified params

    pg.step_back()            # rewind to before "validate"
    snap = pg.step()          # re-execute "validate"

    pg.run_all()              # run remaining steps

Manifesto:
    Debugging workflows requires stepping through execution interactively.
    The Playground lets developers execute one step at a time, inspect
    intermediate state, and re-execute steps without restarting.

Tags:
    spine-core, orchestration, playground, interactive, debugging, step-through

Doc-Types:
    api-reference
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.workflow_runner import (
    WorkflowRunner,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StepSnapshot — immutable record of a step execution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StepSnapshot:
    """Immutable snapshot of a single step execution.

    Captured after each ``step()`` call for inspection and replay.

    Attributes:
        step_name: Name of the executed step.
        step_type: Type of the step (LAMBDA, operation, etc.).
        status: ``'completed'``, ``'failed'``, or ``'skipped'``.
        result: The ``StepResult`` (if step returned one).
        context_before: Context snapshot *before* the step ran.
        context_after: Context snapshot *after* the step ran.
        duration_ms: Wall-clock duration in milliseconds.
        error: Error message if the step failed.
        step_index: 0-based index in the workflow.
    """

    step_name: str
    step_type: StepType
    status: str
    result: StepResult | None
    context_before: dict[str, Any]
    context_after: dict[str, Any]
    duration_ms: float
    error: str | None = None
    step_index: int = 0


# ---------------------------------------------------------------------------
# WorkflowPlayground
# ---------------------------------------------------------------------------

class WorkflowPlayground:
    """Interactive step-by-step workflow executor.

    Wraps a ``WorkflowRunner`` and adds step-by-step control, context
    inspection, parameter modification, and undo/redo capabilities.

    Parameters
    ----------
    runnable
        Optional ``Runnable`` for operation step execution.  If ``None``,
        operation steps return a stub result (useful for dry-run/design).
    """

    def __init__(self, runnable: Any = None) -> None:
        self._runnable = runnable
        self._workflow: Workflow | None = None
        self._context: WorkflowContext | None = None
        self._initial_params: dict[str, Any] = {}
        self._step_index: int = 0
        self._history: list[StepSnapshot] = []
        self._context_snapshots: list[dict[str, Any]] = []
        self._runner: WorkflowRunner | None = None

    # ------------------------------------------------------------------
    # Load / Reset
    # ------------------------------------------------------------------

    def load(
        self,
        workflow: Workflow,
        params: dict[str, Any] | None = None,
        *,
        run_id: str | None = None,
    ) -> None:
        """Load a workflow for step-by-step execution.

        Parameters
        ----------
        workflow
            The workflow to execute.
        params
            Initial parameters.
        run_id
            Optional run ID (auto-generated if not provided).
        """
        self._workflow = workflow
        self._initial_params = dict(params or {})
        self._step_index = 0
        self._history = []
        self._context_snapshots = []

        self._context = WorkflowContext.create(
            workflow_name=workflow.name,
            params=self._initial_params,
            run_id=run_id or str(uuid.uuid4()),
        )
        # Snapshot the initial context
        self._context_snapshots.append(self._context_to_dict())

        self._runner = WorkflowRunner(
            runnable=self._runnable,
            dry_run=(self._runnable is None),
        )
        logger.info("Loaded workflow %s with %d steps", workflow.name, len(workflow.steps))

    def reset(self) -> None:
        """Reset to the initial state (re-load the same workflow)."""
        if self._workflow is None:
            raise RuntimeError("No workflow loaded — call load() first")
        self.load(self._workflow, self._initial_params)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def workflow(self) -> Workflow | None:
        """The currently loaded workflow."""
        return self._workflow

    @property
    def context(self) -> WorkflowContext | None:
        """The current workflow context."""
        return self._context

    @property
    def history(self) -> list[StepSnapshot]:
        """List of all step snapshots executed so far."""
        return list(self._history)

    @property
    def current_step_index(self) -> int:
        """0-based index of the next step to execute."""
        return self._step_index

    @property
    def is_complete(self) -> bool:
        """Whether all steps have been executed."""
        if self._workflow is None:
            return True
        return self._step_index >= len(self._workflow.steps)

    @property
    def remaining_steps(self) -> list[Step]:
        """Steps not yet executed."""
        if self._workflow is None:
            return []
        return list(self._workflow.steps[self._step_index:])

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def step(self) -> StepSnapshot:
        """Execute the next step and return a snapshot.

        Raises
        ------
        RuntimeError
            If no workflow is loaded or all steps are complete.
        """
        if self._workflow is None or self._context is None or self._runner is None:
            raise RuntimeError("No workflow loaded — call load() first")
        if self.is_complete:
            raise RuntimeError("All steps already executed")

        current_step = self._workflow.steps[self._step_index]
        context_before = self._context_to_dict()
        start_time = datetime.now(UTC)

        try:
            result = self._execute_single_step(current_step)
            status = "completed" if result.success else "failed"
            error = result.error if not result.success else None

            # Update context with step output
            if result.output:
                self._context = self._context.with_output(
                    current_step.name, result.output,
                )
        except Exception as exc:
            result = StepResult.fail(str(exc))
            status = "failed"
            error = str(exc)

        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        context_after = self._context_to_dict()

        snapshot = StepSnapshot(
            step_name=current_step.name,
            step_type=current_step.step_type,
            status=status,
            result=result,
            context_before=context_before,
            context_after=context_after,
            duration_ms=duration_ms,
            error=error,
            step_index=self._step_index,
        )
        self._history.append(snapshot)
        self._step_index += 1
        self._context_snapshots.append(context_after)

        return snapshot

    def peek(self) -> Step | None:
        """Return the next step without executing it.

        Returns ``None`` if all steps are complete.
        """
        if self._workflow is None or self.is_complete:
            return None
        return self._workflow.steps[self._step_index]

    def run_to(self, step_name: str) -> list[StepSnapshot]:
        """Execute steps until the named step is reached (inclusive).

        Parameters
        ----------
        step_name
            Name of the step to stop at (inclusive).

        Returns
        -------
        list[StepSnapshot]
            Snapshots of all steps executed.

        Raises
        ------
        ValueError
            If the step name is not found in remaining steps.
        """
        if self._workflow is None:
            raise RuntimeError("No workflow loaded — call load() first")

        remaining_names = [s.name for s in self.remaining_steps]
        if step_name not in remaining_names:
            raise ValueError(
                f"Step {step_name!r} not found in remaining steps: {remaining_names}"
            )

        snapshots: list[StepSnapshot] = []
        while not self.is_complete:
            snap = self.step()
            snapshots.append(snap)
            if snap.step_name == step_name:
                break
        return snapshots

    def run_all(self) -> list[StepSnapshot]:
        """Execute all remaining steps.

        Returns
        -------
        list[StepSnapshot]
            Snapshots of all steps executed.
        """
        snapshots: list[StepSnapshot] = []
        while not self.is_complete:
            snapshots.append(self.step())
        return snapshots

    # ------------------------------------------------------------------
    # Undo / Rewind
    # ------------------------------------------------------------------

    def step_back(self) -> StepSnapshot | None:
        """Rewind to before the last executed step.

        Returns the snapshot that was undone, or ``None`` if there's
        nothing to undo.
        """
        if not self._history:
            return None

        undone = self._history.pop()
        self._step_index = undone.step_index
        self._context_snapshots.pop()

        # Restore context from the snapshot *before* the undone step
        if self._context_snapshots:
            self._context = self._context_from_dict(self._context_snapshots[-1])

        return undone

    # ------------------------------------------------------------------
    # Parameter modification
    # ------------------------------------------------------------------

    def set_param(self, key: str, value: Any) -> None:
        """Modify a parameter in the current context.

        Parameters
        ----------
        key
            Parameter name.
        value
            New value.
        """
        if self._context is None:
            raise RuntimeError("No workflow loaded — call load() first")
        new_params = dict(self._context.params)
        new_params[key] = value
        self._context = self._context.with_params(new_params)

    def set_params(self, params: dict[str, Any]) -> None:
        """Update multiple parameters at once."""
        if self._context is None:
            raise RuntimeError("No workflow loaded — call load() first")
        new_params = dict(self._context.params)
        new_params.update(params)
        self._context = self._context.with_params(new_params)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """Return a summary of the playground state.

        Useful for notebook display or logging.
        """
        return {
            "workflow": self._workflow.name if self._workflow else None,
            "total_steps": len(self._workflow.steps) if self._workflow else 0,
            "executed": self._step_index,
            "remaining": len(self.remaining_steps),
            "is_complete": self.is_complete,
            "history": [
                {
                    "step": s.step_name,
                    "type": s.step_type.value,
                    "status": s.status,
                    "duration_ms": round(s.duration_ms, 2),
                }
                for s in self._history
            ],
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _execute_single_step(self, step: Step) -> StepResult:
        """Execute a single step using the appropriate handler."""
        if step.step_type == StepType.LAMBDA:
            if step.handler is None:
                return StepResult.fail("No handler attached to lambda step")
            raw = step.handler(self._context, step.config)
            return StepResult.from_value(raw)

        elif step.step_type == StepType.OPERATION:
            if self._runnable is None:
                # Dry-run mode: return stub result
                return StepResult.ok(
                    output={"_dry_run": True, "operation": step.operation_name},
                )
            # Execute via runnable

            operation_result = self._runnable.submit_operation_sync(
                step.operation_name or "",
                params=step.config,
                parent_run_id=self._context.run_id if self._context else None,
            )
            if operation_result.succeeded:
                return StepResult.ok(output=operation_result.metrics)
            return StepResult.fail(operation_result.error or "Operation failed")

        elif step.step_type == StepType.WAIT:
            # In playground mode, waits are instant
            return StepResult.ok(
                output={"_wait_skipped": True, "duration_seconds": step.duration_seconds},
            )

        elif step.step_type == StepType.CHOICE:
            if step.condition is None:
                return StepResult.fail("No condition attached to choice step")
            branch = step.condition(self._context)
            chosen = step.then_step if branch else step.else_step
            return StepResult.ok(output={"branch": chosen, "condition_result": branch})

        elif step.step_type == StepType.MAP:
            # In playground mode, map just reports what it would do
            return StepResult.ok(
                output={
                    "_map_preview": True,
                    "items_path": step.items_path,
                    "max_concurrency": step.max_concurrency,
                },
            )

        return StepResult.fail(f"Unknown step type: {step.step_type}")

    def _context_to_dict(self) -> dict[str, Any]:
        """Serialize current context for snapshot storage."""
        if self._context is None:
            return {}
        return {
            "run_id": self._context.run_id,
            "workflow_name": self._context.workflow_name,
            "params": dict(self._context.params),
            "outputs": dict(self._context.outputs),
        }

    def _context_from_dict(self, data: dict[str, Any]) -> WorkflowContext:
        """Restore context from a snapshot dict."""
        ctx = WorkflowContext.create(
            workflow_name=data.get("workflow_name", ""),
            params=data.get("params", {}),
            run_id=data.get("run_id", str(uuid.uuid4())),
        )
        # Restore outputs
        for step_name, output in data.get("outputs", {}).items():
            ctx = ctx.with_output(step_name, output)
        return ctx
