"""Workflow Runner — executes workflows with context passing.

The WorkflowRunner takes a :class:`~spine.orchestration.workflow.Workflow`
and executes each step (sequentially or as a parallel DAG), passing
context between steps.  It handles:

- **Lambda** step execution (inline handler with context)
- **Pipeline** step execution (via the :class:`~spine.execution.runnable.Runnable` protocol)
- **Choice** step evaluation (conditional branching)
- **Wait** steps
- Error handling per step's :class:`~spine.orchestration.step_types.ErrorPolicy`
- Result aggregation

``WorkflowRunner`` depends on the **Runnable** protocol for pipeline
steps.  The canonical Runnable implementation is
:class:`~spine.execution.dispatcher.EventDispatcher`, which creates
proper ``RunRecord`` entries with full execution tracking.  Pass it
via the ``runnable`` constructor argument.

Example::

    from spine.execution.dispatcher import EventDispatcher
    from spine.execution.executors import MemoryExecutor
    from spine.orchestration import Workflow, WorkflowRunner, Step

    dispatcher = EventDispatcher(executor=MemoryExecutor())

    workflow = Workflow(
        name="my.workflow",
        steps=[
            Step.pipeline("ingest", "my.ingest"),
            Step.lambda_("validate", validate_fn),
        ],
    )

    runner = WorkflowRunner(runnable=dispatcher)
    result = runner.execute(workflow, params={"tier": "NMS_TIER_1"})

    if result.status == WorkflowStatus.COMPLETED:
        print(f"Success! Processed {len(result.completed_steps)} steps")
    else:
        print(f"Failed at {result.error_step}: {result.error}")
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from threading import Lock
from typing import Any

from spine.core.logging import get_logger

from spine.execution.runnable import PipelineRunResult, Runnable
from spine.orchestration.exceptions import GroupError
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import ErrorPolicy, Step, StepType
from spine.orchestration.workflow import ExecutionMode, FailurePolicy, Workflow
from spine.orchestration.workflow_context import WorkflowContext

logger = get_logger(__name__)


class WorkflowStatus(str, Enum):
    """Overall status of workflow execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some steps succeeded (continue-on-failure mode)


@dataclass
class StepExecution:
    """Result of executing a single step."""

    step_name: str
    step_type: str
    status: str  # "completed", "failed", "skipped"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: StepResult | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate step duration."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/storage."""
        return {
            "step_name": self.step_name,
            "step_type": self.step_type,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "output": self.result.output if self.result else None,
        }


