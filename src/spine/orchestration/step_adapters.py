"""Plain Function Adapters — decouple business logic from the workflow framework.

Problem
-------
A workflow step handler must accept ``(ctx: WorkflowContext, config: dict)``
and return ``StepResult``.  That signature couples the function to the
orchestration framework — you can't call it from a Jupyter notebook,
reuse it in market-spine, or unit-test it without constructing a
``WorkflowContext``.

Solution
--------
This module provides **adapters** that let you write plain Python functions
with typed parameters and dict/bool/None returns, then plug them into the
workflow engine without changing their signature.

Three mechanisms are provided (use whichever fits):

1.  **``Step.from_function()``** (on the Step class)::

        def calculate_risk(revenue: float, debt: float) -> dict:
            ratio = debt / revenue if revenue > 0 else float("inf")
            return {"risk_score": max(0, 100 - ratio * 10)}

        Step.from_function("assess_risk", calculate_risk)

2.  **``adapt_function()``** (returns a StepHandlerFn)::

        handler = adapt_function(calculate_risk)
        step = Step.lambda_("assess_risk", handler)

3.  **``@workflow_step`` decorator** (marks a function without changing it)::

        @workflow_step(name="assess_risk")
        def calculate_risk(revenue: float, debt: float) -> dict:
            ratio = debt / revenue if revenue > 0 else float("inf")
            return {"risk_score": max(0, 100 - ratio * 10)}

        # Direct call (notebook, script, other project):
        result = calculate_risk(revenue=1_000_000, debt=500_000)
        # => {"risk_score": 50.0}

        # As a workflow step:
        step = calculate_risk.as_step()
        # or
        step = calculate_risk.as_step(config={"revenue": 1e6, "debt": 5e5})

How the adapter works
---------------------
When the WorkflowRunner calls ``handler(ctx, config)``, the adapter:

1.  Merges ``ctx.params`` and ``config`` into a single kwargs dict.
2.  Inspects the function signature to extract only the kwargs the
    function actually accepts (so extra context keys don't cause
    ``TypeError``).
3.  Calls the function with the matched kwargs.
4.  Coerces the return value through ``StepResult.from_value()``.
5.  Catches exceptions and wraps them in ``StepResult.fail()``.

This means the function never needs to import ``WorkflowContext`` or
``StepResult`` — the adapter handles the translation.

Design rationale
~~~~~~~~~~~~~~~~
The decorator does NOT alter the function's signature or wrap it in a
class.  ``@workflow_step`` simply attaches an ``.as_step()`` method and
a ``._workflow_meta`` attribute to the original function.  The function
remains directly callable with its normal parameters.

Tier: Basic (spine-core)

Manifesto:
    Business logic functions should not import or depend on the workflow
    framework.  Step adapters wrap plain functions to conform to the
    step interface, keeping business code decoupled and testable.

Tags:
    spine-core, orchestration, adapters, decoupling, plain-functions

Doc-Types:
    api-reference
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from spine.orchestration.step_result import StepResult

# Lazy imports to avoid circular dependency (StepHandlerFn is defined in step_types)
# We import at function level where needed.


# =============================================================================
# Core adapter
# =============================================================================


def adapt_function(
    fn: Callable[..., Any],
    *,
    strict: bool = False,
) -> Callable[..., StepResult]:
    """Wrap a plain function as a workflow step handler.

    The returned callable has the signature
    ``(ctx: WorkflowContext, config: dict) -> StepResult``, which is
    what ``WorkflowRunner`` expects.  But the *wrapped* function ``fn``
    keeps its normal signature and can be called directly.

    Parameters
    ----------
    fn:
        Any callable.  Its parameters are matched against keys in
        ``config`` (first) and ``ctx.params`` (second).
    strict:
        If ``True``, raise ``TypeError`` when the function has required
        parameters that cannot be resolved from config/params.
        If ``False`` (default), missing params are silently omitted and
        the function's own defaults apply.  If the function has no
        default for a required param, Python will still raise
        ``TypeError`` — but the error message will be about *the function*,
        not about the framework.

    Returns
    -------
    A handler with the ``StepHandlerFn`` signature.
    """
    sig = inspect.signature(fn)
    param_names = list(sig.parameters.keys())
    has_var_keyword = any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    )

    @functools.wraps(fn)
    def _adapter(ctx: Any, config: dict[str, Any]) -> StepResult:
        # Build merged kwargs: config wins over ctx.params
        available = {}
        if hasattr(ctx, "params") and isinstance(ctx.params, dict):
            available.update(ctx.params)
        available.update(config)

        # If function accepts **kwargs, pass everything.
        # Otherwise, filter to only the params the function declares.
        if has_var_keyword:
            kwargs = available
        else:
            kwargs = {k: v for k, v in available.items() if k in param_names}

        if strict:
            # Check required params
            for name, param in sig.parameters.items():
                if (
                    param.default is inspect.Parameter.empty
                    and param.kind not in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    )
                    and name not in kwargs
                ):
                    return StepResult.fail(
                        f"Missing required parameter: '{name}' "
                        f"(not found in config or ctx.params)",
                        category="CONFIGURATION",
                    )

        try:
            result = fn(**kwargs)
            return StepResult.from_value(result)
        except Exception as e:
            return StepResult.fail(
                error=f"{type(e).__name__}: {e}",
                category="INTERNAL",
            )

    # Preserve the original function for direct calls
    _adapter.__wrapped__ = fn  # type: ignore[attr-defined]
    return _adapter


# =============================================================================
# Decorator
# =============================================================================


@dataclass(frozen=True)
class WorkflowStepMeta:
    """Metadata attached by ``@workflow_step``."""

    name: str
    description: str
    tags: tuple[str, ...]
    strict: bool


def workflow_step(
    name: str | None = None,
    *,
    description: str = "",
    tags: tuple[str, ...] | list[str] = (),
    strict: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator that marks a plain function as a reusable workflow step.

    The decorated function is **unchanged** — it keeps its original
    signature and is directly callable.  Two extras are attached:

    - ``fn._workflow_meta`` — a ``WorkflowStepMeta`` dataclass with the
      registered name, description, and tags.
    - ``fn.as_step(**overrides)`` — a convenience that returns a
      ``Step.from_function(...)`` step for use in ``Workflow(steps=[...])``.

    Parameters
    ----------
    name:
        Step name used in workflows.  Defaults to the function name.
    description:
        Human-readable description.
    tags:
        Optional tags for filtering / organisation.
    strict:
        Passed through to ``adapt_function()``.

    Example::

        @workflow_step(name="calculate_risk")
        def calculate_risk(revenue: float, debt: float) -> dict:
            return {"ratio": debt / revenue}

        # Direct call (no framework):
        calculate_risk(revenue=1e6, debt=5e5)

        # As a workflow step:
        step = calculate_risk.as_step(config={"revenue": 1e6})
    """
    _tags = tuple(tags)

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        step_name = name or fn.__name__

        meta = WorkflowStepMeta(
            name=step_name,
            description=description or (fn.__doc__ or "").split("\n")[0].strip(),
            tags=_tags,
            strict=strict,
        )
        fn._workflow_meta = meta  # type: ignore[attr-defined]

        def as_step(
            *,
            step_name_override: str | None = None,
            config: dict[str, Any] | None = None,
            on_error: str | None = None,
            depends_on: list[str] | None = None,
        ) -> Any:
            """Create a Step from this function.

            Parameters
            ----------
            step_name_override:
                Override the step name (defaults to the one in the decorator).
            config:
                Step-specific config dict.
            on_error:
                Error policy string ("stop", "continue", "retry").
            depends_on:
                Step names this step depends on.
            """
            from spine.orchestration.step_types import ErrorPolicy, Step

            error_policy = ErrorPolicy(on_error) if on_error else ErrorPolicy.STOP
            return Step.from_function(
                name=step_name_override or meta.name,
                fn=fn,
                config=config,
                on_error=error_policy,
                depends_on=depends_on,
                strict=strict,
            )

        fn.as_step = as_step  # type: ignore[attr-defined]
        return fn

    return decorator


# =============================================================================
# Utilities
# =============================================================================


def is_workflow_step(fn: Any) -> bool:
    """Check whether a callable was decorated with ``@workflow_step``."""
    return hasattr(fn, "_workflow_meta") and isinstance(
        fn._workflow_meta, WorkflowStepMeta
    )


def get_step_meta(fn: Any) -> WorkflowStepMeta | None:
    """Return the workflow metadata attached by ``@workflow_step``, or None."""
    meta = getattr(fn, "_workflow_meta", None)
    return meta if isinstance(meta, WorkflowStepMeta) else None
