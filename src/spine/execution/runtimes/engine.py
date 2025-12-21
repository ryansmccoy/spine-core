"""Job Engine — orchestrates container job lifecycle.

The ``JobEngine`` is the central facade for submitting, tracking, and
managing container jobs. It coordinates between the runtime adapter
(via ``RuntimeAdapterRouter``), the execution ledger, and the validator.

Architecture:

    .. code-block:: text

        JobEngine — Central Facade
        ┌─────────────────────────────────────────────────────────────┐
        │                                                             │
        │  submit(spec)                                               │
        │    ├── validate spec (SpecValidator)                        │
        │    ├── check idempotency (Ledger)                           │
        │    ├── create execution record (Ledger)                     │
        │    ├── route to adapter (Router)                            │
        │    ├── adapter.submit(spec) → external_ref                  │
        │    ├── update execution metadata with external_ref          │
        │    └── return SubmitResult                                  │
        │                                                             │
        │  status(execution_id)                                       │
        │    ├── get execution from Ledger                             │
        │    ├── get external_ref from metadata                       │
        │    ├── adapter.status(ref) → JobStatus                      │
        │    └── map runtime state → ExecutionStatus                  │
        │                                                             │
        │  cancel(execution_id)                                       │
        │    ├── get execution from Ledger                             │
        │    ├── adapter.cancel(ref)                                  │
        │    └── update Ledger → CANCELLED                            │
        │                                                             │
        │  logs(execution_id)                                         │
        │    ├── get external_ref from metadata                       │
        │    └── adapter.logs(ref) → AsyncIterator[str]               │
        │                                                             │
        │  cleanup(execution_id)                                      │
        │    ├── adapter.cleanup(ref)                                 │
        │    └── record CLEANUP_COMPLETED event                       │
        │                                                             │
        └─────────────────────────────────────────────────────────────┘

    .. mermaid::

        sequenceDiagram
            participant C as Client
            participant E as JobEngine
            participant V as SpecValidator
            participant R as Router
            participant L as Ledger
            participant A as RuntimeAdapter

            C->>E: submit(spec)
            E->>V: validate_or_raise(spec, adapter)
            E->>L: check idempotency
            E->>L: create_execution()
            E->>R: route(spec) → adapter
            E->>A: submit(spec) → external_ref
            E->>L: update metadata (external_ref, runtime)
            E-->>C: SubmitResult

            C->>E: status(execution_id)
            E->>L: get_execution()
            E->>A: status(external_ref) → JobStatus
            E-->>C: JobStatus

            C->>E: cancel(execution_id)
            E->>A: cancel(external_ref)
            E->>L: update_status(CANCELLED)
            E-->>C: True/False

Example:
    >>> from spine.execution.runtimes.engine import JobEngine
    >>> from spine.execution.runtimes._base import StubRuntimeAdapter
    >>> from spine.execution.runtimes.router import RuntimeAdapterRouter
    >>> from spine.execution.runtimes.validator import SpecValidator
    >>> from spine.execution.ledger import ExecutionLedger
    >>>
    >>> router = RuntimeAdapterRouter()
    >>> router.register(StubRuntimeAdapter())
    >>> engine = JobEngine(
    ...     router=router,
    ...     ledger=ExecutionLedger(conn),
    ...     validator=SpecValidator(),
    ... )
    >>> result = await engine.submit(spec)
    >>> print(result.execution_id, result.external_ref)

Manifesto:
    The JobEngine is the single entry-point for submitting work.
    It resolves the right runtime adapter, validates the spec,
    and records the execution — callers never interact with
    adapters directly.

Tags:
    spine-core, execution, runtimes, engine, facade, submission

Doc-Types:
    api-reference
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from spine.execution.models import (
    EventType,
    Execution,
    ExecutionStatus,
    TriggerSource,
)
from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    JobStatus,
    redact_spec,
)
from spine.execution.runtimes.router import RuntimeAdapterRouter
from spine.execution.runtimes.validator import SpecValidator

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Submit result envelope
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubmitResult:
    """Result returned by ``JobEngine.submit()``.

    Contains both the internal execution ID (for ledger tracking) and the
    external reference (container ID, pod name, ARN) from the runtime.

    Attributes:
        execution_id: Internal execution UUID (for ledger/API).
        external_ref: Runtime-provided reference (container ID, pod name).
        runtime: Name of the runtime adapter that handled the submit.
        spec_hash: SHA-256 hash of the canonical spec.
    """

    execution_id: str
    external_ref: str
    runtime: str
    spec_hash: str


# ---------------------------------------------------------------------------
# State mapping: runtime JobStatus → ExecutionStatus
# ---------------------------------------------------------------------------

_RUNTIME_STATE_TO_EXECUTION: dict[str, ExecutionStatus] = {
    "pending": ExecutionStatus.QUEUED,
    "pulling": ExecutionStatus.RUNNING,
    "creating": ExecutionStatus.RUNNING,
    "running": ExecutionStatus.RUNNING,
    "succeeded": ExecutionStatus.COMPLETED,
    "failed": ExecutionStatus.FAILED,
    "cancelled": ExecutionStatus.CANCELLED,
    "unknown": ExecutionStatus.RUNNING,  # Treat unknown as still running
}


def _map_job_status(job_status: JobStatus) -> ExecutionStatus:
    """Map runtime JobStatus state to ExecutionStatus."""
    return _RUNTIME_STATE_TO_EXECUTION.get(
        job_status.state, ExecutionStatus.RUNNING,
    )


# ---------------------------------------------------------------------------
# JobEngine
# ---------------------------------------------------------------------------

class JobEngine:
    """Central facade for container job lifecycle management.

    The engine coordinates between:
    - ``RuntimeAdapterRouter`` — selects the right adapter
    - ``SpecValidator`` — validates specs before submission
    - ``ExecutionLedger`` — persists execution state (sync)
    - ``RuntimeAdapter`` — executes container operations (async)

    All engine methods are ``async`` to match the RuntimeAdapter protocol.
    The ledger is synchronous (SQLite/psycopg) and called from within
    async methods — this is safe because ledger I/O is local and fast.

    Extended data (``external_ref``, ``runtime``, ``spec_hash``, redacted
    spec) is stored in the execution's ``result`` JSON column as metadata
    until the dedicated schema columns are added in Phase 2.

    Example:
        >>> engine = JobEngine(router=router, ledger=ledger)
        >>> result = await engine.submit(spec)
        >>> status = await engine.status(result.execution_id)
        >>> await engine.cancel(result.execution_id)
        >>> await engine.cleanup(result.execution_id)
    """

    def __init__(
        self,
        *,
        router: RuntimeAdapterRouter,
        ledger: Any,  # ExecutionLedger — typed as Any to avoid circular imports
        validator: SpecValidator | None = None,
    ) -> None:
        """Initialize the JobEngine.

        Args:
            router: Runtime adapter router with registered adapters.
            ledger: ExecutionLedger for persisting execution state.
            validator: Optional spec validator. If None, a default is created.
        """
        self._router = router
        self._ledger = ledger
        self._validator = validator or SpecValidator()

        # Internal tracking: execution_id → {external_ref, runtime}
        # This is an in-memory cache for fast lookups. The authoritative
        # data is in the ledger's result/metadata column.
        self._refs: dict[str, dict[str, str]] = {}

    @property
    def router(self) -> RuntimeAdapterRouter:
        """The runtime adapter router."""
        return self._router

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    async def submit(self, spec: ContainerJobSpec) -> SubmitResult:
        """Submit a container job for execution.

        Full lifecycle:
        1. Route to adapter
        2. Validate spec against adapter capabilities
        3. Check idempotency key (if provided)
        4. Create execution record in ledger
        5. Submit to runtime adapter
        6. Update execution with external_ref metadata
        7. Return SubmitResult

        Args:
            spec: The container job specification.

        Returns:
            SubmitResult with execution_id, external_ref, runtime, spec_hash.

        Raises:
            JobError: On validation failure, routing failure, or submit failure.
        """
        # 1. Route to adapter
        adapter = self._router.route(spec)
        runtime_name = adapter.runtime_name

        # 2. Validate
        self._validator.validate_or_raise(spec, adapter)

        # 3. Idempotency check
        if spec.idempotency_key:
            existing = self._ledger.get_by_idempotency_key(spec.idempotency_key)
            if existing is not None:
                logger.info(
                    "Idempotency key '%s' already exists: execution_id=%s",
                    spec.idempotency_key, existing.id,
                )
                # Return cached result from previous submit
                cached_ref = self._refs.get(existing.id, {})
                return SubmitResult(
                    execution_id=existing.id,
                    external_ref=cached_ref.get("external_ref", ""),
                    runtime=cached_ref.get("runtime", runtime_name),
                    spec_hash=spec.spec_hash(),
                )

        # 4. Create execution record
        trigger = _map_trigger_source(spec.trigger_source)
        execution = Execution.create(
            workflow=f"job:{spec.name}",
            params={"spec": redact_spec(spec)},
            lane=spec.lane,
            trigger_source=trigger,
            parent_execution_id=spec.parent_execution_id,
            idempotency_key=spec.idempotency_key,
        )
        self._ledger.create_execution(execution)
        logger.info(
            "Created execution %s for job '%s' on %s",
            execution.id, spec.name, runtime_name,
        )

        # 5. Submit to runtime
        try:
            external_ref = await adapter.submit(spec)
        except JobError:
            # Mark execution as failed
            self._ledger.update_status(
                execution.id,
                ExecutionStatus.FAILED,
                error="Submit failed",
            )
            raise
        except Exception as exc:
            self._ledger.update_status(
                execution.id,
                ExecutionStatus.FAILED,
                error=f"Submit error: {exc}",
            )
            raise JobError(
                category=ErrorCategory.UNKNOWN,
                message=f"Submit failed: {exc}",
                retryable=True,
                runtime=runtime_name,
            ) from exc

        # 6. Update execution with metadata
        spec_hash = spec.spec_hash()
        ref_info = {
            "external_ref": external_ref,
            "runtime": runtime_name,
            "spec_hash": spec_hash,
        }
        self._refs[execution.id] = {
            "external_ref": external_ref,
            "runtime": runtime_name,
        }
        self._ledger.update_status(
            execution.id,
            ExecutionStatus.RUNNING,
        )

        # Record container lifecycle event (carries the metadata)
        self._ledger.record_event(
            execution.id,
            EventType.CONTAINER_CREATED,
            ref_info,
        )

        logger.info(
            "Job '%s' submitted: execution_id=%s, external_ref=%s, runtime=%s",
            spec.name, execution.id, external_ref, runtime_name,
        )

        return SubmitResult(
            execution_id=execution.id,
            external_ref=external_ref,
            runtime=runtime_name,
            spec_hash=spec_hash,
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self, execution_id: str) -> JobStatus:
        """Get current job status from the runtime.

        Fetches real-time status from the runtime adapter and syncs
        the ledger if the execution status has changed.

        Args:
            execution_id: Internal execution UUID.

        Returns:
            JobStatus from the runtime adapter.

        Raises:
            JobError: If execution not found or status check fails.
        """
        execution = self._get_execution_or_raise(execution_id)
        ref_info = self._get_ref_info(execution_id, execution)
        adapter = self._get_adapter_for_execution(ref_info["runtime"])

        job_status = await adapter.status(ref_info["external_ref"])

        # Sync ledger if status changed
        new_exec_status = _map_job_status(job_status)
        if execution.status != new_exec_status:
            try:
                self._ledger.update_status(
                    execution_id,
                    new_exec_status,
                    result={"last_job_status": job_status.to_dict()},
                    error=job_status.message if job_status.state == "failed" else None,
                )
            except Exception:
                # Non-fatal: status sync is best-effort
                logger.warning(
                    "Failed to sync status for %s: %s → %s",
                    execution_id, execution.status.value, new_exec_status.value,
                )

        return job_status

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------

    async def cancel(self, execution_id: str) -> bool:
        """Cancel a running job.

        Args:
            execution_id: Internal execution UUID.

        Returns:
            True if cancellation was initiated, False otherwise.

        Raises:
            JobError: If execution not found.
        """
        execution = self._get_execution_or_raise(execution_id)

        # Already terminal — no-op
        if execution.status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ):
            logger.info(
                "Cancel no-op: execution %s already %s",
                execution_id, execution.status.value,
            )
            return True

        ref_info = self._get_ref_info(execution_id, execution)
        adapter = self._get_adapter_for_execution(ref_info["runtime"])

        result = await adapter.cancel(ref_info["external_ref"])

        if result:
            self._ledger.update_status(
                execution_id,
                ExecutionStatus.CANCELLED,
            )
            logger.info("Cancelled execution %s", execution_id)
        else:
            logger.warning("Cancel failed for execution %s", execution_id)

        return result

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    async def logs(
        self,
        execution_id: str,
        *,
        follow: bool = False,
        tail: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream or fetch log lines from a job.

        Args:
            execution_id: Internal execution UUID.
            follow: If True, stream logs in real-time.
            tail: If set, return only the last N lines.

        Yields:
            Log lines from the runtime adapter.

        Raises:
            JobError: If execution not found.
        """
        self._get_execution_or_raise(execution_id)
        ref_info = self._get_ref_info(execution_id)
        adapter = self._get_adapter_for_execution(ref_info["runtime"])

        async for line in adapter.logs(
            ref_info["external_ref"], follow=follow, tail=tail,
        ):
            yield line

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def cleanup(self, execution_id: str) -> None:
        """Remove runtime resources for a job.

        Idempotent — cleaning up already-removed resources is a no-op.
        Records CLEANUP_STARTED and CLEANUP_COMPLETED events.

        Args:
            execution_id: Internal execution UUID.

        Raises:
            JobError: If execution not found.
        """
        self._get_execution_or_raise(execution_id)
        ref_info = self._get_ref_info(execution_id)
        adapter = self._get_adapter_for_execution(ref_info["runtime"])

        self._ledger.record_event(
            execution_id,
            EventType.CLEANUP_STARTED,
            {"runtime": ref_info["runtime"]},
        )

        await adapter.cleanup(ref_info["external_ref"])

        self._ledger.record_event(
            execution_id,
            EventType.CLEANUP_COMPLETED,
            {"runtime": ref_info["runtime"]},
        )

        logger.info("Cleanup complete for execution %s", execution_id)

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_jobs(
        self,
        status: ExecutionStatus | None = None,
        limit: int = 100,
    ) -> list[Execution]:
        """List job executions with optional filters.

        Only returns executions created by the job engine (workflow
        starts with ``job:``).

        Args:
            status: Filter by execution status.
            limit: Maximum results to return.

        Returns:
            List of Execution records.
        """
        executions = self._ledger.list_executions(
            status=status,
            limit=limit,
        )
        # Filter to job engine executions only
        return [e for e in executions if e.workflow.startswith("job:")]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_execution_or_raise(self, execution_id: str) -> Execution:
        """Get execution from ledger or raise JobError."""
        execution = self._ledger.get_execution(execution_id)
        if execution is None:
            raise JobError(
                category=ErrorCategory.NOT_FOUND,
                message=f"Execution not found: {execution_id}",
                retryable=False,
            )
        return execution

    def _get_ref_info(
        self,
        execution_id: str,
        execution: Execution | None = None,
    ) -> dict[str, str]:
        """Get external_ref and runtime for an execution.

        Checks in-memory cache first, then falls back to the ledger's
        CONTAINER_CREATED event data.

        Returns:
            Dict with 'external_ref' and 'runtime' keys.

        Raises:
            JobError: If no ref info is available.
        """
        # Check in-memory cache
        if execution_id in self._refs:
            return self._refs[execution_id]

        # Fall back to CONTAINER_CREATED event
        events = self._ledger.get_events(execution_id)
        for event in events:
            event_type_val = (
                event.event_type.value
                if hasattr(event.event_type, "value")
                else str(event.event_type)
            )
            if event_type_val == EventType.CONTAINER_CREATED.value:
                ref = event.data.get("external_ref")
                runtime = event.data.get("runtime")
                if ref and runtime:
                    info = {"external_ref": ref, "runtime": runtime}
                    self._refs[execution_id] = info
                    return info

        raise JobError(
            category=ErrorCategory.NOT_FOUND,
            message=(
                f"No runtime reference for execution {execution_id}. "
                "Job may not have been submitted via JobEngine."
            ),
            retryable=False,
        )

    def _get_adapter_for_execution(self, runtime_name: str):
        """Get adapter by runtime name, raising if not found."""
        adapter = self._router.get(runtime_name)
        if adapter is None:
            raise JobError(
                category=ErrorCategory.RUNTIME_UNAVAILABLE,
                message=f"Runtime '{runtime_name}' is no longer registered",
                retryable=True,
            )
        return adapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map_trigger_source(source: str) -> TriggerSource:
    """Map spec trigger_source string to TriggerSource enum."""
    mapping = {
        "api": TriggerSource.API,
        "cli": TriggerSource.CLI,
        "schedule": TriggerSource.SCHEDULE,
        "retry": TriggerSource.RETRY,
        "workflow": TriggerSource.WORKFLOW,
        "internal": TriggerSource.INTERNAL,
    }
    return mapping.get(source, TriggerSource.API)
