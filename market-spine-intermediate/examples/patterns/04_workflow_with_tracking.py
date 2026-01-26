"""
Pattern 04: Workflow with Database Tracking

Use this pattern when:
- Need to track workflow execution in core_manifest
- Need to record failures in core_anomalies
- Need to prevent duplicate processing (idempotency)
- Need auditability and observability

This is the production-ready pattern with full tracking!

Run: uv run python -m examples.patterns.04_workflow_with_tracking
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from typing import Any
from dataclasses import dataclass
from enum import Enum


# =============================================================================
# Simplified Spine-Core Types (for demonstration)
# =============================================================================

class StepType(str, Enum):
    PIPELINE = "pipeline"
    LAMBDA = "lambda"


class WorkflowStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StepResult:
    """Result of a single step."""
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    error_category: str | None = None
    
    @classmethod
    def ok(cls, output: dict[str, Any] | None = None):
        return cls(success=True, output=output or {})
    
    @classmethod
    def fail(cls, error: str, error_category: str = "UNKNOWN"):
        return cls(success=False, error=error, error_category=error_category)


class WorkflowContext:
    """Context passed between workflow steps."""
    
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self._outputs: dict[str, dict[str, Any]] = {}
    
    def set_output(self, step_name: str, output: dict[str, Any]):
        self._outputs[step_name] = output
    
    def get_output(self, step_name: str, key: str = None, default: Any = None) -> Any:
        output = self._outputs.get(step_name, {})
        if key:
            return output.get(key, default)
        return output


# =============================================================================
# Database Schema Setup (core_manifest and core_anomalies)
# =============================================================================

CORE_SCHEMA = """
-- Core manifest: tracks workflow/pipeline execution stages
CREATE TABLE IF NOT EXISTS core_manifest (
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    stage TEXT NOT NULL,
    stage_rank INTEGER NOT NULL,
    row_count INTEGER,
    metrics_json TEXT,
    execution_id TEXT,
    batch_id TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (domain, partition_key, stage)
);

-- Core anomalies: records errors and warnings
CREATE TABLE IF NOT EXISTS core_anomalies (
    anomaly_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    stage TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    metadata TEXT,
    resolved_at TEXT
);

-- Example domain table: OTC venue volume
CREATE TABLE IF NOT EXISTS finra_otc_venue_volume (
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    venue TEXT NOT NULL,
    total_shares REAL,
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    execution_id TEXT,
    PRIMARY KEY (week_ending, tier, symbol, venue, capture_id)
);
"""


def setup_database() -> sqlite3.Connection:
    """Create in-memory database with core schema."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(CORE_SCHEMA)
    return conn


# =============================================================================
# Work Manifest: Track Workflow Progress
# =============================================================================

