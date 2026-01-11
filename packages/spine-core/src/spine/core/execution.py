"""
Execution context for pipeline lineage tracking.

Every pipeline execution gets an execution_id. When pipelines call sub-pipelines,
the parent_execution_id links them. Batch operations share a batch_id.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ExecutionContext:
    """
    Context passed through pipeline execution for lineage.

    Attributes:
        execution_id: Unique ID for this execution
        batch_id: Shared ID for related executions (e.g., a backfill run)
        parent_execution_id: ID of the pipeline that spawned this one
        started_at: When this execution began

    Example:
        # Root execution
        ctx = new_context(batch_id="backfill_2025-12-26")

        # Child execution (sub-pipeline)
        child_ctx = ctx.child()
        assert child_ctx.parent_execution_id == ctx.execution_id
        assert child_ctx.batch_id == ctx.batch_id
    """

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: str | None = None
    parent_execution_id: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)

    def child(self) -> "ExecutionContext":
        """Create child context for sub-pipeline."""
        return ExecutionContext(batch_id=self.batch_id, parent_execution_id=self.execution_id)

    def with_batch(self, batch_id: str) -> "ExecutionContext":
        """Create copy with batch_id set."""
        return ExecutionContext(
            execution_id=self.execution_id,
            batch_id=batch_id,
            parent_execution_id=self.parent_execution_id,
            started_at=self.started_at,
        )


def new_context(batch_id: str = None) -> ExecutionContext:
    """Create new root execution context."""
    return ExecutionContext(batch_id=batch_id)


def new_batch_id(prefix: str = "") -> str:
    """
    Generate a new batch ID.

    Format: {prefix}_{timestamp}_{short_uuid}
    Example: backfill_20251226T150022_a1b2c3d4
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    short_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{ts}_{short_id}" if prefix else f"batch_{ts}_{short_id}"
