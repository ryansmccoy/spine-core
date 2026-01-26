# Scheduler Service

> **Purpose:** Cron-based scheduling for pipeline execution.
> **Tier:** Intermediate
> **Module:** `spine.orchestration.scheduler`
> **Last Updated:** 2026-01-11

---

## Overview

Current state:
- No scheduling capability
- Manual triggering only
- External cron for scripts

Target state:
- In-process scheduler (APScheduler)
- Cron expression support
- Schedule persistence
- Job lifecycle management
- Integration with orchestration

---

## Design Principles

1. **Cron-Compatible** - Standard cron expressions
2. **Persistent** - Schedules survive restarts
3. **Observable** - Job history and metrics (Principle #13)
4. **Graceful** - Clean shutdown handling
5. **Distributed-Ready** - Lock support for multi-instance

> **Design Principles Applied:**
> - **Immutability (#5):** `Schedule` is frozen - create new instances to modify
> - **Separation of Concerns (#10):** Scheduler only triggers; pipelines do the work
> - **Observable (#13):** All job runs recorded in `workflow_runs` table

---

## Core Types

```python
# spine/orchestration/scheduler/types.py
"""
Scheduler types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from enum import Enum


class ScheduleType(str, Enum):
    """Types of schedules."""
    CRON = "cron"          # Cron expression
    INTERVAL = "interval"   # Every N minutes/hours
    DATE = "date"          # One-time at date


class JobStatus(str, Enum):
    """Job execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Schedule:
    """
    Schedule definition.
    
    Immutable configuration for when jobs run.
    """
    name: str
    pipeline: str
    schedule_type: ScheduleType
    
    # Cron fields (for CRON type)
    cron_expression: str | None = None
    
    # Interval fields (for INTERVAL type)
    interval_minutes: int | None = None
    interval_hours: int | None = None
    
    # Date fields (for DATE type)
    run_at: datetime | None = None
    
    # Common fields
    timezone: str = "UTC"
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    max_instances: int = 1  # Prevent overlapping runs
    misfire_grace_time: int = 60  # Seconds to allow late execution
    
    @classmethod
    def cron(
        cls,
        name: str,
        pipeline: str,
        expression: str,
        timezone: str = "UTC",
        params: dict[str, Any] | None = None,
    ) -> "Schedule":
        """Create cron schedule."""
        return cls(
            name=name,
            pipeline=pipeline,
            schedule_type=ScheduleType.CRON,
            cron_expression=expression,
            timezone=timezone,
            params=params or {},
        )
    
    @classmethod
    def interval(
        cls,
        name: str,
        pipeline: str,
        minutes: int = 0,
        hours: int = 0,
        params: dict[str, Any] | None = None,
    ) -> "Schedule":
        """Create interval schedule."""
        return cls(
            name=name,
            pipeline=pipeline,
            schedule_type=ScheduleType.INTERVAL,
            interval_minutes=minutes,
            interval_hours=hours,
            params=params or {},
        )
    
    @classmethod
    def once(
        cls,
        name: str,
        pipeline: str,
        run_at: datetime,
        params: dict[str, Any] | None = None,
    ) -> "Schedule":
        """Create one-time schedule."""
        return cls(
            name=name,
            pipeline=pipeline,
            schedule_type=ScheduleType.DATE,
            run_at=run_at,
            params=params or {},
        )


@dataclass
class JobRun:
    """
    Record of a scheduled job execution.
    """
    run_id: str
    schedule_name: str
    pipeline: str
    status: JobStatus
    scheduled_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    
    @property
    def duration_seconds(self) -> float | None:
        """Calculate run duration."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
```

---

## Scheduler Service

```python
# spine/orchestration/scheduler/service.py
"""
Scheduler service using APScheduler.

Requires: pip install apscheduler
"""

import logging
from datetime import datetime
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from .types import Schedule, ScheduleType, JobRun, JobStatus
from spine.core.storage import DatabaseAdapter


log = logging.getLogger(__name__)


class SchedulerService:
    """
    Pipeline scheduler using APScheduler.
    
    Features:
    - Cron, interval, and one-time schedules
    - Persistent job store (SQLite/PostgreSQL)
    - Job history tracking
    - Graceful shutdown
    
    Usage:
        scheduler = SchedulerService(db_adapter)
        scheduler.add_schedule(Schedule.cron(
            name="daily_finra",
            pipeline="finra.otc_transparency.ingest_week",
            expression="0 6 * * 1-5",  # 6 AM weekdays
        ))
        scheduler.start()
    """
    
    def __init__(
        self,
        db_adapter: DatabaseAdapter,
        executor_threads: int = 4,
        job_defaults: dict[str, Any] | None = None,
    ):
        self.db = db_adapter
        self._pipeline_executor: Callable | None = None
        
        # Build connection URL for APScheduler
        if db_adapter.dialect == "sqlite":
            jobstore_url = "sqlite:///data/scheduler.db"
        elif db_adapter.dialect == "postgresql":
            jobstore_url = db_adapter.config.url or self._build_pg_url(db_adapter.config)
        else:
            # DB2 not directly supported by APScheduler, use SQLite as fallback
            jobstore_url = "sqlite:///data/scheduler.db"
        
        # Configure APScheduler
        jobstores = {
            "default": SQLAlchemyJobStore(url=jobstore_url),
        }
        executors = {
            "default": ThreadPoolExecutor(executor_threads),
        }
        defaults = job_defaults or {
            "coalesce": True,  # Combine missed runs
            "max_instances": 1,
            "misfire_grace_time": 60,
        }
        
        self._scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=defaults,
        )
        
        self._schedules: dict[str, Schedule] = {}
    
    def set_executor(self, executor: Callable[[str, dict], dict]) -> None:
        """
        Set pipeline executor function.
        
        Executor receives (pipeline_name, params) and returns result dict.
        """
        self._pipeline_executor = executor
    
    def add_schedule(self, schedule: Schedule) -> None:
        """Add or update a schedule."""
        self._schedules[schedule.name] = schedule
        
        # Build trigger
        trigger = self._build_trigger(schedule)
        
        # Add/replace job
        self._scheduler.add_job(
            func=self._run_pipeline,
            trigger=trigger,
            args=[schedule],
            id=schedule.name,
            name=f"{schedule.name} -> {schedule.pipeline}",
            replace_existing=True,
            misfire_grace_time=schedule.misfire_grace_time,
            max_instances=schedule.max_instances,
        )
        
        log.info(f"Added schedule: {schedule.name} -> {schedule.pipeline}")
    
    def remove_schedule(self, name: str) -> bool:
        """Remove a schedule."""
        if name in self._schedules:
            del self._schedules[name]
            self._scheduler.remove_job(name)
            log.info(f"Removed schedule: {name}")
            return True
        return False
    
    def pause_schedule(self, name: str) -> bool:
        """Pause a schedule."""
        self._scheduler.pause_job(name)
        log.info(f"Paused schedule: {name}")
        return True
    
    def resume_schedule(self, name: str) -> bool:
        """Resume a paused schedule."""
        self._scheduler.resume_job(name)
        log.info(f"Resumed schedule: {name}")
        return True
    
    def run_now(self, name: str) -> str | None:
        """Trigger immediate run of a schedule."""
        if name not in self._schedules:
            return None
        
        schedule = self._schedules[name]
        return self._run_pipeline(schedule)
    
    def start(self) -> None:
        """Start the scheduler."""
        self._scheduler.start()
        log.info("Scheduler started")
    
    def stop(self, wait: bool = True) -> None:
        """Stop the scheduler."""
        self._scheduler.shutdown(wait=wait)
        log.info("Scheduler stopped")
    
    def get_jobs(self) -> list[dict[str, Any]]:
        """Get all scheduled jobs."""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "pending": job.pending,
            })
        return jobs
    
    def get_schedule(self, name: str) -> Schedule | None:
        """Get schedule by name."""
        return self._schedules.get(name)
    
    # -------------------------------------------------------------------------
    # Private Methods
    # -------------------------------------------------------------------------
    
    def _build_trigger(self, schedule: Schedule):
        """Build APScheduler trigger from Schedule."""
        if schedule.schedule_type == ScheduleType.CRON:
            return CronTrigger.from_crontab(
                schedule.cron_expression,
                timezone=schedule.timezone,
            )
        elif schedule.schedule_type == ScheduleType.INTERVAL:
            return IntervalTrigger(
                minutes=schedule.interval_minutes or 0,
                hours=schedule.interval_hours or 0,
            )
        elif schedule.schedule_type == ScheduleType.DATE:
            return DateTrigger(
                run_date=schedule.run_at,
                timezone=schedule.timezone,
            )
        else:
            raise ValueError(f"Unknown schedule type: {schedule.schedule_type}")
    
    def _run_pipeline(self, schedule: Schedule) -> str:
        """Execute pipeline for schedule."""
        import uuid
        
        run_id = str(uuid.uuid4())[:8]
        started_at = datetime.utcnow()
        
        log.info(f"[{run_id}] Starting scheduled run: {schedule.name} -> {schedule.pipeline}")
        
        # Record start
        run = JobRun(
            run_id=run_id,
            schedule_name=schedule.name,
            pipeline=schedule.pipeline,
            status=JobStatus.RUNNING,
            scheduled_at=started_at,
            started_at=started_at,
        )
        self._record_run(run)
        
        try:
            if self._pipeline_executor is None:
                raise ValueError("No pipeline executor configured")
            
            result = self._pipeline_executor(schedule.pipeline, schedule.params)
            
            run.status = JobStatus.COMPLETED
            run.result = result
            run.completed_at = datetime.utcnow()
            
            log.info(f"[{run_id}] Completed: {schedule.pipeline}")
            
        except Exception as e:
            run.status = JobStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.utcnow()
            
            log.error(f"[{run_id}] Failed: {schedule.pipeline} - {e}")
        
        self._record_run(run)
        return run_id
    
    def _record_run(self, run: JobRun) -> None:
        """Record job run to database."""
        self.db.execute(
            """
            INSERT INTO scheduler_runs (
                run_id, schedule_name, pipeline, status,
                scheduled_at, started_at, completed_at, error, result
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (run_id) DO UPDATE SET
                status = excluded.status,
                completed_at = excluded.completed_at,
                error = excluded.error,
                result = excluded.result
            """,
            (
                run.run_id,
                run.schedule_name,
                run.pipeline,
                run.status.value,
                run.scheduled_at.isoformat(),
                run.started_at.isoformat() if run.started_at else None,
                run.completed_at.isoformat() if run.completed_at else None,
                run.error,
                str(run.result) if run.result else None,
            ),
        )
    
    def _build_pg_url(self, config) -> str:
        """Build PostgreSQL URL from config."""
        return (
            f"postgresql://{config.user}:{config.password}"
            f"@{config.host}:{config.port}/{config.database}"
        )
```

---

## Schedule Loader

```python
# spine/orchestration/scheduler/loader.py
"""
Load schedules from configuration files.
"""

import yaml
import logging
from pathlib import Path

from .types import Schedule, ScheduleType
from .service import SchedulerService


log = logging.getLogger(__name__)


def load_schedules_from_yaml(path: Path | str, scheduler: SchedulerService) -> int:
    """
    Load schedules from YAML file.
    
    YAML format:
        schedules:
          - name: daily_finra
            pipeline: finra.otc_transparency.ingest_week
            cron: "0 6 * * 1-5"
            timezone: America/New_York
            params:
              tier: T1
          
          - name: hourly_prices
            pipeline: prices.ingest
            interval: 60  # minutes
    
    Returns number of schedules loaded.
    """
    path = Path(path)
    
    with open(path) as f:
        config = yaml.safe_load(f)
    
    count = 0
    for item in config.get("schedules", []):
        schedule = _parse_schedule(item)
        if schedule:
            scheduler.add_schedule(schedule)
            count += 1
    
    log.info(f"Loaded {count} schedules from {path}")
    return count


def _parse_schedule(item: dict) -> Schedule | None:
    """Parse schedule from dict."""
    name = item.get("name")
    pipeline = item.get("pipeline")
    
    if not name or not pipeline:
        log.warning(f"Invalid schedule: missing name or pipeline: {item}")
        return None
    
    params = item.get("params", {})
    timezone = item.get("timezone", "UTC")
    enabled = item.get("enabled", True)
    
    # Determine type
    if "cron" in item:
        return Schedule(
            name=name,
            pipeline=pipeline,
            schedule_type=ScheduleType.CRON,
            cron_expression=item["cron"],
            timezone=timezone,
            params=params,
            enabled=enabled,
        )
    elif "interval" in item:
        return Schedule(
            name=name,
            pipeline=pipeline,
            schedule_type=ScheduleType.INTERVAL,
            interval_minutes=item["interval"],
            params=params,
            enabled=enabled,
        )
    else:
        log.warning(f"Unknown schedule type for {name}")
        return None
```

---

## Example Schedule Configuration

```yaml
# config/schedules.yaml
schedules:
  # FINRA OTC Transparency - weekdays at 6 AM ET
  - name: finra_otc_t1
    pipeline: finra.otc_transparency.ingest_week
    cron: "0 6 * * 1-5"
    timezone: America/New_York
    params:
      tier: T1
  
  - name: finra_otc_t2
    pipeline: finra.otc_transparency.ingest_week
    cron: "0 6 * * 1-5"
    timezone: America/New_York
    params:
      tier: T2
  
  # Price updates - every 15 minutes during market hours
  - name: price_updates
    pipeline: prices.ingest_current
    cron: "*/15 9-16 * * 1-5"
    timezone: America/New_York
  
  # Daily cleanup - 2 AM
  - name: daily_cleanup
    pipeline: maintenance.cleanup_old_data
    cron: "0 2 * * *"
    params:
      days_to_keep: 90
  
  # Weekly report - Sunday at midnight
  - name: weekly_report
    pipeline: reports.weekly_summary
    cron: "0 0 * * 0"
```

---

## Database Schema

```sql
-- migrations/0003_scheduler_tables.sql

CREATE TABLE IF NOT EXISTS scheduler_schedules (
    name TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    cron_expression TEXT,
    interval_minutes INTEGER,
    interval_hours INTEGER,
    run_at TEXT,
    timezone TEXT DEFAULT 'UTC',
    params TEXT,  -- JSON
    enabled INTEGER DEFAULT 1,
    max_instances INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scheduler_runs (
    run_id TEXT PRIMARY KEY,
    schedule_name TEXT NOT NULL,
    pipeline TEXT NOT NULL,
    status TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    result TEXT,  -- JSON
    FOREIGN KEY (schedule_name) REFERENCES scheduler_schedules(name)
);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_schedule 
ON scheduler_runs(schedule_name);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status 
ON scheduler_runs(status);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_scheduled_at 
ON scheduler_runs(scheduled_at);
```

---

## Integration with Pipelines

```python
# spine/orchestration/scheduler/executor.py
"""
Pipeline executor for scheduler.
"""

from typing import Any

from spine.framework.pipelines import get_pipeline
from spine.core.execution import ExecutionContext


def create_pipeline_executor(context_factory):
    """
    Create executor function for scheduler.
    
    Usage:
        scheduler.set_executor(create_pipeline_executor(context_factory))
    """
    
    def executor(pipeline_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute pipeline by name."""
        # Get pipeline class from registry
        pipeline_cls = get_pipeline(pipeline_name)
        
        if pipeline_cls is None:
            raise ValueError(f"Unknown pipeline: {pipeline_name}")
        
        # Create execution context
        context = context_factory()
        
        # Instantiate and run
        pipeline = pipeline_cls(context, params)
        result = pipeline.run()
        
        return {
            "status": result.status.value,
            "metrics": result.metrics,
            "error": result.error,
        }
    
    return executor
```

---

## API Endpoints

```python
# spine/api/scheduler.py
"""
Scheduler API endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from spine.orchestration.scheduler import SchedulerService, Schedule


router = APIRouter(prefix="/scheduler", tags=["scheduler"])


# Request/response models
class ScheduleCreate(BaseModel):
    name: str
    pipeline: str
    cron: str | None = None
    interval_minutes: int | None = None
    timezone: str = "UTC"
    params: dict = {}


class ScheduleResponse(BaseModel):
    name: str
    pipeline: str
    schedule_type: str
    cron_expression: str | None
    interval_minutes: int | None
    timezone: str
    enabled: bool
    next_run: str | None


# Endpoints
@router.get("/schedules")
def list_schedules(scheduler: SchedulerService) -> list[ScheduleResponse]:
    """List all schedules."""
    jobs = scheduler.get_jobs()
    schedules = []
    
    for job in jobs:
        schedule = scheduler.get_schedule(job["id"])
        if schedule:
            schedules.append(ScheduleResponse(
                name=schedule.name,
                pipeline=schedule.pipeline,
                schedule_type=schedule.schedule_type.value,
                cron_expression=schedule.cron_expression,
                interval_minutes=schedule.interval_minutes,
                timezone=schedule.timezone,
                enabled=schedule.enabled,
                next_run=job["next_run"],
            ))
    
    return schedules


@router.post("/schedules")
def create_schedule(data: ScheduleCreate, scheduler: SchedulerService) -> ScheduleResponse:
    """Create a new schedule."""
    if data.cron:
        schedule = Schedule.cron(
            name=data.name,
            pipeline=data.pipeline,
            expression=data.cron,
            timezone=data.timezone,
            params=data.params,
        )
    elif data.interval_minutes:
        schedule = Schedule.interval(
            name=data.name,
            pipeline=data.pipeline,
            minutes=data.interval_minutes,
            params=data.params,
        )
    else:
        raise HTTPException(400, "Either cron or interval_minutes required")
    
    scheduler.add_schedule(schedule)
    
    return ScheduleResponse(
        name=schedule.name,
        pipeline=schedule.pipeline,
        schedule_type=schedule.schedule_type.value,
        cron_expression=schedule.cron_expression,
        interval_minutes=schedule.interval_minutes,
        timezone=schedule.timezone,
        enabled=schedule.enabled,
        next_run=None,  # Will be set after next scheduler tick
    )


@router.delete("/schedules/{name}")
def delete_schedule(name: str, scheduler: SchedulerService):
    """Delete a schedule."""
    if not scheduler.remove_schedule(name):
        raise HTTPException(404, f"Schedule not found: {name}")
    return {"deleted": name}


@router.post("/schedules/{name}/run")
def trigger_run(name: str, scheduler: SchedulerService):
    """Trigger immediate run."""
    run_id = scheduler.run_now(name)
    if not run_id:
        raise HTTPException(404, f"Schedule not found: {name}")
    return {"run_id": run_id}


@router.post("/schedules/{name}/pause")
def pause_schedule(name: str, scheduler: SchedulerService):
    """Pause a schedule."""
    scheduler.pause_schedule(name)
    return {"paused": name}


@router.post("/schedules/{name}/resume")
def resume_schedule(name: str, scheduler: SchedulerService):
    """Resume a paused schedule."""
    scheduler.resume_schedule(name)
    return {"resumed": name}
```

---

## Testing

```python
# tests/orchestration/scheduler/test_service.py
import pytest
from datetime import datetime, timedelta

from spine.orchestration.scheduler import (
    SchedulerService,
    Schedule,
    ScheduleType,
)
from spine.core.storage import create_adapter, DatabaseConfig


class TestSchedulerService:
    @pytest.fixture
    def scheduler(self):
        config = DatabaseConfig.sqlite(":memory:")
        adapter = create_adapter(config)
        adapter.connect()
        
        # Create tables
        adapter.execute("""
            CREATE TABLE scheduler_runs (
                run_id TEXT PRIMARY KEY,
                schedule_name TEXT NOT NULL,
                pipeline TEXT NOT NULL,
                status TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                error TEXT,
                result TEXT
            )
        """)
        
        return SchedulerService(adapter)
    
    def test_add_cron_schedule(self, scheduler):
        schedule = Schedule.cron(
            name="test_schedule",
            pipeline="test.pipeline",
            expression="0 6 * * 1-5",
        )
        
        scheduler.add_schedule(schedule)
        
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0]["id"] == "test_schedule"
    
    def test_add_interval_schedule(self, scheduler):
        schedule = Schedule.interval(
            name="interval_test",
            pipeline="test.pipeline",
            minutes=30,
        )
        
        scheduler.add_schedule(schedule)
        
        retrieved = scheduler.get_schedule("interval_test")
        assert retrieved.interval_minutes == 30
    
    def test_remove_schedule(self, scheduler):
        schedule = Schedule.cron(
            name="to_remove",
            pipeline="test.pipeline",
            expression="0 0 * * *",
        )
        
        scheduler.add_schedule(schedule)
        assert len(scheduler.get_jobs()) == 1
        
        scheduler.remove_schedule("to_remove")
        assert len(scheduler.get_jobs()) == 0
    
    def test_run_now_with_executor(self, scheduler):
        results = []
        
        def mock_executor(pipeline: str, params: dict) -> dict:
            results.append({"pipeline": pipeline, "params": params})
            return {"status": "completed"}
        
        scheduler.set_executor(mock_executor)
        
        schedule = Schedule.cron(
            name="manual_run",
            pipeline="test.pipeline",
            expression="0 0 * * *",
            params={"key": "value"},
        )
        scheduler.add_schedule(schedule)
        
        run_id = scheduler.run_now("manual_run")
        
        assert run_id is not None
        assert len(results) == 1
        assert results[0]["pipeline"] == "test.pipeline"
        assert results[0]["params"]["key"] == "value"
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `APScheduler` | >=3.10 | Job scheduling |
| `SQLAlchemy` | >=2.0 | Job store (via APScheduler) |
| `PyYAML` | >=6.0 | Config loading |

---

## Next Steps

1. Build workflow history: [07-WORKFLOW-HISTORY.md](./07-WORKFLOW-HISTORY.md)
2. Document schema changes: [08-SCHEMA-CHANGES.md](./08-SCHEMA-CHANGES.md)
3. Show integration flow: [09-INTEGRATION-FLOW.md](./09-INTEGRATION-FLOW.md)
