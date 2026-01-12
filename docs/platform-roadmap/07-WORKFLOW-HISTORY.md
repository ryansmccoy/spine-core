# Workflow History

> **Purpose:** Persist workflow execution history for audit and debugging.
> **Tier:** Intermediate
> **Module:** `spine.orchestration.history`
> **Last Updated:** 2026-01-11

---

## Overview

Current state:
- No execution history persistence
- Logs only in stdout
- No ability to query past runs

Target state:
- Persistent workflow run records
- Step-level execution details
- Error and output capture
- Query API for history
- Retention policies

---

## Design Principles

1. **Complete** - Capture all execution details
2. **Queryable** - Filter by date, status, pipeline
3. **Efficient** - Indexed for common queries
4. **Configurable** - Retention policies
5. **Consistent** - Same schema across databases

> **Design Principle Note: Immutability (#5) vs State Tracking**
> 
> `WorkflowRun` and `StepRun` are **mutable by design** because they track 
> evolving execution state. This is a pragmatic exception to Principle #5.
> 
> For audit trail, state changes should be recorded via events:
> ```python
> history.record_event(run_id, "status_changed", {"old": "RUNNING", "new": "COMPLETED"})
> ```
> 
> The historical record (events) is immutable; the current state (WorkflowRun) 
> is mutable for efficiency.

---

## Core Types

```python
# spine/orchestration/history/types.py
"""
Workflow history types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    """Step execution status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class WorkflowRun:
    """
    Record of a workflow execution.
    
    Captures start, end, status, and summary metrics.
    """
    run_id: str
    workflow_name: str
    domain: str | None = None
    partition_key: str | None = None
    status: WorkflowStatus = WorkflowStatus.PENDING
    
    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Context
    params: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    
    # Results
    error: str | None = None
    error_category: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    triggered_by: str = "manual"  # manual, schedule, api
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def duration_seconds(self) -> float | None:
        """Calculate execution duration."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def is_terminal(self) -> bool:
        """Check if workflow is in terminal state."""
        return self.status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "run_id": self.run_id,
            "workflow_name": self.workflow_name,
            "domain": self.domain,
            "partition_key": self.partition_key,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "params": self.params,
            "outputs": self.outputs,
            "error": self.error,
            "error_category": self.error_category,
            "metrics": self.metrics,
            "triggered_by": self.triggered_by,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class StepRun:
    """
    Record of a step execution within a workflow.
    """
    step_id: str
    run_id: str  # Parent workflow run
    step_name: str
    step_type: str
    step_order: int
    status: StepStatus = StepStatus.PENDING
    
    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Results
    input_params: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_category: str | None = None
    
    # Metrics
    records_processed: int | None = None
    quality_passed: bool | None = None
    quality_metrics: dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "run_id": self.run_id,
            "step_name": self.step_name,
            "step_type": self.step_type,
            "step_order": self.step_order,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "records_processed": self.records_processed,
            "quality_passed": self.quality_passed,
        }
```

---

## History Store

```python
# spine/orchestration/history/store.py
"""
Workflow history storage.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Iterator

from .types import WorkflowRun, StepRun, WorkflowStatus, StepStatus
from spine.core.storage import DatabaseAdapter


log = logging.getLogger(__name__)


class HistoryStore:
    """
    Persistent storage for workflow execution history.
    
    Features:
    - Workflow and step run persistence
    - Query by status, date range, domain
    - Retention policy enforcement
    
    Usage:
        store = HistoryStore(db_adapter)
        
        # Record workflow start
        run = WorkflowRun(run_id="abc123", workflow_name="ingest")
        store.save_workflow_run(run)
        
        # Record step
        step = StepRun(step_id="s1", run_id="abc123", step_name="fetch")
        store.save_step_run(step)
        
        # Query history
        runs = store.list_workflow_runs(status=WorkflowStatus.COMPLETED)
    """
    
    def __init__(self, db: DatabaseAdapter):
        self.db = db
    
    # -------------------------------------------------------------------------
    # Workflow Runs
    # -------------------------------------------------------------------------
    
    def save_workflow_run(self, run: WorkflowRun) -> None:
        """Insert or update workflow run."""
        self.db.execute(
            """
            INSERT INTO workflow_runs (
                run_id, workflow_name, domain, partition_key, status,
                started_at, completed_at, params, outputs,
                error, error_category, metrics, triggered_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (run_id) DO UPDATE SET
                status = excluded.status,
                completed_at = excluded.completed_at,
                outputs = excluded.outputs,
                error = excluded.error,
                error_category = excluded.error_category,
                metrics = excluded.metrics
            """,
            (
                run.run_id,
                run.workflow_name,
                run.domain,
                run.partition_key,
                run.status.value,
                run.started_at.isoformat() if run.started_at else None,
                run.completed_at.isoformat() if run.completed_at else None,
                json.dumps(run.params),
                json.dumps(run.outputs),
                run.error,
                run.error_category,
                json.dumps(run.metrics),
                run.triggered_by,
                run.created_at.isoformat(),
            ),
        )
    
    def get_workflow_run(self, run_id: str) -> WorkflowRun | None:
        """Get workflow run by ID."""
        result = self.db.query(
            "SELECT * FROM workflow_runs WHERE run_id = ?",
            (run_id,),
        )
        
        if not result.rows:
            return None
        
        return self._row_to_workflow_run(result.records[0])
    
    def list_workflow_runs(
        self,
        workflow_name: str | None = None,
        domain: str | None = None,
        status: WorkflowStatus | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[WorkflowRun]:
        """
        List workflow runs with filters.
        
        Args:
            workflow_name: Filter by workflow name
            domain: Filter by domain
            status: Filter by status
            since: Filter by started_at >= since
            until: Filter by started_at <= until
            limit: Max results
            offset: Pagination offset
        """
        conditions = []
        params = []
        
        if workflow_name:
            conditions.append("workflow_name = ?")
            params.append(workflow_name)
        
        if domain:
            conditions.append("domain = ?")
            params.append(domain)
        
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        
        if since:
            conditions.append("started_at >= ?")
            params.append(since.isoformat())
        
        if until:
            conditions.append("started_at <= ?")
            params.append(until.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        result = self.db.query(
            f"""
            SELECT * FROM workflow_runs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        )
        
        return [self._row_to_workflow_run(row) for row in result]
    
    def count_workflow_runs(
        self,
        workflow_name: str | None = None,
        status: WorkflowStatus | None = None,
        since: datetime | None = None,
    ) -> int:
        """Count workflow runs matching criteria."""
        conditions = []
        params = []
        
        if workflow_name:
            conditions.append("workflow_name = ?")
            params.append(workflow_name)
        
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        
        if since:
            conditions.append("started_at >= ?")
            params.append(since.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        result = self.db.query(
            f"SELECT COUNT(*) as cnt FROM workflow_runs WHERE {where_clause}",
            tuple(params),
        )
        
        return result.records[0]["cnt"]
    
    # -------------------------------------------------------------------------
    # Step Runs
    # -------------------------------------------------------------------------
    
    def save_step_run(self, step: StepRun) -> None:
        """Insert or update step run."""
        self.db.execute(
            """
            INSERT INTO workflow_step_runs (
                step_id, run_id, step_name, step_type, step_order, status,
                started_at, completed_at, input_params, output_data,
                error, error_category, records_processed,
                quality_passed, quality_metrics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (step_id) DO UPDATE SET
                status = excluded.status,
                completed_at = excluded.completed_at,
                output_data = excluded.output_data,
                error = excluded.error,
                error_category = excluded.error_category,
                records_processed = excluded.records_processed,
                quality_passed = excluded.quality_passed,
                quality_metrics = excluded.quality_metrics
            """,
            (
                step.step_id,
                step.run_id,
                step.step_name,
                step.step_type,
                step.step_order,
                step.status.value,
                step.started_at.isoformat() if step.started_at else None,
                step.completed_at.isoformat() if step.completed_at else None,
                json.dumps(step.input_params),
                json.dumps(step.output_data),
                step.error,
                step.error_category,
                step.records_processed,
                step.quality_passed,
                json.dumps(step.quality_metrics),
            ),
        )
    
    def get_step_runs(self, run_id: str) -> list[StepRun]:
        """Get all step runs for a workflow run."""
        result = self.db.query(
            """
            SELECT * FROM workflow_step_runs 
            WHERE run_id = ?
            ORDER BY step_order
            """,
            (run_id,),
        )
        
        return [self._row_to_step_run(row) for row in result]
    
    # -------------------------------------------------------------------------
    # Retention
    # -------------------------------------------------------------------------
    
    def delete_old_runs(self, days: int) -> int:
        """
        Delete workflow runs older than days.
        
        Returns number of deleted runs.
        """
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Delete step runs first (foreign key)
        self.db.execute(
            """
            DELETE FROM workflow_step_runs 
            WHERE run_id IN (
                SELECT run_id FROM workflow_runs 
                WHERE created_at < ?
            )
            """,
            (cutoff,),
        )
        
        # Delete workflow runs
        count = self.db.execute(
            "DELETE FROM workflow_runs WHERE created_at < ?",
            (cutoff,),
        )
        
        log.info(f"Deleted {count} workflow runs older than {days} days")
        return count
    
    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------
    
    def get_run_statistics(
        self,
        workflow_name: str | None = None,
        since: datetime | None = None,
    ) -> dict:
        """Get execution statistics."""
        conditions = []
        params = []
        
        if workflow_name:
            conditions.append("workflow_name = ?")
            params.append(workflow_name)
        
        if since:
            conditions.append("started_at >= ?")
            params.append(since.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        result = self.db.query(
            f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed,
                AVG(
                    CASE WHEN completed_at IS NOT NULL AND started_at IS NOT NULL
                    THEN julianday(completed_at) - julianday(started_at)
                    ELSE NULL END
                ) * 86400 as avg_duration_seconds
            FROM workflow_runs
            WHERE {where_clause}
            """,
            tuple(params),
        )
        
        row = result.records[0]
        return {
            "total_runs": row["total"],
            "completed": row["completed"],
            "failed": row["failed"],
            "success_rate": row["completed"] / row["total"] if row["total"] > 0 else 0,
            "avg_duration_seconds": row["avg_duration_seconds"],
        }
    
    # -------------------------------------------------------------------------
    # Private
    # -------------------------------------------------------------------------
    
    def _row_to_workflow_run(self, row: dict) -> WorkflowRun:
        """Convert database row to WorkflowRun."""
        return WorkflowRun(
            run_id=row["run_id"],
            workflow_name=row["workflow_name"],
            domain=row["domain"],
            partition_key=row["partition_key"],
            status=WorkflowStatus(row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            params=json.loads(row["params"]) if row["params"] else {},
            outputs=json.loads(row["outputs"]) if row["outputs"] else {},
            error=row["error"],
            error_category=row["error_category"],
            metrics=json.loads(row["metrics"]) if row["metrics"] else {},
            triggered_by=row["triggered_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
    
    def _row_to_step_run(self, row: dict) -> StepRun:
        """Convert database row to StepRun."""
        return StepRun(
            step_id=row["step_id"],
            run_id=row["run_id"],
            step_name=row["step_name"],
            step_type=row["step_type"],
            step_order=row["step_order"],
            status=StepStatus(row["status"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            input_params=json.loads(row["input_params"]) if row["input_params"] else {},
            output_data=json.loads(row["output_data"]) if row["output_data"] else {},
            error=row["error"],
            error_category=row["error_category"],
            records_processed=row["records_processed"],
            quality_passed=bool(row["quality_passed"]) if row["quality_passed"] is not None else None,
            quality_metrics=json.loads(row["quality_metrics"]) if row["quality_metrics"] else {},
        )
```

---

## History Tracker

```python
# spine/orchestration/history/tracker.py
"""
History tracker for workflow runner integration.
"""

import uuid
from datetime import datetime

from .types import WorkflowRun, StepRun, WorkflowStatus, StepStatus
from .store import HistoryStore


class HistoryTracker:
    """
    Tracks workflow execution and persists to history store.
    
    Integrates with WorkflowRunner to automatically capture:
    - Workflow start/end
    - Step execution details
    - Errors and outputs
    
    Usage:
        tracker = HistoryTracker(store)
        
        with tracker.track_workflow("my_workflow", domain="finra") as run:
            # Execute workflow...
            with run.track_step("fetch", "lambda") as step:
                # Execute step...
                step.record_output({"count": 100})
    """
    
    def __init__(self, store: HistoryStore):
        self.store = store
    
    def track_workflow(
        self,
        workflow_name: str,
        domain: str | None = None,
        partition_key: str | None = None,
        params: dict | None = None,
        triggered_by: str = "manual",
    ) -> "WorkflowTracker":
        """Start tracking a workflow run."""
        run = WorkflowRun(
            run_id=str(uuid.uuid4())[:8],
            workflow_name=workflow_name,
            domain=domain,
            partition_key=partition_key,
            status=WorkflowStatus.PENDING,
            params=params or {},
            triggered_by=triggered_by,
        )
        
        return WorkflowTracker(run, self.store)


class WorkflowTracker:
    """Context manager for tracking workflow execution."""
    
    def __init__(self, run: WorkflowRun, store: HistoryStore):
        self.run = run
        self.store = store
        self._step_order = 0
    
    def __enter__(self) -> "WorkflowTracker":
        self.run.status = WorkflowStatus.RUNNING
        self.run.started_at = datetime.utcnow()
        self.store.save_workflow_run(self.run)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.run.completed_at = datetime.utcnow()
        
        if exc_type is not None:
            self.run.status = WorkflowStatus.FAILED
            self.run.error = str(exc_val)
            
            # Extract error category if available
            if hasattr(exc_val, "category"):
                self.run.error_category = exc_val.category.value
        else:
            self.run.status = WorkflowStatus.COMPLETED
        
        self.store.save_workflow_run(self.run)
        
        # Don't suppress exceptions
        return False
    
    @property
    def run_id(self) -> str:
        return self.run.run_id
    
    def track_step(
        self,
        step_name: str,
        step_type: str,
        input_params: dict | None = None,
    ) -> "StepTracker":
        """Start tracking a step within this workflow."""
        self._step_order += 1
        
        step = StepRun(
            step_id=f"{self.run.run_id}-{self._step_order}",
            run_id=self.run.run_id,
            step_name=step_name,
            step_type=step_type,
            step_order=self._step_order,
            input_params=input_params or {},
        )
        
        return StepTracker(step, self.store)
    
    def record_output(self, key: str, value) -> None:
        """Record output from workflow."""
        self.run.outputs[key] = value
    
    def record_metric(self, key: str, value) -> None:
        """Record metric from workflow."""
        self.run.metrics[key] = value
    
    def cancel(self) -> None:
        """Mark workflow as cancelled."""
        self.run.status = WorkflowStatus.CANCELLED
        self.run.completed_at = datetime.utcnow()
        self.store.save_workflow_run(self.run)


class StepTracker:
    """Context manager for tracking step execution."""
    
    def __init__(self, step: StepRun, store: HistoryStore):
        self.step = step
        self.store = store
    
    def __enter__(self) -> "StepTracker":
        self.step.status = StepStatus.RUNNING
        self.step.started_at = datetime.utcnow()
        self.store.save_step_run(self.step)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.step.completed_at = datetime.utcnow()
        
        if exc_type is not None:
            self.step.status = StepStatus.FAILED
            self.step.error = str(exc_val)
            
            if hasattr(exc_val, "category"):
                self.step.error_category = exc_val.category.value
        else:
            self.step.status = StepStatus.COMPLETED
        
        self.store.save_step_run(self.step)
        return False
    
    def record_output(self, output: dict) -> None:
        """Record step output."""
        self.step.output_data.update(output)
    
    def record_records(self, count: int) -> None:
        """Record number of records processed."""
        self.step.records_processed = count
    
    def record_quality(self, passed: bool, metrics: dict | None = None) -> None:
        """Record quality check results."""
        self.step.quality_passed = passed
        if metrics:
            self.step.quality_metrics.update(metrics)
    
    def skip(self, reason: str) -> None:
        """Mark step as skipped."""
        self.step.status = StepStatus.SKIPPED
        self.step.output_data["skip_reason"] = reason
```

---

## Usage Example

```python
# In workflow runner
from spine.orchestration.history import HistoryTracker, HistoryStore
from spine.core.storage import create_adapter, DatabaseConfig

# Setup
config = DatabaseConfig.from_env()
adapter = create_adapter(config)
adapter.connect()

store = HistoryStore(adapter)
tracker = HistoryTracker(store)

# Track workflow execution
with tracker.track_workflow(
    workflow_name="finra.otc_transparency.ingest_week",
    domain="finra",
    partition_key="2025-01-10|T1",
    params={"tier": "T1", "week_ending": "2025-01-10"},
    triggered_by="schedule",
) as run:
    
    # Track fetch step
    with run.track_step("fetch_data", "lambda") as step:
        result = fetch_from_finra()
        step.record_records(len(result))
        step.record_output({"url": result.url})
    
    # Track transform step
    with run.track_step("transform", "lambda") as step:
        records = transform_data(result)
        step.record_records(len(records))
    
    # Track quality check
    with run.track_step("quality_check", "pipeline") as step:
        passed, metrics = run_quality_checks(records)
        step.record_quality(passed, metrics)
        if not passed:
            raise ValueError("Quality check failed")
    
    # Track load step
    with run.track_step("load_data", "lambda") as step:
        inserted = load_to_database(records)
        step.record_records(inserted)
    
    run.record_metric("total_records", len(records))
```

---

## API Endpoints

```python
# spine/api/history.py
"""
Workflow history API endpoints.
"""

from datetime import datetime
from fastapi import APIRouter, Query
from pydantic import BaseModel

from spine.orchestration.history import HistoryStore, WorkflowStatus


router = APIRouter(prefix="/history", tags=["history"])


class WorkflowRunResponse(BaseModel):
    run_id: str
    workflow_name: str
    domain: str | None
    status: str
    started_at: str | None
    completed_at: str | None
    duration_seconds: float | None
    error: str | None
    triggered_by: str


class StepRunResponse(BaseModel):
    step_id: str
    step_name: str
    step_type: str
    status: str
    started_at: str | None
    completed_at: str | None
    duration_seconds: float | None
    records_processed: int | None
    quality_passed: bool | None
    error: str | None


class StatisticsResponse(BaseModel):
    total_runs: int
    completed: int
    failed: int
    success_rate: float
    avg_duration_seconds: float | None


@router.get("/runs")
def list_runs(
    store: HistoryStore,
    workflow_name: str | None = None,
    domain: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
) -> list[WorkflowRunResponse]:
    """List workflow runs with filters."""
    status_enum = WorkflowStatus(status) if status else None
    
    runs = store.list_workflow_runs(
        workflow_name=workflow_name,
        domain=domain,
        status=status_enum,
        since=since,
        limit=limit,
        offset=offset,
    )
    
    return [
        WorkflowRunResponse(
            run_id=r.run_id,
            workflow_name=r.workflow_name,
            domain=r.domain,
            status=r.status.value,
            started_at=r.started_at.isoformat() if r.started_at else None,
            completed_at=r.completed_at.isoformat() if r.completed_at else None,
            duration_seconds=r.duration_seconds,
            error=r.error,
            triggered_by=r.triggered_by,
        )
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run(run_id: str, store: HistoryStore) -> dict:
    """Get workflow run with step details."""
    run = store.get_workflow_run(run_id)
    if not run:
        raise HTTPException(404, f"Run not found: {run_id}")
    
    steps = store.get_step_runs(run_id)
    
    return {
        "run": run.to_dict(),
        "steps": [s.to_dict() for s in steps],
    }


@router.get("/statistics")
def get_statistics(
    store: HistoryStore,
    workflow_name: str | None = None,
    since: datetime | None = None,
) -> StatisticsResponse:
    """Get execution statistics."""
    stats = store.get_run_statistics(
        workflow_name=workflow_name,
        since=since,
    )
    return StatisticsResponse(**stats)


@router.delete("/runs/old")
def delete_old_runs(
    store: HistoryStore,
    days: int = Query(default=90, ge=1),
) -> dict:
    """Delete runs older than specified days."""
    deleted = store.delete_old_runs(days)
    return {"deleted": deleted}
```

---

## Database Schema

```sql
-- migrations/0004_workflow_history.sql

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    domain TEXT,
    partition_key TEXT,
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    params TEXT,  -- JSON
    outputs TEXT,  -- JSON
    error TEXT,
    error_category TEXT,
    metrics TEXT,  -- JSON
    triggered_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_name 
ON workflow_runs(workflow_name);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status 
ON workflow_runs(status);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_domain 
ON workflow_runs(domain);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_started 
ON workflow_runs(started_at);


CREATE TABLE IF NOT EXISTS workflow_step_runs (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_type TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    input_params TEXT,  -- JSON
    output_data TEXT,  -- JSON
    error TEXT,
    error_category TEXT,
    records_processed INTEGER,
    quality_passed INTEGER,
    quality_metrics TEXT,  -- JSON
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_step_runs_run 
ON workflow_step_runs(run_id);
```

---

## Module Exports

```python
# spine/orchestration/history/__init__.py
"""
Workflow execution history.

Usage:
    from spine.orchestration.history import (
        HistoryStore,
        HistoryTracker,
        WorkflowRun,
        StepRun,
    )
"""

from .types import (
    WorkflowRun,
    StepRun,
    WorkflowStatus,
    StepStatus,
)
from .store import HistoryStore
from .tracker import HistoryTracker

__all__ = [
    "WorkflowRun",
    "StepRun",
    "WorkflowStatus",
    "StepStatus",
    "HistoryStore",
    "HistoryTracker",
]
```

---

## Next Steps

1. Document schema changes: [08-SCHEMA-CHANGES.md](./08-SCHEMA-CHANGES.md)
2. Show integration flow: [09-INTEGRATION-FLOW.md](./09-INTEGRATION-FLOW.md)
3. See FINRA example: [10-FINRA-EXAMPLE.md](./10-FINRA-EXAMPLE.md)
