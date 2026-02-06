"""
Execution context for pipeline lineage tracking.

Provides execution context tracking for pipeline lineage and tracing. Every
pipeline execution gets a unique `execution_id`. When pipelines call sub-pipelines,
the `parent_execution_id` links them for distributed tracing. Batch operations
(like backfills) share a `batch_id` to correlate related executions.

This module is foundational for observability in spine projects. By passing
ExecutionContext through pipeline calls, you can:
- Trace the complete execution path of a request
- Link logs and metrics to specific executions
- Correlate batch operations that span multiple pipelines
- Debug issues by finding all related executions

Manifesto:
    - **Every execution gets an ID:** Unique identifier for tracing
    - **Parent-child linking:** Sub-pipelines link to their parent
    - **Batch correlation:** Related executions share batch_id
    - **Immutable context:** Context is copied, not mutated

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────────┐
        │                     ExecutionContext                             │
        ├─────────────────────────────────────────────────────────────────┤
        │  execution_id: str       ← Unique ID for this execution         │
        │  batch_id: str | None    ← Shared ID for related executions     │
        │  parent_execution_id: str | None  ← ID of spawning pipeline     │
        │  started_at: datetime    ← When execution began                 │
        ├─────────────────────────────────────────────────────────────────┤
        │                                                                  │
        │  Root Context            Child Context            Batch Context  │
        │  ────────────            ─────────────            ─────────────  │
        │  new_context()           ctx.child()              ctx.with_batch │
        │       │                       │                        │         │
        │       ▼                       ▼                        ▼         │
        │  execution_id: A         execution_id: B         execution_id: A │
        │  parent: None            parent: A               batch_id: X     │
        │  batch_id: X             batch_id: X             parent: None    │
        │                                                                  │
        └─────────────────────────────────────────────────────────────────┘

Features:
    - **Unique execution IDs:** UUID-based identifiers
    - **Parent-child linking:** child() method for sub-pipelines
    - **Batch correlation:** with_batch() and batch_id for grouping
    - **Timestamp tracking:** started_at for duration calculation
    - **Immutable design:** Methods return new contexts, don't mutate

Examples:
    Creating root execution context:

    >>> ctx = new_context()
    >>> len(ctx.execution_id)
    36  # UUID format
    >>> ctx.parent_execution_id is None
    True

    Creating context for a batch operation:

    >>> batch = new_batch_id("backfill")
    >>> ctx = new_context(batch_id=batch)
    >>> "backfill_" in ctx.batch_id
    True

    Linking sub-pipeline executions:

    >>> parent_ctx = new_context()
    >>> child_ctx = parent_ctx.child()
    >>> child_ctx.parent_execution_id == parent_ctx.execution_id
    True
    >>> child_ctx.batch_id == parent_ctx.batch_id
    True

    Using in pipeline code:

    >>> def fetch_filings(ctx: ExecutionContext):
    ...     # Pass child context to sub-pipelines
    ...     for cik in ciks:
    ...         fetch_company(ctx.child(), cik)
    ...     return results

Performance:
    - **new_context():** O(1), single UUID generation
    - **child():** O(1), creates new dataclass instance
    - **new_batch_id():** O(1), timestamp + short UUID

Guardrails:
    ❌ DON'T: Mutate execution context (it's a dataclass, not frozen)
    ✅ DO: Use child() or with_batch() to create new contexts

    ❌ DON'T: Create execution_id manually
    ✅ DO: Use new_context() for root, child() for sub-pipelines

    ❌ DON'T: Pass context by reference and modify it
    ✅ DO: Each function should receive its own context

Context:
    - **Problem:** Need to trace execution across distributed pipelines
    - **Solution:** Execution IDs with parent-child linking and batch IDs
    - **Alternatives:** OpenTelemetry spans, request IDs, correlation headers

Tags:
    execution-context, lineage, tracing, observability, batch-processing,
    spine-core, distributed-tracing

Doc-Types:
    - API Reference
    - Observability Guide
    - Pipeline Development Tutorial
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ExecutionContext:
    """
    Context passed through pipeline execution for lineage tracking.

    ExecutionContext is the core data structure for distributed tracing in
    spine pipelines. Each execution gets a unique ID, and when one pipeline
    calls another, the child execution links back to its parent via
    `parent_execution_id`. Batch operations share a `batch_id` for correlation.

    The context is designed to be immutable-ish: while it's a regular dataclass,
    the intended pattern is to use `child()` or `with_batch()` to create new
    contexts rather than mutating fields directly.

    Manifesto:
        - **Identity:** Every execution has a unique execution_id
        - **Lineage:** Parent-child relationships via parent_execution_id
        - **Batch correlation:** Related executions share batch_id
        - **Timestamp:** started_at enables duration calculation
        - **Copy semantics:** Methods return new contexts, preserving immutability

    Architecture:
        ::

            ┌────────────────────────────────────────────────────────────┐
            │                    ExecutionContext                         │
            ├────────────────────────────────────────────────────────────┤
            │  execution_id: str     ← UUID, auto-generated              │
            │  batch_id: str | None  ← Shared across batch operations    │
            │  parent_execution_id: str | None  ← Links to parent        │
            │  started_at: datetime  ← UTC timestamp                     │
            ├────────────────────────────────────────────────────────────┤
            │  child() -> ExecutionContext                               │
            │      Creates new context with:                              │
            │      - New execution_id                                     │
            │      - parent_execution_id = self.execution_id             │
            │      - Inherited batch_id                                   │
            ├────────────────────────────────────────────────────────────┤
            │  with_batch(batch_id) -> ExecutionContext                  │
            │      Creates copy with batch_id set                        │
            └────────────────────────────────────────────────────────────┘

    Features:
        - **Auto-generated IDs:** execution_id is a UUID by default
        - **Child context creation:** child() for sub-pipeline calls
        - **Batch ID propagation:** batch_id inherited by children
        - **Timestamp tracking:** started_at for metrics/debugging

    Examples:
        Creating root execution context:

        >>> ctx = ExecutionContext()
        >>> len(ctx.execution_id)  # UUID format
        36
        >>> ctx.parent_execution_id is None
        True

        Creating child context for sub-pipeline:

        >>> parent = ExecutionContext(batch_id="batch_123")
        >>> child = parent.child()
        >>> child.parent_execution_id == parent.execution_id
        True
        >>> child.batch_id == parent.batch_id  # Inherited
        True

        Adding batch ID to existing context:

        >>> ctx = ExecutionContext()
        >>> batched = ctx.with_batch("backfill_20260202")
        >>> batched.batch_id
        'backfill_20260202'
        >>> batched.execution_id == ctx.execution_id  # Same execution
        True

        Using in structured logging:

        >>> import json
        >>> ctx = ExecutionContext(batch_id="batch_1")
        >>> log_data = {
        ...     "execution_id": ctx.execution_id,
        ...     "batch_id": ctx.batch_id,
        ...     "message": "Starting pipeline"
        ... }

    Performance:
        - **Creation:** O(1), UUID generation
        - **child():** O(1), dataclass instantiation
        - **with_batch():** O(1), dataclass instantiation
        - **Memory:** ~200 bytes per context

    Guardrails:
        ❌ DON'T: Mutate execution_id or parent_execution_id
        ✅ DO: Treat context as immutable, use child()/with_batch()

        ❌ DON'T: Share context across concurrent operations
        ✅ DO: Each concurrent task gets its own child context

        ❌ DON'T: Generate execution_id manually
        ✅ DO: Let the default factory generate UUIDs

    Context:
        - **Problem:** Need to trace execution flow across pipeline calls
        - **Solution:** Immutable context with parent-child linking
        - **Alternatives:** Thread-local storage, OpenTelemetry context

    Tags:
        execution-context, lineage, tracing, dataclass, spine-core,
        distributed-tracing, batch-processing

    Doc-Types:
        - API Reference
        - Pipeline Development Guide
        - Observability Tutorial

    Attributes:
        execution_id: Unique ID for this execution (UUID string)
        batch_id: Shared ID for related executions (e.g., a backfill run)
        parent_execution_id: ID of the pipeline that spawned this one
        started_at: When this execution began (UTC datetime)
    """

    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: str | None = None
    parent_execution_id: str | None = None
    started_at: datetime = field(default_factory=datetime.utcnow)

    def child(self) -> "ExecutionContext":
        """
        Create child context for sub-pipeline execution.

        Creates a new ExecutionContext with:
        - A new unique execution_id
        - parent_execution_id set to this context's execution_id
        - batch_id inherited from this context
        - New started_at timestamp

        This establishes the parent-child relationship for lineage tracking.

        Examples:
            >>> parent = ExecutionContext(batch_id="batch_1")
            >>> child = parent.child()
            >>> child.parent_execution_id == parent.execution_id
            True
            >>> child.batch_id == parent.batch_id
            True
            >>> child.execution_id != parent.execution_id
            True

        Returns:
            New ExecutionContext linked to this one as parent
        """
        return ExecutionContext(batch_id=self.batch_id, parent_execution_id=self.execution_id)

    def with_batch(self, batch_id: str) -> "ExecutionContext":
        """
        Create copy with batch_id set.

        Creates a new ExecutionContext with the same execution_id but with
        the specified batch_id. Useful for adding batch correlation to an
        existing context without creating a child.

        Examples:
            >>> ctx = ExecutionContext()
            >>> batched = ctx.with_batch("backfill_20260202")
            >>> batched.execution_id == ctx.execution_id
            True
            >>> batched.batch_id
            'backfill_20260202'

        Args:
            batch_id: The batch identifier to set

        Returns:
            New ExecutionContext with batch_id set
        """
        return ExecutionContext(
            execution_id=self.execution_id,
            batch_id=batch_id,
            parent_execution_id=self.parent_execution_id,
            started_at=self.started_at,
        )


def new_context(batch_id: str = None) -> ExecutionContext:
    """
    Create new root execution context.

    Factory function to create a fresh ExecutionContext for a new pipeline
    execution. Optionally associates it with a batch_id for correlation.

    This is the entry point for creating execution contexts. Call this at
    the start of a pipeline execution, then use ctx.child() for sub-pipelines.

    Manifesto:
        - **Clean entry point:** Single function to start execution tracking
        - **Optional batching:** Pass batch_id for batch operations
        - **Root context:** No parent_execution_id (this is the root)

    Examples:
        Simple root context:

        >>> ctx = new_context()
        >>> ctx.parent_execution_id is None
        True

        With batch ID:

        >>> batch = new_batch_id("backfill")
        >>> ctx = new_context(batch_id=batch)
        >>> "backfill_" in ctx.batch_id
        True

        Pipeline entry point pattern:

        >>> def run_pipeline():
        ...     ctx = new_context()
        ...     # ... pipeline logic using ctx
        ...     return ctx.execution_id

    Args:
        batch_id: Optional batch identifier for correlation

    Returns:
        New root ExecutionContext

    Tags:
        factory, execution-context, pipeline-entry, spine-core

    Doc-Types:
        - API Reference
    """
    return ExecutionContext(batch_id=batch_id)


def new_batch_id(prefix: str = "") -> str:
    """
    Generate a new batch ID for correlating related executions.

    Creates a unique batch identifier combining an optional prefix, a UTC
    timestamp, and a short UUID. The format ensures:
    - Human-readable prefix for identification
    - Timestamp for ordering and debugging
    - UUID suffix for uniqueness

    Format: {prefix}_{timestamp}_{short_uuid}
    Example: backfill_20260202T150022_a1b2c3d4

    Manifesto:
        - **Human-readable:** Prefix indicates the operation type
        - **Sortable:** Timestamp enables chronological ordering
        - **Unique:** UUID suffix prevents collisions
        - **Compact:** 8-char UUID suffix, not full 36-char

    Examples:
        With prefix:

        >>> batch_id = new_batch_id("backfill")
        >>> batch_id.startswith("backfill_")
        True
        >>> len(batch_id.split("_"))
        3

        Without prefix:

        >>> batch_id = new_batch_id()
        >>> batch_id.startswith("batch_")
        True

        Using in batch operations:

        >>> batch_id = new_batch_id("daily_ingest")
        >>> ctx1 = new_context(batch_id=batch_id)
        >>> ctx2 = new_context(batch_id=batch_id)
        >>> ctx1.batch_id == ctx2.batch_id  # Same batch
        True

    Args:
        prefix: Optional prefix for the batch ID (e.g., "backfill", "daily")

    Returns:
        Unique batch ID string

    Tags:
        batch-id, factory, correlation, spine-core

    Doc-Types:
        - API Reference
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    short_id = str(uuid.uuid4())[:8]
    return f"{prefix}_{ts}_{short_id}" if prefix else f"batch_{ts}_{short_id}"
