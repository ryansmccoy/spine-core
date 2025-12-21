"""Workflow Templates — pre-built patterns for common workflow shapes.

Manifesto:
Many workflows follow the same shape: ETL operations, fan-out/fan-in,
conditional routing, retry wrappers, scheduled batches.  Instead of
re-inventing these each time, templates provide factory functions that
produce a fully-wired ``Workflow`` you can customise and register.

ARCHITECTURE
────────────
::

    Built-in templates:
      etl_operation(name, extract, transform, load)      → 3-step ETL
      fan_out_fan_in(name, items, iterator, merge)      → scatter/gather
      conditional_branch(name, condition, then, else_)  → if/else routing
      retry_wrapper(name, operation, max_retries)        → retry + fallback
      scheduled_batch(name, operation)                   → wait → run → notify

    Template registry:
      register_template(name, factory)   → add custom template
      get_template(name)                 → retrieve factory
      list_templates()                   → available template names

BEST PRACTICES
──────────────
- Templates return a ``Workflow`` — modify ``steps`` or ``defaults``
  before registering.
- Use ``register_template`` for organisation-specific patterns.

Related modules:
    workflow.py        — the Workflow that templates produce
    step_types.py      — Step factories used inside templates
    workflow_registry  — register the produced workflow

Example::

    from spine.orchestration.templates import etl_operation

    wf = etl_operation(
        name="finra.daily_etl",
        extract_operation="finra.fetch_data",
        transform_operation="finra.normalize",
        load_operation="finra.store",
    )

Tags:
    spine-core, orchestration, templates, ETL, fan-out,
    pipeline, pre-built-patterns

Doc-Types:
    api-reference
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from spine.orchestration.step_types import ErrorPolicy, Step
from spine.orchestration.workflow import (
    FailurePolicy,
    Workflow,
    WorkflowExecutionPolicy,
)

# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, Callable[..., Workflow]] = {}


def register_template(name: str, factory: Callable[..., Workflow]) -> None:
    """Register a custom workflow template.

    Parameters
    ----------
    name
        Template name (e.g., ``"etl_operation"``).
    factory
        Callable that returns a ``Workflow``.
    """
    _TEMPLATES[name] = factory


def get_template(name: str) -> Callable[..., Workflow]:
    """Get a registered template factory by name.

    Raises
    ------
    KeyError
        If the template is not registered.
    """
    if name not in _TEMPLATES:
        raise KeyError(f"Unknown template: {name!r}. Available: {list(_TEMPLATES)}")
    return _TEMPLATES[name]


def list_templates() -> list[str]:
    """List all registered template names."""
    return sorted(_TEMPLATES.keys())


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

def etl_operation(
    *,
    name: str,
    extract_operation: str,
    transform_operation: str,
    load_operation: str,
    domain: str = "",
    validate_handler: Callable[..., Any] | None = None,
    description: str = "",
    tags: list[str] | None = None,
    on_failure: str = "stop",
) -> Workflow:
    """Create an ETL (Extract-Transform-Load) workflow.

    Parameters
    ----------
    name
        Workflow name.
    extract_operation
        Operation name for extraction.
    transform_operation
        Operation name for transformation.
    load_operation
        Operation name for loading.
    domain
        Optional domain classification.
    validate_handler
        Optional validation function between extract and transform.
    description
        Human-readable description.
    tags
        Optional tags.
    on_failure
        Failure policy: ``"stop"`` or ``"continue"``.

    Returns
    -------
    Workflow
        A 3-4 step ETL workflow.
    """
    steps: list[Step] = [
        Step.operation("extract", extract_operation),
    ]

    if validate_handler:
        steps.append(
            Step.lambda_("validate", validate_handler, depends_on=("extract",))
        )
        transform_deps = ("validate",)
    else:
        transform_deps = ("extract",)

    steps.extend([
        Step.operation("transform", transform_operation, depends_on=transform_deps),
        Step.operation("load", load_operation, depends_on=("transform",)),
    ])

    return Workflow(
        name=name,
        steps=steps,
        domain=domain,
        description=description or f"ETL: {extract_operation} → {transform_operation} → {load_operation}",
        tags=tags or ["etl"],
        execution_policy=WorkflowExecutionPolicy(
            on_failure=FailurePolicy(on_failure),
        ),
    )


def fan_out_fan_in(
    *,
    name: str,
    items_path: str,
    iterator_operation: str,
    merge_handler: Callable[..., Any] | None = None,
    max_concurrency: int = 8,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
) -> Workflow:
    """Create a fan-out/fan-in workflow.

    Parameters
    ----------
    name
        Workflow name.
    items_path
        JSONPath to the items collection in context.
    iterator_operation
        Operation to run for each item.
    merge_handler
        Optional handler to merge results after fan-in.
    max_concurrency
        Max parallel iterations.
    domain
        Optional domain.
    description
        Description.
    tags
        Tags.

    Returns
    -------
    Workflow
        A map + optional merge workflow.
    """
    steps: list[Step] = [
        Step.map(
            "scatter",
            items_path=items_path,
            iterator_workflow=iterator_operation,
            max_concurrency=max_concurrency,
        ),
    ]

    if merge_handler:
        steps.append(
            Step.lambda_("merge", merge_handler, depends_on=("scatter",))
        )

    return Workflow(
        name=name,
        steps=steps,
        domain=domain,
        description=description or f"Fan-out: {items_path} × {iterator_operation}",
        tags=tags or ["fan-out", "parallel"],
    )


def conditional_branch(
    *,
    name: str,
    condition: Callable[..., bool],
    true_operation: str,
    false_operation: str,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
) -> Workflow:
    """Create a conditional branching workflow.

    Parameters
    ----------
    name
        Workflow name.
    condition
        Function that returns ``True``/``False`` given context.
    true_operation
        Operation to run if condition is ``True``.
    false_operation
        Operation to run if condition is ``False``.
    domain
        Optional domain.
    description
        Description.
    tags
        Tags.

    Returns
    -------
    Workflow
        A 3-step workflow with choice routing.
    """
    steps = [
        Step.operation("on_true", true_operation),
        Step.operation("on_false", false_operation),
        Step.choice("route", condition, "on_true", "on_false"),
    ]

    return Workflow(
        name=name,
        steps=steps,
        domain=domain,
        description=description or f"Branch: {true_operation} / {false_operation}",
        tags=tags or ["conditional"],
    )


def retry_wrapper(
    *,
    name: str,
    target_operation: str,
    fallback_operation: str | None = None,
    max_retries: int = 3,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
) -> Workflow:
    """Create a workflow that wraps a operation with retry semantics.

    Parameters
    ----------
    name
        Workflow name.
    target_operation
        The operation to attempt.
    fallback_operation
        Optional fallback operation if all retries fail.
    max_retries
        Number of retry attempts (set via retry_policy on step).
    domain
        Optional domain.
    description
        Description.
    tags
        Tags.

    Returns
    -------
    Workflow
        A workflow with retry policy configured.
    """
    from spine.orchestration.step_types import RetryPolicy

    main_step = Step.operation("attempt", target_operation)
    main_step.on_error = ErrorPolicy.CONTINUE
    main_step.retry_policy = RetryPolicy(
        max_attempts=max_retries,
        initial_delay_seconds=1,
        backoff_multiplier=2.0,
    )

    steps: list[Step] = [main_step]

    if fallback_operation:
        steps.append(
            Step.operation("fallback", fallback_operation, depends_on=("attempt",))
        )

    return Workflow(
        name=name,
        steps=steps,
        domain=domain,
        description=description or f"Retry wrapper: {target_operation} (max {max_retries})",
        tags=tags or ["retry", "resilience"],
        execution_policy=WorkflowExecutionPolicy(
            on_failure=FailurePolicy.CONTINUE,
        ),
    )


def scheduled_batch(
    *,
    name: str,
    wait_seconds: int,
    execute_operation: str,
    validate_handler: Callable[..., Any] | None = None,
    notify_handler: Callable[..., Any] | None = None,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
) -> Workflow:
    """Create a scheduled batch workflow: wait → execute → validate → notify.

    Parameters
    ----------
    name
        Workflow name.
    wait_seconds
        How long to wait before execution.
    execute_operation
        Operation to run.
    validate_handler
        Optional validation handler.
    notify_handler
        Optional notification handler.
    domain
        Optional domain.
    description
        Description.
    tags
        Tags.

    Returns
    -------
    Workflow
        A multi-step batch workflow.
    """
    steps: list[Step] = [
        Step.wait("delay", wait_seconds),
        Step.operation("execute", execute_operation, depends_on=("delay",)),
    ]

    if validate_handler:
        steps.append(
            Step.lambda_("validate", validate_handler, depends_on=("execute",))
        )
        notify_deps = ("validate",)
    else:
        notify_deps = ("execute",)

    if notify_handler:
        steps.append(
            Step.lambda_("notify", notify_handler, depends_on=notify_deps)
        )

    return Workflow(
        name=name,
        steps=steps,
        domain=domain,
        description=description or f"Scheduled batch: {wait_seconds}s → {execute_operation}",
        tags=tags or ["batch", "scheduled"],
    )


# ---------------------------------------------------------------------------
# Auto-register built-in templates
# ---------------------------------------------------------------------------

_BUILTINS = {
    "etl_operation": etl_operation,
    "fan_out_fan_in": fan_out_fan_in,
    "conditional_branch": conditional_branch,
    "retry_wrapper": retry_wrapper,
    "scheduled_batch": scheduled_batch,
}

for _name, _factory in _BUILTINS.items():
    register_template(_name, _factory)
