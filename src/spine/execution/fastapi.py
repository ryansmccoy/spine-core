"""FastAPI Router — unified ``/runs`` REST API.

WHY
───
All work types (tasks, pipelines, workflows, steps) share the same
lifecycle.  A single ``/runs`` endpoint avoids endpoint sprawl and
keeps the API surface small.  No separate ``/tasks``, ``/pipelines``,
``/executions`` routes.

ARCHITECTURE
────────────
::

    create_runs_router(dispatcher) → APIRouter
      POST   /runs          ─ submit new work
      GET    /runs           ─ list runs (filter by status/kind)
      GET    /runs/{run_id}  ─ get run details
      POST   /runs/{run_id}/cancel  ─ request cancellation
      GET    /runs/summary   ─ aggregate stats

    Depends on:
      EventDispatcher ─ all operations delegate here
      FastAPI         ─ optional dependency (graceful fallback)

Related modules:
    dispatcher.py — EventDispatcher (business logic)
    spec.py       — WorkSpec (request body model)
    runs.py       — RunRecord (response model)
"""

from datetime import datetime
from typing import Any, Literal

try:
    from fastapi import APIRouter, Body, HTTPException, Query  # noqa: F401
    from pydantic import BaseModel, Field

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore
    HTTPException = None  # type: ignore

from .dispatcher import EventDispatcher
from .runs import RunRecord, RunStatus, RunSummary
from .spec import WorkSpec

# === PYDANTIC MODELS FOR API ===

if FASTAPI_AVAILABLE:

    class WorkSpecRequest(BaseModel):
        """Request body for submitting work."""

        kind: Literal["task", "pipeline", "workflow", "step"]
        name: str
        params: dict[str, Any] = Field(default_factory=dict)
        idempotency_key: str | None = None
        correlation_id: str | None = None
        priority: Literal["realtime", "high", "normal", "low", "slow"] = "normal"
        lane: str = "default"
        parent_run_id: str | None = None
        trigger_source: str = "api"
        metadata: dict[str, Any] = Field(default_factory=dict)
        max_retries: int = 3
        retry_delay_seconds: int = 60

        def to_spec(self) -> WorkSpec:
            """Convert to WorkSpec."""
            return WorkSpec(
                kind=self.kind,
                name=self.name,
                params=self.params,
                idempotency_key=self.idempotency_key,
                correlation_id=self.correlation_id,
                priority=self.priority,
                lane=self.lane,
                parent_run_id=self.parent_run_id,
                trigger_source=self.trigger_source,
                metadata=self.metadata,
                max_retries=self.max_retries,
                retry_delay_seconds=self.retry_delay_seconds,
            )

    class RunResponse(BaseModel):
        """Response for a single run."""

        run_id: str
        kind: str
        name: str
        params: dict[str, Any]
        status: str
        created_at: datetime
        started_at: datetime | None = None
        completed_at: datetime | None = None
        result: Any = None
        error: str | None = None
        error_type: str | None = None
        external_ref: str | None = None
        executor_name: str | None = None
        attempt: int = 1
        duration_seconds: float | None = None
        tags: dict[str, str] = Field(default_factory=dict)

        @classmethod
        def from_record(cls, record: RunRecord) -> "RunResponse":
            """Create from RunRecord."""
            return cls(
                run_id=record.run_id,
                kind=record.spec.kind,
                name=record.spec.name,
                params=record.spec.params,
                status=record.status.value,
                created_at=record.created_at,
                started_at=record.started_at,
                completed_at=record.completed_at,
                result=record.result,
                error=record.error,
                error_type=record.error_type,
                external_ref=record.external_ref,
                executor_name=record.executor_name,
                attempt=record.attempt,
                duration_seconds=record.duration_seconds,
                tags=record.tags,
            )

    class RunSummaryResponse(BaseModel):
        """Response for run list items."""

        run_id: str
        kind: str
        name: str
        status: str
        created_at: datetime
        duration_seconds: float | None = None

        @classmethod
        def from_summary(cls, summary: RunSummary) -> "RunSummaryResponse":
            """Create from RunSummary."""
            return cls(
                run_id=summary.run_id,
                kind=summary.kind,
                name=summary.name,
                status=summary.status.value,
                created_at=summary.created_at,
                duration_seconds=summary.duration_seconds,
            )

    class EventResponse(BaseModel):
        """Response for run events."""

        event_id: str
        run_id: str
        event_type: str
        timestamp: datetime
        data: dict[str, Any] = Field(default_factory=dict)
        source: str = "dispatcher"

    class TaskSubmitRequest(BaseModel):
        """Convenience request for task submission."""

        name: str
        params: dict[str, Any] = Field(default_factory=dict)
        priority: str = "normal"
        metadata: dict[str, Any] = Field(default_factory=dict)
        idempotency_key: str | None = None

    class PipelineSubmitRequest(BaseModel):
        """Convenience request for pipeline submission."""

        name: str
        params: dict[str, Any] = Field(default_factory=dict)
        lane: str = "default"
        metadata: dict[str, Any] = Field(default_factory=dict)
        idempotency_key: str | None = None


