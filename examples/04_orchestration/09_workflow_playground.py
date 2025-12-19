#!/usr/bin/env python3
"""Workflow Playground — interactive step-by-step execution and debugging.

Demonstrates the ``WorkflowPlayground`` for interactively stepping through
workflows, inspecting context between steps, modifying parameters, and
rewinding/replaying execution.  Ideal for notebooks, debugging, and
workflow design.

Demonstrates:
    1. ``load()`` — prepare a workflow for interactive execution
    2. ``step()`` — execute the next step, get a ``StepSnapshot``
    3. ``peek()`` — inspect the next step without running it
    4. ``step_back()`` — rewind to before the last step
    5. ``set_param()`` — modify context params mid-execution
    6. ``run_to()`` — execute up to a named step
    7. ``run_all()`` — execute all remaining steps
    8. ``summary()`` — get execution state as a dict
    9. ``reset()`` — restart from the beginning

Architecture::

    WorkflowPlayground
    ├── load(workflow, params)   → set up step queue
    ├── step()                   → StepSnapshot
    │   ├── context_before       (state before step)
    │   ├── context_after        (state after step)
    │   ├── result               (StepResult)
    │   └── duration_ms
    ├── step_back()              → undo last step
    ├── peek()                   → next Step (read-only)
    ├── run_to("name")           → list[StepSnapshot]
    ├── run_all()                → list[StepSnapshot]
    ├── set_param(k, v)          → mutate context
    └── summary()                → dict overview

Key Concepts:
    - **StepSnapshot**: Immutable record of a step execution with
      before/after context, result, timing, and error info.
    - **Context snapshots**: Each step stores a full context snapshot,
      enabling ``step_back()`` to precisely restore state.
    - **Dry-run mode**: When no ``Runnable`` is provided, pipeline
      steps return stub results — perfect for design-time exploration.

See Also:
    - ``01_workflow_basics.py``    — workflow basics
    - ``03_workflow_context.py``   — context data passing
    - :mod:`spine.orchestration.playground`

Run:
    python examples/04_orchestration/09_workflow_playground.py

Expected Output:
    Six sections: loading, stepping, peeking, rewinding, parameter
    modification, and summary display.
"""

from __future__ import annotations

from spine.orchestration import Workflow, Step, StepResult
from spine.orchestration.playground import WorkflowPlayground, StepSnapshot


# =============================================================================
# Example handler functions
# =============================================================================

def validate_data(ctx, config) -> StepResult:
    """Validate incoming data — returns success with validation stats."""
    records = ctx.params.get("record_count", 100)
    valid = int(records * 0.95)
    return StepResult.ok(output={
        "total_records": records,
        "valid_records": valid,
        "invalid_records": records - valid,
        "validation_rate": round(valid / records, 4),
    })


def enrich_data(ctx, config) -> StepResult:
    """Enrich data with additional metadata."""
    # Access outputs from previous steps
    validation = ctx.outputs.get("validate", {})
    valid_count = validation.get("valid_records", 0)
    return StepResult.ok(output={
        "enriched_count": valid_count,
        "enrichment_source": config.get("source", "default"),
    })


def generate_report(ctx, config) -> StepResult:
    """Generate a summary report from all accumulated outputs."""
    return StepResult.ok(output={
        "report_type": "daily_summary",
        "steps_completed": len(ctx.outputs),
        "params_used": dict(ctx.params),
    })


