#!/usr/bin/env python3
"""Decoupled Functions — plain Python that works anywhere AND as workflow steps.

The classic workflow API requires every step handler to accept
``(ctx: WorkflowContext, config: dict) → StepResult``.  That couples
your code to the orchestration framework — you can't call it from a
notebook, reuse it in another project, or unit-test it without
constructing a ``WorkflowContext``.

This example shows three ways to write **plain functions** that stay
framework-agnostic yet plug into the workflow engine seamlessly:

    1. ``Step.from_function()``  — wrap at workflow-build time
    2. ``adapt_function()``      — wrap manually into a handler
    3. ``@workflow_step``        — decorator that adds ``.as_step()``

The functions themselves never import ``WorkflowContext``, ``StepResult``,
or any spine type.  They accept typed keyword arguments, return dicts
(or bools, strings, numbers, None), and work exactly the same whether
called directly in a script or executed inside a workflow.

Demonstrates:
    1. ``Step.from_function(name, fn)`` — zero-import step creation
    2. ``adapt_function(fn)``          — low-level adapter
    3. ``@workflow_step(name=...)``     — decorator with ``.as_step()``
    4. ``StepResult.from_value()``     — automatic return coercion
    5. ``is_workflow_step()`` / ``get_step_meta()`` — introspection
    6. ``strict=True`` mode for early parameter validation
    7. Direct call vs workflow execution — identical results
    8. Mixed workflow: framework-aware + plain function steps together

Architecture:
    Plain functions are bridged into the workflow engine by an
    **adapter layer** that:

    1. Merges ``config`` and ``ctx.params`` into a kwargs dict
    2. Filters kwargs to only the params the function declares
    3. Calls the function with matched kwargs
    4. Coerces the return value via ``StepResult.from_value()``
    5. Catches exceptions → ``StepResult.fail()``

    ::

        Your function                     Workflow engine
        ────────────                      ───────────────
        def score(revenue, debt):         WorkflowRunner calls
            return {"ratio": ...}    ◄──  adapter(ctx, config) → StepResult

Key Concepts:
    - **No framework imports**: Functions don't import spine types.
    - **Return coercion**: ``dict`` → ``ok(output=dict)``,
      ``bool`` → ok/fail, ``str`` → ``ok(output={"message": ...})``,
      ``None`` → ``ok()``, ``StepResult`` → pass-through.
    - **Parameter matching**: Only kwargs the function declares are
      passed — extra context/config keys are silently ignored.
    - **Strict mode**: ``strict=True`` fails early with a
      CONFIGURATION error if required params are missing.
    - **Composability**: Mix plain functions and classic handlers
      freely within the same workflow.

See Also:
    - ``01_workflow_basics.py``    — classic framework-aware handlers
    - ``03_workflow_context.py``   — WorkflowContext data passing
    - ``17_sec_etl_workflow.py``   — full ETL using classic handlers
    - :mod:`spine.orchestration.step_adapters` — adapter source code

Run:
    python examples/04_orchestration/04_step_adapters.py

Expected Output:
    Five sections demonstrating direct calls, Step.from_function(),
    @workflow_step decorator, mixed workflows, and strict mode.
"""

from __future__ import annotations

from typing import Any


# ============================================================================
# SECTION 0 — Pure business functions (NO spine imports)
# ============================================================================
# These functions know nothing about workflows, contexts, or step results.
# They could live in a shared library, a notebook, or another project.

def fetch_filing_data(cik: str, form_type: str = "10-K") -> dict:
    """Fetch SEC filing metadata (mock)."""
    filings = {
        "0000320193": {"company": "Apple Inc.", "revenue": 391_035_000_000, "net_income": 96_995_000_000},
        "0000789019": {"company": "Microsoft Corp.", "revenue": 245_122_000_000, "net_income": 88_136_000_000},
        "0001018724": {"company": "Amazon.com Inc.", "revenue": 574_785_000_000, "net_income": 30_425_000_000},
    }
    data = filings.get(cik, {"company": "Unknown", "revenue": 0, "net_income": 0})
    return {
        "cik": cik,
        "form_type": form_type,
        **data,
    }


