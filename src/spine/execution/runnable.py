"""Runnable protocol — unified interface for submitting pipeline work.

``EventDispatcher`` (execution layer) is the canonical implementation.
``WorkflowRunner`` depends on ``Runnable`` rather than a concrete
dispatcher class, so any backend that can execute a pipeline by name
is interchangeable.

Usage::

    from spine.execution.dispatcher import EventDispatcher
    from spine.execution.executors import MemoryExecutor
    from spine.orchestration import WorkflowRunner

    dispatcher = EventDispatcher(executor=MemoryExecutor())
    runner = WorkflowRunner(runnable=dispatcher)   # ← accepts any Runnable
    result = runner.execute(workflow, params={...})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

# ── Concrete result ──────────────────────────────────────────────────


@dataclass
class PipelineRunResult:
    """Concrete result returned by ``Runnable.submit_pipeline_sync``."""

    status: str
    """``'completed'``, ``'failed'``, ``'cancelled'``."""

    error: str | None = None
    """Error message if the run failed, else ``None``."""

    metrics: dict[str, Any] = field(default_factory=dict)
    """Arbitrary metrics dict (rows processed, duration, etc.)."""

    run_id: str | None = None
    """Execution-layer run ID (set when routed through ``EventDispatcher``)."""

    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "completed"

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


# ── Protocol ─────────────────────────────────────────────────────────


@runtime_checkable
class Runnable(Protocol):
    """Unified protocol for submitting pipeline work.

    Any object that can run a pipeline by name and return a result
    satisfies this protocol.  ``WorkflowRunner`` depends on this
    rather than a concrete dispatcher class.

    Implementors
    ------------
    * ``EventDispatcher`` — canonical, full tracking via ``RunRecord``
    * Custom backends — just implement ``submit_pipeline_sync()``
    """

    def submit_pipeline_sync(
        self,
        pipeline_name: str,
        params: dict[str, Any] | None = None,
        *,
        parent_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PipelineRunResult:
        """Run a pipeline synchronously and return the result.

        This is the synchronous entry point used by ``WorkflowRunner``
        (which is itself synchronous).

        Args:
            pipeline_name: Registered pipeline name.
            params: Parameters to pass to the pipeline.
            parent_run_id: If this pipeline is a step in a workflow.
            correlation_id: Shared ID linking related runs.

        Returns:
            ``PipelineRunResult`` with status, error, and metrics.
        """
        ...
