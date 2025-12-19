"""Workflow Linter — static analysis for workflows before execution.

Catches structural issues, style violations, and potential bugs in
workflow definitions *before* they run.  Extensible via a rule registry
so teams can add domain-specific checks.

Architecture::

    lint_workflow(workflow)
    │
    ├── _check_empty_workflow
    ├── _check_missing_handlers
    ├── _check_choice_completeness
    ├── _check_unreachable_steps
    ├── _check_deep_chains
    ├── _check_pipeline_naming
    ├── _check_similar_names
    └── (custom rules via register_lint_rule)
    │
    ▼
    LintResult
    ├── diagnostics: list[LintDiagnostic]
    ├── passed → bool (no errors)
    ├── errors / warnings / infos
    └── summary() → str

Example::

    from spine.orchestration.linter import lint_workflow
    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="my.pipeline",
        steps=[
            Step.pipeline("ingest", "my.ingest"),
            Step.lambda_("validate", None),  # missing handler!
        ],
    )

    result = lint_workflow(workflow)
    if not result.passed:
        for d in result.errors:
            print(f"[{d.code}] {d.message}")

See Also:
    spine.orchestration.playground — interactive step-by-step execution
    spine.orchestration.templates — pre-built workflow patterns
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
from typing import Any

from spine.orchestration.step_types import Step, StepType
from spine.orchestration.workflow import Workflow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Diagnostic model
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Severity level for a lint diagnostic."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class LintDiagnostic:
    """A single lint finding.

    Attributes:
        code: Short identifier (e.g. ``"E001"``).
        severity: ``error``, ``warning``, or ``info``.
        message: Human-readable description.
        step_name: Name of the offending step (if applicable).
        suggestion: Recommended fix (optional).
    """

    code: str
    severity: Severity
    message: str
    step_name: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        prefix = f"[{self.code}] {self.severity.value.upper()}"
        location = f" in step '{self.step_name}'" if self.step_name else ""
        hint = f" — {self.suggestion}" if self.suggestion else ""
        return f"{prefix}{location}: {self.message}{hint}"


@dataclass
class LintResult:
    """Aggregated result of linting a workflow.

    Attributes:
        workflow_name: Name of the linted workflow.
        diagnostics: All findings from all rules.
    """

    workflow_name: str
    diagnostics: list[LintDiagnostic] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True if there are no error-level diagnostics."""
        return not any(d.severity == Severity.ERROR for d in self.diagnostics)

    @property
    def errors(self) -> list[LintDiagnostic]:
        """Error-level diagnostics only."""
        return [d for d in self.diagnostics if d.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[LintDiagnostic]:
        """Warning-level diagnostics only."""
        return [d for d in self.diagnostics if d.severity == Severity.WARNING]

    @property
    def infos(self) -> list[LintDiagnostic]:
        """Info-level diagnostics only."""
        return [d for d in self.diagnostics if d.severity == Severity.INFO]

    def summary(self) -> str:
        """One-line summary of the lint result."""
        counts = {
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "infos": len(self.infos),
        }
        status = "PASS" if self.passed else "FAIL"
        parts = [f"{status}: {self.workflow_name}"]
        for label, count in counts.items():
            if count:
                parts.append(f"{count} {label}")
        return " | ".join(parts)

    def __str__(self) -> str:
        lines = [self.summary()]
        for d in self.diagnostics:
            lines.append(f"  {d}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

# Type alias for lint rules: takes a Workflow, returns diagnostics
LintRule = Callable[[Workflow], list[LintDiagnostic]]

_RULES: list[tuple[str, LintRule]] = []


def register_lint_rule(name: str, rule: LintRule) -> None:
    """Register a custom lint rule.

    Parameters
    ----------
    name
        Human-readable rule name (e.g. ``"check_naming"``).
    rule
        Callable that takes a ``Workflow`` and returns a list of
        ``LintDiagnostic`` objects.
    """
    _RULES.append((name, rule))
    logger.debug("registered lint rule: %s", name)


def list_lint_rules() -> list[str]:
    """Return names of all registered lint rules (built-in + custom)."""
    return [name for name, _ in _BUILT_IN_RULES] + [name for name, _ in _RULES]


def clear_custom_rules() -> None:
    """Remove all custom lint rules (built-in rules are preserved)."""
    _RULES.clear()


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------

def _check_empty_workflow(workflow: Workflow) -> list[LintDiagnostic]:
    """E001: Workflow has no steps."""
    if not workflow.steps:
        return [
            LintDiagnostic(
                code="E001",
                severity=Severity.ERROR,
                message="Workflow has no steps.",
                suggestion="Add at least one step to the workflow.",
            )
        ]
    return []


def _check_missing_handlers(workflow: Workflow) -> list[LintDiagnostic]:
    """E002: Lambda step has no handler function."""
    diagnostics: list[LintDiagnostic] = []
    for step in workflow.steps:
        if step.step_type == StepType.LAMBDA and step.handler is None:
            diagnostics.append(
                LintDiagnostic(
                    code="E002",
                    severity=Severity.ERROR,
                    message="Lambda step has no handler function.",
                    step_name=step.name,
                    suggestion="Provide a handler via Step.lambda_(name, handler_fn).",
                )
            )
    return diagnostics


def _check_choice_completeness(workflow: Workflow) -> list[LintDiagnostic]:
    """W001: Choice step is missing an else_step (fallback branch)."""
    diagnostics: list[LintDiagnostic] = []
    for step in workflow.steps:
        if step.step_type == StepType.CHOICE:
            if not step.else_step:
                diagnostics.append(
                    LintDiagnostic(
                        code="W001",
                        severity=Severity.WARNING,
                        message="Choice step has no else_step (fallback branch).",
                        step_name=step.name,
                        suggestion="Add an else_step for the false-condition path.",
                    )
                )
            if step.condition is None:
                diagnostics.append(
                    LintDiagnostic(
                        code="E003",
                        severity=Severity.ERROR,
                        message="Choice step has no condition function.",
                        step_name=step.name,
                        suggestion="Provide a condition via Step.choice(name, condition=fn, ...).",
                    )
                )
    return diagnostics


def _check_unreachable_steps(workflow: Workflow) -> list[LintDiagnostic]:
    """W002: Steps that can never be reached.

    A step is unreachable if:
    - It's a choice target (then_step or else_step) but not depended on
      by any other path, AND
    - It has depends_on pointing to a step that doesn't exist.

    For simple sequential workflows (no deps) all steps are reachable
    by definition.
    """
    if not workflow.has_dependencies():
        return []

    diagnostics: list[LintDiagnostic] = []
    step_names = {s.name for s in workflow.steps}

    # Build the set of steps reachable from the dependency graph
    # Steps with no depends_on are roots (always reachable)
    depended_on: set[str] = set()
    for step in workflow.steps:
        for dep in step.depends_on:
            depended_on.add(dep)

    # Also consider choice targets as reachable
    choice_targets: set[str] = set()
    for step in workflow.steps:
        if step.step_type == StepType.CHOICE:
            if step.then_step:
                choice_targets.add(step.then_step)
            if step.else_step:
                choice_targets.add(step.else_step)

    roots = {s.name for s in workflow.steps if not s.depends_on}

    # BFS from roots
    reachable: set[str] = set()
    queue = list(roots | choice_targets)
    reachable.update(queue)

    adjacency = workflow.dependency_graph()
    while queue:
        node = queue.pop(0)
        for neighbor in adjacency.get(node, []):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)

    for step in workflow.steps:
        if step.name not in reachable:
            diagnostics.append(
                LintDiagnostic(
                    code="W002",
                    severity=Severity.WARNING,
                    message="Step appears unreachable in the dependency graph.",
                    step_name=step.name,
                    suggestion="Check depends_on edges or remove the step.",
                )
            )

    return diagnostics


def _check_deep_chains(workflow: Workflow, max_depth: int = 20) -> list[LintDiagnostic]:
    """W003: Sequential chain exceeds recommended depth."""
    if len(workflow.steps) > max_depth:
        return [
            LintDiagnostic(
                code="W003",
                severity=Severity.WARNING,
                message=f"Workflow has {len(workflow.steps)} steps (threshold: {max_depth}).",
                suggestion="Consider splitting into sub-workflows or using fan-out patterns.",
            )
        ]
    return []


def _check_pipeline_naming(workflow: Workflow) -> list[LintDiagnostic]:
    """I001: Pipeline name doesn't follow domain.action convention."""
    diagnostics: list[LintDiagnostic] = []
    for step in workflow.steps:
        if step.step_type == StepType.PIPELINE and step.pipeline_name:
            if "." not in step.pipeline_name:
                diagnostics.append(
                    LintDiagnostic(
                        code="I001",
                        severity=Severity.INFO,
                        message=f"Pipeline name '{step.pipeline_name}' does not use dotted convention.",
                        step_name=step.name,
                        suggestion="Use 'domain.action' format (e.g. 'finra.ingest_daily').",
                    )
                )
    return diagnostics


def _check_similar_names(workflow: Workflow, threshold: float = 0.85) -> list[LintDiagnostic]:
    """W004: Step names are suspiciously similar (possible typo)."""
    diagnostics: list[LintDiagnostic] = []
    names = [s.name for s in workflow.steps]
    seen_pairs: set[tuple[str, str]] = set()

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a == b:
                continue  # Duplicates caught by Workflow.__post_init__
            pair = tuple(sorted((a, b)))
            if pair in seen_pairs:
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio >= threshold:
                seen_pairs.add(pair)
                diagnostics.append(
                    LintDiagnostic(
                        code="W004",
                        severity=Severity.WARNING,
                        message=f"Step names '{a}' and '{b}' are very similar (similarity: {ratio:.0%}).",
                        suggestion="Verify these are intentionally different steps.",
                    )
                )

    return diagnostics


def _check_missing_pipeline_name(workflow: Workflow) -> list[LintDiagnostic]:
    """E004: Pipeline step has no pipeline_name."""
    diagnostics: list[LintDiagnostic] = []
    for step in workflow.steps:
        if step.step_type == StepType.PIPELINE and not step.pipeline_name:
            diagnostics.append(
                LintDiagnostic(
                    code="E004",
                    severity=Severity.ERROR,
                    message="Pipeline step has no pipeline_name.",
                    step_name=step.name,
                    suggestion="Provide a pipeline name via Step.pipeline(name, pipeline_name).",
                )
            )
    return diagnostics


def _check_single_step_workflow(workflow: Workflow) -> list[LintDiagnostic]:
    """I002: Workflow has only one step — may not need orchestration."""
    if len(workflow.steps) == 1:
        return [
            LintDiagnostic(
                code="I002",
                severity=Severity.INFO,
                message="Workflow has only one step.",
                suggestion="Consider running the pipeline directly if orchestration isn't needed.",
            )
        ]
    return []


# Ordered list of built-in rules
_BUILT_IN_RULES: list[tuple[str, LintRule]] = [
    ("check_empty_workflow", _check_empty_workflow),
    ("check_missing_handlers", _check_missing_handlers),
    ("check_choice_completeness", _check_choice_completeness),
    ("check_unreachable_steps", _check_unreachable_steps),
    ("check_deep_chains", _check_deep_chains),
    ("check_pipeline_naming", _check_pipeline_naming),
    ("check_similar_names", _check_similar_names),
    ("check_missing_pipeline_name", _check_missing_pipeline_name),
    ("check_single_step_workflow", _check_single_step_workflow),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lint_workflow(workflow: Workflow,
                  *, include_infos: bool = True,
                  extra_rules: list[LintRule] | None = None) -> LintResult:
    """Run all lint rules against a workflow.

    Parameters
    ----------
    workflow
        The workflow to lint.
    include_infos
        If ``False``, info-level diagnostics are suppressed.
    extra_rules
        One-shot rules to run in addition to built-in and registered rules.

    Returns
    -------
    LintResult
        Aggregated diagnostics from all rules.
    """
    result = LintResult(workflow_name=workflow.name)
    all_rules = list(_BUILT_IN_RULES) + list(_RULES)

    if extra_rules:
        for i, rule in enumerate(extra_rules):
            all_rules.append((f"extra_rule_{i}", rule))

    for rule_name, rule in all_rules:
        try:
            diagnostics = rule(workflow)
            result.diagnostics.extend(diagnostics)
        except Exception:
            logger.warning("lint rule %s raised an exception", rule_name, exc_info=True)
            result.diagnostics.append(
                LintDiagnostic(
                    code="X001",
                    severity=Severity.WARNING,
                    message=f"Lint rule '{rule_name}' raised an exception.",
                )
            )

    if not include_infos:
        result.diagnostics = [d for d in result.diagnostics if d.severity != Severity.INFO]

    logger.debug("linted %s: %s", workflow.name, result.summary())
    return result
