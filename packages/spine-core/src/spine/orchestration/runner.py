"""
Group execution runner - Actually executes resolved execution plans.

This module provides the GroupRunner class which takes an ExecutionPlan
and runs each step in dependency order using the existing Dispatcher.

Features:
- Sequential execution with dependency ordering
- Parallel execution with max_concurrency and dependency respect
- Stop-on-failure or continue-on-failure policies
- Status tracking per step
- Integration with Dispatcher.submit()
- Execution result aggregation

Example:
    from spine.orchestration import PlanResolver, GroupRunner, get_group

    # Get and resolve a group
    group = get_group("finra.weekly_refresh")
    resolver = PlanResolver()
    plan = resolver.resolve(group, params={"tier": "NMS_TIER_1"})

    # Execute the plan
    runner = GroupRunner()
    result = runner.execute(plan)

    if result.status == GroupExecutionStatus.COMPLETED:
        print(f"Success! {result.successful_steps} steps completed")
    else:
        print(f"Failed: {result.failed_steps} failures")
"""

from __future__ import annotations

import structlog
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any, TYPE_CHECKING

from spine.framework.dispatcher import Dispatcher, get_dispatcher, TriggerSource
from spine.framework.pipelines import PipelineStatus
from spine.orchestration.models import ExecutionPlan, PlannedStep, FailurePolicy, ExecutionMode
from spine.orchestration.exceptions import GroupError

if TYPE_CHECKING:
    from spine.framework.pipelines import PipelineResult

logger = structlog.get_logger(__name__)


class StepStatus(Enum):
    """Status of a single step execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # Skipped due to dependency failure


@dataclass
class StepExecution:
    """
    Result of executing a single step.

    Tracks the execution status, timing, and result for one step
    in a group execution.
    """

    step_name: str
    pipeline_name: str
    status: StepStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: PipelineResult | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        result_dict = None
        if self.result:
            result_dict = {
                "status": self.result.status.value,
                "started_at": self.result.started_at.isoformat() if self.result.started_at else None,
                "completed_at": self.result.completed_at.isoformat() if self.result.completed_at else None,
                "error": self.result.error,
                "metrics": self.result.metrics,
            }
        return {
            "step_name": self.step_name,
            "pipeline_name": self.pipeline_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "result": result_dict,
        }


class GroupExecutionStatus(Enum):
    """Overall status of group execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some steps succeeded, some failed (continue-on-failure)


