#!/usr/bin/env python3
"""Multiprocessing Comparison — raw parallelism vs orchestrated workflows.

Side-by-side comparison showing when to use raw ``multiprocessing.Pool``
or ``concurrent.futures.ThreadPoolExecutor`` versus the spine-core
workflow engine's built-in DAG parallelism.  Measures wall-clock time
for CPU-bound and I/O-bound workloads under both approaches.

**TL;DR**:
- **CPU-bound** (hashing, compression, parsing): Use ``ProcessPool``
  to escape the GIL.  Workflow DAG uses threads (GIL-bound).
- **I/O-bound** (network, disk, DB): Workflow DAG parallelism is
  ideal — threads release the GIL during I/O, and you get tracking,
  context passing, and error handling for free.
- **Orchestrated pipelines**: Use workflows when you need audit
  trails, quality gates, context passing, and retry semantics.

Demonstrates:
    1. ``multiprocessing.Pool`` for CPU-bound fan-out (escapes GIL)
    2. ``ThreadPoolExecutor`` for I/O-bound fan-out
    3. Workflow DAG parallelism (``ExecutionMode.PARALLEL``) for I/O
    4. Timing comparison across all approaches
    5. When workflow overhead is justified vs raw parallelism

Architecture:
    Four benchmarks run in sequence::

        A. CPU-bound — multiprocessing.Pool (4 workers)
        B. CPU-bound — workflow DAG threads (4 concurrent, GIL-bound)
        C. I/O-bound — ThreadPoolExecutor (4 workers)
        D. I/O-bound — workflow DAG threads (4 concurrent)

Key Concepts:
    - **GIL**: Python's Global Interpreter Lock prevents true parallel
      CPU execution in threads.  ``multiprocessing`` spawns separate
      processes to bypass this.
    - **Workflow threads**: The orchestration engine uses
      ``ThreadPoolExecutor`` for DAG parallelism.  This is excellent
      for I/O (sleep/network releases GIL) but limited for CPU.
    - **Orchestration overhead**: Workflows add context management,
      logging, and step tracking — worth it for pipelines, not for
      tight numerical loops.

See Also:
    - ``07_parallel_dag.py``       — workflow DAG timing demo
    - ``17_sec_etl_workflow.py``   — real-world parallel ETL
    - :mod:`spine.orchestration.workflow_runner` — ThreadPoolExecutor usage

Run:
    python examples/04_orchestration/18_parallel_vs_multiprocessing.py

Expected Output:
    Four benchmark results with wall-clock times showing that
    ProcessPool wins for CPU-bound work while workflow DAG matches
    ThreadPoolExecutor for I/O-bound work.
"""

from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor
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
# CPU-bound workload (must be at module level for multiprocessing)
# ---------------------------------------------------------------------------

HASH_ITERATIONS = 40_000  # tune for ~0.1s per call


def cpu_bound_hash(batch_id: int) -> dict[str, Any]:
    """Hash a byte string repeatedly — CPU-intensive work."""
    data = f"spine-core-batch-{batch_id}".encode()
    for _ in range(HASH_ITERATIONS):
        data = hashlib.sha256(data).digest()
    return {"batch_id": batch_id, "digest": data.hex()[:16]}


# ---------------------------------------------------------------------------
# I/O-bound workload
# ---------------------------------------------------------------------------

IO_SLEEP_SECONDS = 0.25  # simulate network call


def io_bound_fetch(batch_id: int) -> dict[str, Any]:
    """Simulate an I/O-bound network fetch."""
    time.sleep(IO_SLEEP_SECONDS)
    return {"batch_id": batch_id, "status": "fetched", "bytes": 1024 * batch_id}


# ---------------------------------------------------------------------------
# Workflow step wrappers (for DAG benchmarks)
# ---------------------------------------------------------------------------

