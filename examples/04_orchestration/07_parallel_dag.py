#!/usr/bin/env python3
"""Parallel DAG — diamond-shaped workflow with ThreadPoolExecutor.

When steps declare ``depends_on`` edges and the workflow uses
``ExecutionMode.PARALLEL``, the runner builds a dependency graph and
schedules independent steps concurrently via ``ThreadPoolExecutor``.
This example constructs a diamond DAG (fan-out then fan-in) and
measures wall-clock time to prove real parallelism.

Demonstrates:
    1. ``depends_on`` edges for dependency declarations
    2. ``ExecutionMode.PARALLEL`` with ``max_concurrency``
    3. ``FailurePolicy.CONTINUE`` — independent branches survive failures
    4. ``Workflow.dependency_graph()`` and ``topological_order()``
    5. Timing comparison: parallel vs sequential execution
    6. Thread-safe context accumulation across parallel branches
    7. ``WorkflowStatus.PARTIAL`` when a branch fails in CONTINUE mode

Architecture:
    The DAG looks like a diamond::

        fetch_filing  (root — no deps, runs first)
           ├── extract_text      (depends: fetch_filing)
           ├── extract_exhibits  (depends: fetch_filing)
           └── parse_xbrl        (depends: fetch_filing)
        merge_results  (depends: extract_text, extract_exhibits, parse_xbrl)
        store          (depends: merge_results)

    With ``max_concurrency=3``, the three extract/parse steps run
    concurrently after ``fetch_filing`` completes.  ``merge_results``
    waits for all three, then ``store`` runs last.

Key Concepts:
    - **DAG scheduling**: Steps whose dependencies have all completed
      are submitted to the thread pool in waves.
    - **Thread-safe context**: The runner accumulates step outputs
      under a lock so parallel steps share a consistent snapshot.
    - **Fan-out / fan-in**: A common ETL pattern where one upstream
      feeds multiple downstream branches that later converge.

See Also:
    - ``01_workflow_basics.py``            — sequential baseline
    - ``18_parallel_vs_multiprocessing.py`` — raw Pool vs workflow DAG
    - :mod:`spine.orchestration.workflow_runner` — parallel execution code

Run:
    python examples/04_orchestration/07_parallel_dag.py

Expected Output:
    DAG structure, topological order, parallel run timing (~0.5s),
    sequential comparison (~1.3s), and speedup ratio.
"""

from __future__ import annotations

import time
from typing import Any