class WorkManifest:
    """
    Track processing stages for work items.
    
    Uses core_manifest table to record progress through workflow stages.
    This enables:
    - Idempotency: Skip already-completed stages
    - Observability: See current state of any partition
    - Recovery: Resume from last completed stage
    """
    
    def __init__(
        self,
        conn: sqlite3.Connection,
        domain: str,
        stages: list[str],
    ):
        self.conn = conn
        self.domain = domain
        self.stages = stages
        self._stage_ranks = {stage: idx for idx, stage in enumerate(stages)}
    
    def _key_str(self, key: dict[str, Any]) -> str:
        """Serialize partition key to string."""
        return json.dumps(key, sort_keys=True)
    
    def advance_to(
        self,
        key: dict[str, Any],
        stage: str,
        *,
        row_count: int | None = None,
        execution_id: str | None = None,
        batch_id: str | None = None,
        **metrics,
    ) -> None:
        """
        Upsert stage record for a partition.
        
        This records that we've reached a particular stage for a given
        partition key. Used to track workflow progress.
        """
        if stage not in self._stage_ranks:
            raise ValueError(f"Unknown stage: {stage}. Valid: {self.stages}")
        
        partition_key = self._key_str(key)
        stage_rank = self._stage_ranks[stage]
        metrics_json = json.dumps(metrics) if metrics else None
        updated_at = datetime.now(timezone.utc).isoformat()
        
        self.conn.execute("""
            INSERT INTO core_manifest (
                domain, partition_key, stage, stage_rank,
                row_count, metrics_json, execution_id, batch_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (domain, partition_key, stage) DO UPDATE SET
                stage_rank = excluded.stage_rank,
                row_count = excluded.row_count,
                metrics_json = excluded.metrics_json,
                execution_id = excluded.execution_id,
                batch_id = excluded.batch_id,
                updated_at = excluded.updated_at
        """, (
            self.domain, partition_key, stage, stage_rank,
            row_count, metrics_json, execution_id, batch_id, updated_at,
        ))
        self.conn.commit()
        print(f"  📋 Manifest: {self.domain} → {stage} (partition={key})")
    
    def is_at_least(self, key: dict[str, Any], stage: str) -> bool:
        """Check if partition has reached at least the given stage."""
        partition_key = self._key_str(key)
        target_rank = self._stage_ranks.get(stage, -1)
        
        result = self.conn.execute("""
            SELECT MAX(stage_rank) FROM core_manifest
            WHERE domain = ? AND partition_key = ?
        """, (self.domain, partition_key)).fetchone()
        
        current_rank = result[0] if result and result[0] is not None else -1
        return current_rank >= target_rank
    
    def get_current_stage(self, key: dict[str, Any]) -> str | None:
        """Get the highest completed stage for a partition."""
        partition_key = self._key_str(key)
        
        result = self.conn.execute("""
            SELECT stage FROM core_manifest
            WHERE domain = ? AND partition_key = ?
            ORDER BY stage_rank DESC
            LIMIT 1
        """, (self.domain, partition_key)).fetchone()
        
        return result[0] if result else None


# =============================================================================
# Anomaly Recorder: Track Errors and Issues
# =============================================================================

