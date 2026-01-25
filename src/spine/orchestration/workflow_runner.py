"""
Workflow Runner - Executes workflows with context passing.

The WorkflowRunner takes a Workflow and executes each step in sequence,
passing context between steps. It handles:
- Lambda step execution (call handler with context)
- Pipeline step execution (dispatch via existing framework)
- Choice step evaluation (conditional branching - Intermediate)
- Error handling per step's ErrorPolicy
- Result aggregation

Tier: Basic (core runner), Intermediate (choice steps), Advanced (map/wait)

Example:
    from spine.orchestration import Workflow, WorkflowRunner, Step

    workflow = Workflow(
        name="my.workflow",
        steps=[
            Step.pipeline("ingest", "my.ingest"),
            Step.lambda_("validate", validate_fn),
        ],
    )

    runner = WorkflowRunner()
    result = runner.execute(workflow, params={"tier": "NMS_TIER_1"})

    if result.status == WorkflowStatus.COMPLETED:
        print(f"Success! Processed {len(result.completed_steps)} steps")
    else:
        print(f"Failed at {result.error_step}: {result.error}")
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from spine.framework.dispatcher import Dispatcher, get_dispatcher
from spine.framework.pipelines import PipelineResult, PipelineStatus
from spine.orchestration.exceptions import GroupError
from spine.orchestration.step_result import StepResult, QualityMetrics
from spine.orchestration.step_types import Step, StepType, ErrorPolicy
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_context import WorkflowContext

logger = structlog.get_logger(__name__)


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
    """
    Executes workflows with context passing.

    Basic tier supports:
    - Lambda steps (inline functions)
    - Pipeline steps (via Dispatcher)
    - Sequential execution
    - Error handling per step

    Intermediate tier adds:
    - Choice steps (conditional branching)

    Advanced tier adds:
    - Wait steps (requires scheduler)
    - Map steps (requires parallel execution)
    - Checkpointing (requires database)
    """

    def __init__(
        self,
        dispatcher: Dispatcher | None = None,
        dry_run: bool = False,
    ):
        """
        Initialize the workflow runner.

        Args:
            dispatcher: Dispatcher for pipeline execution (uses default if None)
            dry_run: If True, pipeline steps return mock success
        """
        self._dispatcher = dispatcher
        self._dry_run = dry_run

    @property
    def dispatcher(self) -> Dispatcher:
        """Get the dispatcher (lazy initialization)."""
        if self._dispatcher is None:
            self._dispatcher = get_dispatcher()
        return self._dispatcher

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

        started_at = datetime.now(timezone.utc)
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

        # Execute steps
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

        completed_at = datetime.now(timezone.utc)

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

    def _execute_step(
        self,
        step: Step,
        context: WorkflowContext,
        workflow: Workflow,
    ) -> StepExecution:
        """Execute a single step."""
        started_at = datetime.now(timezone.utc)

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

        completed_at = datetime.now(timezone.utc)

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
        """Execute a lambda step (inline function)."""
        if step.handler is None:
            return StepResult.fail("Lambda step has no handler")

        return step.handler(context, step.config)

    def _execute_pipeline(self, step: Step, context: WorkflowContext) -> StepResult:
        """Execute a pipeline step (via Dispatcher)."""
        if step.pipeline_name is None:
            return StepResult.fail("Pipeline step has no pipeline_name")

        if self._dry_run:
            return StepResult.ok(
                output={"dry_run": True, "pipeline": step.pipeline_name},
            )

        # Merge context params with step-specific params
        params = {**context.params, **step.config}

        # Execute via dispatcher
        pipeline_result: PipelineResult = self.dispatcher.submit(
            pipeline_name=step.pipeline_name,
            params=params,
        )

        # Convert PipelineResult to StepResult
        if pipeline_result.status == PipelineStatus.COMPLETED:
            return StepResult.ok(
                output={
                    "pipeline_result": {
                        "status": pipeline_result.status.value,
                        "metrics": pipeline_result.metrics,
                        "started_at": pipeline_result.started_at.isoformat() if pipeline_result.started_at else None,
                        "completed_at": pipeline_result.completed_at.isoformat() if pipeline_result.completed_at else None,
                    },
                },
            )
        else:
            return StepResult.fail(
                error=pipeline_result.error or "Pipeline failed",
                category="INTERNAL",
                output={
                    "pipeline_result": {
                        "status": pipeline_result.status.value,
                        "error": pipeline_result.error,
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
            # next_step tells runner where to jump
        )._replace_next_step(next_step)

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


# Helper for StepResult to set next_step (immutable pattern)
def _replace_next_step(self: StepResult, next_step: str | None) -> StepResult:
    """Create new StepResult with next_step set."""
    return StepResult(
        success=self.success,
        output=self.output,
        context_updates=self.context_updates,
        error=self.error,
        error_category=self.error_category,
        quality=self.quality,
        events=self.events,
        next_step=next_step,
    )


# Monkey-patch the helper onto StepResult
StepResult._replace_next_step = _replace_next_step


def get_workflow_runner(
    dispatcher: Dispatcher | None = None,
    dry_run: bool = False,
) -> WorkflowRunner:
    """Get a workflow runner instance."""
    return WorkflowRunner(dispatcher=dispatcher, dry_run=dry_run)
