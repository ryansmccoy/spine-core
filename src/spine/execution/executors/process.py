"""Process Executor — multi-process execution to escape the GIL.

Manifesto:
CPU-bound work (NLP extraction, PDF parsing, data aggregation)
cannot benefit from threads due to the GIL.  ``ProcessExecutor``
uses ``ProcessPoolExecutor`` to distribute work across cores.

ARCHITECTURE
────────────
::

    ProcessExecutor(max_workers=4)
      ├── .register(kind, name, import_path)  ─ dotted path string
      ├── .submit(spec)                       ─ fork to process
      └── .shutdown()                         ─ drain pool

    Handlers must be top-level picklable functions
    (not closures or lambdas).  Reference by import path:
    ``"myapp.parsers.parse_pdf"``

Related modules:
    protocol.py    — Executor protocol
    local.py       — ThreadPool (I/O-bound or simpler use-case)

Example::

    executor = ProcessExecutor(max_workers=4)
    executor.register("task", "parse_pdf", "myapp.parsers.parse_pdf")
    ref = await executor.submit(task_spec("parse_pdf", {"path": "file.pdf"}))

Tags:
    spine-core, execution, executor, process-pool, CPU-bound, multiprocessing

Doc-Types:
    api-reference
"""

from __future__ import annotations

import asyncio
import importlib
import uuid
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from spine.core.logging import get_logger
from spine.execution.spec import WorkSpec

logger = get_logger(__name__)


def _run_handler_in_process(handler_path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Import and execute a handler in a separate worker process.

    This function is the *only* thing sent across the process boundary.
    It dynamically imports ``handler_path`` (e.g. ``"myapp.parsers.parse_pdf"``)
    and invokes it with ``params``.

    The handler must be a **top-level function** (picklable) that accepts a
    ``dict`` and returns a ``dict``.
    """
    module_path, func_name = handler_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    handler = getattr(module, func_name)
    result = handler(params)
    return result if isinstance(result, dict) else {"result": result}


class ProcessExecutor:
    """``ProcessPoolExecutor``-based executor for CPU-bound operations.

    Runs handlers in separate processes to escape the GIL.
    Handlers are registered by their dotted import path so they can
    be pickled across the process boundary.

    Implements the :class:`~spine.execution.executors.protocol.Executor`
    protocol (``submit``, ``cancel``, ``get_status``).

    Parameters
    ----------
    max_workers : int
        Number of worker processes (defaults to 4).
    """

    name = "process"

    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ProcessPoolExecutor(max_workers=max_workers)
        self._handlers: dict[str, str] = {}  # key → dotted.path.to.function
        self._futures: dict[str, asyncio.Future[Any]] = {}
        self._max_workers = max_workers

    # ── Handler registration ─────────────────────────────────────────

    def register(self, kind: str, name: str, handler_path: str) -> None:
        """Register a handler by dotted import path.

        Args:
            kind: Work type (``task``, ``operation``).
            name: Handler name.
            handler_path: Dotted path, e.g. ``"myapp.parsers.parse_pdf"``.
        """
        key = f"{kind}:{name}"
        self._handlers[key] = handler_path
        logger.debug("process_executor.registered", kind=kind, name=name, path=handler_path)

    # ── Executor protocol ────────────────────────────────────────────

    async def submit(self, spec: WorkSpec) -> str:
        """Submit work for process-based execution.

        Returns:
            ``external_ref`` — unique tracking ID.

        Raises:
            RuntimeError: If no handler is registered for the spec.
        """
        ref = f"proc-{uuid.uuid4().hex[:12]}"
        key = f"{spec.kind}:{spec.name}"

        handler_path = self._handlers.get(key)
        if not handler_path:
            raise RuntimeError(f"No process handler registered for {key}")

        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            self._pool,
            _run_handler_in_process,
            handler_path,
            spec.params,
        )
        self._futures[ref] = future

        logger.info("process_executor.submitted", ref=ref, kind=spec.kind, name=spec.name)
        return ref

    async def cancel(self, external_ref: str) -> bool:
        """Cancel a process task (best-effort).

        ``ProcessPoolExecutor`` futures can only be cancelled before they
        start running.  Once a worker picks up the task it cannot be
        interrupted from the parent process.
        """
        future = self._futures.get(external_ref)
        if future and not future.done():
            return future.cancel()
        return False

    async def get_status(self, external_ref: str) -> str | None:
        """Get task status."""
        future = self._futures.get(external_ref)
        if not future:
            return None
        if not future.done():
            return "running"
        try:
            future.result()  # raises if the handler raised
            return "completed"
        except Exception:
            return "failed"

    # ── Lifecycle ────────────────────────────────────────────────────

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the process pool.

        Args:
            wait: Block until all running tasks finish.
        """
        self._pool.shutdown(wait=wait)
        logger.info("process_executor.shutdown", wait=wait)
