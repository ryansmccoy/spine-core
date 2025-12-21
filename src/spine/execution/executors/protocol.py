"""Executor Protocol — the single backend interface.

Manifesto:
Regardless of how work is actually executed (threads, processes,
Celery, Kubernetes), the ``EventDispatcher`` needs a uniform
interface.  ``Executor`` is a ``typing.Protocol`` — any object with
the right methods satisfies it, no base class required.

ARCHITECTURE
────────────
::

    Executor (Protocol)
      ├── .submit(spec)    ─ start work, return external_ref
      ├── .get_status(ref) ─ query status (optional)
      └── .cancel(ref)     ─ request cancellation (optional)

    Implementations:
      MemoryExecutor     ─ in-process, sync   (testing)
      LocalExecutor      ─ ThreadPool          (dev / small prod)
      AsyncLocalExecutor ─ asyncio semaphore   (I/O-bound)
      ProcessExecutor    ─ ProcessPool         (CPU-bound)
      CeleryExecutor     ─ distributed         (production)
      StubExecutor       ─ no-op               (dry-run)

Related modules:
    dispatcher.py — EventDispatcher delegates to Executor
    runnable.py   — Runnable protocol (blocking operation interface)

Tags:
    spine-core, execution, executor, protocol, interface, abc

Doc-Types:
    api-reference
"""

from typing import Protocol, runtime_checkable

from ..spec import WorkSpec


@runtime_checkable
class Executor(Protocol):
    """Executor adapter - how work gets executed.

    This is the ONLY "backend" concept in spine-core. All runtimes
    (Celery, Airflow, K8s Jobs, local threads) implement this interface.

    Key responsibilities:
    - Submit work to the underlying runtime
    - Return an external_ref for tracking
    - Optionally: cancel, get status (if runtime supports)

    Example implementation:
        >>> class MyExecutor:
        ...     async def submit(self, spec: WorkSpec) -> str:
        ...         # Submit to my runtime
        ...         return "my-runtime-id-123"
        ...
        ...     async def cancel(self, external_ref: str) -> bool:
        ...         return False  # Not supported
        ...
        ...     async def get_status(self, external_ref: str) -> str | None:
        ...         return None  # Not supported
    """

    async def submit(self, spec: WorkSpec) -> str:
        """Submit work to the executor.

        Args:
            spec: Work specification

        Returns:
            external_ref: Runtime-specific identifier
            - Celery: task_id (UUID)
            - Airflow: dag_run_id
            - K8s: job name
            - Local: thread id or "sync"

        Raises:
            RuntimeError: If submission fails
        """
        ...

    async def cancel(self, external_ref: str) -> bool:
        """Cancel work (if runtime supports it).

        Args:
            external_ref: Runtime identifier from submit()

        Returns:
            True if cancelled, False if not supported or already finished
        """
        ...

    async def get_status(self, external_ref: str) -> str | None:
        """Get runtime status (if runtime supports it).

        Args:
            external_ref: Runtime identifier from submit()

        Returns:
            Runtime-specific status string, or None if not available
        """
        ...
