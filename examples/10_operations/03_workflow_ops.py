#!/usr/bin/env python3
"""Workflow Operations — List, inspect, and run registered workflows.

WHY WORKFLOW OPS
────────────────
The ops layer bridges the orchestration Workflow registry with typed
request/response contracts.  This is how the API and CLI surface
workflow capabilities without importing the full orchestration engine.

ARCHITECTURE
────────────
    API / CLI
         │
         ▼
    ops.workflows.list_workflows(ctx)    → [{name, steps, domain}]
    ops.workflows.get_workflow(ctx, name)→ {definition detail}
    ops.workflows.run_workflow(ctx, ...)  → WorkflowResult
         │
         ├─▶ Workflow Registry (spine.orchestration)
         └─▶ WorkflowRunner / TrackedWorkflowRunner

    The Workflow registry and the Operation registry are separate:
      register_operation() → spine.framework (building blocks)
      register_workflow() → spine.orchestration (compositions)

    Workflows compose operations into multi-step processes with
    context passing, failure policies, and persistence.

BEST PRACTICES
──────────────
• Register workflows before calling list_workflows().
• Use run_workflow() for one-shot execution; use ManagedWorkflow
  for persistent, query-able runs.
• Check result.status — COMPLETED vs PARTIAL vs FAILED.

Run: python examples/10_operations/03_workflow_ops.py

See Also:
    02_run_management — per-run CRUD
    04_orchestration/01_workflow_basics — defining workflows
    04_orchestration/12_managed_workflow — zero-coupling builder
"""

import sys
from pathlib import Path

# Add examples directory to path for _db import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _db import get_demo_connection, load_env

from spine.orchestration.step_types import Step
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_registry import (
    register_workflow,
    clear_workflow_registry,
)
from spine.ops.context import OperationContext
from spine.ops.workflows import list_workflows, get_workflow, run_workflow
from spine.ops.requests import GetWorkflowRequest, RunWorkflowRequest


def _register_sample_workflows():
    """Register test workflows."""
    clear_workflow_registry()

    register_workflow(
        Workflow(
            name="finra.otc.weekly",
            domain="finra",
            steps=[
                Step.operation("download", "finra.otc.download"),
                Step.operation(
                    "normalize",
                    "finra.otc.normalize",
                    depends_on=["download"],
                ),
                Step.operation(
                    "aggregate",
                    "finra.otc.aggregate",
                    depends_on=["normalize"],
                ),
            ],
        )
    )

    register_workflow(
        Workflow(
            name="sec.daily.filings",
            domain="sec",
            steps=[
                Step.operation("fetch", "sec.daily.fetch"),
                Step.operation(
                    "parse",
                    "sec.daily.parse",
                    depends_on=["fetch"],
                ),
            ],
        )
    )


def main():
    print("=" * 60)
    print("Operations Layer — Workflow Operations")
    print("=" * 60)
    
    # Load .env and get connection (in-memory or persistent based on config)
    load_env()
    conn, info = get_demo_connection()
    print(f"  Backend: {'persistent' if info.persistent else 'in-memory'}")

    ctx = OperationContext(conn=conn, caller="example")

    _register_sample_workflows()

    # --- 1. List workflows ------------------------------------------------
    print("\n[1] List Registered Workflows")

    result = list_workflows(ctx)
    assert result.success
    print(f"  total: {result.total}")
    for wf in result.data:
        print(f"  {wf.name:30s}  steps={wf.step_count}")

    # --- 2. Get workflow detail -------------------------------------------
    print("\n[2] Get Workflow Detail: finra.otc.weekly")

    detail = get_workflow(ctx, GetWorkflowRequest(name="finra.otc.weekly"))
    assert detail.success
    print(f"  name: {detail.data.name}")
    print(f"  steps:")
    for step in detail.data.steps:
        deps = step.get("depends_on", [])
        dep_str = f" (depends_on: {deps})" if deps else ""
        print(f"    → {step['name']}: {step.get('operation', 'N/A')}{dep_str}")
    print(f"  metadata: {detail.data.metadata}")

    # --- 3. Get non-existent workflow -------------------------------------
    print("\n[3] Get Non-Existent Workflow")

    missing = get_workflow(ctx, GetWorkflowRequest(name="does.not.exist"))
    assert not missing.success
    print(f"  ✗ code    : {missing.error.code}")
    print(f"  ✗ message : {missing.error.message}")

    # --- 4. Run workflow (dry-run) ----------------------------------------
    print("\n[4] Run Workflow (dry-run)")

    dry_ctx = OperationContext(conn=conn, caller="example", dry_run=True)
    dry_run = run_workflow(
        dry_ctx,
        RunWorkflowRequest(
            name="finra.otc.weekly",
            params={"week_ending": "2026-02-06"},
        ),
    )
    assert dry_run.success
    print(f"  ✓ dry_run       : {dry_run.data.dry_run}")
    print(f"  would_execute   : {dry_run.data.would_execute}")

    # --- 5. Validation errors ---------------------------------------------
    print("\n[5] Validation: Empty Workflow Name")

    bad = get_workflow(ctx, GetWorkflowRequest(name=""))
    assert not bad.success
    print(f"  ✗ code    : {bad.error.code}")
    print(f"  ✗ message : {bad.error.message}")

    # --- 6. Result serialization ------------------------------------------
    print("\n[6] Result → dict")

    d = detail.to_dict()
    print(f"  keys: {sorted(d.keys())}")
    print(f"  success: {d['success']}")

    clear_workflow_registry()
    conn.close()
    print("\n✓ Workflow operations complete.")


if __name__ == "__main__":
    main()
