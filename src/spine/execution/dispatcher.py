"""Dispatcher - central submission and query API.

The Dispatcher is the ONLY public API for executing work in spine-core.
It handles submitting work to executors, recording runs, publishing events,
and querying run status.

This provides a single, unified interface regardless of:
- Work type (task, pipeline, workflow, step)
- Executor (Memory, Local, Celery, etc.)
- Persistence (in-memory or database ledger)
"""
import uuid
from datetime import datetime
from typing import Any, Dict, TYPE_CHECKING

from .spec import WorkSpec
from .runs import RunRecord, RunStatus, RunSummary
from .events import RunEvent, EventType

if TYPE_CHECKING:
    from .executors.protocol import Executor


class Dispatcher:
    """Central submission point for all work types.
    
    This is the ONLY public API for executing work in spine-core.
    It handles:
    - Submitting work to executors
    - Recording runs in ledger (in-memory or persistent)
    - Publishing events for observability
    - Querying run status
    - Control operations (cancel, retry)
    
    Example:
        >>> from spine.execution import Dispatcher, task_spec
        >>> from spine.execution.executors import MemoryExecutor
        >>>
        >>> # Create dispatcher with executor
        >>> executor = MemoryExecutor(handlers={"task:send_email": send_email_handler})
        >>> dispatcher = Dispatcher(executor=executor)
        >>>
        >>> # Submit work
        >>> run_id = await dispatcher.submit_task("send_email", {"to": "user@example.com"})
        >>>
        >>> # Query status
        >>> run = await dispatcher.get_run(run_id)
        >>> print(run.status)  # RunStatus.COMPLETED
    """
    
    def __init__(
        self,
        executor: "Executor",
        ledger: Any = None,  # Optional RunLedger for persistence
        registry: Any = None,  # Optional HandlerRegistry
        concurrency: Any = None,  # Optional ConcurrencyGuard
    ):
        """Initialize dispatcher.
        
        Args:
            executor: Executor adapter (Memory, Local, Celery, etc.)
            ledger: Optional run persistence (in-memory if None)
            registry: Optional handler registry
            concurrency: Optional concurrency control
        """
        self.executor = executor
        self.ledger = ledger
        self.registry = registry
        self.concurrency = concurrency
        
        # In-memory ledger if none provided
        self._memory_runs: Dict[str, RunRecord] = {}
        self._memory_events: Dict[str, list[RunEvent]] = {}
        self._idempotency_index: Dict[str, str] = {}  # idempotency_key -> run_id
    
    # === CANONICAL API ===
    
    async def submit(self, spec: WorkSpec) -> str:
        """Submit work (canonical form).
        
        This is the canonical submission method. All other submit_* methods
        are convenience wrappers that call this.
        
        Args:
            spec: Work specification
            
        Returns:
            run_id: Unique identifier for this run
            
        Example:
            >>> run_id = await dispatcher.submit(WorkSpec(
            ...     kind="task",
            ...     name="send_email",
            ...     params={"to": "user@example.com"},
            ...     priority="high",
            ... ))
        """
        # Check idempotency
        if spec.idempotency_key:
            existing = await self._find_by_idempotency_key(spec.idempotency_key)
            if existing:
                return existing.run_id
        
        # Create run record
        run_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        run = RunRecord(
            run_id=run_id,
            spec=spec,
            status=RunStatus.PENDING,
            created_at=now,
            executor_name=getattr(self.executor, 'name', None),
            tags={
                "kind": spec.kind,
                "name": spec.name,
                **(spec.metadata or {}),
            }
        )
        
        # Index idempotency key
        if spec.idempotency_key:
            self._idempotency_index[spec.idempotency_key] = run_id
        
        # Persist
        await self._save_run(run)
        await self._record_event(run_id, EventType.CREATED, {
            "kind": spec.kind,
            "name": spec.name,
        })
        
        # Submit to executor
        try:
            external_ref = await self.executor.submit(spec)
            run.external_ref = external_ref
            run.status = RunStatus.QUEUED
            await self._save_run(run)
            await self._record_event(run_id, EventType.QUEUED, {
                "external_ref": external_ref
            })
            
            # For synchronous executors (like MemoryExecutor), the work may
            # already be complete. Check status and sync if needed.
            await self._sync_from_executor(run)
            
        except Exception as e:
            run.status = RunStatus.FAILED
            run.error = str(e)
            run.error_type = type(e).__name__
            await self._save_run(run)
            await self._record_event(run_id, EventType.FAILED, {
                "error": str(e),
                "error_type": type(e).__name__,
            })
        
        return run_id
    
    # === CONVENIENCE WRAPPERS ===
    
    async def submit_task(
        self,
        name: str,
        params: dict | None = None,
        **kwargs
    ) -> str:
        """Convenience: submit a task.
        
        Example:
            >>> run_id = await dispatcher.submit_task("send_email", {"to": "user@example.com"})
        """
        spec = WorkSpec(kind="task", name=name, params=params or {}, **kwargs)
        return await self.submit(spec)
    
    async def submit_pipeline(
        self,
        name: str,
        params: dict | None = None,
        **kwargs
    ) -> str:
        """Convenience: submit a pipeline.
        
        Example:
            >>> run_id = await dispatcher.submit_pipeline("ingest_otc", {"date": "2026-01-15"})
        """
        spec = WorkSpec(kind="pipeline", name=name, params=params or {}, **kwargs)
        return await self.submit(spec)
    
    async def submit_workflow(
        self,
        name: str,
        params: dict | None = None,
        **kwargs
    ) -> str:
        """Convenience: submit a workflow.
        
        Example:
            >>> run_id = await dispatcher.submit_workflow("daily_ingest", {"tier": "NMS_TIER_1"})
        """
        spec = WorkSpec(kind="workflow", name=name, params=params or {}, **kwargs)
        return await self.submit(spec)
    
    async def submit_step(
        self,
        name: str,
        params: dict | None = None,
        parent_run_id: str | None = None,
        **kwargs
    ) -> str:
        """Convenience: submit a workflow step.
        
        Example:
            >>> run_id = await dispatcher.submit_step(
            ...     "validate",
            ...     {"data": results},
            ...     parent_run_id=workflow_run_id,
            ... )
        """
        spec = WorkSpec(
            kind="step",
            name=name,
            params=params or {},
            parent_run_id=parent_run_id,
            correlation_id=parent_run_id,  # Steps share parent's correlation
            **kwargs
        )
        return await self.submit(spec)
    
    # === QUERY ===
    
    async def get_run(self, run_id: str) -> RunRecord | None:
        """Get run by ID.
        
        Args:
            run_id: Run identifier
            
        Returns:
            RunRecord if found, None otherwise
        """
        if self.ledger:
            return await self.ledger.get_run(run_id)
        return self._memory_runs.get(run_id)
    
    async def list_runs(
        self,
        kind: str | None = None,
        status: RunStatus | None = None,
        name: str | None = None,
        parent_run_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunSummary]:
        """List runs with filters.
        
        Args:
            kind: Filter by work kind (task, pipeline, workflow, step)
            status: Filter by status
            name: Filter by handler/pipeline name
            parent_run_id: Filter steps by parent workflow
            limit: Max results (default 50)
            offset: Skip first N results
            
        Returns:
            List of RunSummary objects
            
        Example:
            >>> # List failed pipelines
            >>> runs = await dispatcher.list_runs(kind="pipeline", status=RunStatus.FAILED)
        """
        if self.ledger:
            return await self.ledger.list_runs(
                kind=kind, status=status, name=name,
                parent_run_id=parent_run_id, limit=limit, offset=offset
            )
        
        # In-memory filter
        runs = list(self._memory_runs.values())
        
        if kind:
            runs = [r for r in runs if r.spec.kind == kind]
        if status:
            runs = [r for r in runs if r.status == status]
        if name:
            runs = [r for r in runs if r.spec.name == name]
        if parent_run_id:
            runs = [r for r in runs if r.spec.parent_run_id == parent_run_id]
        
        # Sort by created_at descending (newest first)
        runs = sorted(runs, key=lambda r: r.created_at, reverse=True)
        runs = runs[offset:offset + limit]
        
        return [
            RunSummary(
                run_id=r.run_id,
                kind=r.spec.kind,
                name=r.spec.name,
                status=r.status,
                created_at=r.created_at,
                duration_seconds=r.duration_seconds,
            )
            for r in runs
        ]
    
    async def get_events(self, run_id: str) -> list[RunEvent]:
        """Get event history for run.
        
        Args:
            run_id: Run identifier
            
        Returns:
            List of events in chronological order
        """
        if self.ledger:
            return await self.ledger.get_events(run_id)
        return self._memory_events.get(run_id, [])
    
    async def get_children(self, parent_run_id: str) -> list[RunSummary]:
        """Get child runs (steps) of a workflow.
        
        Args:
            parent_run_id: Parent workflow run_id
            
        Returns:
            List of child step summaries
        """
        return await self.list_runs(parent_run_id=parent_run_id)
    
    # === CONTROL ===
    
    async def cancel(self, run_id: str) -> bool:
        """Cancel a run.
        
        Args:
            run_id: Run identifier
            
        Returns:
            True if cancelled, False if not cancellable
        """
        run = await self.get_run(run_id)
        if not run or not run.external_ref:
            return False
        
        if run.status not in (RunStatus.PENDING, RunStatus.QUEUED, RunStatus.RUNNING):
            return False  # Already finished
        
        success = await self.executor.cancel(run.external_ref)
        if success:
            run.mark_cancelled()
            await self._save_run(run)
            await self._record_event(run_id, EventType.CANCELLED)
        
        return success
    
    async def retry(self, run_id: str) -> str:
        """Retry a failed run (creates new run).
        
        Args:
            run_id: Run identifier of failed run
            
        Returns:
            New run_id for the retry
            
        Raises:
            ValueError: If original run not found
        """
        original = await self.get_run(run_id)
        if not original:
            raise ValueError(f"Run {run_id} not found")
        
        # Create new spec (clone original, clear idempotency)
        retry_spec = WorkSpec(
            kind=original.spec.kind,
            name=original.spec.name,
            params=original.spec.params,
            correlation_id=original.spec.correlation_id,
            priority=original.spec.priority,
            lane=original.spec.lane,
            parent_run_id=original.spec.parent_run_id,
            trigger_source="retry",
            metadata=original.spec.metadata,
            max_retries=original.spec.max_retries,
            retry_delay_seconds=original.spec.retry_delay_seconds,
            # Don't copy idempotency_key - this is a new run
        )
        
        # Submit new run
        new_run_id = await self.submit(retry_spec)
        
        # Link to original
        new_run = await self.get_run(new_run_id)
        if new_run:
            new_run.retry_of_run_id = run_id
            new_run.attempt = original.attempt + 1
            await self._save_run(new_run)
        
        # Record retry event on original
        await self._record_event(original.run_id, EventType.RETRIED, {
            "new_run_id": new_run_id
        })
        
        return new_run_id
    
    # === LIFECYCLE UPDATES (called by workers/executors) ===
    
    async def mark_started(self, run_id: str) -> None:
        """Mark run as started (called when execution begins)."""
        run = await self.get_run(run_id)
        if run:
            run.mark_started()
            await self._save_run(run)
            await self._record_event(run_id, EventType.STARTED)
    
    async def mark_completed(self, run_id: str, result: Any = None) -> None:
        """Mark run as completed with result."""
        run = await self.get_run(run_id)
        if run:
            run.mark_completed(result)
            await self._save_run(run)
            await self._record_event(run_id, EventType.COMPLETED, {
                "duration_seconds": run.duration_seconds,
            })
    
    async def mark_failed(self, run_id: str, error: str, error_type: str | None = None) -> None:
        """Mark run as failed with error."""
        run = await self.get_run(run_id)
        if run:
            run.mark_failed(error, error_type)
            await self._save_run(run)
            await self._record_event(run_id, EventType.FAILED, {
                "error": error,
                "error_type": error_type,
            })
    
    async def record_progress(self, run_id: str, progress: float, message: str | None = None) -> None:
        """Record progress update for long-running work."""
        await self._record_event(run_id, EventType.PROGRESS, {
            "progress": progress,
            "message": message,
        })
    
    # === INTERNAL ===
    
    async def _save_run(self, run: RunRecord) -> None:
        """Persist run."""
        if self.ledger:
            await self.ledger.save_run(run)
        else:
            self._memory_runs[run.run_id] = run
    
    async def _record_event(self, run_id: str, event_type: str, data: dict | None = None) -> None:
        """Record an event."""
        event = RunEvent(
            event_id=str(uuid.uuid4()),
            run_id=run_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            data=data or {},
        )
        
        if self.ledger:
            await self.ledger.record_event(event)
        else:
            if run_id not in self._memory_events:
                self._memory_events[run_id] = []
            self._memory_events[run_id].append(event)
    
    async def _find_by_idempotency_key(self, key: str) -> RunRecord | None:
        """Find existing run by idempotency key."""
        if self.ledger:
            return await self.ledger.find_by_idempotency_key(key)
        
        # In-memory lookup
        run_id = self._idempotency_index.get(key)
        if run_id:
            return self._memory_runs.get(run_id)
        return None
    
    async def _sync_from_executor(self, run: RunRecord) -> None:
        """Sync run status from executor.
        
        For synchronous executors like MemoryExecutor, work completes during
        submit(). This method checks the executor status and updates the
        run record accordingly.
        """
        if not run.external_ref:
            return
        
        # Check if executor has status method
        if not hasattr(self.executor, 'get_status'):
            return
        
        try:
            status = await self.executor.get_status(run.external_ref)
            
            if status == "completed":
                # Get result if available
                result = None
                if hasattr(self.executor, 'get_result'):
                    result = await self.executor.get_result(run.external_ref)
                
                run.mark_completed(result)
                await self._save_run(run)
                await self._record_event(run.run_id, EventType.COMPLETED, {
                    "duration_seconds": run.duration_seconds,
                })
                
            elif status == "failed":
                error = "Unknown error"
                if hasattr(self.executor, 'get_error'):
                    error = await self.executor.get_error(run.external_ref) or error
                
                run.mark_failed(error)
                await self._save_run(run)
                await self._record_event(run.run_id, EventType.FAILED, {
                    "error": error,
                })
                
        except Exception:
            # Executor doesn't support status checking, that's fine
            pass
    
    def clear(self) -> None:
        """Clear all in-memory data (for testing)."""
        self._memory_runs.clear()
        self._memory_events.clear()
        self._idempotency_index.clear()
