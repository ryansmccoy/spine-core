#!/usr/bin/env python3
"""Choice & Branching — conditional routing and error handling.

Workflows often need to take different paths based on runtime data.
``Step.choice()`` evaluates a condition function against the workflow
context and jumps to ``then_step`` (condition True) or ``else_step``
(condition False).  Combined with ``ErrorPolicy``, this enables
sophisticated control flow within a single workflow definition.

Demonstrates:
    1. ``Step.choice()`` for conditional routing based on form type
    2. Branch-exclusive execution (skip steps not on the active path)
    3. ``ErrorPolicy.STOP`` vs ``ErrorPolicy.CONTINUE``
    4. ``WorkflowStatus.PARTIAL`` when steps fail in CONTINUE mode
    5. ``StepResult.skip()`` for idempotency checks
    6. Multiple workflows in one example with different failure modes
    7. Context updates across choice branches

Architecture:
    Workflow A — Conditional Routing::

        classify_filing
            │
        route_by_type ─── condition: is_annual?
            │                 │
          (True)           (False)
            │                 │
        process_annual    process_quarterly
            │                 │
            └────── summarize ◄┘
                       │
                     store

    Workflow B — Error Handling::

        step_ok_1 ─(continue)─► step_fail ─(continue)─► step_ok_2
                                                         │
        Result: PARTIAL (2 completed, 1 failed)

Key Concepts:
    - **Choice step**: ``Step.choice(name, condition, then_step, else_step)``
      — the condition is a ``(ctx) → bool`` callable.
    - **Branch skipping**: After a choice branches to ``then_step``,
      steps between the choice and the target are skipped.
    - **next_step on lambda**: A lambda step can return a ``StepResult``
      with ``next_step`` set to skip ahead (branch-exclusive paths).
    - **ErrorPolicy.CONTINUE**: Steps after a failure still execute;
      the workflow finishes with ``WorkflowStatus.PARTIAL``.
    - **StepResult.skip()**: Signal that work was already done —
      success with ``{skipped: True, skip_reason: ...}``.

See Also:
    - ``01_workflow_basics.py``  — sequential baseline
    - ``07_parallel_dag.py``     — parallel branching
    - :mod:`spine.orchestration.step_types` — Step.choice() source
    - :mod:`spine.orchestration.workflow_runner` — branching logic

Run:
    python examples/04_orchestration/05_choice_branching.py

Expected Output:
    Two workflow executions — one showing choice-based routing for
    an annual filing, one demonstrating CONTINUE-mode error handling
    with a PARTIAL result.
"""

from __future__ import annotations

from typing import Any

from spine.orchestration import (
    ErrorPolicy,
    ExecutionMode,
    FailurePolicy,
    Step,
    StepResult,
    StepType,
    Workflow,
    WorkflowContext,
    WorkflowExecutionPolicy,
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
)


# ---------------------------------------------------------------------------
# Runnable stub
# ---------------------------------------------------------------------------

class _StubRunnable:
    def submit_pipeline_sync(self, pipeline_name, params=None, *,
                             parent_run_id=None, correlation_id=None):
        from spine.execution.runnable import PipelineRunResult
        return PipelineRunResult(status="failed", error="Not configured")


# ============================================================================
# WORKFLOW A — Conditional Routing by Form Type
# ============================================================================

