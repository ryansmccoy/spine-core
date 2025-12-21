"""
Backfill planning primitives for gap-filling operations.

Provides a structured plan for re-processing a range of partitions
after detecting gaps, corrections, or data-quality issues.  Supports
checkpoint-based resume so that multi-hour backfills can survive
crashes without restarting from scratch.

Manifesto:
    Financial data has strict completeness requirements. If an SEC EDGAR
    crawl misses Q3 filings for 200 companies, downstream models,
    compliance reports, and client queries break. Backfill plans capture
    *what* is missing, *why*, and *how far* recovery has progressed:

    - **Structured recovery:** BackfillPlan captures partition_keys, reason, progress
    - **Crash safety:** Checkpoint-based resume for multi-hour backfills
    - **Audit trail:** Reason enum (GAP, CORRECTION, SCHEMA_CHANGE, QUALITY_FAILURE)
    - **Progress visibility:** completed_keys, failed_keys, progress_pct

Architecture:
    ::

        ┌───────────────────────────────────────────────────────────┐
        │                  Backfill Lifecycle                        │
        └───────────────────────────────────────────────────────────┘

        WatermarkStore.list_gaps()
              │
              ▼
        BackfillPlan.create(domain, source, partition_keys, reason)
              │  status: PLANNED
              ▼
        plan.start()         → status: RUNNING
              │
              ├── plan.mark_partition_done("AAPL")   progress: 33%
              ├── plan.mark_partition_done("MSFT")   progress: 66%
              └── plan.mark_partition_done("GOOG")   progress: 100%
                    │
                    ▼
        status: COMPLETED (or FAILED if errors)

Features:
    - **BackfillPlan:** Specification + mutable progress tracking
    - **BackfillStatus:** PLANNED → RUNNING → COMPLETED / FAILED / CANCELLED
    - **BackfillReason:** GAP, CORRECTION, QUALITY_FAILURE, SCHEMA_CHANGE, MANUAL
    - **Checkpoint resume:** Crash at hour 4 → resume from last checkpoint
    - **Progress tracking:** completed_keys, failed_keys, progress_pct

Examples:
    >>> from spine.core.backfill import BackfillPlan, BackfillReason
    >>> plan = BackfillPlan.create(
    ...     domain="equity",
    ...     source="polygon",
    ...     partition_keys=["AAPL", "MSFT", "GOOG"],
    ...     reason=BackfillReason.GAP,
    ... )
    >>> plan.progress_pct
    0.0
    >>> plan = plan.mark_partition_done("AAPL")
    >>> plan.progress_pct
    33.33

Performance:
    - Plan creation: O(1), lightweight dataclass
    - mark_partition_done(): O(1) set operation
    - progress_pct: O(1) computation from set sizes

Guardrails:
    ❌ DON'T: Run backfills without a BackfillPlan (no audit trail)
    ✅ DO: Always create a plan with reason for compliance tracking

    ❌ DON'T: Restart from scratch after a crash
    ✅ DO: Use checkpoint-based resume via completed_keys

    ❌ DON'T: Backfill without checking watermarks first
    ✅ DO: Use WatermarkStore.list_gaps() to drive backfill decisions

Context:
    Problem: Multi-hour backfills crash without progress tracking, and
        ad-hoc re-processing scripts have no audit trail or visibility.
    Solution: Structured backfill plans with lifecycle states, reason
        tracking, and checkpoint-based resume.
    Alternatives Considered: Airflow backfill (external dependency),
        manual scripts (no audit), database flags (no progress tracking).

Tags:
    backfill, gap-fill, resume, checkpoint, operation, spine-core,
    crash-recovery, partition-tracking, audit-trail

Doc-Types:
    - API Reference
    - Operation Patterns Guide
    - Data Engineering Best Practices

STDLIB ONLY — no Pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from spine.core.timestamps import generate_ulid, utc_now

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BackfillStatus(str, Enum):
    """Lifecycle status of a backfill plan."""

    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackfillReason(str, Enum):
    """Why a backfill was triggered."""

    GAP = "gap"
    CORRECTION = "correction"
    QUALITY_FAILURE = "quality_failure"
    SCHEMA_CHANGE = "schema_change"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# BackfillPlan
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BackfillPlan:
    """Tracks a backfill across a set of partitions with resume support.

    BackfillPlan is intentionally *not* frozen — its progress tracking
    fields (``completed_keys``, ``status``, ``checkpoint``) are mutated
    during execution.  The immutable specification fields
    (``domain``, ``source``, ``partition_keys``, ``reason``) define
    *what* is being backfilled and should not change after creation.

    Attributes:
        plan_id: Unique identifier for this plan (ULID).
        domain: Logical domain being backfilled.
        source: Data source identifier.
        partition_keys: The full list of partitions to process.
        reason: Why the backfill was created.
        status: Current lifecycle status.
        range_start: Optional start of the temporal range.
        range_end: Optional end of the temporal range.
        completed_keys: Partitions that have been successfully processed.
        failed_keys: Partitions that failed (with error messages).
        checkpoint: Opaque resume token (e.g. last offset within a partition).
        metadata: Arbitrary extras.
        created_at: When the plan was created.
        started_at: When execution began.
        completed_at: When execution finished (success, fail, or cancel).
        created_by: Who/what created the plan.
    """

    plan_id: str
    domain: str
    source: str
    partition_keys: list[str]
    reason: BackfillReason
    status: BackfillStatus = BackfillStatus.PLANNED
    range_start: str | None = None
    range_end: str | None = None
    completed_keys: list[str] = field(default_factory=list)
    failed_keys: dict[str, str] = field(default_factory=dict)
    checkpoint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_by: str = "system"

    # -- factory -------------------------------------------------------------

    @classmethod
    def create(
        cls,
        domain: str,
        source: str,
        partition_keys: list[str],
        reason: BackfillReason,
        *,
        range_start: str | None = None,
        range_end: str | None = None,
        created_by: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> BackfillPlan:
        """Create a new backfill plan.

        Args:
            domain: Logical domain.
            source: Data source identifier.
            partition_keys: Partitions to backfill (1 or more).
            reason: Why the backfill is being created.
            range_start: Optional lower bound of temporal range.
            range_end: Optional upper bound of temporal range.
            created_by: Creator identifier.
            metadata: Arbitrary extras.

        Returns:
            A new :class:`BackfillPlan` in ``PLANNED`` status.

        Raises:
            ValueError: If *partition_keys* is empty.
        """
        if not partition_keys:
            raise ValueError("partition_keys must not be empty")
        return cls(
            plan_id=generate_ulid(),
            domain=domain,
            source=source,
            partition_keys=list(partition_keys),
            reason=reason,
            range_start=range_start,
            range_end=range_end,
            created_by=created_by,
            metadata=metadata or {},
        )

    # -- properties ----------------------------------------------------------

    @property
    def progress_pct(self) -> float:
        """Completion percentage (0.0 – 100.0)."""
        total = len(self.partition_keys)
        if total == 0:
            return 100.0
        done = len(self.completed_keys) + len(self.failed_keys)
        return round(done / total * 100, 2)

    @property
    def is_resumable(self) -> bool:
        """Can this plan be resumed after interruption?

        True when status is ``RUNNING`` or ``FAILED`` and there are
        still unfinished partitions.
        """
        if self.status not in (BackfillStatus.RUNNING, BackfillStatus.FAILED):
            return False
        return len(self.remaining_keys) > 0

    @property
    def remaining_keys(self) -> list[str]:
        """Partition keys that have not yet been completed or failed."""
        done = set(self.completed_keys) | set(self.failed_keys)
        return [k for k in self.partition_keys if k not in done]

    # -- lifecycle transitions -----------------------------------------------

    def start(self) -> BackfillPlan:
        """Transition to ``RUNNING``.

        Raises:
            ValueError: If the plan is not in ``PLANNED`` or ``FAILED`` status.

        Returns:
            ``self`` (for chaining).
        """
        if self.status not in (BackfillStatus.PLANNED, BackfillStatus.FAILED):
            raise ValueError(
                f"Cannot start plan in status {self.status.value}"
            )
        self.status = BackfillStatus.RUNNING
        self.started_at = datetime.now(UTC)
        return self

    def mark_partition_done(self, partition_key: str) -> BackfillPlan:
        """Record that *partition_key* was processed successfully.

        Args:
            partition_key: The key that completed.

        Raises:
            ValueError: If *partition_key* is not one of the plan's keys.

        Returns:
            ``self`` (for chaining).
        """
        if partition_key not in self.partition_keys:
            raise ValueError(f"Unknown partition_key: {partition_key}")
        if partition_key not in self.completed_keys:
            self.completed_keys.append(partition_key)
        # Auto-complete when all partitions are done
        if not self.remaining_keys:
            self.status = BackfillStatus.COMPLETED
            self.completed_at = datetime.now(UTC)
        return self

    def mark_partition_failed(
        self,
        partition_key: str,
        error: str,
    ) -> BackfillPlan:
        """Record that *partition_key* failed.

        Args:
            partition_key: The key that failed.
            error: Error description.

        Raises:
            ValueError: If *partition_key* is not one of the plan's keys.

        Returns:
            ``self`` (for chaining).
        """
        if partition_key not in self.partition_keys:
            raise ValueError(f"Unknown partition_key: {partition_key}")
        self.failed_keys[partition_key] = error
        # If all partitions are done (some failed), mark as FAILED
        if not self.remaining_keys:
            self.status = BackfillStatus.FAILED
            self.completed_at = datetime.now(UTC)
        return self

    def save_checkpoint(self, checkpoint: str) -> BackfillPlan:
        """Persist an opaque checkpoint token for resume.

        Args:
            checkpoint: Opaque string (e.g. offset, timestamp, page token).

        Returns:
            ``self`` (for chaining).
        """
        self.checkpoint = checkpoint
        return self

    def cancel(self) -> BackfillPlan:
        """Cancel the backfill.

        Returns:
            ``self`` (for chaining).
        """
        self.status = BackfillStatus.CANCELLED
        self.completed_at = datetime.now(UTC)
        return self

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict (for DB persistence).

        Returns:
            Dict with all plan fields, datetimes as ISO-8601 strings.
        """
        return {
            "plan_id": self.plan_id,
            "domain": self.domain,
            "source": self.source,
            "partition_keys_json": self.partition_keys,
            "reason": self.reason.value,
            "status": self.status.value,
            "range_start": self.range_start,
            "range_end": self.range_end,
            "completed_keys_json": self.completed_keys,
            "failed_keys_json": self.failed_keys,
            "checkpoint": self.checkpoint,
            "metadata_json": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_by": self.created_by,
        }
