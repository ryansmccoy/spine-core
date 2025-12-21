"""Step Types — definitions for workflow step variants.

Manifesto:
A Workflow is a list of Steps, but steps come in different flavours:
lambda (inline function), operation (registered Operation), choice
(conditional branch), wait (pause), and map (fan-out/fan-in).  This
module defines the ``Step`` dataclass and its factory methods so that
workflow authors never deal with raw internals.

ARCHITECTURE
────────────
::

    Step
      ├── .operation(name, operation_name)     ── wraps a registered Operation
      ├── .lambda_(name, handler)             ── inline function
      ├── .from_function(name, fn)            ── plain Python → adapted handler
      ├── .choice(name, condition, then/else) ── conditional branch
      ├── .wait(name, seconds)                ── pause execution
      └── .map(name, items, iterator)          ── fan-out/fan-in

    StepType      ── enum: LAMBDA, operation, CHOICE, WAIT, MAP
    ErrorPolicy   ── STOP or CONTINUE on step failure
    RetryPolicy   ── max_retries + backoff configuration

Related modules:
    step_result.py     — StepResult returned by every step
    step_adapters.py   — adapt plain functions into step handlers
    workflow.py        — Workflow that contains the steps

Example::

    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="my.workflow",
        steps=[
            Step.operation("ingest", "my.ingest_operation"),
            Step.lambda_("validate", validate_fn),
            Step.choice("route",
                condition=lambda ctx: ctx.params.get("valid"),
                then_step="process",
                else_step="reject",
            ),
        ],
    )

Tags:
    spine-core, orchestration, step-types, lambda, operation, choice, wait

Doc-Types:
    api-reference
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from spine.orchestration.step_result import StepResult
    from spine.orchestration.workflow_context import WorkflowContext


def _callable_ref(fn: Callable[..., Any] | None) -> str | None:
    """Return ``'module:qualname'`` for a named function, else ``None``.

    Lambdas, built-ins, bound methods, and ``None`` all return ``None``
    because they cannot be reliably re-imported.
    """
    if fn is None:
        return None
    module = getattr(fn, "__module__", None)
    qualname = getattr(fn, "__qualname__", None)
    if not module or not qualname:
        return None
    # Reject lambdas, locals, and nested definitions
    if "<lambda>" in qualname or "<locals>" in qualname:
        return None
    return f"{module}:{qualname}"


def resolve_callable_ref(ref: str) -> Callable[..., Any]:
    """Import and return the callable identified by ``'module:qualname'``.

    Raises:
        ImportError: If the module cannot be found.
        AttributeError: If the qualname path is invalid.
    """
    import importlib

    module_path, _, attr_path = ref.partition(":")
    if not attr_path:
        raise ValueError(f"Invalid callable ref (missing ':'): {ref!r}")
    mod = importlib.import_module(module_path)
    obj: Any = mod
    for part in attr_path.split("."):
        obj = getattr(obj, part)
    if not callable(obj):
        raise TypeError(f"{ref!r} resolved to non-callable: {type(obj)}")
    return obj


class StepType(str, Enum):
    """Type of workflow step."""

    LAMBDA = "lambda"  # Inline function (Basic)
    OPERATION = "operation"  # Registered operation (Basic)
    CHOICE = "choice"  # Conditional branch (Intermediate)
    WAIT = "wait"  # Pause execution (Advanced)
    MAP = "map"  # Fan-out/fan-in (Advanced)


class ErrorPolicy(str, Enum):
    """What to do when a step fails."""

    STOP = "stop"  # Stop workflow immediately (default)
    CONTINUE = "continue"  # Skip to next step
    RETRY = "retry"  # Retry per retry policy (Advanced tier)


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
        ctx: WorkflowContext,
        config: dict[str, Any],
    ) -> StepResult:
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
    - Step.operation() for registered operations
    - Step.choice() for conditional branching (Intermediate)
    """

    name: str
    step_type: StepType
    config: dict[str, Any] = field(default_factory=dict)
    on_error: ErrorPolicy = ErrorPolicy.STOP
    retry_policy: RetryPolicy | None = None

    # Type-specific fields (only some apply per type)
    handler: StepHandlerFn | None = None  # Lambda
    operation_name: str | None = None  # Operation
    condition: ConditionFn | None = None  # Choice
    then_step: str | None = None  # Choice
    else_step: str | None = None  # Choice
    duration_seconds: int | None = None  # Wait
    items_path: str | None = None  # Map
    iterator_workflow: Any | None = None  # Map (Workflow type, avoid circular import)
    max_concurrency: int = 4  # Map

    # Dependency edges (Phase 2: enables DAG execution)
    depends_on: tuple[str, ...] = ()  # Step names this step depends on

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
        depends_on: list[str] | tuple[str, ...] | None = None,
    ) -> Step:
        """
        Create a lambda step (inline function).

        Tier: Basic

        Args:
            name: Unique step name within workflow
            handler: Function (ctx, config) -> StepResult
            config: Step-specific configuration
            on_error: Error handling policy
            depends_on: Step names this step depends on
        """
        return cls(
            name=name,
            step_type=StepType.LAMBDA,
            handler=handler,
            config=config or {},
            on_error=on_error,
            depends_on=tuple(depends_on or ()),
        )

    @classmethod
    def operation(
        cls,
        name: str,
        operation_name: str,
        params: dict[str, Any] | None = None,
        on_error: ErrorPolicy = ErrorPolicy.STOP,
        depends_on: list[str] | tuple[str, ...] | None = None,
    ) -> Step:
        """
        Create a operation step (wraps registered operation).

        Tier: Basic

        Args:
            name: Unique step name within workflow
            operation_name: Registered operation name (e.g., "finra.otc.ingest")
            params: Additional params to merge with context params
            on_error: Error handling policy
            depends_on: Step names this step depends on
        """
        return cls(
            name=name,
            step_type=StepType.OPERATION,
            operation_name=operation_name,
            config=params or {},
            on_error=on_error,
            depends_on=tuple(depends_on or ()),
        )

    @classmethod
    def choice(
        cls,
        name: str,
        condition: ConditionFn,
        then_step: str,
        else_step: str | None = None,
    ) -> Step:
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
    ) -> Step:
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
    ) -> Step:
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

    @classmethod
    def from_function(
        cls,
        name: str,
        fn: Callable[..., Any],
        config: dict[str, Any] | None = None,
        on_error: ErrorPolicy = ErrorPolicy.STOP,
        depends_on: list[str] | tuple[str, ...] | None = None,
        strict: bool = False,
    ) -> Step:
        """Create a step from a **plain function** (no framework imports needed).

        This is the recommended way to bridge standalone business logic
        into the workflow engine.  The function keeps its normal
        signature and can be called directly in notebooks, scripts, or
        other projects — the adapter handles the translation.

        How it works:

        1. ``config`` keys and ``ctx.params`` keys are merged.
        2. Only the keys that match the function's parameter names are
           passed as ``**kwargs``.
        3. The return value is coerced through ``StepResult.from_value()``:
           ``dict`` → ``ok(output=dict)``, ``bool`` → ok/fail, etc.
        4. Exceptions are caught and wrapped in ``StepResult.fail()``.

        Tier: Basic

        Args:
            name: Unique step name within workflow.
            fn: Any callable — plain function, method, or lambda.
            config: Static config dict (keys are passed as kwargs).
            on_error: Error handling policy.
            depends_on: Step names this step depends on.
            strict: If True, fail when required params are missing
                from config/ctx.params instead of relying on Python's
                own TypeError.

        Example::

            def calculate_risk(revenue: float, debt: float) -> dict:
                return {"ratio": debt / revenue}

            step = Step.from_function("risk", calculate_risk,
                                      config={"revenue": 1e6, "debt": 5e5})
        """
        from spine.orchestration.step_adapters import adapt_function

        handler = adapt_function(fn, strict=strict)
        return cls(
            name=name,
            step_type=StepType.LAMBDA,
            handler=handler,
            config=config or {},
            on_error=on_error,
            depends_on=tuple(depends_on or ()),
        )

    # =========================================================================
    # Utilities
    # =========================================================================

    def is_basic_tier(self) -> bool:
        """Check if this step type is available in Basic tier."""
        return self.step_type in (StepType.LAMBDA, StepType.OPERATION)

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
        if self.step_type == StepType.OPERATION:
            result["operation"] = self.operation_name
        elif self.step_type == StepType.LAMBDA:
            ref = self._handler_ref()
            if ref:
                result["handler_ref"] = ref
        elif self.step_type == StepType.CHOICE:
            result["then_step"] = self.then_step
            result["else_step"] = self.else_step
            ref = self._condition_ref()
            if ref:
                result["condition_ref"] = ref
        elif self.step_type == StepType.WAIT:
            result["duration_seconds"] = self.duration_seconds
        elif self.step_type == StepType.MAP:
            result["items_path"] = self.items_path
            result["max_concurrency"] = self.max_concurrency

        if self.depends_on:
            result["depends_on"] = list(self.depends_on)

        return result

    def _handler_ref(self) -> str | None:
        """Get importable reference string for the handler callable.

        Returns ``'module:qualname'`` for named functions, ``None`` for
        lambdas, built-ins, or missing handlers.
        """
        return _callable_ref(self.handler)

    def _condition_ref(self) -> str | None:
        """Get importable reference string for the condition callable."""
        return _callable_ref(self.condition)

    def __repr__(self) -> str:
        if self.step_type == StepType.OPERATION:
            return f"Step.operation({self.name!r}, {self.operation_name!r})"
        elif self.step_type == StepType.LAMBDA:
            return f"Step.lambda_({self.name!r}, <handler>)"
        elif self.step_type == StepType.CHOICE:
            return f"Step.choice({self.name!r}, then={self.then_step!r})"
        else:
            return f"Step({self.name!r}, type={self.step_type.value})"
