#!/usr/bin/env python3
"""WorkSpec — The Universal Work Description for Tasks, Operations, and Workflows.

================================================================================
WHY WORKSPEC?
================================================================================

Every job engine needs to answer: "What work should be done?"  WorkSpec is
spine-core's answer — a single dataclass that describes ALL types of work::

    WorkSpec(kind="task",     name="fetch_filing",    params={...})
    WorkSpec(kind="operation", name="ingest_10k",      params={...})
    WorkSpec(kind="workflow", name="daily_etl",       params={...})
    WorkSpec(kind="step",     name="normalize_prices", params={...})

Why one type instead of four?  Because the execution infrastructure
(dispatcher, executor, ledger, DLQ) treats all work uniformly::

    dispatcher.submit(spec)     # Same method for task, operation, or workflow
    executor.execute(spec)      # Same executor interface
    ledger.record(spec, result) # Same audit trail

This is the **Uniform Work Contract** — the foundation of spine-core's
execution layer.


================================================================================
ARCHITECTURE: WorkSpec IN THE EXECUTION operation
================================================================================

::

    ┌──────────┐     WorkSpec      ┌────────────┐     RunRecord    ┌──────────┐
    │  Client  │──────────────────►│ Dispatcher │───────────────►│ Executor │
    │  (API/   │  kind="task"     │            │  status=PENDING │          │
    │   CLI)   │  name="fetch"    │ Validates  │  run_id=ulid() │ Runs the │
    └──────────┘  params={...}    │ Resolves   │                │ handler  │
                                   │ handler    │                │          │
                                   └────────────┘                └──────────┘

    WorkSpec Fields:
    ┌──────────────┬──────────────────────────────────────────────────────────┐
    │ kind         │ "task" | "operation" | "workflow" | "step"               │
    │ name         │ Handler name (matches registry key)                     │
    │ params       │ Dict of parameters passed to the handler                │
    │ description  │ Optional human-readable description                     │
    │ tags         │ Optional dict for filtering/routing                     │
    │ timeout_sec  │ Optional execution timeout                              │
    └──────────────┴──────────────────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/02_execution/01_workspec_basics.py

See Also:
    - :mod:`spine.execution` — WorkSpec, EventDispatcher
    - ``examples/02_execution/02_handler_registration.py`` — Registering handlers
    - ``examples/02_execution/03_dispatcher_basics.py`` — Submitting work
"""
from spine.execution import WorkSpec


def main():
    print("=" * 60)
    print("WorkSpec Basics")
    print("=" * 60)
    
    # === 1. Create a simple task spec ===
    print("\n[1] Simple Task Spec")
    task_spec = WorkSpec(
        kind="task",
        name="fetch_data",
        params={"url": "https://api.example.com/data"},
    )
    print(f"  Kind: {task_spec.kind}")
    print(f"  Name: {task_spec.name}")
    print(f"  Params: {task_spec.params}")
    
    # === 2. Create a operation spec with priority ===
    print("\n[2] Operation Spec with Priority")
    operation_spec = WorkSpec(
        kind="operation",
        name="data_ingestion",
        params={"source": "sec-edgar", "batch_size": 100},
        priority="high",
        lane="ingestion",
    )
    print(f"  Kind: {operation_spec.kind}")
    print(f"  Name: {operation_spec.name}")
    print(f"  Priority: {operation_spec.priority}")
    print(f"  Lane: {operation_spec.lane}")
    
    # === 3. Create a workflow spec with idempotency ===
    print("\n[3] Workflow Spec with Idempotency Key")
    workflow_spec = WorkSpec(
        kind="workflow",
        name="daily_reconciliation",
        params={"date": "2026-02-02"},
        idempotency_key="recon-2026-02-02",
        trigger_source="scheduler",
    )
    print(f"  Kind: {workflow_spec.kind}")
    print(f"  Name: {workflow_spec.name}")
    print(f"  Idempotency Key: {workflow_spec.idempotency_key}")
    print(f"  Trigger Source: {workflow_spec.trigger_source}")
    
    # === 4. WorkSpec with metadata ===
    print("\n[4] WorkSpec with Metadata")
    annotated_spec = WorkSpec(
        kind="task",
        name="analyze_filing",
        params={"cik": "0000320193", "form": "10-K"},
        metadata={
            "company": "Apple Inc.",
            "priority_reason": "earnings_release",
        },
    )
    print(f"  Name: {annotated_spec.name}")
    print(f"  Metadata: {annotated_spec.metadata}")
    
    # === 5. Retry configuration ===
    print("\n[5] WorkSpec with Retry Config")
    retry_spec = WorkSpec(
        kind="task",
        name="fetch_with_retry",
        params={"endpoint": "/filings"},
        max_retries=5,
        retry_delay_seconds=30,
    )
    print(f"  Max Retries: {retry_spec.max_retries}")
    print(f"  Retry Delay: {retry_spec.retry_delay_seconds}s")
    
    print("\n" + "=" * 60)
    print("[OK] WorkSpec Basics Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