def main() -> None:
    """Run all WorkflowPlayground demonstrations."""

    # ─────────────────────────────────────────────────────────────────
    print("=" * 72)
    print("SECTION 1: Loading a Workflow")
    print("=" * 72)

    # Build a workflow with mixed step types
    workflow = Workflow(
        name="debug.etl",
        steps=[
            Step.pipeline("fetch", "data.fetch_source"),
            Step.lambda_("validate", validate_data),
            Step.lambda_("enrich", enrich_data, config={"source": "sec_api"}),
            Step.lambda_("report", generate_report),
        ],
        domain="data",
        description="4-step ETL for interactive debugging",
    )

    # Create playground in dry-run mode (no real pipeline executor)
    pg = WorkflowPlayground()
    pg.load(workflow, params={"date": "2026-01-15", "record_count": 500})

    print(f"\nWorkflow:        {pg.workflow.name}")
    print(f"Total steps:     {len(workflow.steps)}")
    print(f"Current index:   {pg.current_step_index}")
    print(f"Is complete:     {pg.is_complete}")
    print(f"Remaining steps: {[s.name for s in pg.remaining_steps]}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 2: Peeking Without Executing")
    print("=" * 72)

    next_step = pg.peek()
    print(f"\nNext step:  {next_step.name}")
    print(f"Step type:  {next_step.step_type.value}")
    print(f"Pipeline:   {next_step.pipeline_name}")
    print(f"Still at index: {pg.current_step_index}")  # hasn't moved

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 3: Stepping Through One at a Time")
    print("=" * 72)

    # Step 1: fetch (pipeline, dry-run mode → stub result)
    snap1 = pg.step()
    print(f"\n--- Step 1: {snap1.step_name} ---")
    print(f"  Type:     {snap1.step_type.value}")
    print(f"  Status:   {snap1.status}")
    print(f"  Duration: {snap1.duration_ms:.1f}ms")
    print(f"  Result:   {snap1.result.output if snap1.result else None}")

    # Step 2: validate (lambda, actually runs)
    snap2 = pg.step()
    print(f"\n--- Step 2: {snap2.step_name} ---")
    print(f"  Type:     {snap2.step_type.value}")
    print(f"  Status:   {snap2.status}")
    print(f"  Result:   {snap2.result.output if snap2.result else None}")

    # Check context between steps
    print(f"\n  Context outputs so far:")
    for step_name, output in pg.context.outputs.items():
        print(f"    {step_name}: {output}")

    print(f"\n  Current index: {pg.current_step_index}")
    print(f"  History count: {len(pg.history)}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 4: Stepping Back (Undo)")
    print("=" * 72)

    print(f"\nBefore step_back:")
    print(f"  Index:    {pg.current_step_index}")
    print(f"  History:  {len(pg.history)} snapshots")
    print(f"  Outputs:  {list(pg.context.outputs.keys())}")

    undone = pg.step_back()
    print(f"\nUndone step: {undone.step_name}")
    print(f"After step_back:")
    print(f"  Index:    {pg.current_step_index}")
    print(f"  History:  {len(pg.history)} snapshots")
    print(f"  Outputs:  {list(pg.context.outputs.keys())}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 5: Modify Parameters and Re-Execute")
    print("=" * 72)

    # Change record_count before re-running validate
    original = pg.context.params.get("record_count")
    pg.set_param("record_count", 1000)
    print(f"\nChanged record_count: {original} → {pg.context.params['record_count']}")

    # Re-execute validate with new params
    snap2_retry = pg.step()
    print(f"\nRe-executed: {snap2_retry.step_name}")
    print(f"  New result: {snap2_retry.result.output if snap2_retry.result else None}")
    print(f"  (Notice valid_records changed with new record_count)")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 6: Run Remaining Steps")
    print("=" * 72)

    remaining = pg.remaining_steps
    print(f"\nRemaining: {[s.name for s in remaining]}")

    snapshots = pg.run_all()
    print(f"Executed {len(snapshots)} remaining steps:")
    for snap in snapshots:
        print(f"  {snap.step_name}: {snap.status} ({snap.duration_ms:.1f}ms)")
        if snap.result and snap.result.output:
            for k, v in snap.result.output.items():
                print(f"    {k}: {v}")

    print(f"\nIs complete: {pg.is_complete}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 7: Summary and History")
    print("=" * 72)

    summary = pg.summary()
    print(f"\nPlayground summary:")
    print(f"  Workflow:    {summary['workflow']}")
    print(f"  Total steps: {summary['total_steps']}")
    print(f"  Executed:    {summary['executed']}")
    print(f"  Remaining:   {summary['remaining']}")
    print(f"  Complete:    {summary['is_complete']}")

    print(f"\nExecution history:")
    for entry in summary["history"]:
        print(f"  {entry['step']:15s}  {entry['type']:10s}  {entry['status']:10s}  {entry['duration_ms']:.1f}ms")

    # Full history with context diffs
    print(f"\nContext evolution (params → outputs):")
    for snap in pg.history:
        before_outputs = list(snap.context_before.get("outputs", {}).keys())
        after_outputs = list(snap.context_after.get("outputs", {}).keys())
        new = set(after_outputs) - set(before_outputs)
        print(f"  {snap.step_name}: +{new if new else '(no new outputs)'}")

    # ─────────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SECTION 8: Reset and Replay")
    print("=" * 72)

    pg.reset()
    print(f"\nAfter reset:")
    print(f"  Index:    {pg.current_step_index}")
    print(f"  History:  {len(pg.history)}")
    print(f"  Complete: {pg.is_complete}")
    print(f"  Params:   {dict(pg.context.params)}")

    # Run straight through this time
    all_snaps = pg.run_all()
    print(f"\nRan all {len(all_snaps)} steps in one call:")
    for snap in all_snaps:
        print(f"  {snap.step_name}: {snap.status}")

    print("\n" + "=" * 72)
    print("All WorkflowPlayground demonstrations complete!")
    print("=" * 72)


if __name__ == "__main__":
    main()