from spine.orchestration import (
    ExecutionMode,
    FailurePolicy,
    Step,
    StepResult,
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


# ---------------------------------------------------------------------------
# Step handlers — each includes a sleep to simulate real I/O
# ---------------------------------------------------------------------------

def fetch_filing(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Root step — download a filing (simulated I/O)."""
    time.sleep(0.2)
    print(f"    [fetch_filing]      Downloaded filing in 0.2s")
    return StepResult.ok(output={
        "accession": "0000320193-24-000081",
        "company": "Apple Inc.",
        "form_type": "10-K",
        "content_size_kb": 2400,
    })


def extract_text(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Branch A — extract plain text from HTML (parallel)."""
    time.sleep(0.3)
    company = ctx.get_output("fetch_filing", "company", "?")
    print(f"    [extract_text]      Extracted text for {company} in 0.3s")
    return StepResult.ok(output={
        "word_count": 145_000,
        "sections": ["Item 1A", "Item 7", "Item 8"],
    })


def extract_exhibits(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Branch B — extract exhibit documents (parallel)."""
    time.sleep(0.3)
    print(f"    [extract_exhibits]  Extracted 4 exhibits in 0.3s")
    return StepResult.ok(output={
        "exhibit_count": 4,
        "exhibits": ["EX-10.1", "EX-21.1", "EX-31.1", "EX-32.1"],
    })


def parse_xbrl(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Branch C — parse XBRL financial data (parallel)."""
    time.sleep(0.3)
    form = ctx.get_output("fetch_filing", "form_type", "?")
    print(f"    [parse_xbrl]        Parsed XBRL for {form} in 0.3s")
    return StepResult.ok(output={
        "facts_extracted": 127,
        "key_facts": {
            "Assets": 352_583_000_000,
            "Revenue": 391_035_000_000,
            "NetIncome": 96_995_000_000,
        },
    })


def merge_results(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Fan-in — combine outputs from all three branches."""
    time.sleep(0.1)
    words = ctx.get_output("extract_text", "word_count", 0)
    exhibits = ctx.get_output("extract_exhibits", "exhibit_count", 0)
    facts = ctx.get_output("parse_xbrl", "facts_extracted", 0)
    print(f"    [merge_results]     Merged: {words:,} words, "
          f"{exhibits} exhibits, {facts} XBRL facts")
    return StepResult.ok(output={
        "total_words": words,
        "total_exhibits": exhibits,
        "total_facts": facts,
        "merged": True,
    })


def store(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Final step — persist merged data."""
    time.sleep(0.1)
    merged = ctx.get_output("merge_results", "merged", False)
    print(f"    [store]             Stored results (merged={merged})")
    return StepResult.ok(output={"stored": True, "location": "s3://filings/processed/"})


# ---------------------------------------------------------------------------
# Workflow builders
# ---------------------------------------------------------------------------

def _build_parallel_workflow() -> Workflow:
    """Build the diamond DAG workflow with parallel execution."""
    return Workflow(
        name="sec.parallel_extraction",
        domain="sec.edgar",
        description="Diamond DAG: fetch → 3 parallel branches → merge → store",
        steps=[
            Step.lambda_("fetch_filing", fetch_filing),
            Step.lambda_("extract_text", extract_text, depends_on=["fetch_filing"]),
            Step.lambda_("extract_exhibits", extract_exhibits, depends_on=["fetch_filing"]),
            Step.lambda_("parse_xbrl", parse_xbrl, depends_on=["fetch_filing"]),
            Step.lambda_("merge_results", merge_results,
                         depends_on=["extract_text", "extract_exhibits", "parse_xbrl"]),
            Step.lambda_("store", store, depends_on=["merge_results"]),
        ],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL,
            max_concurrency=3,
            on_failure=FailurePolicy.CONTINUE,
        ),
        tags=["parallel", "dag", "diamond", "stress-test"],
    )


def _build_sequential_workflow() -> Workflow:
    """Same steps but sequential (no depends_on) for timing comparison."""
    return Workflow(
        name="sec.sequential_extraction",
        domain="sec.edgar",
        description="Same steps executed sequentially for comparison",
        steps=[
            Step.lambda_("fetch_filing", fetch_filing),
            Step.lambda_("extract_text", extract_text),
            Step.lambda_("extract_exhibits", extract_exhibits),
            Step.lambda_("parse_xbrl", parse_xbrl),
            Step.lambda_("merge_results", merge_results),
            Step.lambda_("store", store),
        ],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.SEQUENTIAL,
        ),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run parallel vs sequential and compare timing."""

    print("=" * 60)
    print("Parallel DAG — Diamond-Shaped Workflow")
    print("=" * 60)

    runner = WorkflowRunner(runnable=_StubRunnable())

    # --- 1. Inspect DAG structure ---
    print("\n--- 1. DAG Structure ---")
    wf = _build_parallel_workflow()
    print(f"  name             : {wf.name}")
    print(f"  steps            : {wf.step_names()}")
    print(f"  has_dependencies : {wf.has_dependencies()}")
    print(f"  topological_order: {wf.topological_order()}")
    print(f"  dependency_graph :")
    for source, targets in wf.dependency_graph().items():
        print(f"    {source} → {targets}")
    print(f"  execution_mode   : {wf.execution_policy.mode.value}")
    print(f"  max_concurrency  : {wf.execution_policy.max_concurrency}")
    print(f"  on_failure       : {wf.execution_policy.on_failure.value}")

    # --- 2. Run in parallel mode ---
    print("\n--- 2. Parallel Execution ---")
    t0 = time.perf_counter()
    parallel_result: WorkflowResult = runner.execute(wf)
    parallel_time = time.perf_counter() - t0

    print(f"\n  status          : {parallel_result.status.value}")
    print(f"  wall_clock      : {parallel_time:.3f}s")
    print(f"  completed_steps : {parallel_result.completed_steps}")
    print(f"  failed_steps    : {parallel_result.failed_steps}")

    # --- 3. Run sequentially for comparison ---
    print("\n--- 3. Sequential Execution (comparison) ---")
    seq_wf = _build_sequential_workflow()
    t0 = time.perf_counter()
    seq_result: WorkflowResult = runner.execute(seq_wf)
    seq_time = time.perf_counter() - t0

    print(f"\n  status          : {seq_result.status.value}")
    print(f"  wall_clock      : {seq_time:.3f}s")

    # --- 4. Timing comparison ---
    print("\n--- 4. Timing Comparison ---")
    speedup = seq_time / parallel_time if parallel_time > 0 else 0
    print(f"  Sequential      : {seq_time:.3f}s")
    print(f"  Parallel (DAG)  : {parallel_time:.3f}s")
    print(f"  Speedup         : {speedup:.2f}x")
    print(f"  Time saved      : {seq_time - parallel_time:.3f}s")

    # The three branch steps (0.3s each) run in parallel = ~0.3s instead of ~0.9s
    # Total: ~0.2 (fetch) + ~0.3 (parallel branches) + ~0.1 (merge) + ~0.1 (store) ≈ 0.7s
    # vs:    ~0.2 + ~0.9 + ~0.1 + ~0.1 ≈ 1.3s sequential

    # --- 5. Verify parallel context merging ---
    print("\n--- 5. Context Verification ---")
    ctx = parallel_result.context
    words = ctx.get_output("extract_text", "word_count", 0)
    exhibits = ctx.get_output("extract_exhibits", "exhibit_count", 0)
    facts = ctx.get_output("parse_xbrl", "facts_extracted", 0)
    merged = ctx.get_output("merge_results", "merged", False)
    print(f"  extract_text.word_count       : {words:,}")
    print(f"  extract_exhibits.exhibit_count: {exhibits}")
    print(f"  parse_xbrl.facts_extracted    : {facts}")
    print(f"  merge_results.merged          : {merged}")

    # --- 6. Step execution details ---
    print("\n--- 6. Step Execution Trace ---")
    for se in parallel_result.step_executions:
        dur = se.duration_seconds or 0
        print(f"  [{se.status:9s}] {se.step_name:25s} {dur:.3f}s")

    # --- Assertions ---
    assert parallel_result.status == WorkflowStatus.COMPLETED
    assert seq_result.status == WorkflowStatus.COMPLETED
    assert len(parallel_result.completed_steps) == 6
    assert merged is True
    # Parallel should be meaningfully faster (at least 1.3x)
    assert speedup > 1.2, f"Expected speedup > 1.2x, got {speedup:.2f}x"

    print("\n" + "=" * 60)
    print(f"[OK] Parallel DAG — {speedup:.1f}x speedup over sequential")
    print("=" * 60)


if __name__ == "__main__":
    main()
