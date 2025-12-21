"""Run records - execution state and status.

This module defines RunRecord and RunStatus, the canonical contracts for
tracking execution state in spine-core. All work types use these same
structures regardless of which executor ran them.

Manifesto:
    Run tracking must be executor-agnostic.  Whether a run executes
    locally, in Celery, or in a container, the same RunRecord
    captures its lifecycle so dashboards and alerting work
    unchanged across backends.

Tags:
    spine-core, execution, runs, run-record, state-tracking

Doc-Types:
    api-reference
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .spec import WorkSpec


class RunStatus(str, Enum):
    """Execution status — the canonical state machine.

    State transitions are enforced via ``RUN_VALID_TRANSITIONS``.  The
    ``validate_run_transition()`` function and ``RunRecord.mark_*()``
    methods enforce these rules automatically.

    Valid transition graph::

        PENDING       → QUEUED | RUNNING | CANCELLED
        QUEUED        → RUNNING | COMPLETED | FAILED | CANCELLED
        RUNNING       → COMPLETED | FAILED | CANCELLED
        FAILED        → DEAD_LETTERED | PENDING (retry)
        COMPLETED     → (terminal)
        CANCELLED     → (terminal)
        DEAD_LETTERED → PENDING (retry)
    """

    PENDING = "pending"  # Created, not yet submitted to executor
    QUEUED = "queued"  # Submitted to executor, waiting to run
    RUNNING = "running"  # Actively executing
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Finished with error
    CANCELLED = "cancelled"  # Cancelled by user/system
    DEAD_LETTERED = "dead_lettered"  # Moved to DLQ after retries exhausted


# --- RunStatus transition rules ---

RUN_VALID_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.CANCELLED,
    }),
    RunStatus.QUEUED: frozenset({
        RunStatus.RUNNING,
        RunStatus.COMPLETED,  # synchronous executors may complete immediately
        RunStatus.FAILED,     # executor rejection or submission failure
        RunStatus.CANCELLED,
    }),
    RunStatus.RUNNING: frozenset({
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    }),
    RunStatus.FAILED: frozenset({
        RunStatus.DEAD_LETTERED,
        RunStatus.PENDING,  # retry
    }),
    RunStatus.COMPLETED: frozenset(),  # terminal
    RunStatus.CANCELLED: frozenset(),  # terminal
    RunStatus.DEAD_LETTERED: frozenset({
        RunStatus.PENDING,  # retry from DLQ
    }),
}


def validate_run_transition(
    current: RunStatus,
    target: RunStatus,
) -> None:
    """Raise :class:`~spine.execution.models.InvalidTransitionError` if *current → target* is illegal.

    Args:
        current: The current run status.
        target: The desired next status.

    Raises:
        InvalidTransitionError: If the transition is not in
            ``RUN_VALID_TRANSITIONS``.

    Example:
        >>> validate_run_transition(RunStatus.RUNNING, RunStatus.COMPLETED)
        >>> # OK — no exception
        >>> validate_run_transition(RunStatus.COMPLETED, RunStatus.RUNNING)
        InvalidTransitionError: Invalid RunStatus transition: completed → running
    """
    from .models import InvalidTransitionError

    allowed = RUN_VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(current.value, target.value, "RunStatus")


@dataclass
class RunRecord:
    """Execution state - the canonical tracking record.

    This is persisted to the RunLedger and represents the full state
    of a work execution, regardless of which executor ran it.

    Example:
        >>> run = RunRecord(
        ...     run_id="abc-123",
        ...     spec=task_spec("send_email", {"to": "user@example.com"}),
        ...     status=RunStatus.PENDING,
        ...     created_at=datetime.utcnow(),
        ... )
    """

    run_id: str
    """Unique identifier for this run (UUID)"""

    spec: "WorkSpec"
    """What was requested to run"""

    status: RunStatus
    """Current execution status"""

    # === TIMESTAMPS ===
    created_at: datetime
    """When the run was created"""

    started_at: datetime | None = None
    """When execution began"""

    completed_at: datetime | None = None
    """When execution finished (success or failure)"""

    # === RESULTS ===
    result: Any = None
    """Output on success (can be dict, list, primitive, etc.)"""

    error: str | None = None
    """Error message on failure"""

    error_type: str | None = None
    """Exception class name on failure"""

    # === RUNTIME TRACKING (the key for runtime-agnostic design) ===
    external_ref: str | None = None
    """Runtime-specific identifier:
    - Celery: task_id
    - Airflow: dag_run_id
    - K8s: job name
    - Local: thread id
    """

    executor_name: str | None = None
    """Which executor ran this (celery, local, airflow, k8s, etc.)"""

    # === RETRY TRACKING ===
    attempt: int = 1
    """Current attempt number (1-indexed)"""

    retry_of_run_id: str | None = None
    """If this is a retry, the run_id of the original failed run"""

    # === OBSERVABILITY ===
    duration_seconds: float | None = None
    """Execution duration (computed from started_at to completed_at)"""

    tags: dict[str, str] = field(default_factory=dict)
    """Indexed tags for filtering (tenant_id, user_id, etc.)"""

    def _transition_to(self, target: RunStatus) -> None:
        """Validate and apply a status transition.

        Raises:
            InvalidTransitionError: If *self.status → target* is illegal.
        """
        validate_run_transition(self.status, target)
        self.status = target

    def mark_started(self) -> None:
        """Mark run as started.

        Raises:
            InvalidTransitionError: If current status is not PENDING or QUEUED.
        """
        self._transition_to(RunStatus.RUNNING)
        self.started_at = datetime.utcnow()

    def mark_completed(self, result: Any = None) -> None:
        """Mark run as completed with optional result.

        Raises:
            InvalidTransitionError: If current status is not RUNNING.
        """
        self._transition_to(RunStatus.COMPLETED)
        self.completed_at = datetime.utcnow()
        self.result = result
        if self.started_at and self.completed_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

    def mark_failed(self, error: str, error_type: str | None = None) -> None:
        """Mark run as failed with error details.

        Raises:
            InvalidTransitionError: If current status is not RUNNING.
        """
        self._transition_to(RunStatus.FAILED)
        self.completed_at = datetime.utcnow()
        self.error = error
        self.error_type = error_type
        if self.started_at and self.completed_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()

    def mark_cancelled(self) -> None:
        """Mark run as cancelled.

        Raises:
            InvalidTransitionError: If current status is terminal.
        """
        self._transition_to(RunStatus.CANCELLED)
        self.completed_at = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON/storage."""
        return {
            "run_id": self.run_id,
            "kind": self.spec.kind,
            "name": self.spec.name,
            "params": self.spec.params,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "error_type": self.error_type,
            "external_ref": self.external_ref,
            "executor_name": self.executor_name,
            "attempt": self.attempt,
            "duration_seconds": self.duration_seconds,
            "tags": self.tags,
        }


@dataclass
class RunSummary:
    """Lightweight run view for list endpoints.

    Used when returning lists of runs to avoid serializing full spec/result.
    """

    run_id: str
    kind: str
    name: str
    status: RunStatus
    created_at: datetime
    duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "name": self.name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "duration_seconds": self.duration_seconds,
        }
