"""
Tracked Workflow Runner - Executes workflows with database persistence.

This module extends WorkflowRunner to add full database tracking:
- Progress tracking via core_manifest
- Error recording via core_anomalies
- Idempotency via manifest checks
- Full audit trail

This is the PRODUCTION runner that should be used when you need:
- Resumable workflows
- Failure tracking
- Idempotent execution
- Observability

For testing or simple cases, use the basic WorkflowRunner.

Tier: Intermediate (requires database connection)

Example:
    from spine.orchestration import Workflow, TrackedWorkflowRunner, Step

    workflow = Workflow(
        name="finra.otc_transparency.weekly_refresh",
        domain="finra.otc_transparency",
        steps=[
            Step.pipeline("ingest", "finra.otc.ingest"),
            Step.lambda_("validate", validate_fn),
            Step.pipeline("normalize", "finra.otc.normalize"),
        ],
    )

    # With database tracking
    runner = TrackedWorkflowRunner(conn)
    result = runner.execute(
        workflow,
        params={"tier": "NMS_TIER_1", "week_ending": "2026-01-10"},
        partition={"week_ending": "2026-01-10", "tier": "NMS_TIER_1"},
    )

    # Idempotent - running again with same partition skips
    result2 = runner.execute(workflow, params=..., partition=same_partition)
    # result2.status == "skipped" if already completed
"""

from __future__ import annotations

import structlog
from datetime import datetime, timezone
from typing import Any, Protocol

from spine.core.manifest import WorkManifest
from spine.core.anomalies import AnomalyRecorder, Severity, AnomalyCategory
from spine.orchestration.workflow import Workflow
from spine.orchestration.workflow_context import WorkflowContext
from spine.orchestration.workflow_runner import (
    WorkflowRunner,
    WorkflowResult,
    WorkflowStatus,
    StepExecution,
)
from spine.orchestration.step_types import Step, StepType, ErrorPolicy
from spine.orchestration.step_result import StepResult

logger = structlog.get_logger(__name__)


class Connection(Protocol):
    """Minimal SYNC DB connection interface."""

    def execute(self, sql: str, params: tuple = ()) -> Any: ...
    def commit(self) -> None: ...


def _make_stages(workflow: Workflow) -> list[str]:
    """Generate stage names for a workflow's manifest tracking."""
    stages = ["STARTED"]
    for step in workflow.steps:
        stages.append(f"STEP_{step.name.upper()}")
    stages.append("COMPLETED")
    return stages


