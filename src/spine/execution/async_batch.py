"""Async Batch Executor — asyncio fan-out for parallel I/O-bound work.

WHY
───
Many spine pipelines need to fan-out hundreds of I/O calls (SEC EDGAR
downloads, LLM API calls, DB queries) and collect results.  Using
``asyncio.gather`` with a semaphore gives true concurrency without
the thread-pool overhead of :class:`~spine.execution.batch.BatchExecutor`.

ARCHITECTURE
────────────
::

    AsyncBatchExecutor
      ├── .add(name, coroutine, params)  ─ enqueue work item
      ├── .run_all()                     ─ asyncio.gather + semaphore
      └── AsyncBatchResult               ─ succeeded / failed / items

    vs BatchExecutor (threads)       vs AsyncBatchExecutor (asyncio)
    ─────────────────────────       ────────────────────────────────
    ThreadPoolExecutor               asyncio.gather + Semaphore
    sync handlers                    async handlers (coroutines)
    OS-thread per item               single event loop

Related modules:
    batch.py       — sync/thread-pool version
    context.py     — ExecutionContext for lineage tracking

Example::

    batch = AsyncBatchExecutor(max_concurrency=20)
    batch.add("dl_1", download_filing, {"url": url1})
    batch.add("dl_2", download_filing, {"url": url2})
    result = await batch.run_all()
    print(result.succeeded, result.failed)  # 2 0
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from spine.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AsyncBatchItem:
    """A single item in an async batch."""

    name: str
    handler: Callable[..., Coroutine[Any, Any, Any]]
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration if both timestamps are set."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class AsyncBatchResult:
    """Aggregate result of running an async batch."""

    batch_id: str
    items: list[AsyncBatchItem]
    started_at: datetime
    completed_at: datetime

    @property
    def succeeded(self) -> int:
        """Number of items that completed successfully."""
        return sum(1 for i in self.items if i.status == "completed")

    @property
    def failed(self) -> int:
        """Number of items that failed."""
        return sum(1 for i in self.items if i.status == "failed")

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def duration_seconds(self) -> float:
        """Wall-clock duration of the entire batch."""
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Serialise for logging / API responses."""
        return {
            "batch_id": self.batch_id,
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "duration_seconds": self.duration_seconds,
            "items": [
                {
                    "name": i.name,
                    "status": i.status,
                    "duration_seconds": i.duration_seconds,
                    "error": i.error,
                }
                for i in self.items
            ],
        }


class AsyncBatchExecutor:
    """Async batch executor with semaphore-bounded concurrency.

    All items run as native coroutines — no threads involved.
    Use :meth:`add` to enqueue items, then :meth:`run_all` to execute
    them concurrently (up to ``max_concurrency`` at a time).

    Parameters
    ----------
    max_concurrency : int
        Maximum simultaneous coroutines (default 10).
    """

    def __init__(self, max_concurrency: int = 10) -> None:
        self._max_concurrency = max_concurrency
        self._items: list[AsyncBatchItem] = []
        self._batch_id = str(uuid.uuid4())

    # ── Building ─────────────────────────────────────────────────────

    def add(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
        params: dict[str, Any] | None = None,
    ) -> AsyncBatchExecutor:
        """Add an item to the batch.

        Args:
            name: Human-readable name for this item.
            handler: Async callable ``(params) -> result``.
            params: Dict of parameters passed to the handler.

        Returns:
            ``self`` for fluent chaining.
        """
        self._items.append(
            AsyncBatchItem(
                name=name,
                handler=handler,
                params=params or {},
            )
        )
        return self

    # ── Execution ────────────────────────────────────────────────────

    async def run_all(self) -> AsyncBatchResult:
        """Execute all items concurrently, bounded by ``max_concurrency``.

        Returns:
            :class:`AsyncBatchResult` with per-item status and metrics.
        """
        sem = asyncio.Semaphore(self._max_concurrency)
        started_at = datetime.now(UTC)

        logger.info(
            "async_batch.start",
            batch_id=self._batch_id,
            items=len(self._items),
            max_concurrency=self._max_concurrency,
        )

        async def _run_one(item: AsyncBatchItem) -> AsyncBatchItem:
            async with sem:
                item.started_at = datetime.now(UTC)
                item.status = "running"
                try:
                    result = await item.handler(item.params)
                    item.result = result if isinstance(result, dict) else {"result": result}
                    item.status = "completed"
                except Exception as e:
                    item.status = "failed"
                    item.error = str(e)
                    logger.warning(
                        "async_batch.item_failed",
                        batch_id=self._batch_id,
                        name=item.name,
                        error=str(e),
                    )
                item.completed_at = datetime.now(UTC)
                return item

        await asyncio.gather(
            *[_run_one(item) for item in self._items],
            return_exceptions=True,
        )

        completed_at = datetime.now(UTC)
        result = AsyncBatchResult(
            batch_id=self._batch_id,
            items=self._items,
            started_at=started_at,
            completed_at=completed_at,
        )

        logger.info(
            "async_batch.complete",
            batch_id=self._batch_id,
            succeeded=result.succeeded,
            failed=result.failed,
            duration_seconds=result.duration_seconds,
        )

        return result

    # ── Inspection ───────────────────────────────────────────────────

    @property
    def item_count(self) -> int:
        """Number of items queued."""
        return len(self._items)

    @property
    def batch_id(self) -> str:
        return self._batch_id