class AnomalyRecorder:
    """
    Record anomalies to core_anomalies table.
    
    Anomalies are issues that should be tracked but don't necessarily
    stop processing. They provide:
    - Audit trail of problems
    - Alerting on patterns
    - Quality metrics over time
    """
    
    def __init__(self, conn: sqlite3.Connection, domain: str):
        self.conn = conn
        self.domain = domain
    
    def record(
        self,
        stage: str,
        partition_key: str,
        severity: str,
        category: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Record an anomaly.
        
        Severity levels: DEBUG, INFO, WARN, ERROR, CRITICAL
        Categories: QUALITY_GATE, NETWORK, DATA_QUALITY, STEP_FAILURE, WORKFLOW_FAILURE
        """
        anomaly_id = str(uuid.uuid4())
        detected_at = datetime.now(timezone.utc).isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        
        self.conn.execute("""
            INSERT INTO core_anomalies (
                anomaly_id, domain, stage, partition_key,
                severity, category, message, detected_at, metadata, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (
            anomaly_id, self.domain, stage, partition_key,
            severity, category, message, detected_at, metadata_json,
        ))
        self.conn.commit()
        
        icon = {"DEBUG": "🔍", "INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}.get(severity, "❓")
        print(f"  {icon} Anomaly: [{severity}] {category} - {message}")
        
        return anomaly_id
    
    def resolve(self, anomaly_id: str) -> None:
        """Mark an anomaly as resolved."""
        resolved_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute("""
            UPDATE core_anomalies SET resolved_at = ?
            WHERE anomaly_id = ?
        """, (resolved_at, anomaly_id))
        self.conn.commit()


# =============================================================================
# Pipelines (Do the Actual Work)
# =============================================================================

def ingest_pipeline(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    """
    Pipeline: Ingest OTC data for a week.
    
    This is where actual data processing happens.
    Returns metrics that can be used by lambda validators.
    """
    week_ending = params["week_ending"]
    tier = params["tier"]
    execution_id = params.get("execution_id")
    
    # Simulate fetching data
    records = [
        {"symbol": "AAPL", "venue": "NITE", "shares": 1000000},
        {"symbol": "AAPL", "venue": "CDRG", "shares": 500000},
        {"symbol": "TSLA", "venue": "NITE", "shares": 750000},
        {"symbol": "TSLA", "venue": "VIRTU", "shares": None},  # Bad record
        {"symbol": "MSFT", "venue": "NITE", "shares": 2000000},
    ]
    
    # Generate capture_id for this run
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    capture_id = f"finra.otc.INGEST.{week_ending}|{tier}.{timestamp}"
    captured_at = datetime.now(timezone.utc).isoformat()
    
    # Write valid records to database
    valid_records = 0
    null_records = 0
    
    for record in records:
        if record["shares"] is None:
            null_records += 1
            continue
        
        conn.execute("""
            INSERT INTO finra_otc_venue_volume (
                week_ending, tier, symbol, venue, total_shares,
                capture_id, captured_at, execution_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            week_ending, tier, record["symbol"], record["venue"],
            record["shares"], capture_id, captured_at, execution_id,
        ))
        valid_records += 1
    
    conn.commit()
    
    return {
        "row_count": valid_records,
        "null_count": null_records,
        "capture_id": capture_id,
        "null_rate": null_records / len(records) if records else 0,
    }


def normalize_pipeline(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    """Pipeline: Normalize ingested data."""
    # In real implementation, this would transform/clean data
    return {
        "row_count": 4,
        "normalized": True,
    }


def aggregate_pipeline(conn: sqlite3.Connection, params: dict[str, Any]) -> dict[str, Any]:
    """Pipeline: Aggregate to summary level."""
    # In real implementation, this would compute aggregates
    return {
        "row_count": 3,
        "symbols_processed": 3,
    }


# =============================================================================
# Lambda Validators (Lightweight Checks Between Steps)
# =============================================================================

def validate_ingest(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """
    Lambda: Validate ingest output before normalize.
    
    This is a LIGHTWEIGHT check - no database queries, no business logic.
    Just validates metrics from the previous step.
    """
    result = ctx.get_output("ingest")
    if not result:
        return StepResult.fail("No ingest output", "STEP_ERROR")
    
    row_count = result.get("row_count", 0)
    if row_count < 1:
        return StepResult.fail(f"No records ingested: {row_count}", "QUALITY_GATE")
    
    null_rate = result.get("null_rate", 0)
    if null_rate > 0.25:  # More than 25% null values
        return StepResult.fail(f"Null rate too high: {null_rate:.1%}", "DATA_QUALITY")
    
    return StepResult.ok(output={"validated": True, "row_count": row_count})


def validate_normalize(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Lambda: Validate normalize output before aggregate."""
    result = ctx.get_output("normalize")
    if not result:
        return StepResult.fail("No normalize output", "STEP_ERROR")
    
    if not result.get("normalized"):
        return StepResult.fail("Normalization not complete", "STEP_ERROR")
    
    return StepResult.ok()


# =============================================================================
# Workflow Execution with Full Tracking
# =============================================================================

@dataclass
class WorkflowResult:
    """Result of workflow execution."""
    status: WorkflowStatus
    run_id: str
    completed_steps: list[str]
    error_step: str | None = None
    error: str | None = None
    duration_seconds: float = 0.0


def execute_workflow_with_tracking(
    conn: sqlite3.Connection,
    workflow_name: str,
    params: dict[str, Any],
) -> WorkflowResult:
    """
    Execute a workflow with full database tracking.
    
    This demonstrates the production pattern where:
    1. core_manifest tracks stage progression
    2. core_anomalies records any failures
    3. Idempotency is enforced via manifest checks
    """
    
    run_id = str(uuid.uuid4())
    partition_key = {"week_ending": params["week_ending"], "tier": params["tier"]}
    partition_key_str = json.dumps(partition_key, sort_keys=True)
    
    # Initialize trackers
    manifest = WorkManifest(
        conn,
        domain=f"workflow.{workflow_name}",
        stages=["STARTED", "INGESTED", "INGEST_VALIDATED", "NORMALIZED", "NORMALIZE_VALIDATED", "AGGREGATED", "COMPLETED"]
    )
    anomaly_recorder = AnomalyRecorder(conn, domain=workflow_name)
    
    start_time = datetime.now(timezone.utc)
    completed_steps: list[str] = []
    ctx = WorkflowContext(params)
    
    print(f"\n🚀 Starting workflow: {workflow_name}")
    print(f"   Run ID: {run_id}")
    print(f"   Params: {params}")
    
    # Check for idempotency - skip if already completed
    if manifest.is_at_least(partition_key, "COMPLETED"):
        print(f"\n⏭️  Skipping: Already completed for {partition_key}")
        return WorkflowResult(
            status=WorkflowStatus.COMPLETED,
            run_id=run_id,
            completed_steps=["skipped - already complete"],
        )
    
    # Record workflow start
    manifest.advance_to(partition_key, "STARTED", execution_id=run_id)
    
    try:
        # Step 1: Ingest (Pipeline)
        print("\n📥 Step 1: Ingest")
        result = ingest_pipeline(conn, {**params, "execution_id": run_id})
        ctx.set_output("ingest", result)
        manifest.advance_to(partition_key, "INGESTED", row_count=result["row_count"], execution_id=run_id)
        completed_steps.append("ingest")
        print(f"   ✅ Ingested {result['row_count']} records (null_rate: {result['null_rate']:.1%})")
        
        # Step 2: Validate Ingest (Lambda)
        print("\n🔍 Step 2: Validate Ingest")
        validation = validate_ingest(ctx, {})
        if not validation.success:
            raise ValueError(f"Validation failed: {validation.error}")
        ctx.set_output("validate_ingest", validation.output)
        manifest.advance_to(partition_key, "INGEST_VALIDATED", execution_id=run_id)
        completed_steps.append("validate_ingest")
        print(f"   ✅ Validation passed")
        
        # Step 3: Normalize (Pipeline)
        print("\n🔄 Step 3: Normalize")
        result = normalize_pipeline(conn, params)
        ctx.set_output("normalize", result)
        manifest.advance_to(partition_key, "NORMALIZED", row_count=result["row_count"], execution_id=run_id)
        completed_steps.append("normalize")
        print(f"   ✅ Normalized {result['row_count']} records")
        
        # Step 4: Validate Normalize (Lambda)
        print("\n🔍 Step 4: Validate Normalize")
        validation = validate_normalize(ctx, {})
        if not validation.success:
            raise ValueError(f"Validation failed: {validation.error}")
        manifest.advance_to(partition_key, "NORMALIZE_VALIDATED", execution_id=run_id)
        completed_steps.append("validate_normalize")
        print(f"   ✅ Validation passed")
        
        # Step 5: Aggregate (Pipeline)
        print("\n📊 Step 5: Aggregate")
        result = aggregate_pipeline(conn, params)
        ctx.set_output("aggregate", result)
        manifest.advance_to(partition_key, "AGGREGATED", row_count=result["row_count"], execution_id=run_id)
        completed_steps.append("aggregate")
        print(f"   ✅ Aggregated to {result['symbols_processed']} symbols")
        
        # Workflow complete
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        manifest.advance_to(
            partition_key, 
            "COMPLETED", 
            execution_id=run_id,
            step_count=len(completed_steps),
            duration_seconds=duration,
        )
        
        print(f"\n✅ Workflow completed successfully in {duration:.2f}s")
        print(f"   Steps completed: {completed_steps}")
        
        return WorkflowResult(
            status=WorkflowStatus.COMPLETED,
            run_id=run_id,
            completed_steps=completed_steps,
            duration_seconds=duration,
        )
        
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        error_step = completed_steps[-1] if completed_steps else "start"
        
        # Record anomaly
        anomaly_recorder.record(
            stage=f"step.{error_step}",
            partition_key=partition_key_str,
            severity="ERROR",
            category="WORKFLOW_FAILURE",
            message=str(e),
            metadata={"run_id": run_id, "completed_steps": completed_steps},
        )
        
        print(f"\n❌ Workflow failed at step: {error_step}")
        print(f"   Error: {e}")
        
        return WorkflowResult(
            status=WorkflowStatus.FAILED,
            run_id=run_id,
            completed_steps=completed_steps,
            error_step=error_step,
            error=str(e),
            duration_seconds=duration,
        )


# =============================================================================
# Query Functions for Monitoring
# =============================================================================

def show_manifest_state(conn: sqlite3.Connection):
    """Display current manifest state."""
    print("\n📋 Manifest State:")
    print("-" * 80)
    
    rows = conn.execute("""
        SELECT domain, partition_key, stage, stage_rank, row_count, execution_id, updated_at
        FROM core_manifest
        ORDER BY domain, partition_key, stage_rank
    """).fetchall()
    
    for row in rows:
        print(f"  {row[0]:40} | {row[2]:20} | rows={row[4]} | exec={row[5][:8] if row[5] else 'N/A'}...")


def show_anomalies(conn: sqlite3.Connection):
    """Display recorded anomalies."""
    print("\n⚠️  Anomalies:")
    print("-" * 80)
    
    rows = conn.execute("""
        SELECT severity, category, message, stage, detected_at, resolved_at
        FROM core_anomalies
        ORDER BY detected_at DESC
    """).fetchall()
    
    if not rows:
        print("  (No anomalies recorded)")
        return
    
    for row in rows:
        status = "✅ Resolved" if row[5] else "🔴 Open"
        print(f"  [{row[0]}] {row[1]}: {row[2]}")
        print(f"       Stage: {row[3]} | {status}")


def show_data_sample(conn: sqlite3.Connection):
    """Show sample of ingested data."""
    print("\n📊 Data Sample (finra_otc_venue_volume):")
    print("-" * 80)
    
    rows = conn.execute("""
        SELECT week_ending, tier, symbol, venue, total_shares, capture_id
        FROM finra_otc_venue_volume
        LIMIT 5
    """).fetchall()
    
    for row in rows:
        print(f"  {row[0]} | {row[1]} | {row[2]:4} | {row[3]:8} | shares={row[4]:>10,.0f}")


# =============================================================================
# Main Demo
# =============================================================================

def main():
    """Demonstrate workflow with full database tracking."""
    
    print("=" * 80)
    print("Pattern 04: Workflow with Database Tracking")
    print("=" * 80)
    
    # Setup
    conn = setup_database()
    
    # First run - should complete successfully
    print("\n" + "=" * 80)
    print("FIRST RUN: Execute workflow")
    print("=" * 80)
    
    result = execute_workflow_with_tracking(
        conn,
        workflow_name="finra.otc_transparency.weekly_refresh",
        params={"week_ending": "2025-01-09", "tier": "NMS_TIER_1"},
    )
    
    # Show tracking state
    show_manifest_state(conn)
    show_anomalies(conn)
    show_data_sample(conn)
    
    # Second run with same params - should skip (idempotency)
    print("\n" + "=" * 80)
    print("SECOND RUN: Same params (should skip due to idempotency)")
    print("=" * 80)
    
    result = execute_workflow_with_tracking(
        conn,
        workflow_name="finra.otc_transparency.weekly_refresh",
        params={"week_ending": "2025-01-09", "tier": "NMS_TIER_1"},
    )
    
    # Third run with different params - should execute
    print("\n" + "=" * 80)
    print("THIRD RUN: Different tier (should execute)")
    print("=" * 80)
    
    result = execute_workflow_with_tracking(
        conn,
        workflow_name="finra.otc_transparency.weekly_refresh",
        params={"week_ending": "2025-01-09", "tier": "NMS_TIER_2"},
    )
    
    # Final state
    print("\n" + "=" * 80)
    print("FINAL STATE")
    print("=" * 80)
    show_manifest_state(conn)
    show_anomalies(conn)
    
    conn.close()
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