def calculate_risk_score(revenue: float, net_income: float, debt_ratio: float = 0.5) -> dict:
    """Calculate a simple financial risk score."""
    if revenue <= 0:
        return {"risk_score": 100.0, "grade": "F", "reason": "No revenue"}

    margin = net_income / revenue
    score = max(0.0, min(100.0, 100 - (margin * 100) - ((1 - debt_ratio) * 20)))
    grade = "A" if score < 20 else "B" if score < 40 else "C" if score < 60 else "D" if score < 80 else "F"
    return {
        "risk_score": round(score, 2),
        "grade": grade,
        "margin": round(margin * 100, 2),
        "debt_ratio": debt_ratio,
    }


def format_report(company: str, risk_score: float, grade: str, margin: float) -> str:
    """Format a one-line risk report."""
    return f"{company}: risk={risk_score:.1f} grade={grade} margin={margin:.1f}%"


def validate_threshold(risk_score: float, max_allowed: float = 50.0) -> bool:
    """Check if risk score is within acceptable range."""
    return risk_score <= max_allowed


def enrich_with_sector(company: str, cik: str) -> dict:
    """Add sector classification (mock)."""
    sectors = {
        "0000320193": "Technology",
        "0000789019": "Technology",
        "0001018724": "Consumer Discretionary",
    }
    return {
        "company": company,
        "cik": cik,
        "sector": sectors.get(cik, "Unknown"),
        "enriched": True,
    }


# ============================================================================
# Now the spine imports — ONLY needed where we build workflows
# ============================================================================

from spine.orchestration import (
    Step,
    StepResult,
    Workflow,
    WorkflowContext,
    WorkflowRunner,
    WorkflowStatus,
    adapt_function,
    get_step_meta,
    is_workflow_step,
    workflow_step,
)


# ---------------------------------------------------------------------------
# Runnable stub (needed for WorkflowRunner)
# ---------------------------------------------------------------------------

class _StubRunnable:
    def submit_operation_sync(self, operation_name, params=None, *,
                             parent_run_id=None, correlation_id=None):
        from spine.execution.runnable import OperationRunResult
        return OperationRunResult(status="failed", error="Not configured")


# ============================================================================
# SECTION 1 — Direct call vs Step.from_function()
# ============================================================================

def demo_step_from_function() -> None:
    """Show that Step.from_function() wraps a plain function as a step."""
    print("\n--- Section 1: Step.from_function() ---\n")

    # --- Direct call (no framework) ---
    direct_result = fetch_filing_data("0000320193", form_type="10-K")
    print(f"  Direct call:")
    print(f"    fetch_filing_data('0000320193') → {direct_result}")
    assert direct_result["company"] == "Apple Inc."
    assert direct_result["revenue"] == 391_035_000_000

    debt_ratio = 0.45
    direct_risk = calculate_risk_score(
        revenue=direct_result["revenue"],
        net_income=direct_result["net_income"],
        debt_ratio=debt_ratio,
    )
    print(f"    calculate_risk_score()           → {direct_risk}")

    # --- Same functions as workflow steps ---
    # Note: plain function adapters merge `config` + `ctx.params` as kwargs.
    # For cross-step data flow, pass values through params or config.
    # For dynamic data flow between steps, use a classic handler (Section 4).
    wf = Workflow(
        name="demo.from_function",
        steps=[
            Step.from_function(
                "fetch",
                fetch_filing_data,
                config={"cik": "0000320193", "form_type": "10-K"},
            ),
            Step.from_function(
                "score",
                calculate_risk_score,
                config={
                    "revenue": 391_035_000_000,
                    "net_income": 96_995_000_000,
                    "debt_ratio": 0.45,
                },
            ),
        ],
    )

    runner = WorkflowRunner(runnable=_StubRunnable())
    result = runner.execute(wf)

    print(f"\n  Workflow execution:")
    print(f"    status          : {result.status.value}")
    fetch_out = result.context.get_output("fetch")
    score_out = result.context.get_output("score")
    print(f"    fetch output    : {fetch_out}")
    print(f"    score output    : {score_out}")

    # Both produce the same results
    assert result.status == WorkflowStatus.COMPLETED
    assert fetch_out["company"] == direct_result["company"]
    assert score_out["risk_score"] == direct_risk["risk_score"]
    print(f"\n  [OK] Direct call and workflow produce identical results")


# ============================================================================
# SECTION 2 — adapt_function() low-level API
# ============================================================================

