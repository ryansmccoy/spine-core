"""
Step Types - Definitions for different kinds of workflow steps.

This module defines the step types that can be used in workflows:

Basic tier:
- LambdaStep: Inline function (validation, routing, notifications)
- PipelineStep: Wraps a registered pipeline

Intermediate tier:
- ChoiceStep: Conditional branching based on context

Advanced tier:
- WaitStep: Pause execution (for scheduling)
- MapStep: Fan-out/fan-in parallel execution

Example:
    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="my.workflow",
        steps=[
            Step.pipeline("ingest", "my.ingest_pipeline"),
            Step.lambda_("validate", validate_fn),
            Step.choice("route",
                condition=lambda ctx: ctx.params.get("valid"),
                then_step="process",
                else_step="reject",
            ),
            Step.pipeline("process", "my.process_pipeline"),
        ],
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable, TYPE_CHECKING

if TYPE_CHECKING:
    from spine.orchestration.workflow_context import WorkflowContext
    from spine.orchestration.step_result import StepResult


class StepType(str, Enum):
    """Type of workflow step."""

    LAMBDA = "lambda"      # Inline function (Basic)
    PIPELINE = "pipeline"  # Registered pipeline (Basic)
    CHOICE = "choice"      # Conditional branch (Intermediate)
    WAIT = "wait"          # Pause execution (Advanced)
    MAP = "map"            # Fan-out/fan-in (Advanced)


class ErrorPolicy(str, Enum):
    """What to do when a step fails."""

    STOP = "stop"          # Stop workflow immediately (default)
    CONTINUE = "continue"  # Skip to next step
    RETRY = "retry"        # Retry per retry policy (Advanced tier)


@dataclass(frozen=True)
class RetryPolicy:
    """
    Retry configuration for a step.

    Tier: Advanced (requires async execution)
    """

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 60.0
    retryable_categories: tuple[str, ...] = ("TRANSIENT", "TIMEOUT")


# =============================================================================
# Step Handler Protocol
# =============================================================================


@runtime_checkable
class StepHandler(Protocol):
    """
    Protocol for lambda step handlers.

    Handlers can be:
    - Functions: def my_step(ctx, config) -> StepResult
    - Callable classes: class MyStep: def __call__(self, ctx, config) -> StepResult
    """

    def __call__(
        self,
        ctx: "WorkflowContext",
        config: dict[str, Any],
    ) -> "StepResult":
        """Execute the step."""
        ...


# Type alias for step handlers
StepHandlerFn = Callable[["WorkflowContext", dict[str, Any]], "StepResult"]

# Type alias for choice conditions
ConditionFn = Callable[["WorkflowContext"], bool]


# =============================================================================
# Base Step
# =============================================================================


@dataclass
class Step:
    """
    A single step within a workflow.

    This is the base class for all step types. Use the factory methods
    to create specific step types:
    - Step.lambda_() for inline functions
    - Step.pipeline() for registered pipelines
    - Step.choice() for conditional branching (Intermediate)
    """

    name: str
    step_type: StepType
    config: dict[str, Any] = field(default_factory=dict)
    on_error: ErrorPolicy = ErrorPolicy.STOP
    retry_policy: RetryPolicy | None = None

    # Type-specific fields (only some apply per type)
    handler: StepHandlerFn | None = None      # Lambda
    pipeline_name: str | None = None          # Pipeline
    condition: ConditionFn | None = None      # Choice
    then_step: str | None = None              # Choice
    else_step: str | None = None              # Choice
    duration_seconds: int | None = None       # Wait
    items_path: str | None = None             # Map
    iterator_workflow: Any | None = None      # Map (Workflow type, avoid circular import)
    max_concurrency: int = 4                  # Map

    # =========================================================================
    # Factory Methods
    # =========================================================================

    @classmethod
    def lambda_(
        cls,
        name: str,
        handler: StepHandlerFn,
        config: dict[str, Any] | None = None,
        on_error: ErrorPolicy = ErrorPolicy.STOP,
    ) -> "Step":
        """
        Create a lambda step (inline function).

        Tier: Basic

        Args:
            name: Unique step name within workflow
            handler: Function (ctx, config) -> StepResult
            config: Step-specific configuration
            on_error: Error handling policy
        """
        return cls(
            name=name,
            step_type=StepType.LAMBDA,
            handler=handler,
            config=config or {},
            on_error=on_error,
        )

    @classmethod
    def pipeline(
        cls,
        name: str,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        on_error: ErrorPolicy = ErrorPolicy.STOP,
    ) -> "Step":
        """
        Create a pipeline step (wraps registered pipeline).

        Tier: Basic

        Args:
            name: Unique step name within workflow
            pipeline_name: Registered pipeline name (e.g., "finra.otc.ingest")
            params: Additional params to merge with context params
            on_error: Error handling policy
        """
        return cls(
            name=name,
            step_type=StepType.PIPELINE,
            pipeline_name=pipeline_name,
            config=params or {},
            on_error=on_error,
        )

    @classmethod
    def choice(
        cls,
        name: str,
        condition: ConditionFn,
        then_step: str,
        else_step: str | None = None,
    ) -> "Step":
        """
        Create a choice step (conditional branch).

        Tier: Intermediate

        Args:
            name: Unique step name within workflow
            condition: Function (ctx) -> bool
            then_step: Step name to go to if condition is True
            else_step: Step name to go to if condition is False (optional)
        """
        return cls(
            name=name,
            step_type=StepType.CHOICE,
            condition=condition,
            then_step=then_step,
            else_step=else_step,
        )

    @classmethod
    def wait(
        cls,
        name: str,
        duration_seconds: int,
        next_step: str | None = None,
    ) -> "Step":
        """
        Create a wait step (pause execution).

        Tier: Advanced (requires async/scheduler)

        Args:
            name: Unique step name within workflow
            duration_seconds: How long to wait
            next_step: Step to go to after wait (default: next in sequence)
        """
        return cls(
            name=name,
            step_type=StepType.WAIT,
            duration_seconds=duration_seconds,
            then_step=next_step,
        )

    @classmethod
    def map(
        cls,
        name: str,
        items_path: str,
        iterator_workflow: Any,  # Workflow type
        max_concurrency: int = 4,
        item_param: str = "item",
    ) -> "Step":
        """
        Create a map step (fan-out/fan-in).

        Tier: Advanced (requires parallel execution)

        Args:
            name: Unique step name within workflow
            items_path: Path in context.params to the items list
            iterator_workflow: Workflow to run for each item
            max_concurrency: Max parallel executions
            item_param: Param name for each item in iterator context
        """
        return cls(
            name=name,
            step_type=StepType.MAP,
            items_path=items_path,
            iterator_workflow=iterator_workflow,
            max_concurrency=max_concurrency,
            config={"item_param": item_param},
        )

    # =========================================================================
    # Utilities
    # =========================================================================

    def is_basic_tier(self) -> bool:
        """Check if this step type is available in Basic tier."""
        return self.step_type in (StepType.LAMBDA, StepType.PIPELINE)

    def is_intermediate_tier(self) -> bool:
        """Check if this step type requires Intermediate tier."""
        return self.step_type == StepType.CHOICE

    def is_advanced_tier(self) -> bool:
        """Check if this step type requires Advanced tier."""
        return self.step_type in (StepType.WAIT, StepType.MAP)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for YAML/JSON."""
        result: dict[str, Any] = {
            "name": self.name,
            "type": self.step_type.value,
        }

        if self.config:
            result["config"] = self.config
        if self.on_error != ErrorPolicy.STOP:
            result["on_error"] = self.on_error.value

        # Type-specific fields
        if self.step_type == StepType.PIPELINE:
            result["pipeline"] = self.pipeline_name
        elif self.step_type == StepType.CHOICE:
            result["then_step"] = self.then_step
            result["else_step"] = self.else_step
        elif self.step_type == StepType.WAIT:
            result["duration_seconds"] = self.duration_seconds
        elif self.step_type == StepType.MAP:
            result["items_path"] = self.items_path
            result["max_concurrency"] = self.max_concurrency

        return result

    def __repr__(self) -> str:
        if self.step_type == StepType.PIPELINE:
            return f"Step.pipeline({self.name!r}, {self.pipeline_name!r})"
        elif self.step_type == StepType.LAMBDA:
            return f"Step.lambda_({self.name!r}, <handler>)"
        elif self.step_type == StepType.CHOICE:
            return f"Step.choice({self.name!r}, then={self.then_step!r})"
        else:
            return f"Step({self.name!r}, type={self.step_type.value})"
