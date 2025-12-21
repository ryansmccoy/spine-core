#!/usr/bin/env python3
"""Composition Operators — functional workflow builders.

Demonstrates the composition operators for building workflows
from reusable building blocks: ``chain()``, ``parallel()``,
``conditional()``, ``retry()``, and ``merge_workflows()``.

Demonstrates:
    1. ``chain()``           — sequential composition
    2. ``parallel()``        — concurrent DAG composition
    3. ``conditional()``     — if/else branching
    4. ``retry()``           — retry wrapper
    5. ``merge_workflows()`` — combine multiple workflows

Architecture::

    Composition Operators
    ├── chain(name, *steps)              → sequential workflow
    ├── parallel(name, *steps, merge)    → DAG with shared root
    ├── conditional(name, cond, then, else) → choice branching
    ├── retry(name, step, max_attempts)  → retry semantics
    └── merge_workflows(name, *wfs)      → combine workflows

Key Concepts:
    - All operators return a ``Workflow`` instance.
    - Operators can be nested for complex topologies.
    - ``merge_workflows`` auto-prefixes on name collision.

See Also:
    - ``13_workflow_templates.py``     — domain template patterns
    - ``23_dry_run.py``                — preview composed workflows
    - :mod:`spine.orchestration.composition`

Run:
    python examples/04_orchestration/22_composition_operators.py

Expected Output:
    Demonstrations of chain, parallel, conditional, retry, and
    merge composition patterns with step details.
"""

from spine.orchestration.composition import (
    chain,
    conditional,
    merge_workflows,
    parallel,
    retry,
)
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step
from spine.orchestration.workflow import FailurePolicy


def _handler(ctx, config):
    return StepResult.ok(output={"done": True})


def _always_true(ctx):
    return True


def main() -> None:
    # ------------------------------------------------------------------
    # 1. chain() — sequential composition
    # ------------------------------------------------------------------
    print("=" * 60)
    print("1. chain() — Sequential Composition")
    print("=" * 60)

    etl = chain(
        "my.etl",
        Step.operation("extract", "data.extract"),
        Step.lambda_("validate", _handler),
        Step.operation("load", "data.load"),
        domain="data.processing",
    )
    print(f"  Workflow: {etl.name}")
    print(f"  Steps:    {[s.name for s in etl.steps]}")
    print(f"  Mode:     {etl.execution_policy.mode.value}")
    print(f"  Domain:   {etl.domain}")
    print()

    # ------------------------------------------------------------------
    # 2. parallel() — concurrent composition
    # ------------------------------------------------------------------
    print("=" * 60)
    print("2. parallel() — Concurrent Composition")
    print("=" * 60)

    multi_source = parallel(
        "multi.ingest",
        Step.operation("source_a", "ingest.source_a"),
        Step.operation("source_b", "ingest.source_b"),
        Step.operation("source_c", "ingest.source_c"),
        max_concurrency=4,
        on_failure=FailurePolicy.CONTINUE,
    )
    print(f"  Workflow:       {multi_source.name}")
    print(f"  Steps:          {[s.name for s in multi_source.steps]}")
    print(f"  Mode:           {multi_source.execution_policy.mode.value}")
    print(f"  Max concurrency: {multi_source.execution_policy.max_concurrency}")
    print()

    # ------------------------------------------------------------------
    # 3. parallel() with merge function
    # ------------------------------------------------------------------
    print("=" * 60)
    print("3. parallel() with merge_fn")
    print("=" * 60)

    def combine_results(ctx, config):
        return StepResult.ok(output={"combined": True})

    merged_parallel = parallel(
        "parallel.with_merge",
        Step.operation("a", "pipe.a"),
        Step.operation("b", "pipe.b"),
        merge_fn=combine_results,
    )
    print(f"  Steps: {[s.name for s in merged_parallel.steps]}")
    merge_step = merged_parallel.steps[-1]
    print(f"  Merge step: {merge_step.name} depends_on={merge_step.depends_on}")
    print()

    # ------------------------------------------------------------------
    # 4. conditional() — if/else branching
    # ------------------------------------------------------------------
    print("=" * 60)
    print("4. conditional() — If/Else Branching")
    print("=" * 60)

    quality_check = conditional(
        "quality.check",
        condition=_always_true,
        then_steps=[
            Step.operation("publish", "data.publish"),
            Step.lambda_("notify_success", _handler),
        ],
        else_steps=[
            Step.operation("quarantine", "data.quarantine"),
            Step.lambda_("alert", _handler),
        ],
    )
    print(f"  Workflow: {quality_check.name}")
    print(f"  Steps:    {[s.name for s in quality_check.steps]}")
    choice = quality_check.steps[0]
    print(f"  Choice:   then={choice.then_step}, else={choice.else_step}")
    print()

    # ------------------------------------------------------------------
    # 5. retry() — retry wrapper
    # ------------------------------------------------------------------
    print("=" * 60)
    print("5. retry() — Retry Wrapper")
    print("=" * 60)

    resilient = retry(
        "resilient.fetch",
        Step.operation("fetch", "data.fetch"),
        max_attempts=3,
    )
    print(f"  Workflow: {resilient.name}")
    print(f"  Steps:    {[s.name for s in resilient.steps]}")
    for s in resilient.steps:
        print(f"    {s.name}: error_policy={s.on_error.value}, attempt={s.config.get('__attempt__')}")
    print()

    # ------------------------------------------------------------------
    # 6. merge_workflows() — combine workflows
    # ------------------------------------------------------------------
    print("=" * 60)
    print("6. merge_workflows() — Combine Workflows")
    print("=" * 60)

    ingest_wf = chain("ingest", Step.lambda_("fetch", _handler))
    transform_wf = chain("transform", Step.lambda_("clean", _handler))
    load_wf = chain("load", Step.lambda_("store", _handler))

    full_operation = merge_workflows(
        "full.operation",
        ingest_wf,
        transform_wf,
        load_wf,
    )
    print(f"  Workflow: {full_operation.name}")
    print(f"  Steps:    {[s.name for s in full_operation.steps]}")
    print(f"  From:     {ingest_wf.name} + {transform_wf.name} + {load_wf.name}")
    print()

    print("All composition examples completed successfully!")


if __name__ == "__main__":
    main()