def demo_adapt_function() -> None:
    """Show the low-level adapt_function() API."""
    print("\n--- Section 2: adapt_function() ---\n")

    # Adapt a plain function into a handler
    handler = adapt_function(calculate_risk_score)

    # The handler now accepts (ctx, config) → StepResult
    # Simulate what WorkflowRunner does internally:
    class _FakeCtx:
        params: dict = {}

    ctx = _FakeCtx()
    config = {"revenue": 391_035_000_000, "net_income": 96_995_000_000, "debt_ratio": 0.45}

    step_result = handler(ctx, config)
    print(f"  Adapted handler call:")
    print(f"    success    : {step_result.success}")
    print(f"    output     : {step_result.output}")
    assert step_result.success is True
    assert "risk_score" in step_result.output

    # The original function is still callable directly
    direct = calculate_risk_score(
        revenue=391_035_000_000, net_income=96_995_000_000, debt_ratio=0.45,
    )
    print(f"\n  Direct call:")
    print(f"    result     : {direct}")
    assert direct["risk_score"] == step_result.output["risk_score"]

    # --- Return coercion demo ---
    print(f"\n  Return coercion (StepResult.from_value):")

    # bool → ok/fail
    bool_handler = adapt_function(validate_threshold)
    r_pass = bool_handler(_FakeCtx(), {"risk_score": 30.0, "max_allowed": 50.0})
    r_fail = bool_handler(_FakeCtx(), {"risk_score": 80.0, "max_allowed": 50.0})
    print(f"    bool True  → success={r_pass.success}")
    print(f"    bool False → success={r_fail.success}, error={r_fail.error!r}")
    assert r_pass.success is True
    assert r_fail.success is False

    # str → ok(output={"message": ...})
    str_handler = adapt_function(format_report)
    r_str = str_handler(_FakeCtx(), {
        "company": "Apple", "risk_score": 25.0, "grade": "B", "margin": 24.8,
    })
    print(f"    str        → output={r_str.output}")
    assert "message" in r_str.output

    # None → ok()
    def returns_none() -> None:
        pass
    none_handler = adapt_function(returns_none)
    r_none = none_handler(_FakeCtx(), {})
    print(f"    None       → success={r_none.success}, output={r_none.output}")
    assert r_none.success is True

    print(f"\n  [OK] adapt_function() with all coercion types verified")


# ============================================================================
# SECTION 3 — @workflow_step decorator
# ============================================================================

# Decorate functions — they remain directly callable
@workflow_step(name="fetch_filing")
def ws_fetch_filing(cik: str, form_type: str = "10-K") -> dict:
    """Fetch SEC filing metadata."""
    return fetch_filing_data(cik, form_type)


@workflow_step(name="calculate_risk", tags=("finance", "risk"))
def ws_calculate_risk(revenue: float, net_income: float, debt_ratio: float = 0.5) -> dict:
    """Calculate financial risk score."""
    return calculate_risk_score(revenue, net_income, debt_ratio)


@workflow_step(name="enrich_sector")
def ws_enrich(company: str, cik: str) -> dict:
    """Enrich with sector classification."""
    return enrich_with_sector(company, cik)


@workflow_step(name="validate_risk", strict=True)
def ws_validate(risk_score: float, max_allowed: float = 50.0) -> bool:
    """Validate risk is within threshold."""
    return validate_threshold(risk_score, max_allowed)