def create_runs_router(
    dispatcher: EventDispatcher,
    prefix: str = "/api/v1/runs",
    tags: list[str] | None = None,
) -> "APIRouter":
    """Create unified runs router for all work types.

    This is the ONLY FastAPI router you need. Pipeline executions,
    task submissions, and workflow runs all go through /runs.

    Args:
        dispatcher: Configured EventDispatcher instance
        prefix: URL prefix (default: /api/v1/runs)
        tags: OpenAPI tags (default: ["runs"])

    Returns:
        FastAPI APIRouter

    Example:
        >>> from fastapi import FastAPI
        >>> from spine.execution import EventDispatcher, create_runs_router
        >>> from spine.execution.executors import LocalExecutor
        >>>
        >>> app = FastAPI()
        >>> dispatcher = EventDispatcher(executor=LocalExecutor())
        >>> app.include_router(create_runs_router(dispatcher))

    Endpoints:
        GET  /runs              - List runs with filters
        GET  /runs/{run_id}     - Get run details
        POST /runs              - Submit work (canonical)
        POST /runs/task         - Submit task (convenience)
        POST /runs/pipeline     - Submit pipeline (convenience)
        POST /runs/{run_id}/cancel  - Cancel run
        POST /runs/{run_id}/retry   - Retry failed run
        GET  /runs/{run_id}/events  - Get event history
        GET  /runs/{run_id}/children - Get child runs (workflow steps)
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI not installed. Install with: pip install fastapi")

    router = APIRouter(prefix=prefix, tags=tags or ["runs"])

    @router.get("", response_model=list[RunSummaryResponse])
    async def list_runs(
        kind: Literal["task", "pipeline", "workflow", "step"] | None = None,
        status: str | None = None,
        name: str | None = None,
        parent_run_id: str | None = None,
        limit: int = Query(50, le=200),
        offset: int = 0,
    ):
        """List runs with optional filters.

        Examples:
        - GET /runs - all runs
        - GET /runs?kind=pipeline - only pipeline executions
        - GET /runs?status=failed - only failed runs
        - GET /runs?name=ingest_otc&kind=pipeline - specific pipeline
        - GET /runs?parent_run_id=abc-123 - workflow steps
        """
        # Convert status string to enum if provided
        status_enum = None
        if status:
            try:
                status_enum = RunStatus(status)
            except ValueError:
                raise HTTPException(400, f"Invalid status: {status}") from None

        summaries = await dispatcher.list_runs(
            kind=kind,
            status=status_enum,
            name=name,
            parent_run_id=parent_run_id,
            limit=limit,
            offset=offset,
        )
        return [RunSummaryResponse.from_summary(s) for s in summaries]

    @router.get("/{run_id}", response_model=RunResponse)
    async def get_run(run_id: str):
        """Get run details by ID."""
        run = await dispatcher.get_run(run_id)
        if not run:
            raise HTTPException(404, f"Run {run_id} not found")
        return RunResponse.from_record(run)

    @router.post("", response_model=RunResponse)
    async def submit_run(spec: WorkSpecRequest):
        """Submit any kind of work (canonical form).

        Body:
        ```json
        {
          "kind": "task",
          "name": "send_email",
          "params": {"to": "user@example.com"},
          "priority": "high"
        }
        ```
        """
        run_id = await dispatcher.submit(spec.to_spec())
        run = await dispatcher.get_run(run_id)
        if not run:
            raise HTTPException(500, "Failed to create run")
        return RunResponse.from_record(run)

    # === CONVENIENCE ENDPOINTS ===

    @router.post("/task", response_model=RunResponse)
    async def submit_task(request: TaskSubmitRequest):
        """Convenience: submit a task.

        Body:
        ```json
        {
          "name": "send_email",
          "params": {"to": "user@example.com"},
          "priority": "high"
        }
        ```
        """
        run_id = await dispatcher.submit_task(
            request.name,
            request.params,
            priority=request.priority,
            metadata=request.metadata,
            idempotency_key=request.idempotency_key,
        )
        run = await dispatcher.get_run(run_id)
        return RunResponse.from_record(run)

    @router.post("/pipeline", response_model=RunResponse)
    async def submit_pipeline(request: PipelineSubmitRequest):
        """Convenience: submit a pipeline execution.

        Body:
        ```json
        {
          "name": "ingest_otc",
          "params": {"date": "2026-01-15"},
          "lane": "backfill"
        }
        ```
        """
        run_id = await dispatcher.submit_pipeline(
            request.name,
            request.params,
            lane=request.lane,
            metadata=request.metadata,
            idempotency_key=request.idempotency_key,
        )
        run = await dispatcher.get_run(run_id)
        return RunResponse.from_record(run)

    # === CONTROL ===

    @router.post("/{run_id}/cancel")
    async def cancel_run(run_id: str):
        """Cancel a pending or running work item."""
        success = await dispatcher.cancel(run_id)
        if not success:
            run = await dispatcher.get_run(run_id)
            if not run:
                raise HTTPException(404, f"Run {run_id} not found")
            raise HTTPException(400, f"Cannot cancel run {run_id} (status: {run.status.value})")
        return {"status": "cancelled", "run_id": run_id}

    @router.post("/{run_id}/retry", response_model=RunResponse)
    async def retry_run(run_id: str):
        """Retry a failed work item (creates new run)."""
        try:
            new_run_id = await dispatcher.retry(run_id)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e

        run = await dispatcher.get_run(new_run_id)
        return RunResponse.from_record(run)

    # === OBSERVABILITY ===

    @router.get("/{run_id}/events", response_model=list[EventResponse])
    async def get_run_events(run_id: str):
        """Get event-sourced history for a run."""
        run = await dispatcher.get_run(run_id)
        if not run:
            raise HTTPException(404, f"Run {run_id} not found")

        events = await dispatcher.get_events(run_id)
        return [
            EventResponse(
                event_id=e.event_id,
                run_id=e.run_id,
                event_type=e.event_type,
                timestamp=e.timestamp,
                data=e.data,
                source=e.source,
            )
            for e in events
        ]

    @router.get("/{run_id}/children", response_model=list[RunSummaryResponse])
    async def get_run_children(run_id: str):
        """Get child runs (workflow steps)."""
        run = await dispatcher.get_run(run_id)
        if not run:
            raise HTTPException(404, f"Run {run_id} not found")

        children = await dispatcher.get_children(run_id)
        return [RunSummaryResponse.from_summary(s) for s in children]

    return router
