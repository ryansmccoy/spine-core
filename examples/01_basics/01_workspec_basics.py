#!/usr/bin/env python3
"""WorkSpec Basics - Creating work specifications.

This example demonstrates the core WorkSpec dataclass that defines
all work (tasks, pipelines, workflows, steps) in spine-core.

Run: python examples/01_basics/01_workspec_basics.py
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
    
    # === 2. Create a pipeline spec with priority ===
    print("\n[2] Pipeline Spec with Priority")
    pipeline_spec = WorkSpec(
        kind="pipeline",
        name="data_ingestion",
        params={"source": "sec-edgar", "batch_size": 100},
        priority="high",
        lane="ingestion",
    )
    print(f"  Kind: {pipeline_spec.kind}")
    print(f"  Name: {pipeline_spec.name}")
    print(f"  Priority: {pipeline_spec.priority}")
    print(f"  Lane: {pipeline_spec.lane}")
    
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