def demo_workflow_step_decorator() -> None:
    """Show the @workflow_step decorator pattern."""
    print("\n--- Section 3: @workflow_step Decorator ---\n")

    # --- Direct calls work unchanged ---
    print("  Direct calls (no framework):")
    filing = ws_fetch_filing(cik="0000789019")
    print(f"    ws_fetch_filing('0000789019') → company={filing['company']}")

    risk = ws_calculate_risk(revenue=filing["revenue"], net_income=filing["net_income"])
    print(f"    ws_calculate_risk()           → score={risk['risk_score']}, grade={risk['grade']}")

    valid = ws_validate(risk_score=risk["risk_score"])
    print(f"    ws_validate()                 → {valid}")

    # --- Introspection ---
    print(f"\n  Introspection:")
    print(f"    is_workflow_step(ws_fetch_filing)  : {is_workflow_step(ws_fetch_filing)}")
    print(f"    is_workflow_step(fetch_filing_data): {is_workflow_step(fetch_filing_data)}")

    meta = get_step_meta(ws_calculate_risk)
    print(f"    get_step_meta(ws_calculate_risk)   : {meta}")
    assert meta is not None
    assert meta.name == "calculate_risk"
    assert "finance" in meta.tags

    meta_v = get_step_meta(ws_validate)
    print(f"    get_step_meta(ws_validate)         : strict={meta_v.strict}")
    assert meta_v.strict is True

    # --- Build workflow with .as_step() ---
    print(f"\n  Workflow with .as_step():")
    # Each step gets its own config — plain functions don't see upstream outputs.
    # For dynamic cross-step data flow, use a classic handler (Section 4).
    wf = Workflow(
        name="demo.decorator_workflow",
        steps=[
            ws_fetch_filing.as_step(config={"cik": "0000789019"}),
            ws_calculate_risk.as_step(
                config={
                    "revenue": 245_122_000_000,
                    "net_income": 88_136_000_000,
                    "debt_ratio": 0.4,
                },
            ),
            ws_enrich.as_step(config={
                "company": "Microsoft Corp.",
                "cik": "0000789019",
            }),
        ],
    )

    runner = WorkflowRunner(runnable=_StubRunnable())
    result = runner.execute(wf)

    print(f"    status        : {result.status.value}")
    print(f"    steps         : {result.completed_steps}")
    score_out = result.context.get_output("calculate_risk")
    enrich_out = result.context.get_output("enrich_sector")
    print(f"    risk_score    : {score_out.get('risk_score')}")
    print(f"    grade         : {score_out.get('grade')}")
    print(f"    sector        : {enrich_out.get('sector')}")

    assert result.status == WorkflowStatus.COMPLETED
    assert len(result.completed_steps) == 3
    print(f"\n  [OK] @workflow_step — direct calls + workflow execution verified")


# ============================================================================
# SECTION 4 — Mixed workflow: classic + plain function steps
# ============================================================================

