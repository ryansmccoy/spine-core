"""Dry-Run Mode — preview workflow execution without side effects.

WHY
───
Before running a workflow against production data, developers need to
verify the execution plan: which steps will run, in what order, and
what resources will be consumed.  Dry-run mode executes the workflow
graph *structurally* — evaluating dependencies, validating configs,
and estimating cost — without actually invoking pipeline backends.

ARCHITECTURE
────────────
::

    dry_run(workflow, params)
    │
    ├── Validate all steps (lint)
    ├── Resolve execution order
    ├── Estimate per-step cost/time
    ├── Check parameter requirements
    │
    ▼
    DryRunResult
    ├── execution_plan: list[DryRunStep]
    ├── total_estimated_seconds: float
    ├── validation_issues: list[str]
    ├── is_valid: bool
    └── summary() → str

    DryRunStep
    ├── step_name, step_type
    ├── order: int
    ├── estimated_seconds: float
    ├── will_execute: bool
    └── notes: list[str]

BEST PRACTICES
──────────────
- Always dry-run before deploying to production.
- Register cost estimators for expensive pipelines.
- Combine with ``lint_workflow()`` for comprehensive pre-flight checks.

Related modules:
    workflow_runner.py — has ``dry_run=True`` for mock pipeline runs
    linter.py          — static analysis (complementary)
    visualizer.py      — visual representation of the plan

Example::

    from spine.orchestration.dry_run import dry_run

    result = dry_run(workflow, params={"tier": "NMS_TIER_1"})
    print(result.summary())
    if result.is_valid:
        runner.execute(workflow, params=params)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import ExecutionMode, Workflow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cost estimator registry
# ---------------------------------------------------------------------------

# Maps pipeline_name → estimated seconds
_COST_ESTIMATES: dict[str, float] = {}

# Custom estimator functions: (step, params) → estimated_seconds
_CUSTOM_ESTIMATORS: dict[str, Callable[[Step, dict[str, Any]], float]] = {}

# Default per-type estimates
_DEFAULT_ESTIMATES: dict[str, float] = {
    "lambda": 0.1,
    "pipeline": 5.0,
    "choice": 0.01,
    "wait": 0.0,  # actual wait time used
    "map": 10.0,
}


def register_cost_estimate(pipeline_name: str, estimated_seconds: float) -> None:
    """Register an estimated execution time for a pipeline.

    Parameters
    ----------
    pipeline_name
        The pipeline identifier (e.g. ``"finra.otc.ingest"``).
    estimated_seconds
        Expected duration in seconds.
    """
    _COST_ESTIMATES[pipeline_name] = estimated_seconds


def register_estimator(
    step_name: str,
    estimator: Callable[[Step, dict[str, Any]], float],
) -> None:
    """Register a custom cost estimator function for a step.

    Parameters
    ----------
    step_name
        The step name to apply this estimator to.
    estimator
        Callable ``(step, params) -> float`` returning estimated seconds.
    """
    _CUSTOM_ESTIMATORS[step_name] = estimator


def clear_cost_registry() -> None:
    """Clear all registered cost estimates and estimators."""
    _COST_ESTIMATES.clear()
    _CUSTOM_ESTIMATORS.clear()


# ---------------------------------------------------------------------------
# Dry-run result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DryRunStep:
    """Preview of a single step's planned execution.

    Attributes:
        step_name: Name of the step.
        step_type: Type (lambda, pipeline, choice, etc.).
        order: Execution order (1-based).
        estimated_seconds: Estimated duration.
        will_execute: Whether this step will actually run.
        dependencies: Steps this step depends on.
        notes: Any warnings or info about the step.
    """

    step_name: str
    step_type: str
    order: int
    estimated_seconds: float
    will_execute: bool = True
    dependencies: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass
class DryRunResult:
    """Result of a dry-run analysis.

    Attributes:
        workflow_name: Name of the analysed workflow.
        execution_plan: Ordered list of step previews.
        validation_issues: Problems detected during analysis.
        params_provided: Parameters that were supplied.
        execution_mode: Sequential or parallel.
    """

    workflow_name: str
    execution_plan: list[DryRunStep] = field(default_factory=list)
    validation_issues: list[str] = field(default_factory=list)
    params_provided: dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "sequential"

    @property
    def is_valid(self) -> bool:
        """True if no validation issues were found."""
        return len(self.validation_issues) == 0

    @property
    def total_estimated_seconds(self) -> float:
        """Total estimated execution time.

        For sequential mode, sums all step estimates.
        For parallel mode, uses the longest critical path.
        """
        if self.execution_mode == "parallel":
            return self._parallel_estimate()
        return sum(s.estimated_seconds for s in self.execution_plan if s.will_execute)

    @property
    def step_count(self) -> int:
        """Number of steps that will execute."""
        return sum(1 for s in self.execution_plan if s.will_execute)

    def _parallel_estimate(self) -> float:
        """Estimate parallel execution time via critical path."""
        if not self.execution_plan:
            return 0.0

        # Build dependency completion times
        completion: dict[str, float] = {}
        for step in self.execution_plan:
            if not step.will_execute:
                continue
            dep_time = max(
                (completion.get(d, 0.0) for d in step.dependencies),
                default=0.0,
            )
            completion[step.step_name] = dep_time + step.estimated_seconds

        return max(completion.values()) if completion else 0.0

    def summary(self) -> str:
        """Human-readable summary of the dry-run result."""
        lines: list[str] = []
        lines.append(f"=== Dry-Run: {self.workflow_name} ===")
        lines.append(f"Mode: {self.execution_mode}")
        lines.append(f"Steps: {self.step_count}")
        lines.append(f"Estimated time: {self.total_estimated_seconds:.1f}s")
        lines.append("")

        if self.validation_issues:
            lines.append("VALIDATION ISSUES:")
            for issue in self.validation_issues:
                lines.append(f"  ! {issue}")
            lines.append("")

        lines.append("EXECUTION PLAN:")
        for step in self.execution_plan:
            marker = ">" if step.will_execute else "x"
            deps = f" (after: {', '.join(step.dependencies)})" if step.dependencies else ""
            lines.append(
                f"  {marker} {step.order}. [{step.step_type}] {step.step_name}"
                f" ~{step.estimated_seconds:.1f}s{deps}"
            )
            for note in step.notes:
                lines.append(f"      {note}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core dry-run function
# ---------------------------------------------------------------------------


def _estimate_step(step: Step, params: dict[str, Any]) -> float:
    """Estimate execution time for a single step."""
    # Custom estimator takes priority
    if step.name in _CUSTOM_ESTIMATORS:
        return _CUSTOM_ESTIMATORS[step.name](step, params)

    # Pipeline-specific estimate
    if step.step_type == StepType.PIPELINE and step.pipeline_name:
        if step.pipeline_name in _COST_ESTIMATES:
            return _COST_ESTIMATES[step.pipeline_name]

    # Wait steps use their configured duration
    if step.step_type == StepType.WAIT and step.duration_seconds:
        return float(step.duration_seconds)

    # Fall back to type default
    return _DEFAULT_ESTIMATES.get(step.step_type.value, 1.0)


def _validate_step(step: Step, params: dict[str, Any]) -> list[str]:
    """Validate a single step and return any issues."""
    issues: list[str] = []

    if step.step_type == StepType.LAMBDA and step.handler is None:
        issues.append(f"Step '{step.name}': lambda has no handler")

    if step.step_type == StepType.PIPELINE and not step.pipeline_name:
        issues.append(f"Step '{step.name}': pipeline has no pipeline_name")

    if step.step_type == StepType.CHOICE and step.condition is None:
        issues.append(f"Step '{step.name}': choice has no condition function")

    return issues


def _collect_notes(step: Step, params: dict[str, Any]) -> list[str]:
    """Collect informational notes about a step."""
    notes: list[str] = []

    if step.step_type == StepType.PIPELINE:
        if step.pipeline_name and step.pipeline_name in _COST_ESTIMATES:
            notes.append(f"Custom cost estimate: {_COST_ESTIMATES[step.pipeline_name]:.1f}s")
        elif step.pipeline_name:
            notes.append("Using default cost estimate (register_cost_estimate for accuracy)")

    if step.on_error == "continue":
        notes.append("Continues on failure (ErrorPolicy.CONTINUE)")

    if step.depends_on:
        notes.append(f"Depends on: {', '.join(step.depends_on)}")

    if step.step_type == StepType.CHOICE:
        notes.append(f"Then → {step.then_step}, Else → {step.else_step or 'skip'}")

    return notes


def dry_run(
    workflow: Workflow,
    params: dict[str, Any] | None = None,
) -> DryRunResult:
    """Preview a workflow's execution plan without running it.

    Analyses the workflow structure, validates steps, estimates
    execution time, and returns a detailed plan.

    Parameters
    ----------
    workflow
        The workflow to analyse.
    params
        Parameters that would be passed at execution time.

    Returns
    -------
    DryRunResult
        Detailed execution preview.

    Example::

        result = dry_run(my_workflow, params={"tier": "NMS_TIER_1"})
        if result.is_valid:
            print(f"Ready! Estimated {result.total_estimated_seconds:.0f}s")
        else:
            for issue in result.validation_issues:
                print(f"ISSUE: {issue}")
    """
    effective_params = {**workflow.defaults, **(params or {})}
    mode = workflow.execution_policy.mode.value
    issues: list[str] = []
    plan: list[DryRunStep] = []

    # Workflow-level validation
    if not workflow.steps:
        issues.append("Workflow has no steps")

    # Check for duplicate step names
    names = [s.name for s in workflow.steps]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        issues.append(f"Duplicate step names: {', '.join(sorted(dupes))}")

    # Validate dependencies reference real steps
    all_names = set(names)
    for step in workflow.steps:
        for dep in step.depends_on:
            if dep not in all_names:
                issues.append(
                    f"Step '{step.name}' depends on unknown step '{dep}'"
                )

    # Build the execution plan
    for idx, step in enumerate(workflow.steps, 1):
        step_issues = _validate_step(step, effective_params)
        issues.extend(step_issues)

        notes = _collect_notes(step, effective_params)
        estimated = _estimate_step(step, effective_params)

        plan.append(DryRunStep(
            step_name=step.name,
            step_type=step.step_type.value,
            order=idx,
            estimated_seconds=estimated,
            will_execute=len(step_issues) == 0,
            dependencies=step.depends_on,
            notes=tuple(notes),
        ))

    logger.info(
        "dry_run.complete  workflow=%s  steps=%d  issues=%d  estimated=%.1fs",
        workflow.name,
        len(plan),
        len(issues),
        sum(s.estimated_seconds for s in plan),
    )

    return DryRunResult(
        workflow_name=workflow.name,
        execution_plan=plan,
        validation_issues=issues,
        params_provided=effective_params,
        execution_mode=mode,
    )
