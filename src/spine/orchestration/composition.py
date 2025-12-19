"""Composition Operators — functional builders for workflow construction.

WHY
───
Constructing ``Workflow`` objects by hand with ``Step.pipeline()`` and
``Step.lambda_()`` is verbose for common patterns.  Composition operators
provide concise, composable functions that produce well-formed
workflows from building blocks.

ARCHITECTURE
────────────
::

    Composition operators:
      chain(name, *steps)                 → sequential workflow
      parallel(name, *steps, merge_fn)    → DAG with shared root
      conditional(name, cond, then, else) → choice-based branching
      retry(name, step, max_attempts)     → retry wrapper around a step
      merge_workflows(name, *workflows)   → combine multiple workflows

    All operators return a ``Workflow`` instance that can be:
      - Executed directly via ``WorkflowRunner``
      - Registered in the ``WorkflowRegistry``
      - Composed further with other operators

BEST PRACTICES
──────────────
- Use ``chain()`` instead of manually listing sequential steps.
- Use ``parallel()`` for independent steps that can run concurrently.
- Nest operators to build complex topologies:
    ``chain("outer", step_a, parallel("inner", step_b, step_c), step_d)``

Related modules:
    templates.py       — higher-level domain-specific patterns
    step_types.py      — Step factories used by operators
    workflow.py        — the Workflow these operators produce

Example::

    from spine.orchestration.composition import chain, parallel

    wf = chain(
        "my.etl",
        Step.pipeline("extract", "my.extract"),
        Step.pipeline("transform", "my.transform"),
        Step.pipeline("load", "my.load"),
    )

    wf = parallel(
        "my.parallel_ingest",
        Step.pipeline("source_a", "ingest.source_a"),
        Step.pipeline("source_b", "ingest.source_b"),
        Step.pipeline("source_c", "ingest.source_c"),
    )
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import (
    ConditionFn,
    ErrorPolicy,
    Step,
    StepType,
)
from spine.orchestration.workflow import (
    ExecutionMode,
    FailurePolicy,
    Workflow,
    WorkflowExecutionPolicy,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# chain — sequential composition
# ---------------------------------------------------------------------------


def chain(
    name: str,
    *steps: Step,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> Workflow:
    """Create a sequential workflow from ordered steps.

    Each step runs after the previous one completes.  Dependencies are
    *not* added — the sequential execution mode handles ordering.

    Parameters
    ----------
    name
        Workflow name.
    *steps
        Steps in execution order.
    domain
        Optional domain classification.
    description
        Human-readable description.
    tags
        Optional tags.
    defaults
        Default parameters for the workflow.

    Returns
    -------
    Workflow
        A sequential workflow.

    Raises
    ------
    ValueError
        If fewer than one step is provided.

    Example::

        wf = chain(
            "my.etl",
            Step.pipeline("extract", "data.extract"),
            Step.lambda_("validate", validate_fn),
            Step.pipeline("load", "data.load"),
        )
    """
    if len(steps) < 1:
        raise ValueError("chain() requires at least one step")

    return Workflow(
        name=name,
        steps=list(steps),
        domain=domain,
        description=description or f"chain({len(steps)} steps)",
        tags=tags or ["composition", "chain"],
        defaults=defaults or {},
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.SEQUENTIAL,
        ),
    )


# ---------------------------------------------------------------------------
# parallel — concurrent composition
# ---------------------------------------------------------------------------


def parallel(
    name: str,
    *steps: Step,
    merge_fn: Callable[..., Any] | None = None,
    max_concurrency: int = 4,
    on_failure: FailurePolicy = FailurePolicy.STOP,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> Workflow:
    """Create a parallel workflow where all steps run concurrently.

    All steps are independent (no inter-step dependencies) and execute
    in a DAG mode.  An optional ``merge_fn`` is appended as a final
    lambda step that depends on all parallel steps.

    Parameters
    ----------
    name
        Workflow name.
    *steps
        Steps to run in parallel.
    merge_fn
        Optional handler ``(ctx, config) -> StepResult`` that runs
        after all parallel steps complete.
    max_concurrency
        Maximum number of steps to run simultaneously.
    on_failure
        What to do when a step fails (``STOP`` or ``CONTINUE``).
    domain
        Optional domain classification.
    description
        Human-readable description.
    tags
        Optional tags.
    defaults
        Default parameters.

    Returns
    -------
    Workflow
        A parallel DAG workflow.

    Raises
    ------
    ValueError
        If fewer than two steps are provided.

    Example::

        wf = parallel(
            "multi.ingest",
            Step.pipeline("source_a", "ingest.a"),
            Step.pipeline("source_b", "ingest.b"),
            Step.pipeline("source_c", "ingest.c"),
            merge_fn=combine_results,
        )
    """
    if len(steps) < 2:
        raise ValueError("parallel() requires at least two steps")

    all_steps = list(steps)

    # Enable DAG mode: mark all input steps as having no dependencies
    # (they're independent).  Then if merge_fn is provided, add a
    # merge step that depends on all of them.
    if merge_fn:
        dep_names = tuple(s.name for s in steps)
        merge_step = Step.lambda_(
            "__merge__",
            merge_fn,
            depends_on=list(dep_names),
        )
        all_steps.append(merge_step)

    return Workflow(
        name=name,
        steps=all_steps,
        domain=domain,
        description=description or f"parallel({len(steps)} branches)",
        tags=tags or ["composition", "parallel"],
        defaults=defaults or {},
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL,
            max_concurrency=max_concurrency,
            on_failure=on_failure,
        ),
    )


# ---------------------------------------------------------------------------
# conditional — choice-based branching
# ---------------------------------------------------------------------------


def conditional(
    name: str,
    condition: ConditionFn,
    then_steps: list[Step],
    else_steps: list[Step] | None = None,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> Workflow:
    """Create a conditional workflow with if/else branching.

    Produces a workflow with a choice step followed by two branches.
    The ``then_steps`` execute when ``condition(ctx)`` is ``True``;
    ``else_steps`` (optional) execute otherwise.

    Parameters
    ----------
    name
        Workflow name.
    condition
        Callable ``(ctx) -> bool`` for the branch decision.
    then_steps
        Steps to execute when condition is True.
    else_steps
        Steps to execute when condition is False (optional).
    domain
        Optional domain classification.
    description
        Human-readable description.
    tags
        Optional tags.
    defaults
        Default parameters.

    Returns
    -------
    Workflow
        A workflow with choice-based branching.

    Raises
    ------
    ValueError
        If no ``then_steps`` are provided.

    Example::

        wf = conditional(
            "check.quality",
            condition=lambda ctx: ctx.params.get("valid", False),
            then_steps=[Step.pipeline("publish", "data.publish")],
            else_steps=[Step.pipeline("quarantine", "data.quarantine")],
        )
    """
    if not then_steps:
        raise ValueError("conditional() requires at least one then_step")

    # Build steps list: choice → then branch → else branch
    all_steps: list[Step] = []

    then_first = then_steps[0].name
    else_first = else_steps[0].name if else_steps else None

    # Choice step routes to the correct branch
    choice = Step.choice(
        "__condition__",
        condition=condition,
        then_step=then_first,
        else_step=else_first,
    )
    all_steps.append(choice)

    # Then branch
    all_steps.extend(then_steps)

    # Else branch (appended after then steps)
    if else_steps:
        all_steps.extend(else_steps)

    return Workflow(
        name=name,
        steps=all_steps,
        domain=domain,
        description=description or f"conditional({then_first}|{else_first})",
        tags=tags or ["composition", "conditional"],
        defaults=defaults or {},
    )


# ---------------------------------------------------------------------------
# retry — retry wrapper
# ---------------------------------------------------------------------------


def retry(
    name: str,
    step: Step,
    max_attempts: int = 3,
    on_exhaust: ErrorPolicy = ErrorPolicy.STOP,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> Workflow:
    """Create a workflow that retries a step on failure.

    Wraps the given step in a retry loop using lambda steps that track
    and manage attempt counts.  This is a structural retry — it creates
    multiple copies of the step for up to ``max_attempts``.

    Parameters
    ----------
    name
        Workflow name.
    step
        The step to retry on failure.
    max_attempts
        Maximum number of attempts (including the first).
    on_exhaust
        Error policy if all attempts fail.
    domain
        Optional domain classification.
    description
        Description.
    tags
        Tags.
    defaults
        Default parameters.

    Returns
    -------
    Workflow
        A workflow with retry semantics.

    Raises
    ------
    ValueError
        If ``max_attempts`` < 1.

    Example::

        wf = retry(
            "resilient.ingest",
            Step.pipeline("fetch", "data.fetch"),
            max_attempts=3,
        )
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    steps: list[Step] = []

    for attempt in range(max_attempts):
        suffix = f"_attempt_{attempt + 1}" if max_attempts > 1 else ""
        attempt_step = Step(
            name=f"{step.name}{suffix}",
            step_type=step.step_type,
            config={**step.config, "__attempt__": attempt + 1},
            on_error=ErrorPolicy.CONTINUE if attempt < max_attempts - 1 else on_exhaust,
            handler=step.handler,
            pipeline_name=step.pipeline_name,
            condition=step.condition,
            then_step=step.then_step,
            else_step=step.else_step,
            duration_seconds=step.duration_seconds,
        )
        steps.append(attempt_step)

    return Workflow(
        name=name,
        steps=steps,
        domain=domain,
        description=description or f"retry({step.name}, max={max_attempts})",
        tags=tags or ["composition", "retry"],
        defaults=defaults or {},
    )