class TrackedWorkflowRunner(WorkflowRunner):
    """
    Workflow runner with full database tracking.

    Features:
    - Progress tracking in core_manifest (one row per stage)
    - Error recording in core_anomalies
    - Idempotency via manifest checks (skip if already completed)
    - Automatic retry from last successful stage

    This extends the basic WorkflowRunner with persistence.
    """

    def __init__(
        self,
        conn: Connection,
        *,
        dispatcher=None,
        dry_run: bool = False,
        skip_if_completed: bool = True,
    ):
        """
        Initialize tracked workflow runner.

        Args:
            conn: Database connection (sync protocol)
            dispatcher: Optional dispatcher for pipeline execution
            dry_run: If True, pipeline steps return mock success
            skip_if_completed: If True, skip workflow if already completed
        """
        super().__init__(dispatcher=dispatcher, dry_run=dry_run)
        self.conn = conn
        self.skip_if_completed = skip_if_completed

    def execute(
        self,
        workflow: Workflow,
        params: dict[str, Any] | None = None,
        partition: dict[str, Any] | None = None,
        context: WorkflowContext | None = None,
        start_from: str | None = None,
    ) -> WorkflowResult:
        """
        Execute a workflow with database tracking.

        Args:
            workflow: The workflow to execute
            params: Input parameters
            partition: Partition key for tracking (REQUIRED for idempotency)
            context: Resume from existing context
            start_from: Start from specific step

        Returns:
            WorkflowResult with final status and context
        """
        # Require partition for tracking
        if partition is None:
            logger.warning(
                "workflow.no_partition",
                workflow=workflow.name,
                message="No partition provided - tracking disabled",
            )
            return super().execute(workflow, params, partition, context, start_from)

        # Initialize trackers
        domain = f"workflow.{workflow.name}"
        stages = _make_stages(workflow)
        manifest = WorkManifest(self.conn, domain=domain, stages=stages)
        anomaly_recorder = AnomalyRecorder(self.conn, domain=workflow.domain or domain)

        # Check idempotency
        if self.skip_if_completed and manifest.is_at_least(partition, "COMPLETED"):
            logger.info(
                "workflow.skipped",
                workflow=workflow.name,
                partition=partition,
                reason="already_completed",
            )
            # Return a result indicating skip
            ctx = context or WorkflowContext.create(
                workflow_name=workflow.name,
                params={**workflow.defaults, **(params or {})},
                partition=partition,
            )
            return WorkflowResult(
                workflow_name=workflow.name,
                run_id=ctx.run_id,
                status=WorkflowStatus.COMPLETED,
                context=ctx,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                step_executions=[],
                error_step=None,
                error="Skipped - already completed",
            )

        # Create context
        if context is None:
            context = WorkflowContext.create(
                workflow_name=workflow.name,
                params={**workflow.defaults, **(params or {})},
                partition=partition,
                dry_run=self._dry_run,
            )

        started_at = datetime.now(timezone.utc)
        step_executions: list[StepExecution] = []
        error_step: str | None = None
        error_msg: str | None = None
        final_status = WorkflowStatus.COMPLETED

        # Record workflow start
        manifest.advance_to(partition, "STARTED", execution_id=context.run_id)

        logger.info(
            "workflow.start",
            workflow=workflow.name,
            run_id=context.run_id,
            partition=partition,
            step_count=len(workflow.steps),
        )

        # Determine starting point (support resume from last successful)
        start_index = 0
        if start_from:
            start_index = workflow.step_index(start_from)
            if start_index < 0:
                from spine.orchestration.exceptions import GroupError
                raise GroupError(f"Start step not found: {start_from}")
        else:
            # Auto-resume: find last completed stage
            for i, step in enumerate(workflow.steps):
                stage_name = f"STEP_{step.name.upper()}"
                if manifest.has_stage(partition, stage_name):
                    start_index = i + 1  # Start from next step
                    logger.info(
                        "workflow.resume",
                        workflow=workflow.name,
                        from_step=workflow.steps[start_index].name if start_index < len(workflow.steps) else "END",
                        last_completed=step.name,
                    )

        # Execute steps
        current_index = start_index
        skip_to_step: str | None = None

        while current_index < len(workflow.steps):
            step = workflow.steps[current_index]

            # Handle choice step jumps
            if skip_to_step:
                if step.name != skip_to_step:
                    current_index += 1
                    continue
                skip_to_step = None

            # Execute step
            step_exec = self._execute_step(step, context, workflow)
            step_executions.append(step_exec)

            if step_exec.status == "completed":
                # Record progress in manifest
                stage_name = f"STEP_{step.name.upper()}"
                row_count = None
                if step_exec.result and step_exec.result.output:
                    row_count = step_exec.result.output.get("row_count")

                manifest.advance_to(
                    partition,
                    stage_name,
                    row_count=row_count,
                    execution_id=context.run_id,
                    duration_seconds=step_exec.duration_seconds,
                )

                # Update context with step output
                if step_exec.result:
                    context = context.with_output(step.name, step_exec.result.output)
                    if step_exec.result.context_updates:
                        context = context.with_params(step_exec.result.context_updates)

                    # Handle choice step branching
                    if step_exec.result.next_step:
                        skip_to_step = step_exec.result.next_step

            elif step_exec.status == "failed":
                error_step = step.name
                error_msg = step_exec.error

                # Record anomaly
                anomaly_recorder.record(
                    stage=f"step.{step.name}",
                    partition_key=partition,
                    severity=Severity.ERROR,
                    category=AnomalyCategory.STEP_FAILURE,
                    message=error_msg or "Step failed",
                    execution_id=context.run_id,
                    metadata={
                        "step_type": step.step_type.value,
                        "completed_steps": [s.step_name for s in step_executions if s.status == "completed"],
                    },
                )

                if step.on_error == ErrorPolicy.STOP:
                    final_status = WorkflowStatus.FAILED
                    break
                elif step.on_error == ErrorPolicy.CONTINUE:
                    final_status = WorkflowStatus.PARTIAL

            current_index += 1

        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()

        # Record final status
        if final_status == WorkflowStatus.COMPLETED:
            manifest.advance_to(
                partition,
                "COMPLETED",
                execution_id=context.run_id,
                step_count=len([s for s in step_executions if s.status == "completed"]),
                duration_seconds=duration,
            )
        elif final_status == WorkflowStatus.FAILED:
            # Record workflow-level anomaly
            anomaly_recorder.record(
                stage="workflow",
                partition_key=partition,
                severity=Severity.ERROR,
                category=AnomalyCategory.WORKFLOW_FAILURE,
                message=f"Workflow failed at step {error_step}: {error_msg}",
                execution_id=context.run_id,
                metadata={
                    "error_step": error_step,
                    "completed_steps": [s.step_name for s in step_executions if s.status == "completed"],
                    "duration_seconds": duration,
                },
            )

        logger.info(
            "workflow.complete",
            workflow=workflow.name,
            run_id=context.run_id,
            status=final_status.value,
            duration_seconds=duration,
            completed_steps=len([s for s in step_executions if s.status == "completed"]),
            failed_steps=len([s for s in step_executions if s.status == "failed"]),
        )

        return WorkflowResult(
            workflow_name=workflow.name,
            run_id=context.run_id,
            status=final_status,
            context=context,
            started_at=started_at,
            completed_at=completed_at,
            step_executions=step_executions,
            error_step=error_step,
            error=error_msg,
        )


