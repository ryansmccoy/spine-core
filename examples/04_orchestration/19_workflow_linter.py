#!/usr/bin/env python3
"""Workflow Linter — static analysis for workflow definitions.

Demonstrates the ``lint_workflow()`` function for detecting common
mistakes, anti-patterns, and questionable constructs in workflow
definitions *before* execution.  Catches issues like empty workflows,
missing handlers, unreachable steps, and naming problems.

Demonstrates:
    1. ``lint_workflow()`` — run all rules against a Workflow
    2. ``LintResult``     — inspect diagnostics, filter by severity
    3. ``Severity``       — ERROR / WARNING / INFO classification
    4. Custom lint rules  — register your own checks
    5. ``list_lint_rules()`` — see all available rules
    6. Clean workflow     — verify no false positives
    7. Pipeline naming    — INFO-level naming conventions

Architecture::

    lint_workflow(workflow)
    ├── Built-in rules (9 checks)
    │   ├── E001 — empty workflow (no steps)
    │   ├── E002 — missing failure handler
    │   ├── E003 — choice missing condition
    │   ├── E004 — missing pipeline_name
    │   ├── W001 — choice without else_step
    │   ├── W002 — unreachable steps
    │   ├── W003 — deep chains (>20 steps)
    │   ├── W004 — similar step names
    │   └── I001 — pipeline naming convention
    ├── Custom rules (register_lint_rule)
    └── Returns LintResult
        ├── .passed          — bool
        ├── .errors          — list[LintDiagnostic]
        ├── .warnings        — list[LintDiagnostic]
        ├── .infos           — list[LintDiagnostic]
        └── .summary()       — human-readable text

Key Concepts:
    - **Static analysis**: Linting runs without executing anything.
    - **Severity tiers**: ERRORs break CI, WARNINGs flag review items,
      INFOs are suggestions.
    - **Custom rules**: Register domain-specific checks via
      ``register_lint_rule()``.

See Also:
    - ``01_workflow_basics.py``     — workflow construction
    - ``20_step_recorder.py``       — runtime recording
    - ``21_workflow_visualizer.py``  — visual output formats
    - :mod:`spine.orchestration.linter`

Run:
    python examples/04_orchestration/19_workflow_linter.py

Expected Output:
    Lint results showing errors, warnings, and info-level diagnostics
    for various problematic workflow definitions, plus a clean pass
    for a well-formed workflow.
"""

from spine.orchestration.step_types import Step
from spine.orchestration.workflow import Workflow
from spine.orchestration.linter import (
    LintDiagnostic,
    LintResult,
    Severity,
    lint_workflow,
    register_lint_rule,
    list_lint_rules,
    clear_custom_rules,
)


def _always_true(ctx):
    return True


def main() -> None:
    # ------------------------------------------------------------------
    # 1. Lint an empty workflow (E001 — error)
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("1. Lint an empty workflow")
    print(f"{'='*60}")

    empty = Workflow(name="empty_pipeline", steps=[])
    result = lint_workflow(empty)

    print(f"   Workflow: {empty.name}")
    print(f"   Passed:   {result.passed}")
    print(f"   Errors:   {len(result.errors)}")
    for d in result.errors:
        print(f"     [{d.code}] {d.message}")

    # ------------------------------------------------------------------
    # 2. Workflow with missing pipeline_name (E004)
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("2. Missing pipeline_name on pipeline step")
    print(f"{'='*60}")

    steps_no_name = [
        Step.pipeline("ingest", ""),
        Step.pipeline("transform", "etl-core"),
    ]
    wf_no_name = Workflow(name="etl", steps=steps_no_name)
    result = lint_workflow(wf_no_name)

    print(f"   Passed:  {result.passed}")
    for d in result.diagnostics:
        print(f"     [{d.severity.value}] {d.code}: {d.message}")

    # ------------------------------------------------------------------
    # 3. Choice step without else_step (W001)
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("3. Choice step without else_step")
    print(f"{'='*60}")

    steps_choice = [
        Step.choice(
            "routing",
            condition=_always_true,
            then_step="a",
            else_step=None,
        ),
        Step.pipeline("a", "branch-a"),
    ]
    wf_choice = Workflow(name="choice_demo", steps=steps_choice)
    result = lint_workflow(wf_choice)

    print(f"   Errors:   {len(result.errors)}")
    print(f"   Warnings: {len(result.warnings)}")
    for d in result.diagnostics:
        print(f"     [{d.code}] {d.message}")

    # ------------------------------------------------------------------
    # 4. Custom lint rule — domain-specific check
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("4. Custom lint rule")
    print(f"{'='*60}")

    clear_custom_rules()

    def check_naming_prefix(workflow: Workflow) -> list[LintDiagnostic]:
        """Require all step names to start with an alphabetic char."""
        diags = []
        for step in workflow.steps:
            if step.name and step.name[0].isdigit():
                diags.append(LintDiagnostic(
                    code="C001",
                    severity=Severity.WARNING,
                    message=f"Step '{step.name}' starts with a digit",
                    step_name=step.name,
                    suggestion="Prefix step names with letters",
                ))
        return diags

    register_lint_rule("check_naming_prefix", check_naming_prefix)

    steps_custom = [
        Step.pipeline("1_load", "loader"),
        Step.pipeline("transform", "xform"),
    ]
    wf_custom = Workflow(name="custom_check", steps=steps_custom)
    result = lint_workflow(wf_custom)

    print(f"   Custom warnings: {len(result.warnings)}")
    for d in result.warnings:
        print(f"     [{d.code}] {d.message}")

    clear_custom_rules()

    # ------------------------------------------------------------------
    # 5. List all available rules
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("5. Available lint rules")
    print(f"{'='*60}")

    rules = list_lint_rules()
    for name in rules:
        print(f"   • {name}")

    # ------------------------------------------------------------------
    # 6. Clean workflow — no diagnostics
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("6. Clean workflow (no issues)")
    print(f"{'='*60}")

    clean_steps = [
        Step.pipeline("extract", "etl-extract"),
        Step.pipeline("transform", "etl-transform"),
        Step.pipeline("load", "etl-load"),
    ]
    wf_clean = Workflow(name="etl_pipeline", steps=clean_steps)
    result = lint_workflow(wf_clean)

    print(f"   Passed: {result.passed}")
    print(f"   Summary:\n{result.summary()}")

    # ------------------------------------------------------------------
    # 7. LintResult summary for a complex case
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("7. Summary report")
    print(f"{'='*60}")

    messy_steps = [
        Step.pipeline("step_a", "a"),
        Step.pipeline("step_b", ""),  # Empty pipeline_name
        Step.choice("decide", condition=_always_true, then_step="step_a"),
    ]
    wf_messy = Workflow(name="messy", steps=messy_steps)
    result = lint_workflow(wf_messy)

    print(result.summary())

    print(f"\n{'='*60}")
    print("Done — workflow linter example complete")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