def _make_cpu_step(batch_id: int):
    """Create a lambda step handler for CPU-bound work."""
    def handler(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
        result = cpu_bound_hash(batch_id)
        return StepResult.ok(output=result)
    return handler


def _make_io_step(batch_id: int):
    """Create a lambda step handler for I/O-bound work."""
    def handler(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
        result = io_bound_fetch(batch_id)
        return StepResult.ok(output=result)
    return handler


def _build_parallel_workflow(step_factory, n_steps: int, name: str) -> Workflow:
    """Build a workflow with N parallel steps (all independent)."""
    # Root step
    steps = [Step.lambda_("root", lambda ctx, cfg: StepResult.ok(output={"started": True}))]
    # Fan-out steps
    for i in range(n_steps):
        steps.append(Step.lambda_(
            f"worker_{i}",
            step_factory(i),
            depends_on=["root"],
        ))
    # Fan-in step
    def collect(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
        results = [ctx.get_output(f"worker_{i}") for i in range(n_steps)]
        return StepResult.ok(output={"collected": len(results)})

    steps.append(Step.lambda_(
        "collect",
        collect,
        depends_on=[f"worker_{i}" for i in range(n_steps)],
    ))

    return Workflow(
        name=name,
        steps=steps,
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL,
            max_concurrency=n_steps,
            on_failure=FailurePolicy.STOP,
        ),
    )


# ---------------------------------------------------------------------------
# Benchmark functions
# ---------------------------------------------------------------------------

N_WORKERS = 4


def bench_cpu_multiprocessing() -> float:
    """Benchmark A: CPU-bound with multiprocessing.Pool."""
    import multiprocessing
    t0 = time.perf_counter()
    with multiprocessing.Pool(processes=N_WORKERS) as pool:
        results = pool.map(cpu_bound_hash, range(N_WORKERS))
    elapsed = time.perf_counter() - t0
    assert len(results) == N_WORKERS
    return elapsed


def bench_cpu_sequential() -> float:
    """Baseline: CPU-bound sequential."""
    t0 = time.perf_counter()
    results = [cpu_bound_hash(i) for i in range(N_WORKERS)]
    elapsed = time.perf_counter() - t0
    assert len(results) == N_WORKERS
    return elapsed


def bench_cpu_workflow_dag() -> float:
    """Benchmark B: CPU-bound with workflow DAG (threads)."""
    wf = _build_parallel_workflow(_make_cpu_step, N_WORKERS, "bench.cpu_workflow")
    runner = WorkflowRunner(runnable=_StubRunnable())
    t0 = time.perf_counter()
    result = runner.execute(wf)
    elapsed = time.perf_counter() - t0
    assert result.status == WorkflowStatus.COMPLETED
    return elapsed


def bench_io_threadpool() -> float:
    """Benchmark C: I/O-bound with ThreadPoolExecutor."""
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N_WORKERS) as pool:
        results = list(pool.map(io_bound_fetch, range(N_WORKERS)))
    elapsed = time.perf_counter() - t0
    assert len(results) == N_WORKERS
    return elapsed


def bench_io_sequential() -> float:
    """Baseline: I/O-bound sequential."""
    t0 = time.perf_counter()
    results = [io_bound_fetch(i) for i in range(N_WORKERS)]
    elapsed = time.perf_counter() - t0
    assert len(results) == N_WORKERS
    return elapsed


def bench_io_workflow_dag() -> float:
    """Benchmark D: I/O-bound with workflow DAG (threads)."""
    wf = _build_parallel_workflow(_make_io_step, N_WORKERS, "bench.io_workflow")
    runner = WorkflowRunner(runnable=_StubRunnable())
    t0 = time.perf_counter()
    result = runner.execute(wf)
    elapsed = time.perf_counter() - t0
    assert result.status == WorkflowStatus.COMPLETED
    return elapsed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all benchmarks and compare."""

    print("=" * 60)
    print("Multiprocessing vs Workflow DAG")
    print("=" * 60)
    print(f"  workers/steps    : {N_WORKERS}")
    print(f"  hash iterations  : {HASH_ITERATIONS:,}")
    print(f"  I/O sleep        : {IO_SLEEP_SECONDS}s per call")

    # ===== CPU-bound benchmarks =====
    print("\n--- CPU-Bound Benchmarks ---")

    print("\n  [A] Sequential (baseline)...")
    cpu_seq = bench_cpu_sequential()
    print(f"      Time: {cpu_seq:.3f}s")

    print("\n  [B] multiprocessing.Pool...")
    cpu_mp = bench_cpu_multiprocessing()
    print(f"      Time: {cpu_mp:.3f}s")

    print("\n  [C] Workflow DAG (threads, GIL-bound)...")
    cpu_wf = bench_cpu_workflow_dag()
    print(f"      Time: {cpu_wf:.3f}s")

    # ===== I/O-bound benchmarks =====
    print("\n--- I/O-Bound Benchmarks ---")

    print("\n  [D] Sequential (baseline)...")
    io_seq = bench_io_sequential()
    print(f"      Time: {io_seq:.3f}s")

    print("\n  [E] ThreadPoolExecutor...")
    io_tp = bench_io_threadpool()
    print(f"      Time: {io_tp:.3f}s")

    print("\n  [F] Workflow DAG (threads)...")
    io_wf = bench_io_workflow_dag()
    print(f"      Time: {io_wf:.3f}s")

    # ===== Summary =====
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    print(f"\n  {'Benchmark':<35s} {'Time':>8s} {'Speedup':>10s}")
    print(f"  {'─' * 35} {'─' * 8} {'─' * 10}")

    def row(label: str, val: float, baseline: float) -> None:
        speedup = baseline / val if val > 0 else 0
        marker = " *" if speedup > 1.5 else ""
        print(f"  {label:<35s} {val:>7.3f}s {speedup:>9.2f}x{marker}")

    print(f"\n  CPU-bound ({N_WORKERS} batches × {HASH_ITERATIONS:,} hashes):")
    row("Sequential (baseline)", cpu_seq, cpu_seq)
    row("multiprocessing.Pool", cpu_mp, cpu_seq)
    row("Workflow DAG (threads)", cpu_wf, cpu_seq)

    print(f"\n  I/O-bound ({N_WORKERS} fetches × {IO_SLEEP_SECONDS}s sleep):")
    row("Sequential (baseline)", io_seq, io_seq)
    row("ThreadPoolExecutor", io_tp, io_seq)
    row("Workflow DAG (threads)", io_wf, io_seq)

    # ===== Key takeaways =====
    print(f"""
  KEY TAKEAWAYS:
  ─────────────
  • CPU-bound: multiprocessing.Pool achieves ~{cpu_seq/cpu_mp:.1f}x speedup
    by escaping the GIL. Workflow DAG threads are GIL-bound: ~{cpu_seq/cpu_wf:.1f}x.

  • I/O-bound: ThreadPoolExecutor and Workflow DAG both achieve
    ~{io_seq/io_tp:.1f}x speedup — threads release the GIL during sleep/IO.

  • Workflow DAG adds orchestration overhead (~ms) but provides:
    context passing, step tracking, error handling, quality gates,
    serialisable audit trails, and retry semantics — worth it for
    data pipelines, not for tight numerical loops.
""")

    # ===== Assertions =====
    # CPU: On Windows, process spawn overhead can exceed benefits for small
    # workloads.  We only assert I/O-bound results where threads shine.
    import sys
    if sys.platform != "win32":
        assert cpu_mp < cpu_seq * 0.95, f"Pool should be faster on *nix: {cpu_mp:.3f}s"
    else:
        # On Windows (spawn, not fork), Pool startup may dominate small tasks
        print("  NOTE: On Windows, multiprocessing.Pool uses 'spawn' which has")
        print("        high startup cost.  Pool may be slower for small tasks.")

    # I/O: both parallel approaches should be faster than sequential
    assert io_tp < io_seq * 0.6, f"ThreadPool should be ~4x faster"
    assert io_wf < io_seq * 0.7, f"Workflow DAG should be meaningfully faster"

    print("[OK] All benchmarks passed — parallelism verified")
    print("=" * 60)


if __name__ == "__main__":
    main()