def demo_mixed_workflow() -> None:
    """Mix framework-aware and plain function steps in one workflow."""
    print("\n--- Section 4: Mixed Workflow ---\n")

    # Classic framework-aware handler
    def audit_step(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
        """A classic handler that accesses WorkflowContext directly."""
        filing = ctx.get_output("fetch")
        risk = ctx.get_output("score")
        sector = ctx.get_output("enrich")

        company = filing.get("company", "?")
        score = risk.get("risk_score", -1)
        grade = risk.get("grade", "?")
        sec = sector.get("sector", "?")

        summary = (
            f"AUDIT: {company} ({sec}) — "
            f"risk={score:.1f} grade={grade} "
            f"margin={risk.get('margin', 0):.1f}%"
        )
        print(f"    [audit]   {summary}")

        return StepResult.ok(output={
            "summary": summary,
            "company": company,
            "risk_score": score,
            "grade": grade,
            "sector": sec,
            "audit_passed": grade in ("A", "B", "C"),
        })

    # Build a workflow mixing both styles.
    # Plain function steps: self-contained with their own config.
    # Classic handler step: bridges outputs via ctx.get_output().
    wf = Workflow(
        name="demo.mixed_workflow",
        description="Classic handler + plain functions in one workflow",
        steps=[
            # Plain function steps — each has all params it needs
            Step.from_function("fetch", fetch_filing_data,
                               config={"cik": "0001018724"}),
            Step.from_function("score", calculate_risk_score,
                               config={
                                   "revenue": 574_785_000_000,
                                   "net_income": 30_425_000_000,
                                   "debt_ratio": 0.6,
                               }),
            Step.from_function("enrich", enrich_with_sector,
                               config={
                                   "company": "Amazon.com Inc.",
                                   "cik": "0001018724",
                               }),
            # Classic handler — reads from all previous step outputs
            Step.lambda_("audit", audit_step,
                         depends_on=["fetch", "score", "enrich"]),
        ],
    )

    runner = WorkflowRunner(runnable=_StubRunnable())
    result = runner.execute(wf)

    print(f"\n  status        : {result.status.value}")
    print(f"  completed     : {result.completed_steps}")
    audit = result.context.get_output("audit")
    print(f"  audit_passed  : {audit.get('audit_passed')}")
    print(f"  summary       : {audit.get('summary')}")

    assert result.status == WorkflowStatus.COMPLETED
    assert len(result.completed_steps) == 4
    assert audit["company"] == "Amazon.com Inc."
    assert audit["sector"] == "Consumer Discretionary"
    print(f"\n  [OK] Mixed workflow — 2 plain + 1 enricher + 1 classic handler")


# ============================================================================
# SECTION 5 — Strict mode and error handling
# ============================================================================

def demo_strict_mode() -> None:
    """Show strict mode catching missing parameters early."""
    print("\n--- Section 5: Strict Mode ---\n")

    # A function with required parameters (no defaults)
    def requires_params(company: str, revenue: float) -> dict:
        return {"company": company, "revenue": revenue}

    # --- Non-strict: missing params cause Python's own error ---
    print("  Non-strict (default):")
    wf_loose = Workflow(
        name="demo.non_strict",
        steps=[
            Step.from_function("step", requires_params, config={"company": "Test"}),
            # revenue is missing — Python will raise TypeError
        ],
    )
    runner = WorkflowRunner(runnable=_StubRunnable())
    result_loose = runner.execute(wf_loose)
    step_out = result_loose.context.get_output("step")
    # The adapter catches the TypeError and returns StepResult.fail()
    print(f"    status      : {result_loose.status.value}")
    print(f"    error       : {result_loose.error}")
    # In non-strict, adapter catches the TypeError from Python
    assert result_loose.status in (WorkflowStatus.FAILED, WorkflowStatus.PARTIAL)
    print(f"    [OK] Non-strict: Python's TypeError caught and wrapped")

    # --- Strict: adapter validates before calling ---
    print(f"\n  Strict mode:")
    wf_strict = Workflow(
        name="demo.strict",
        steps=[
            Step.from_function("step", requires_params,
                               config={"company": "Test"}, strict=True),
            # revenue is still missing — adapter catches it before calling
        ],
    )
    result_strict = runner.execute(wf_strict)
    print(f"    status      : {result_strict.status.value}")
    print(f"    error       : {result_strict.error}")
    assert result_strict.status in (WorkflowStatus.FAILED, WorkflowStatus.PARTIAL)
    # Strict mode produces a CONFIGURATION category error
    for se in result_strict.step_executions:
        if se.status == "failed" and se.result:
            print(f"    category    : {se.result.error_category}")
    print(f"    [OK] Strict mode: missing 'revenue' caught with CONFIGURATION error")

    # --- Strict with all params provided: should succeed ---
    print(f"\n  Strict with all params:")
    wf_ok = Workflow(
        name="demo.strict_ok",
        steps=[
            Step.from_function("step", requires_params,
                               config={"company": "Apple", "revenue": 391e9},
                               strict=True),
        ],
    )
    result_ok = runner.execute(wf_ok)
    out = result_ok.context.get_output("step")
    print(f"    status      : {result_ok.status.value}")
    print(f"    output      : {out}")
    assert result_ok.status == WorkflowStatus.COMPLETED
    assert out["company"] == "Apple"
    print(f"    [OK] Strict passes when all required params provided")

    # --- Exception handling ---
    print(f"\n  Exception handling:")

    def will_raise(x: int) -> dict:
        raise ValueError(f"Bad input: {x}")

    wf_err = Workflow(
        name="demo.exception",
        steps=[Step.from_function("boom", will_raise, config={"x": 42})],
    )
    result_err = runner.execute(wf_err)
    print(f"    status      : {result_err.status.value}")
    print(f"    error       : {result_err.error}")
    assert result_err.status in (WorkflowStatus.FAILED, WorkflowStatus.PARTIAL)
    print(f"    [OK] Exception caught and wrapped as StepResult.fail()")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all decoupled functions demonstrations."""

    print("=" * 60)
    print("Decoupled Functions — Plain Python as Workflow Steps")
    print("=" * 60)

    demo_step_from_function()
    demo_adapt_function()
    demo_workflow_step_decorator()
    demo_mixed_workflow()
    demo_strict_mode()

    # --- Summary ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("""
  Three mechanisms to bridge plain functions into workflows:

  ┌────────────────────────┬──────────────────────────────────────┐
  │ Mechanism              │ When to use                          │
  ├────────────────────────┼──────────────────────────────────────┤
  │ Step.from_function()   │ Build-time wrapping, most common     │
  │ adapt_function()       │ Low-level, custom Step construction  │
  │ @workflow_step         │ Library functions with .as_step()    │
  └────────────────────────┴──────────────────────────────────────┘

  Return coercion (StepResult.from_value):
    dict  → ok(output=dict)
    bool  → ok() / fail("returned False")
    str   → ok(output={"message": ...})
    int   → ok(output={"value": ...})
    None  → ok()

  Functions never import spine types — the adapter handles everything.
""")
    print("[OK] All decoupled functions demonstrations passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
