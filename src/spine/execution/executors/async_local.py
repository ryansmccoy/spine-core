"""Async Local Executor — asyncio-based bounded concurrency.

WHY
───
I/O-bound work (HTTP downloads, DB queries, LLM API calls) benefits
from async concurrency without OS threads.  ``AsyncLocalExecutor``
uses ``asyncio.Semaphore`` for bounded parallelism on a single
event loop — the recommended executor for feedspine-style async work.

ARCHITECTURE
────────────
::

    AsyncLocalExecutor(max_concurrency=10)
      ├── .register(kind, name, handler)  ─ async handler
      ├── .submit(spec)                   ─ enqueue coroutine
      ├── .wait(ref)                      ─ await completion
      └── .get_status(ref)                ─ poll result

    Handlers must be ``async def`` coroutines.

BEST PRACTICES
──────────────
- Use for SEC EDGAR downloads, LLM API calls, async DB queries.
- Set ``max_concurrency`` to respect upstream rate limits.
- Combine with ``RateLimiter`` for per-endpoint throttling.

Related modules:
    protocol.py     — Executor protocol
    local.py        — ThreadPool version for sync handlers
    async_batch.py  — higher-level batch API using asyncio

Example::

    executor = AsyncLocalExecutor(max_concurrency=10)
    executor.register("task", "download", download_handler)
    ref = await executor.submit(task_spec("download", {"url": url}))
    await executor.wait(ref)
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from spine.core.logging import get_logger

from spine.execution.spec import WorkSpec

logger = get_logger(__name__)


class AsyncLocalExecutor:
    """asyncio-native executor for I/O-bound pipelines.

    Unlike :class:`~spine.execution.executors.local.LocalExecutor`
    (``ThreadPoolExecutor``), this runs handlers as native coroutines on
    the event loop.  No threads are involved.

    Implements the :class:`~spine.execution.executors.protocol.Executor`
    protocol (``submit``, ``cancel``, ``get_status``).

    Parameters
    ----------
    max_concurrency : int
        Maximum number of handlers executing simultaneously.
        Backed by an ``asyncio.Semaphore``.
    """

    name = "async_local"

    def __init__(self, max_concurrency: int = 10) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._errors: dict[str, str] = {}
        self._max_concurrency = max_concurrency

    # ── Handler registration ─────────────────────────────────────────

    def register(
        self,
        kind: str,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Register an async handler.

        Args:
            kind: Work type (``task``, ``pipeline``, ``workflow``, ``step``).
            name: Handler name.
            handler: Async function ``(params: dict) -> dict``.
        """
        key = f"{kind}:{name}"
        self._handlers[key] = handler
        logger.debug("async_executor.registered", kind=kind, name=name)

    # ── Executor protocol ────────────────────────────────────────────

    async def submit(self, spec: WorkSpec) -> str:
        """Submit work for async execution.

        The handler runs inside the current event loop, bounded by
        ``max_concurrency``.

        Returns:
            ``external_ref`` — a unique ID for tracking this execution.

        Raises:
            RuntimeError: If no handler is registered for ``spec.kind:spec.name``.
        """
        ref = f"async-{uuid.uuid4().hex[:12]}"
        key = f"{spec.kind}:{spec.name}"

        handler = self._handlers.get(key) or self._handlers.get(f"{spec.kind}:__all__")
        if not handler:
            raise RuntimeError(f"No async handler registered for {key}")

        async def _run() -> None:
            async with self._semaphore:
                logger.debug("async_executor.running", ref=ref, name=spec.name)
                try:
                    params = {
                        **spec.params,
                        "__spec_name__": spec.name,
                        "__spec_metadata__": spec.metadata,
                    }
                    result = await handler(params)
                    self._results[ref] = result if isinstance(result, dict) else {"result": result}
                except Exception as e:
                    self._errors[ref] = str(e)
                    logger.error("async_executor.failed", ref=ref, error=str(e))
                    raise

        task = asyncio.create_task(_run())
        self._tasks[ref] = task

        logger.info("async_executor.submitted", ref=ref, kind=spec.kind, name=spec.name)
        return ref

    async def cancel(self, external_ref: str) -> bool:
        """Cancel a running async task."""
        task = self._tasks.get(external_ref)
        if task and not task.done():
            task.cancel()
            logger.info("async_executor.cancelled", ref=external_ref)
            return True
        return False

    async def get_status(self, external_ref: str) -> str | None:
        """Get task status.

        Returns:
            ``"running"``, ``"completed"``, ``"cancelled"``, ``"failed"``,
            or ``None`` if the ref is unknown.
        """
        task = self._tasks.get(external_ref)
        if not task:
            return None
        if not task.done():
            return "running"
        if task.cancelled():
            return "cancelled"
        if external_ref in self._errors:
            return "failed"
        return "completed"

    # ── Extended helpers ──────────────────────────────────────────────

    async def get_result(self, external_ref: str) -> dict[str, Any] | None:
        """Get result dict of a completed task (``None`` if not done)."""
        return self._results.get(external_ref)

    async def get_error(self, external_ref: str) -> str | None:
        """Get error message of a failed task (``None`` if not failed)."""
        return self._errors.get(external_ref)

    async def wait(self, external_ref: str, timeout: float | None = None) -> str:
        """Wait for a task to finish.

        Args:
            external_ref: The ref returned by ``submit()``.
            timeout: Seconds to wait (``None`` = forever).

        Returns:
            Final status string.
        """
        task = self._tasks.get(external_ref)
        if not task:
            return "not_found"
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except TimeoutError:
            return "running"
        except asyncio.CancelledError:
            return "cancelled"
        except Exception:
            return "failed"
        return "completed"

    @property
    def active_count(self) -> int:
        """Number of tasks currently running (not yet done)."""
        return sum(1 for t in self._tasks.values() if not t.done())