@dataclass
class GroupExecutionResult:
    """
    Result of executing an entire group.

    Aggregates results from all step executions.
    """

    group_name: str
    batch_id: str
    status: GroupExecutionStatus
    started_at: datetime
    completed_at: datetime | None = None
    step_executions: list[StepExecution] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float | None:
        """Total execution duration."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def successful_steps(self) -> int:
        """Count of successfully completed steps."""
        return sum(1 for s in self.step_executions if s.status == StepStatus.COMPLETED)

    @property
    def failed_steps(self) -> int:
        """Count of failed steps."""
        return sum(1 for s in self.step_executions if s.status == StepStatus.FAILED)

    @property
    def skipped_steps(self) -> int:
        """Count of skipped steps."""
        return sum(1 for s in self.step_executions if s.status == StepStatus.SKIPPED)

    @property
    def total_steps(self) -> int:
        """Total number of steps."""
        return len(self.step_executions)

    @property
    def completed_steps(self) -> int:
        """Alias for successful_steps (for API consistency)."""
        return self.successful_steps

    @property
    def step_results(self) -> list[StepExecution]:
        """Alias for step_executions (for API consistency)."""
        return self.step_executions

    def get_step_execution(self, step_name: str) -> StepExecution | None:
        """Get execution result for a specific step."""
        for step_exec in self.step_executions:
            if step_exec.step_name == step_name:
                return step_exec
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "group_name": self.group_name,
            "batch_id": self.batch_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "successful_steps": self.successful_steps,
            "failed_steps": self.failed_steps,
            "skipped_steps": self.skipped_steps,
            "step_executions": [s.to_dict() for s in self.step_executions],
        }


class GroupRunner:
    """
    Execute resolved pipeline group plans.

    Takes an ExecutionPlan and runs each step in dependency order,
    respecting the execution policy (sequential/parallel, failure handling).

    Example:
        plan = resolver.resolve(group, params={...})
        runner = GroupRunner()
        result = runner.execute(plan)

        if result.status == GroupExecutionStatus.COMPLETED:
            print(f"Success! {result.successful_steps} steps completed")
        else:
            print(f"Failed: {result.failed_steps} failures")
    """

    def __init__(self, dispatcher: Dispatcher | None = None):
        """
        Initialize runner.

        Args:
            dispatcher: Optional dispatcher instance. If None, uses get_dispatcher()
        """
        self.dispatcher = dispatcher or get_dispatcher()

    def execute(self, plan: ExecutionPlan) -> GroupExecutionResult:
        """
        Execute an execution plan.

        Args:
            plan: Resolved execution plan from PlanResolver

        Returns:
            GroupExecutionResult with aggregated results

        Raises:
            GroupError: If plan execution fails catastrophically
        """
        logger.info(
            "group_runner.execute.start",
            group=plan.group_name,
            batch_id=plan.batch_id,
            step_count=plan.step_count,
            policy=plan.policy.mode.value,
        )

        result = GroupExecutionResult(
            group_name=plan.group_name,
            batch_id=plan.batch_id,
            status=GroupExecutionStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        try:
            # Route to appropriate execution mode
            if plan.policy.mode == ExecutionMode.PARALLEL:
                logger.info(
                    "group_runner.using_parallel",
                    group=plan.group_name,
                    max_concurrency=plan.policy.max_concurrency,
                )
                self._execute_parallel(plan, result)
            else:
                self._execute_sequential(plan, result)

            # Determine final status based on policy and outcomes
            if result.failed_steps == 0 and result.skipped_steps == 0:
                # All steps completed successfully
                result.status = GroupExecutionStatus.COMPLETED
            elif result.failed_steps > 0:
                # At least one step failed
                if plan.policy.on_failure == FailurePolicy.STOP:
                    # STOP policy: any failure means overall failure
                    result.status = GroupExecutionStatus.FAILED
                elif result.successful_steps > 0:
                    # CONTINUE policy with mixed results
                    result.status = GroupExecutionStatus.PARTIAL
                else:
                    # CONTINUE policy but nothing succeeded
                    result.status = GroupExecutionStatus.FAILED
            elif result.skipped_steps > 0 and result.successful_steps > 0:
                # Steps were skipped (dependency failures) but some succeeded
                result.status = GroupExecutionStatus.PARTIAL
            else:
                # Everything was skipped
                result.status = GroupExecutionStatus.FAILED

        except Exception as e:
            logger.error(
                "group_runner.execute.error",
                group=plan.group_name,
                batch_id=plan.batch_id,
                error=str(e),
            )
            result.status = GroupExecutionStatus.FAILED
            raise GroupError(f"Group execution failed: {e}") from e

        finally:
            result.completed_at = datetime.now(timezone.utc)

        logger.info(
            "group_runner.execute.complete",
            group=plan.group_name,
            batch_id=plan.batch_id,
            status=result.status.value,
            successful=result.successful_steps,
            failed=result.failed_steps,
            skipped=result.skipped_steps,
            duration_seconds=result.duration_seconds,
        )

        return result

    def _execute_sequential(
        self,
        plan: ExecutionPlan,
        result: GroupExecutionResult,
    ) -> None:
        """
        Execute steps sequentially in dependency order.

        Args:
            plan: Execution plan
            result: Result object to populate
        """
        # Track which steps have been completed successfully
        completed_steps: set[str] = set()

        for planned_step in plan.steps:
            # Check if dependencies were met
            if not self._dependencies_met(planned_step, completed_steps):
                # Skip this step - dependencies failed
                step_exec = StepExecution(
                    step_name=planned_step.step_name,
                    pipeline_name=planned_step.pipeline_name,
                    status=StepStatus.SKIPPED,
                )
                result.step_executions.append(step_exec)

                logger.warning(
                    "group_runner.step_skipped",
                    step=planned_step.step_name,
                    reason="dependency_failed",
                )
                continue

            # Execute the step
            step_exec = self._execute_step(plan, planned_step)
            result.step_executions.append(step_exec)

            # Check result
            if step_exec.status == StepStatus.COMPLETED:
                completed_steps.add(planned_step.step_name)
            elif step_exec.status == StepStatus.FAILED:
                # Handle failure based on policy
                if plan.policy.on_failure == FailurePolicy.STOP:
                    logger.error(
                        "group_runner.stopping_on_failure",
                        step=planned_step.step_name,
                        policy="stop",
                    )
                    # Mark remaining steps as skipped
                    self._skip_remaining_steps(plan, planned_step, result)
                    break
                else:
                    logger.warning(
                        "group_runner.continuing_after_failure",
                        step=planned_step.step_name,
                        policy="continue",
                    )
                    # Continue to next step

    def _execute_parallel(
        self,
        plan: ExecutionPlan,
        result: GroupExecutionResult,
    ) -> None:
        """
        Execute steps in parallel, respecting dependencies.

        Uses a ThreadPoolExecutor with max_concurrency limit.
        Steps wait for their dependencies to complete before starting.
        
        The algorithm:
        1. Track completed and failed steps
        2. Find "ready" steps (all deps completed)
        3. Submit ready steps to thread pool (up to max_concurrency)
        4. Wait for completions, update tracking
        5. Repeat until all steps processed or stopped

        Args:
            plan: Execution plan
            result: Result object to populate
        """
        max_workers = plan.policy.max_concurrency or 4
        
        # Thread-safe tracking
        lock = Lock()
        completed_steps: set[str] = set()
        failed_steps: set[str] = set()
        step_results: dict[str, StepExecution] = {}
        should_stop = False
        
        # Map step names to PlannedStep for easy lookup
        step_map = {s.step_name: s for s in plan.steps}
        pending_steps = set(step_map.keys())
        
        def is_ready_unlocked(step: PlannedStep) -> bool:
            """Check if step's dependencies are all completed successfully.
            MUST be called while holding lock."""
            if step.step_name not in pending_steps:
                return False  # Already processed
            # All deps must be completed (not failed, not pending)
            return all(dep in completed_steps for dep in step.depends_on)
        
        def should_skip_unlocked(step: PlannedStep) -> bool:
            """Check if step should be skipped due to failed dependencies.
            MUST be called while holding lock."""
            # If any dependency failed, this step should be skipped
            return any(dep in failed_steps for dep in step.depends_on)
        
        def run_step(step: PlannedStep) -> StepExecution:
            """Execute a single step (runs in thread pool)."""
            return self._execute_step(plan, step)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures: dict[Future, PlannedStep] = {}
            
            while pending_steps and not should_stop:
                # Find ready steps that aren't already running
                running_steps = {step.step_name for step in futures.values()}
                
                with lock:
                    ready = [
                        step_map[name] for name in pending_steps
                        if name not in running_steps
                        and is_ready_unlocked(step_map[name])
                    ]
                    
                    # Also find steps to skip (failed deps)
                    to_skip = [
                        step_map[name] for name in pending_steps
                        if name not in running_steps
                        and should_skip_unlocked(step_map[name])
                    ]
                
                # Mark skipped steps
                for step in to_skip:
                    step_exec = StepExecution(
                        step_name=step.step_name,
                        pipeline_name=step.pipeline_name,
                        status=StepStatus.SKIPPED,
                    )
                    with lock:
                        step_results[step.step_name] = step_exec
                        pending_steps.discard(step.step_name)
                    
                    logger.warning(
                        "group_runner.step_skipped",
                        step=step.step_name,
                        reason="dependency_failed",
                    )
                
                # Submit ready steps (up to available slots)
                slots_available = max_workers - len(futures)
                for step in ready[:slots_available]:
                    future = executor.submit(run_step, step)
                    futures[future] = step
                    
                    logger.debug(
                        "group_runner.parallel.submitted",
                        step=step.step_name,
                        active_futures=len(futures),
                    )
                
                # If no futures and no ready steps, we might be stuck or done
                if not futures:
                    if pending_steps:
                        # All remaining steps have unmet dependencies
                        # This shouldn't happen with valid DAG, but mark as skipped
                        for name in list(pending_steps):
                            step = step_map[name]
                            step_exec = StepExecution(
                                step_name=step.step_name,
                                pipeline_name=step.pipeline_name,
                                status=StepStatus.SKIPPED,
                            )
                            step_results[step.step_name] = step_exec
                            pending_steps.discard(name)
                    break
                
                # Wait for at least one future to complete
                done_futures = []
                for future in as_completed(futures.keys()):
                    done_futures.append(future)
                    break  # Process one at a time to recheck ready steps
                
                for future in done_futures:
                    step = futures.pop(future)
                    try:
                        step_exec = future.result()
                    except Exception as e:
                        step_exec = StepExecution(
                            step_name=step.step_name,
                            pipeline_name=step.pipeline_name,
                            status=StepStatus.FAILED,
                            error=str(e),
                        )
                    
                    with lock:
                        step_results[step.step_name] = step_exec
                        pending_steps.discard(step.step_name)
                        
                        if step_exec.status == StepStatus.COMPLETED:
                            completed_steps.add(step.step_name)
                        else:
                            failed_steps.add(step.step_name)
                            
                            if plan.policy.on_failure == FailurePolicy.STOP:
                                should_stop = True
                                logger.error(
                                    "group_runner.parallel.stopping_on_failure",
                                    step=step.step_name,
                                    policy="stop",
                                )
            
            # If we stopped early, cancel remaining futures and mark pending as skipped
            if should_stop:
                for future in futures:
                    future.cancel()
                
                for name in list(pending_steps):
                    step = step_map[name]
                    step_exec = StepExecution(
                        step_name=step.step_name,
                        pipeline_name=step.pipeline_name,
                        status=StepStatus.SKIPPED,
                    )
                    step_results[step.step_name] = step_exec
                    
                    logger.debug(
                        "group_runner.step_skipped",
                        step=step.step_name,
                        reason="stopped_on_failure",
                    )
        
        # Add results in original order
        for step in plan.steps:
            if step.step_name in step_results:
                result.step_executions.append(step_results[step.step_name])

    def _execute_step(
        self,
        plan: ExecutionPlan,
        step: PlannedStep,
    ) -> StepExecution:
        """
        Execute a single pipeline step using the Dispatcher.

        The Dispatcher handles:
        - Pipeline instantiation via the registry
        - Execution context and logging
        - Result capture

        Args:
            plan: Full execution plan (for batch_id in params)
            step: Step to execute

        Returns:
            StepExecution with result
        """
        logger.info(
            "group_runner.step.start",
            group=plan.group_name,
            step=step.step_name,
            pipeline=step.pipeline_name,
            sequence=step.sequence_order,
            batch_id=plan.batch_id,
        )

        step_exec = StepExecution(
            step_name=step.step_name,
            pipeline_name=step.pipeline_name,
            status=StepStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )

        try:
            # Inject batch_id into params for lineage tracking
            params = {**step.params, "batch_id": plan.batch_id}

            # Submit to Dispatcher - it handles registry lookup and execution
            execution = self.dispatcher.submit(
                pipeline=step.pipeline_name,
                params=params,
                trigger_source=TriggerSource.SCHEDULER,  # Orchestration is automated
            )

            # Execution is synchronous in Basic tier, result is available immediately
            pipeline_result = execution.result

            # Check if successful
            if execution.status == PipelineStatus.COMPLETED:
                step_exec.status = StepStatus.COMPLETED
                step_exec.result = pipeline_result

                logger.info(
                    "group_runner.step.success",
                    group=plan.group_name,
                    step=step.step_name,
                    pipeline=step.pipeline_name,
                    batch_id=plan.batch_id,
                    duration_seconds=(datetime.now(timezone.utc) - step_exec.started_at).total_seconds(),
                )
            else:
                step_exec.status = StepStatus.FAILED
                step_exec.result = pipeline_result
                # PipelineResult has 'error' field, not 'message'
                step_exec.error = execution.error or (pipeline_result.error if pipeline_result else None)

                logger.error(
                    "group_runner.step.failed",
                    group=plan.group_name,
                    step=step.step_name,
                    pipeline=step.pipeline_name,
                    batch_id=plan.batch_id,
                    status=execution.status.value,
                    error=step_exec.error,
                )

        except Exception as e:
            step_exec.status = StepStatus.FAILED
            step_exec.error = str(e)

            logger.error(
                "group_runner.step.exception",
                step=step.step_name,
                pipeline=step.pipeline_name,
                error=str(e),
                exc_info=True,
            )

        finally:
            step_exec.completed_at = datetime.now(timezone.utc)

        return step_exec

    def _dependencies_met(
        self,
        step: PlannedStep,
        completed_steps: set[str],
    ) -> bool:
        """
        Check if all dependencies for a step have been met.

        Args:
            step: Step to check
            completed_steps: Set of step names that completed successfully

        Returns:
            True if all dependencies are in completed_steps
        """
        return all(dep in completed_steps for dep in step.depends_on)

    def _skip_remaining_steps(
        self,
        plan: ExecutionPlan,
        failed_step: PlannedStep,
        result: GroupExecutionResult,
    ) -> None:
        """
        Mark all remaining steps as skipped after a failure.

        Args:
            plan: Execution plan
            failed_step: The step that failed
            result: Result object to update
        """
        # Find index of failed step
        failed_idx = plan.steps.index(failed_step)

        # Skip all subsequent steps
        for step in plan.steps[failed_idx + 1 :]:
            step_exec = StepExecution(
                step_name=step.step_name,
                pipeline_name=step.pipeline_name,
                status=StepStatus.SKIPPED,
            )
            result.step_executions.append(step_exec)

            logger.debug(
                "group_runner.step_skipped",
                step=step.step_name,
                reason="prior_failure",
                failed_step=failed_step.step_name,
            )


def get_runner(dispatcher: Dispatcher | None = None) -> GroupRunner:
    """
    Get a GroupRunner instance.

    This is the public API for getting a runner. Allows for future
    configuration and dependency injection.

    Args:
        dispatcher: Optional dispatcher to use

    Returns:
        GroupRunner instance
    """
    return GroupRunner(dispatcher=dispatcher)