def classify_filing(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Determine filing type from params."""
    form_type = ctx.get_param("form_type", "10-K")
    is_annual = form_type in ("10-K", "20-F")
    print(f"    [classify]          form_type={form_type}, is_annual={is_annual}")
    return StepResult.ok(output={
        "form_type": form_type,
        "is_annual": is_annual,
        "company": ctx.get_param("company", "Example Corp."),
    })


def process_annual(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Process 10-K annual filing — full XBRL + all sections."""
    company = ctx.get_output("classify_filing", "company", "?")
    print(f"    [process_annual]    Full annual processing for {company}")
    print(f"                        → Extracting all 18 Items + XBRL + exhibits")
    # Set next_step to skip over the quarterly branch
    return StepResult(
        success=True,
        output={
            "processing_type": "annual",
            "items_extracted": 18,
            "xbrl_parsed": True,
            "exhibits_count": 12,
        },
        next_step="summarize",  # skip process_quarterly
    )


def process_quarterly(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Process 10-Q quarterly filing — limited sections."""
    company = ctx.get_output("classify_filing", "company", "?")
    print(f"    [process_quarterly] Quarterly processing for {company}")
    print(f"                        → Extracting Part I + Part II only")
    return StepResult.ok(output={
        "processing_type": "quarterly",
        "items_extracted": 6,
        "xbrl_parsed": True,
        "exhibits_count": 3,
    })


def summarize(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Summarize results from whichever branch executed."""
    # Read from whichever branch ran — only one will have output
    annual_output = ctx.get_output("process_annual")
    quarterly_output = ctx.get_output("process_quarterly")

    if annual_output:
        processing_type = "annual"
        items = annual_output.get("items_extracted", 0)
    elif quarterly_output:
        processing_type = "quarterly"
        items = quarterly_output.get("items_extracted", 0)
    else:
        processing_type = "unknown"
        items = 0

    print(f"    [summarize]         {processing_type} processing: {items} items extracted")
    return StepResult.ok(output={
        "processing_type": processing_type,
        "total_items": items,
        "summary": f"Processed {items} items via {processing_type} path",
    })


def store_filing(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Store processed filing data."""
    summary = ctx.get_output("summarize", "summary", "")
    print(f"    [store]             {summary}")
    return StepResult.ok(output={"stored": True})


def _build_routing_workflow() -> Workflow:
    """Build a workflow with choice-based routing."""
    return Workflow(
        name="sec.form_routing",
        domain="sec.edgar",
        description="Route filing processing by form type (10-K vs 10-Q)",
        steps=[
            Step.lambda_("classify_filing", classify_filing),
            Step.choice(
                "route_by_type",
                condition=lambda ctx: ctx.get_output("classify_filing", "is_annual", False),
                then_step="process_annual",
                else_step="process_quarterly",
            ),
            Step.lambda_("process_annual", process_annual),
            Step.lambda_("process_quarterly", process_quarterly),
            Step.lambda_("summarize", summarize),
            Step.lambda_("store", store_filing),
        ],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.SEQUENTIAL,
            on_failure=FailurePolicy.STOP,
        ),
        tags=["choice", "branching", "conditional"],
    )


# ============================================================================
# WORKFLOW B — Error Handling with CONTINUE Policy
# ============================================================================

def step_ok_1(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Step that always succeeds."""
    print(f"    [step_ok_1]         Completed successfully")
    return StepResult.ok(output={"step": 1, "status": "ok"})


def step_fail(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Step that always fails — demonstrates CONTINUE policy."""
    print(f"    [step_fail]         Intentional failure!")
    return StepResult.fail(
        "Database connection timeout (simulated)",
        category="TRANSIENT",
    )


def step_ok_2(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Step that succeeds — runs despite prior failure in CONTINUE mode."""
    prior_failed = not ctx.has_output("step_fail")
    print(f"    [step_ok_2]         Running after failure (prior_failed={prior_failed})")
    return StepResult.ok(output={"step": 3, "status": "ok", "ran_after_failure": True})


def _build_error_handling_workflow() -> Workflow:
    """Build a workflow demonstrating CONTINUE-mode error handling."""
    return Workflow(
        name="sec.error_handling_demo",
        domain="demo",
        description="Demonstrates ErrorPolicy.CONTINUE with partial success",
        steps=[
            Step.lambda_("step_ok_1", step_ok_1, on_error=ErrorPolicy.CONTINUE),
            Step.lambda_("step_fail", step_fail, on_error=ErrorPolicy.CONTINUE),
            Step.lambda_("step_ok_2", step_ok_2, on_error=ErrorPolicy.CONTINUE),
        ],
    )


# ============================================================================
# WORKFLOW C — Idempotency with StepResult.skip()
# ============================================================================

# Track whether we've "processed" this filing already
_processed_accessions: set[str] = set()


def idempotent_process(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Process only once — skip on repeated invocations."""
    accession = ctx.get_param("accession", "0000320193-24-000081")
    if accession in _processed_accessions:
        print(f"    [idempotent]        SKIP — {accession} already processed")
        # Don't override output — let skip() use its default:
        #   {"skipped": True, "skip_reason": reason}
        return StepResult.skip(reason=f"Already processed: {accession}")
    _processed_accessions.add(accession)
    print(f"    [idempotent]        Processing {accession} for the first time")
    return StepResult.ok(output={"accession": accession, "newly_processed": True})


def _build_idempotent_workflow() -> Workflow:
    """Build a workflow demonstrating StepResult.skip()."""
    return Workflow(
        name="sec.idempotent_demo",
        domain="demo",
        steps=[
            Step.lambda_("process", idempotent_process),
        ],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run three workflows demonstrating branching and error handling."""

    print("=" * 60)
    print("Choice & Branching — Conditional Routing")
    print("=" * 60)

    runner = WorkflowRunner(runnable=_StubRunnable())

    # ===== A. Conditional Routing — 10-K (annual) path =====
    print("\n--- A1. Conditional Routing — 10-K (annual) ---")
    wf = _build_routing_workflow()

    # Inspect choice step
    route_step = wf.get_step("route_by_type")
    assert route_step is not None
    print(f"  choice step     : {route_step.name}")
    print(f"  step_type       : {route_step.step_type.value}")
    print(f"  then_step       : {route_step.then_step}")
    print(f"  else_step       : {route_step.else_step}")
    print(f"  has_choice_steps: {wf.has_choice_steps()}")

    result_10k = runner.execute(wf, params={"form_type": "10-K", "company": "Apple Inc."})

    print(f"\n  status          : {result_10k.status.value}")
    print(f"  completed_steps : {result_10k.completed_steps}")
    proc_type = result_10k.context.get_output("summarize", "processing_type", "?")
    print(f"  processing_type : {proc_type}")

    # ===== A2. Conditional Routing — 10-Q (quarterly) path =====
    print("\n--- A2. Conditional Routing — 10-Q (quarterly) ---")
    result_10q = runner.execute(wf, params={"form_type": "10-Q", "company": "Microsoft Corp."})

    print(f"\n  status          : {result_10q.status.value}")
    print(f"  completed_steps : {result_10q.completed_steps}")
    proc_type_q = result_10q.context.get_output("summarize", "processing_type", "?")
    print(f"  processing_type : {proc_type_q}")

    # ===== B. Error Handling with CONTINUE =====
    print("\n--- B. Error Handling — CONTINUE Policy ---")
    err_wf = _build_error_handling_workflow()
    err_result = runner.execute(err_wf)

    print(f"\n  status          : {err_result.status.value}")
    print(f"  completed_steps : {err_result.completed_steps}")
    print(f"  failed_steps    : {err_result.failed_steps}")
    print(f"  error_step      : {err_result.error_step}")
    print(f"  error           : {err_result.error}")
    for se in err_result.step_executions:
        icon = "PASS" if se.status == "completed" else "FAIL"
        print(f"    [{icon}] {se.step_name:20s} {se.status}")

    # ===== C. Idempotency with skip() =====
    print("\n--- C. Idempotency — StepResult.skip() ---")
    skip_wf = _build_idempotent_workflow()

    # First run — should process
    r1 = runner.execute(skip_wf, params={"accession": "0000320193-24-000081"})
    newly = r1.context.get_output("process", "newly_processed", False)
    print(f"  run 1 status    : {r1.status.value}")
    print(f"  newly_processed : {newly}")

    # Second run — should skip (skip info is in output dict)
    r2 = runner.execute(skip_wf, params={"accession": "0000320193-24-000081"})
    skipped = r2.context.get_output("process", "skipped", False)
    skip_reason = r2.context.get_output("process", "skip_reason", "")
    print(f"  run 2 status    : {r2.status.value}")
    print(f"  skipped         : {skipped}")
    print(f"  skip_reason     : {skip_reason}")

    # --- Assertions ---
    # A: routing
    assert result_10k.status == WorkflowStatus.COMPLETED
    assert result_10q.status == WorkflowStatus.COMPLETED
    assert proc_type == "annual"
    assert proc_type_q == "quarterly"
    # Verify the 10-K path did NOT run process_quarterly
    has_quarterly = result_10k.context.has_output("process_quarterly")
    assert not has_quarterly, "10-K path should not run process_quarterly"

    # B: error handling
    assert err_result.status == WorkflowStatus.PARTIAL
    assert len(err_result.completed_steps) == 2
    assert len(err_result.failed_steps) == 1

    # C: idempotency
    assert r1.status == WorkflowStatus.COMPLETED
    assert newly is True
    assert skipped is True, f"Second run should be skipped"
    assert "already processed" in skip_reason.lower()

    print("\n" + "=" * 60)
    print("[OK] Choice & Branching — all 3 patterns verified")
    print("=" * 60)


if __name__ == "__main__":
    main()