@dataclass
class WorkflowResult:
    """Result of executing a workflow."""

    workflow_name: str
    run_id: str
    status: WorkflowStatus
    context: WorkflowContext
    started_at: datetime
    completed_at: datetime | None = None
    step_executions: list[StepExecution] = field(default_factory=list)
    error_step: str | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Total workflow duration."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def completed_steps(self) -> list[str]:
        """List of successfully completed step names."""
        return [s.step_name for s in self.step_executions if s.status == "completed"]

    @property
    def failed_steps(self) -> list[str]:
        """List of failed step names."""
        return [s.step_name for s in self.step_executions if s.status == "failed"]

    @property
    def total_steps(self) -> int:
        """Total number of steps executed."""
        return len(self.step_executions)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/storage."""
        return {
            "workflow_name": self.workflow_name,
            "run_id": self.run_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "completed_steps": self.completed_steps,
            "failed_steps": self.failed_steps,
            "error_step": self.error_step,
            "error": self.error,
            "step_executions": [s.to_dict() for s in self.step_executions],
        }


class WorkflowRunner:
    """Executes workflows with context passing.

    Pipeline steps are dispatched through the
    :class:`~spine.execution.runnable.Runnable` protocol.  The canonical
    implementation is :class:`~spine.execution.dispatcher.EventDispatcher`,
    which creates ``RunRecord`` entries for every pipeline step so your
    execution history is complete and portable.

    Supports:

    * **Lambda** steps — inline functions
    * **Pipeline** steps — via ``Runnable.submit_pipeline_sync()``
    * **Choice** steps — conditional branching
    * **Wait** steps
    * **Sequential** and **parallel DAG** execution modes
    * Error handling per step
    """

    def __init__(
        self,
        runnable: Runnable,
        dry_run: bool = False,
    ) -> None:
        """Initialise the workflow runner.

        Args:
            runnable: Any object implementing the ``Runnable`` protocol
                (typically ``EventDispatcher``).
            dry_run: If ``True``, pipeline steps return mock success.
        """
        self._runnable = runnable
        self._dry_run = dry_run

    @property
    def runnable(self) -> Runnable:
        """Return the ``Runnable`` backend."""
        return self._runnable

    def execute(
        self,
        workflow: Workflow,
        params: dict[str, Any] | None = None,
        partition: dict[str, Any] | None = None,
        context: WorkflowContext | None = None,
        start_from: str | None = None,
    ) -> WorkflowResult:
        """
        Execute a workflow.

        Args:
            workflow: The workflow to execute
            params: Input parameters
            partition: Partition key for tracking
            context: Resume from existing context (for checkpoint resume)
            start_from: Start from specific step (skip earlier steps)

        Returns:
            WorkflowResult with final status and context
        """
        # Create or use provided context
        if context is None:
            context = WorkflowContext.create(
                workflow_name=workflow.name,
                params={**workflow.defaults, **(params or {})},
                partition=partition or {},
                dry_run=self._dry_run,
            )

        started_at = datetime.now(UTC)
        step_executions: list[StepExecution] = []
        error_step: str | None = None
        error_msg: str | None = None
        final_status = WorkflowStatus.COMPLETED

        # Determine starting point
        start_index = 0
        if start_from:
            start_index = workflow.step_index(start_from)
            if start_index < 0:
                raise GroupError(f"Start step not found: {start_from}")

        logger.info(
            "workflow.start",
            workflow=workflow.name,
            run_id=context.run_id,
            step_count=len(workflow.steps),
            start_from=start_from,
        )

        # Execute steps — choose sequential or parallel mode
        use_parallel = (
            workflow.execution_policy.mode == ExecutionMode.PARALLEL
            and workflow.has_dependencies()
        )

        if use_parallel:
            final_status, step_executions, error_step, error_msg, context = (
                self._execute_parallel(workflow, context, start_index)
            )
        else:
            # Sequential execution (default)
            current_index = start_index
            skip_to_step: str | None = None

            while current_index < len(workflow.steps):
                step = workflow.steps[current_index]

                # Handle choice step jumps
                if skip_to_step:
                    if step.name != skip_to_step:
                        current_index += 1
                        continue
                    skip_to_step = None

                # Execute step
                step_exec = self._execute_step(step, context, workflow)
                step_executions.append(step_exec)

                if step_exec.status == "completed":
                    # Update context with step output
                    if step_exec.result:
                        context = context.with_output(step.name, step_exec.result.output)
                        if step_exec.result.context_updates:
                            context = context.with_params(step_exec.result.context_updates)

                        # Handle choice step branching
                        if step_exec.result.next_step:
                            skip_to_step = step_exec.result.next_step
                            logger.debug(
                                "workflow.branch",
                                step=step.name,
                                next_step=skip_to_step,
                            )

                elif step_exec.status == "failed":
                    error_step = step.name
                    error_msg = step_exec.error

                    if step.on_error == ErrorPolicy.STOP:
                        final_status = WorkflowStatus.FAILED
                        break
                    elif step.on_error == ErrorPolicy.CONTINUE:
                        final_status = WorkflowStatus.PARTIAL
                        # Continue to next step

                current_index += 1

        completed_at = datetime.now(UTC)

        logger.info(
            "workflow.complete",
            workflow=workflow.name,
            run_id=context.run_id,
            status=final_status.value,
            duration_seconds=(completed_at - started_at).total_seconds(),
            completed_steps=len([s for s in step_executions if s.status == "completed"]),
            failed_steps=len([s for s in step_executions if s.status == "failed"]),
        )

        return WorkflowResult(
            workflow_name=workflow.name,
            run_id=context.run_id,
            status=final_status,
            context=context,
            started_at=started_at,
            completed_at=completed_at,
            step_executions=step_executions,
            error_step=error_step,
            error=error_msg,
        )

    def _execute_parallel(
        self,
        workflow: Workflow,
        context: WorkflowContext,
        start_index: int,
    ) -> tuple[WorkflowStatus, list[StepExecution], str | None, str | None, WorkflowContext]:
        """
        Execute steps in parallel, respecting dependency ordering.

        Uses a ThreadPoolExecutor with max_concurrency from execution_policy.
        Steps whose dependencies have all completed are submitted in waves.
        Context is accumulated under a lock as steps complete.

        Args:
            workflow: The workflow to execute
            context: The starting workflow context
            start_index: Index to start from (for checkpoint resume)

        Returns:
            Tuple of (final_status, step_executions, error_step, error_msg, context)
        """
        policy = workflow.execution_policy
        max_workers = policy.max_concurrency or 4
        failure_policy = policy.on_failure

        steps = workflow.steps[start_index:]
        step_map: dict[str, Step] = {s.name: s for s in steps}
        pending: set[str] = set(step_map.keys())

        # Thread-safe tracking
        lock = Lock()
        completed_names: set[str] = set()
        failed_names: set[str] = set()
        step_results: dict[str, StepExecution] = {}
        should_stop = False
        error_step: str | None = None
        error_msg: str | None = None

        def is_ready(step: Step) -> bool:
            """All dependencies completed (caller must hold lock)."""
            if step.name not in pending:
                return False
            return all(dep in completed_names for dep in step.depends_on)

        def should_skip(step: Step) -> bool:
            """Any dependency failed (caller must hold lock)."""
            return any(dep in failed_names for dep in step.depends_on)

        def run_step(step: Step) -> StepExecution:
            """Execute a single step in a thread."""
            with lock:
                ctx_snapshot = context
            return self._execute_step(step, ctx_snapshot, workflow)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Future, Step] = {}

            while pending and not should_stop:
                running_names = {s.name for s in futures.values()}

                with lock:
                    ready = [
                        step_map[name]
                        for name in pending
                        if name not in running_names and is_ready(step_map[name])
                    ]
                    to_skip = [
                        step_map[name]
                        for name in pending
                        if name not in running_names and should_skip(step_map[name])
                    ]

                # Mark skipped steps
                for step in to_skip:
                    step_exec = StepExecution(
                        step_name=step.name,
                        step_type=step.step_type.value,
                        status="skipped",
                    )
                    with lock:
                        step_results[step.name] = step_exec
                        failed_names.add(step.name)  # propagate: dependents also skip
                        pending.discard(step.name)

                    logger.warning(
                        "workflow.parallel.step_skipped",
                        step=step.name,
                        reason="dependency_failed",
                    )

                # Submit ready steps (up to available slots)
                slots_available = max_workers - len(futures)
                for step in ready[:slots_available]:
                    future = executor.submit(run_step, step)
                    futures[future] = step

                    logger.debug(
                        "workflow.parallel.submitted",
                        step=step.name,
                        active_futures=len(futures),
                    )

                # If no futures and no ready steps, remaining steps are unreachable
                if not futures:
                    if pending:
                        for name in list(pending):
                            step_exec = StepExecution(
                                step_name=name,
                                step_type=step_map[name].step_type.value,
                                status="skipped",
                            )
                            step_results[name] = step_exec
                            pending.discard(name)
                    break

                # Wait for one future to complete, then recheck ready steps
                for future in as_completed(futures.keys()):
                    step = futures.pop(future)
                    try:
                        step_exec = future.result()
                    except Exception as e:
                        step_exec = StepExecution(
                            step_name=step.name,
                            step_type=step.step_type.value,
                            status="failed",
                            error=str(e),
                        )

                    with lock:
                        step_results[step.name] = step_exec
                        pending.discard(step.name)

                        if step_exec.status == "completed":
                            completed_names.add(step.name)
                            # Merge step output into shared context
                            if step_exec.result:
                                context = context.with_output(step.name, step_exec.result.output)
                                if step_exec.result.context_updates:
                                    context = context.with_params(step_exec.result.context_updates)
                        else:
                            failed_names.add(step.name)
                            if failure_policy == FailurePolicy.STOP:
                                should_stop = True
                                error_step = step.name
                                error_msg = step_exec.error
                                logger.error(
                                    "workflow.parallel.stopping_on_failure",
                                    step=step.name,
                                )
                    break  # Process one at a time to recheck ready steps

            # Cancel remaining futures on failure-stop
            if should_stop:
                for future in futures:
                    future.cancel()
                for name in list(pending):
                    step_exec = StepExecution(
                        step_name=name,
                        step_type=step_map[name].step_type.value,
                        status="skipped",
                    )
                    step_results[name] = step_exec

        # Assemble results in original step order
        step_executions: list[StepExecution] = []
        for step in steps:
            if step.name in step_results:
                step_executions.append(step_results[step.name])

        # Determine final status
        has_failures = bool(failed_names)
        has_completions = bool(completed_names)
        if should_stop or (has_failures and not has_completions):
            final_status = WorkflowStatus.FAILED
        elif has_failures and has_completions:
            final_status = WorkflowStatus.PARTIAL
        else:
            final_status = WorkflowStatus.COMPLETED

        # Capture first error if not already set by stop logic
        if error_step is None and failed_names:
            for step in steps:
                if step.name in failed_names and step.name in step_results:
                    error_step = step.name
                    error_msg = step_results[step.name].error
                    break

        return final_status, step_executions, error_step, error_msg, context

    def _execute_step(
        self,
        step: Step,
        context: WorkflowContext,
        workflow: Workflow,
    ) -> StepExecution:
        """Execute a single step."""
        started_at = datetime.now(UTC)

        logger.debug(
            "step.start",
            workflow=workflow.name,
            step=step.name,
            type=step.step_type.value,
        )

        try:
            if step.step_type == StepType.LAMBDA:
                result = self._execute_lambda(step, context)
            elif step.step_type == StepType.PIPELINE:
                result = self._execute_pipeline(step, context)
            elif step.step_type == StepType.CHOICE:
                result = self._execute_choice(step, context)
            elif step.step_type == StepType.WAIT:
                result = self._execute_wait(step, context)
            elif step.step_type == StepType.MAP:
                result = self._execute_map(step, context, workflow)
            else:
                result = StepResult.fail(f"Unknown step type: {step.step_type}")

        except Exception as e:
            logger.exception(
                "step.exception",
                workflow=workflow.name,
                step=step.name,
                error=str(e),
            )
            result = StepResult.fail(
                error=str(e),
                category="INTERNAL",
            )

        completed_at = datetime.now(UTC)

        status = "completed" if result.success else "failed"

        logger.debug(
            "step.complete",
            workflow=workflow.name,
            step=step.name,
            status=status,
            duration_seconds=(completed_at - started_at).total_seconds(),
        )

        return StepExecution(
            step_name=step.name,
            step_type=step.step_type.value,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            result=result,
            error=result.error if not result.success else None,
        )

    def _execute_lambda(self, step: Step, context: WorkflowContext) -> StepResult:
        """Execute a lambda step (inline function).

        If the handler returns something other than a ``StepResult`` (e.g.
        a dict, bool, or None), it is coerced via ``StepResult.from_value()``
        so that plain functions work without importing the framework.
        """
        if step.handler is None:
            return StepResult.fail("Lambda step has no handler")

        raw = step.handler(context, step.config)
        return StepResult.from_value(raw)

    def _execute_pipeline(self, step: Step, context: WorkflowContext) -> StepResult:
        """Execute a pipeline step via the ``Runnable`` protocol.

        Calls ``self.runnable.submit_pipeline_sync()`` which — when backed
        by ``EventDispatcher`` — creates a ``RunRecord`` with full
        execution tracking.
        """
        if step.pipeline_name is None:
            return StepResult.fail("Pipeline step has no pipeline_name")

        if self._dry_run:
            return StepResult.ok(
                output={"dry_run": True, "pipeline": step.pipeline_name},
            )

        # Merge context params with step-specific params
        params = {**context.params, **step.config}

        # Execute via Runnable protocol
        result: PipelineRunResult = self.runnable.submit_pipeline_sync(
            pipeline_name=step.pipeline_name,
            params=params,
            parent_run_id=context.run_id,
            correlation_id=context.run_id,
        )

        # Convert PipelineRunResult to StepResult
        if result.succeeded:
            return StepResult.ok(
                output={
                    "pipeline_result": {
                        "status": result.status,
                        "metrics": result.metrics,
                        "run_id": result.run_id,
                        "started_at": result.started_at.isoformat() if result.started_at else None,
                        "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                    },
                },
            )
        else:
            return StepResult.fail(
                error=result.error or "Pipeline failed",
                category="INTERNAL",
                output={
                    "pipeline_result": {
                        "status": result.status,
                        "error": result.error,
                        "run_id": result.run_id,
                    },
                },
            )

    def _execute_choice(self, step: Step, context: WorkflowContext) -> StepResult:
        """Execute a choice step (conditional branch)."""
        if step.condition is None:
            return StepResult.fail("Choice step has no condition")

        try:
            condition_result = step.condition(context)
        except Exception as e:
            return StepResult.fail(f"Condition evaluation failed: {e}")

        if condition_result:
            next_step = step.then_step
            branch = "then"
        else:
            next_step = step.else_step
            branch = "else"

        logger.debug(
            "choice.evaluated",
            step=step.name,
            result=condition_result,
            branch=branch,
            next_step=next_step,
        )

        return StepResult.ok(
            output={"condition_result": condition_result, "branch": branch},
            context_updates={f"__choice_{step.name}": branch},
        ).with_next_step(next_step)

    def _execute_wait(self, step: Step, context: WorkflowContext) -> StepResult:
        """Execute a wait step (pause execution)."""
        # Basic tier: just skip the wait in synchronous mode
        # Advanced tier would schedule a timer
        duration = step.duration_seconds or 0

        if duration > 0 and not self._dry_run:
            import time

            time.sleep(duration)

        return StepResult.ok(
            output={"waited_seconds": duration},
        )

    def _execute_map(
        self,
        step: Step,
        context: WorkflowContext,
        workflow: Workflow,
    ) -> StepResult:
        """Execute a map step (fan-out/fan-in)."""
        # Advanced tier feature - not implemented in Basic
        return StepResult.fail(
            error="Map steps require Advanced tier (parallel execution)",
            category="CONFIGURATION",
        )


def get_workflow_runner(
    runnable: Runnable,
    dry_run: bool = False,
) -> WorkflowRunner:
    """Get a workflow runner instance.

    Args:
        runnable: Any :class:`~spine.execution.runnable.Runnable`
            (typically ``EventDispatcher``).
        dry_run: If ``True``, pipeline steps return mock success.
    """
    return WorkflowRunner(runnable=runnable, dry_run=dry_run)
