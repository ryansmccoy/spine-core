"""TrackedWorkflowRunner — Database-backed workflow execution.

WHY DATABASE-BACKED WORKFLOWS
─────────────────────────────
In-memory workflows vanish on crash.  TrackedWorkflowRunner persists
every step’s status, output, and error to the database.  This gives you:
• Idempotency — skip already-completed steps on restart.
• Progress monitoring — see what step a long workflow is on.
• Post-mortem — inspect failed step’s output and error.
• Audit trail — who ran what, when, with which parameters.

ARCHITECTURE
────────────
    ┌─────────────────────┐
    │ TrackedWorkflowRunner │
    └──────────┬──────────┘
               │ run(workflow, params)
               ▼
    ┌──────────────────────────────────────┐
    │ For each Step:                         │
    │   1. Check DB — already completed?     │
    │   2. No → execute step function         │
    │   3. INSERT/UPDATE core_workflow_steps  │
    │   4. StepResult → WorkflowContext       │
    └──────────────────────────────────────┘
               │ WorkflowResult
               ▼
    ┌──────────────────────────────────────┐
    │ status: COMPLETED | FAILED | PARTIAL  │
    │ step_results: {step_name: StepResult}  │
    │ duration, error, outputs               │
    └──────────────────────────────────────┘

WORKFLOW STATUS TRANSITIONS
───────────────────────────
    PENDING → RUNNING → COMPLETED
                     → FAILED    (step failed, workflow aborted)
                     → PARTIAL   (some steps succeeded, some failed)

BEST PRACTICES
──────────────
• Use TrackedWorkflowRunner for any workflow that runs > 30 seconds.
• Always provide partition keys for idempotent re-runs.
• Inspect WorkflowResult.step_results for per-step diagnostics.
• Use WorkflowContext.get_output() to chain step results.

Run: python examples/04_orchestration/08_tracked_runner.py

See Also:
    03_workflow_context — how data flows between steps
    15_runnable_protocol — pluggable execution backends
"""

import sqlite3
from spine.core import create_core_tables
from spine.execution.runnable import PipelineRunResult, Runnable
from spine.orchestration import (
    Workflow,
    Step,
    StepResult,
    WorkflowContext,
    TrackedWorkflowRunner,
    WorkflowStatus,
)


class _NoOpRunnable:
    """Minimal Runnable for examples that only use lambda steps."""

    def submit_pipeline_sync(self, pipeline_name, params=None, *, parent_run_id=None, correlation_id=None):
        return PipelineRunResult(status="completed")


def main():
    """Demonstrate TrackedWorkflowRunner for persistent workflows."""
    print("=" * 60)
    print("TrackedWorkflowRunner - Database-Backed Workflows")
    print("=" * 60)
    
    # Create in-memory database with core tables
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    # Also create manifest table for tracking
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core_manifest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            stage TEXT NOT NULL,
            rank INTEGER NOT NULL,
            row_count INTEGER,
            execution_id TEXT,
            batch_id TEXT,
            metrics TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(domain, partition_key, stage)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS core_anomalies (
            id TEXT PRIMARY KEY,
            domain TEXT NOT NULL,
            partition_key TEXT,
            stage TEXT,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            metadata TEXT,
            detected_at TEXT NOT NULL,
            resolved_at TEXT,
            resolution TEXT
        )
    """)
    conn.commit()
    
    print("\n1. Defining a workflow with lambda steps...")
    
    # Define step functions
    def ingest_step(ctx: WorkflowContext, config: dict) -> StepResult:
        """Ingest data from source."""
        print(f"      Ingesting data for {ctx.params.get('tier')}...")
        return StepResult.ok(
            output={"record_count": 1000, "source": "finra_api"},
        )
    
    def validate_step(ctx: WorkflowContext, config: dict) -> StepResult:
        """Validate ingested data."""
        record_count = ctx.get_output("ingest", "record_count", 0)
        print(f"      Validating {record_count} records...")
        
        if record_count < 100:
            return StepResult.fail("Too few records")
        
        return StepResult.ok(
            output={"valid_count": record_count - 5, "rejected": 5},
        )
    
    def normalize_step(ctx: WorkflowContext, config: dict) -> StepResult:
        """Normalize validated data."""
        valid_count = ctx.get_output("validate", "valid_count", 0)
        print(f"      Normalizing {valid_count} records...")
        return StepResult.ok(
            output={"normalized_count": valid_count},
        )
    
    # Create workflow
    workflow = Workflow(
        name="finra.otc_transparency.weekly_refresh",
        domain="finra.otc_transparency",
        steps=[
            Step.lambda_("ingest", ingest_step),
            Step.lambda_("validate", validate_step),
            Step.lambda_("normalize", normalize_step),
        ],
    )
    
    print(f"   Workflow: {workflow.name}")
    print(f"   Domain: {workflow.domain}")
    print(f"   Steps: {[s.name for s in workflow.steps]}")
    
    print("\n2. Creating TrackedWorkflowRunner...")
    
    runner = TrackedWorkflowRunner(conn, runnable=_NoOpRunnable())
    
    print("\n3. Executing workflow (first run)...")
    
    partition = {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}
    
    result = runner.execute(
        workflow,
        params={"tier": "NMS_TIER_1", "week_ending": "2025-12-26"},
        partition=partition,
    )
    
    print(f"\n   Result:")
    print(f"   Status: {result.status.value}")
    print(f"   Run ID: {result.run_id[:8]}...")
    
    print("\n   Step executions:")
    for step_exec in result.step_executions:
        icon = "✓" if step_exec.status == "completed" else "✗"
        output = step_exec.result.output if step_exec.result else {}
        print(f"     {icon} {step_exec.step_name}: {output}")
    
    print("\n4. Idempotent re-execution (same partition)...")
    
    result2 = runner.execute(
        workflow,
        params={"tier": "NMS_TIER_1", "week_ending": "2025-12-26"},
        partition=partition,
    )
    
    print(f"   Status: {result2.status.value}")
    if not result2.step_executions and result2.error:
        print(f"   → {result2.error}")
    
    print("\n5. Checking manifest progress...")
    
    cursor.execute("""
        SELECT stage, stage_rank, row_count
        FROM core_manifest
        WHERE domain = 'finra.otc_transparency'
        ORDER BY stage_rank
    """)
    
    rows = cursor.fetchall()
    if rows:
        print("   Manifest stages:")
        for row in rows:
            print(f"     Stage {row[1]}: {row[0]} ({row[2]} rows)")
    else:
        print("   (No manifest entries - basic runner used)")
    
    print("\n6. Different partition (new execution)...")
    
    partition2 = {"week_ending": "2025-12-26", "tier": "NMS_TIER_2"}
    
    result3 = runner.execute(
        workflow,
        params={"tier": "NMS_TIER_2", "week_ending": "2025-12-26"},
        partition=partition2,
    )
    
    print(f"   Status: {result3.status.value}")
    print(f"   Run ID: {result3.run_id[:8]}... (different from first)")
    
    conn.close()
    print("\n" + "=" * 60)
    print("TrackedWorkflowRunner demo complete!")


if __name__ == "__main__":
    main()