# ---------------------------------------------------------------------------
# merge_workflows — combine workflows
# ---------------------------------------------------------------------------


def merge_workflows(
    name: str,
    *workflows: Workflow,
    domain: str = "",
    description: str = "",
    tags: list[str] | None = None,
    defaults: dict[str, Any] | None = None,
) -> Workflow:
    """Merge multiple workflows into a single sequential workflow.

    Steps from each workflow are concatenated in order.  Step names are
    prefixed with the source workflow name to avoid collisions.

    Parameters
    ----------
    name
        Name for the merged workflow.
    *workflows
        Workflows to merge.
    domain
        Optional domain classification.
    description
        Description.
    tags
        Tags.
    defaults
        Default parameters.

    Returns
    -------
    Workflow
        A merged workflow containing all steps from all inputs.

    Raises
    ------
    ValueError
        If fewer than two workflows are provided.

    Example::

        merged = merge_workflows(
            "full.pipeline",
            ingest_workflow,
            transform_workflow,
            load_workflow,
        )
    """
    if len(workflows) < 2:
        raise ValueError("merge_workflows() requires at least two workflows")

    all_steps: list[Step] = []
    merged_defaults: dict[str, Any] = defaults.copy() if defaults else {}
    seen_names: set[str] = set()

    for wf in workflows:
        # Merge defaults from sub-workflows
        merged_defaults.update(wf.defaults)

        for step in wf.steps:
            # Prefix step name if there's a collision
            step_name = step.name
            if step_name in seen_names:
                step_name = f"{wf.name}.{step.name}"

            if step_name != step.name:
                # Create a copy with the new name
                step = Step(
                    name=step_name,
                    step_type=step.step_type,
                    config=step.config,
                    on_error=step.on_error,
                    handler=step.handler,
                    pipeline_name=step.pipeline_name,
                    condition=step.condition,
                    then_step=step.then_step,
                    else_step=step.else_step,
                    duration_seconds=step.duration_seconds,
                    depends_on=step.depends_on,
                )

            seen_names.add(step_name)
            all_steps.append(step)

    source_names = ", ".join(wf.name for wf in workflows)
    return Workflow(
        name=name,
        steps=all_steps,
        domain=domain,
        description=description or f"merge({source_names})",
        tags=tags or ["composition", "merge"],
        defaults=merged_defaults,
    )
