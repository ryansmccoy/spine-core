"""Runnable Protocol — Unified pipeline execution interface.

WHY STRUCTURAL TYPING (PROTOCOLS)
─────────────────────────────────
WorkflowRunner needs to submit pipeline work, but it shouldn’t know
whether the backend is EventDispatcher, a Celery queue, or a mock.
The Runnable *protocol* (PEP 544) defines the contract via structural
typing — any class with `submit_pipeline_sync()` satisfies it
automatically, with no inheritance required.

ARCHITECTURE
────────────
    ┌─────────────────┐
    │ WorkflowRunner  │
    │  (consumer)     │
    └────────┬────────┘
             │ runnable.submit_pipeline_sync()
             ▼
    ┌─────────────────────────────────────┐
    │  Runnable  (Protocol)                  │
    │  submit_pipeline_sync(name, params,    │
    │      parent_run_id, correlation_id)     │
    │  → PipelineRunResult                   │
    └────────────┬───────┬───────┬───────────┘
                 │       │       │
         ┌───────┴┐  ┌───┴───┐  ┌─┴───────┐
         │EventDisp│  │Celery │  │MockRunn │
         │atcher   │  │Backend│  │able     │
         └─────────┘  └───────┘  └─────────┘

    isinstance(my_obj, Runnable) returns True if my_obj has
    the right method signature — no base class needed.

PipelineRunResult FIELDS
────────────────────────
    Field       Type          Purpose
    ─────────── ───────────── ──────────────────────
    status      str           "completed" | "failed"
    succeeded   bool          Derived from status
    run_id      str | None    Execution tracking ID
    error       str | None    Error message if failed
    metrics     dict | None   {rows_processed, duration_ms}

BEST PRACTICES
──────────────
• Type-hint with Runnable, never with EventDispatcher directly.
• Use MockRunnable in tests to avoid real execution.
• Check result.succeeded before proceeding to the next step.
• Pass correlation_id for cross-workflow tracing.

Run: python examples/04_orchestration/15_runnable_protocol.py

See Also:
    08_tracked_runner — TrackedWorkflowRunner uses Runnable
    03_workflow_context — context threading through runnables
"""

from spine.execution.runnable import PipelineRunResult, Runnable
from spine.orchestration import (
    Workflow,
    Step,
    StepResult,
    WorkflowContext,
    WorkflowRunner,
)


def main():
    print("=" * 60)
    print("Runnable Protocol — Unified Execution Interface")
    print("=" * 60)

    # === 1. PipelineRunResult ===
    print("\n[1] PipelineRunResult Basics")

    success = PipelineRunResult(
        status="completed",
        run_id="run-abc123",
        metrics={"rows_processed": 1000, "duration_ms": 450},
    )
    print(f"  Status: {success.status}")
    print(f"  Succeeded: {success.succeeded}")
    print(f"  Metrics: {success.metrics}")
    print(f"  Run ID: {success.run_id}")

    failure = PipelineRunResult(
        status="failed",
        error="Connection refused: FINRA API unreachable",
    )
    print(f"\n  Failed: status={failure.status}, succeeded={failure.succeeded}")
    print(f"  Error: {failure.error}")

    # === 2. Custom Runnable (protocol compliance) ===
    print("\n[2] Custom Runnable (protocol satisfaction)")

    class MockRunnable:
        """A minimal class that satisfies the Runnable protocol.

        No inheritance needed — just implement ``submit_pipeline_sync``.
        """

        def __init__(self):
            self.calls: list[tuple[str, dict]] = []

        def submit_pipeline_sync(
            self,
            pipeline_name: str,
            params: dict | None = None,
            *,
            parent_run_id: str | None = None,
            correlation_id: str | None = None,
        ) -> PipelineRunResult:
            self.calls.append((pipeline_name, params or {}))
            return PipelineRunResult(
                status="completed",
                run_id=f"mock-{len(self.calls):03d}",
                metrics={"rows": 100},
            )

    mock = MockRunnable()

    # Verify protocol compliance at runtime
    is_runnable = isinstance(mock, Runnable)
    print(f"  MockRunnable satisfies Runnable protocol: {is_runnable}")

    result = mock.submit_pipeline_sync("test.pipeline", {"key": "value"})
    print(f"  Result: {result.status}, run_id={result.run_id}")
    print(f"  Calls recorded: {mock.calls}")

    # === 3. WorkflowRunner with custom Runnable ===
    print("\n[3] WorkflowRunner Accepts Any Runnable")

    def ingest_step(ctx: WorkflowContext, config: dict) -> StepResult:
        """Ingest step — calls a pipeline via the Runnable."""
        print(f"      [ingest] Running for tier={ctx.params.get('tier')}")
        return StepResult.ok(output={"records": 500})

    def validate_step(ctx: WorkflowContext, config: dict) -> StepResult:
        """Validation step."""
        records = ctx.get_output("ingest", "records", 0)
        print(f"      [validate] Checking {records} records")
        return StepResult.ok(output={"valid": records, "rejected": 3})

    workflow = Workflow(
        name="demo.runnable_workflow",
        steps=[
            Step.lambda_("ingest", ingest_step),
            Step.lambda_("validate", validate_step),
        ],
    )

    # Pass the mock into WorkflowRunner — no concrete dispatcher needed
    runner = WorkflowRunner(runnable=mock)
    result = runner.execute(workflow, params={"tier": "NMS_TIER_1"})

    print(f"\n  Workflow status: {result.status.value}")
    for step_exec in result.step_executions:
        output = step_exec.result.output if step_exec.result else {}
        print(f"    ✓ {step_exec.step_name}: {output}")

    # === 4. EventDispatcher as Runnable (canonical) ===
    print("\n[4] EventDispatcher as Runnable (canonical path)")

    from spine.execution.dispatcher import EventDispatcher
    from spine.execution.executors import MemoryExecutor

    # EventDispatcher satisfies Runnable
    executor = MemoryExecutor(handlers={})
    dispatcher = EventDispatcher(executor=executor)
    print(f"  EventDispatcher is Runnable: {isinstance(dispatcher, Runnable)}")

    # In production code:
    # runner = WorkflowRunner(runnable=dispatcher)
    # result = runner.execute(workflow, params={...})

    # === 5. Decision guide ===
    print("\n[5] Which Runnable to Use?")
    print()
    print("  EventDispatcher (canonical):")
    print("    ✓ Full run tracking (RunRecord, events, external_ref)")
    print("    ✓ Supports all executors (Memory, Local, Async, Process)")
    print("    ✓ Required for production workflows")
    print()
    print("  Custom Runnable (for external orchestrators):")
    print("    ✓ Bridge to Windmill, Kestra, Airflow, etc.")
    print("    ✓ Just implement submit_pipeline_sync()")
    print("    ✓ WorkflowRunner doesn't care about the backend")

    print("\n" + "=" * 60)
    print("[OK] Runnable Protocol Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