# =============================================================================
# Query Functions for Monitoring
# =============================================================================


def get_workflow_state(
    conn: Connection,
    workflow_name: str,
    partition: dict[str, Any],
) -> dict[str, Any]:
    """
    Get the current state of a workflow run.

    Returns:
        Dict with stages, latest_stage, is_completed
    """
    import json
    domain = f"workflow.{workflow_name}"
    partition_str = json.dumps(partition, sort_keys=True)

    cursor = conn.execute(
        """
        SELECT stage, stage_rank, row_count, execution_id, updated_at
        FROM core_manifest
        WHERE domain = ? AND partition_key = ?
        ORDER BY stage_rank ASC
        """,
        (domain, partition_str),
    )

    stages = []
    for row in cursor.fetchall():
        stages.append({
            "stage": row[0],
            "rank": row[1],
            "row_count": row[2],
            "execution_id": row[3],
            "updated_at": row[4],
        })

    latest = stages[-1] if stages else None

    return {
        "workflow_name": workflow_name,
        "partition": partition,
        "stages": stages,
        "latest_stage": latest["stage"] if latest else None,
        "is_completed": latest["stage"] == "COMPLETED" if latest else False,
    }


def list_workflow_failures(
    conn: Connection,
    workflow_name: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    List recent workflow failures.

    Args:
        workflow_name: Optional filter by workflow
        limit: Maximum number to return

    Returns:
        List of anomaly records for workflow failures
    """
    query = """
        SELECT id, domain, stage, partition_key, severity, category,
               message, detected_at, metadata_json, resolved_at
        FROM core_anomalies
        WHERE category = 'WORKFLOW_FAILURE'
    """
    params: list[Any] = []

    if workflow_name:
        query += " AND domain LIKE ?"
        params.append(f"%{workflow_name}%")

    query += " ORDER BY detected_at DESC LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, tuple(params))
    import json

    return [
        {
            "id": row[0],
            "domain": row[1],
            "stage": row[2],
            "partition_key": row[3],
            "severity": row[4],
            "category": row[5],
            "message": row[6],
            "detected_at": row[7],
            "metadata": json.loads(row[8]) if row[8] else {},
            "resolved_at": row[9],
        }
        for row in cursor.fetchall()
    ]
