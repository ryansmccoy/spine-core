#!/usr/bin/env python3
"""Dry-Run Mode — preview workflow execution without running.

Demonstrates the ``dry_run()`` function for analysing a workflow's
execution plan, estimating costs, and validating structure before
committing to a real execution.

Demonstrates:
    1. ``dry_run()``              — basic analysis
    2. ``DryRunResult``           — inspect plan and issues
    3. ``register_cost_estimate`` — custom pipeline timing
    4. ``register_estimator``     — dynamic cost estimation
    5. Validation issue detection
    6. ``summary()``              — human-readable output

Architecture::

    dry_run(workflow, params)
    │
    ├── Validate all steps
    ├── Resolve execution order
    ├── Estimate per-step cost
    ├── Check parameters
    │
    ▼
    DryRunResult
    ├── execution_plan[]  — ordered step previews
    ├── is_valid          — no issues?
    ├── total_estimated_seconds
    └── summary()

Key Concepts:
    - Dry-run is *structural* analysis — no handlers execute.
    - Register cost estimates for pipelines to get accurate timing.
    - Combine with ``lint_workflow()`` for comprehensive pre-flight.

See Also:
    - ``19_workflow_linter.py``         — static analysis
    - ``22_composition_operators.py``   — build workflows to dry-run
    - :mod:`spine.orchestration.dry_run`

Run:
    python examples/04_orchestration/23_dry_run.py

Expected Output:
    Dry-run summaries showing execution plans, cost estimates, and
    validation issues for various workflow configurations.
"""

from spine.orchestration.dry_run import (
    clear_cost_registry,
    dry_run,
    register_cost_estimate,
    register_estimator,
)
from spine.orchestration.step_result import StepResult
from spine.orchestration.step_types import Step
from spine.orchestration.workflow import (
    ExecutionMode,
    Workflow,
    WorkflowExecutionPolicy,
)


def _handler(ctx, config):
    return StepResult.ok(output={"done": True})


def main() -> None:
    clear_cost_registry()

    # ------------------------------------------------------------------
    # 1. Basic dry-run — valid workflow
    # ------------------------------------------------------------------
    print("=" * 60)
    print("1. Basic Dry-Run — Valid Workflow")
    print("=" * 60)

    wf = Workflow(
        name="finra.daily_etl",
        steps=[
            Step.pipeline("extract", "finra.fetch_data"),
            Step.lambda_("validate", _handler),
            Step.pipeline("load", "finra.store_data"),
        ],
    )
    result = dry_run(wf, params={"tier": "NMS_TIER_1"})
    print(result.summary())
    print()

    # ------------------------------------------------------------------
    # 2. Custom cost estimates
    # ------------------------------------------------------------------
    print("=" * 60)
    print("2. Custom Cost Estimates")
    print("=" * 60)

    register_cost_estimate("finra.fetch_data", 45.0)
    register_cost_estimate("finra.store_data", 12.0)

    result = dry_run(wf, params={"tier": "NMS_TIER_1"})
    print(result.summary())
    print()

    # ------------------------------------------------------------------
    # 3. Dynamic estimator
    # ------------------------------------------------------------------
    print("=" * 60)
    print("3. Dynamic Estimator (based on params)")
    print("=" * 60)

    def size_based_estimator(step, params):
        return params.get("batch_size", 100) * 0.1

    register_estimator("process", size_based_estimator)

    wf2 = Workflow(
        name="batch.processor",
        steps=[
            Step.lambda_("process", _handler),
        ],
    )
    small = dry_run(wf2, params={"batch_size": 10})
    large = dry_run(wf2, params={"batch_size": 1000})
    print(f"  Small batch (10):   {small.total_estimated_seconds:.1f}s")
    print(f"  Large batch (1000): {large.total_estimated_seconds:.1f}s")
    print()

    # ------------------------------------------------------------------
    # 4. Invalid workflow detection
    # ------------------------------------------------------------------
    print("=" * 60)
    print("4. Invalid Workflow Detection")
    print("=" * 60)

    bad_wf = Workflow(
        name="test.invalid",
        steps=[
            Step.lambda_("broken", None),  # Missing handler
            Step.pipeline("no_pipe", ""),   # Empty pipeline name
        ],
    )
    result = dry_run(bad_wf)
    print(result.summary())
    print(f"  Is valid: {result.is_valid}")
    print()

    # ------------------------------------------------------------------
    # 5. Parallel workflow estimation
    # ------------------------------------------------------------------
    print("=" * 60)
    print("5. Parallel Workflow (Critical Path)")
    print("=" * 60)

    par_wf = Workflow(
        name="parallel.ingest",
        steps=[
            Step.pipeline("source_a", "ingest.a"),
            Step.pipeline("source_b", "ingest.b"),
            Step.pipeline("merge", "data.merge", depends_on=["source_a", "source_b"]),
        ],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL,
        ),
    )
    result = dry_run(par_wf)
    print(result.summary())
    print(f"  Parallel estimate: {result.total_estimated_seconds:.1f}s")
    print()

    # ------------------------------------------------------------------
    # 6. Wait step duration
    # ------------------------------------------------------------------
    print("=" * 60)
    print("6. Wait Step Duration")
    print("=" * 60)

    wait_wf = Workflow(
        name="scheduled.batch",
        steps=[
            Step.wait("delay", 300),
            Step.pipeline("process", "batch.process"),
        ],
    )
    result = dry_run(wait_wf)
    for s in result.execution_plan:
        print(f"  {s.step_name}: {s.estimated_seconds:.0f}s ({s.step_type})")
    print(f"  Total: {result.total_estimated_seconds:.0f}s")
    print()

    clear_cost_registry()
    print("All dry-run examples completed successfully!")


if __name__ == "__main__":
    main()
