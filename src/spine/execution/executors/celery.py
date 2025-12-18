"""Celery Executor — distributed execution via Celery workers.

.. warning::
    **EXPERIMENTAL** — not yet production-tested.  API may change.

WHY
───
For production workloads requiring distributed execution across
multiple machines, priority queues, and durable result backends,
Celery provides a mature platform.  This executor wraps it behind
the standard ``Executor`` protocol.

ARCHITECTURE
────────────
::

    CeleryExecutor(app=celery_app)
      ├── .submit(spec)     ─ celery_app.send_task()
      ├── .get_status(ref)  ─ AsyncResult(ref).status
      └── .cancel(ref)      ─ AsyncResult(ref).revoke()

    Requires: ``pip install celery[redis]``
    Optional dependency — graceful ImportError fallback.

Related modules:
    protocol.py — Executor protocol
    tasks.py    — Celery task stubs
    local.py    — non-distributed alternative
"""

import warnings
from typing import TYPE_CHECKING, Any

from ..spec import WorkSpec

# Celery is an optional dependency
try:
    from celery import Celery
    from celery.result import AsyncResult

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    Celery = None  # type: ignore
    AsyncResult = None  # type: ignore

if TYPE_CHECKING:
    from celery import Celery


class CeleryExecutor:
    """Celery-based executor for production.

    Features:
    - Distributed execution across workers
    - Priority queues (realtime, high, normal, low, slow)
    - Lane-based routing (gpu, cpu, io-bound)
    - Retries with exponential backoff
    - Result backend for status/results
    - Monitoring via Flower

    Requires:
    - pip install celery[redis]
    - Redis/RabbitMQ broker running
    - Celery workers running

    Example:
        >>> from celery import Celery
        >>>
        >>> app = Celery('spine', broker='redis://localhost:6379/0')
        >>> executor = CeleryExecutor(app)
        >>> ref = await executor.submit(task_spec("send_email", {"to": "user@example.com"}))
        >>> # ref is the Celery task_id

    Worker setup (separate process):
        >>> # In your Celery app module, register the spine executor task:
        >>> @app.task(name="spine.execute.task")
        >>> def execute_task(name: str, params: dict, **kwargs):
        ...     handler = registry.get("task", name)
        ...     return handler(params)
    """

    def __init__(self, celery_app: "Celery"):
        """Initialize with Celery app.

        Args:
            celery_app: Configured Celery instance

        Raises:
            RuntimeError: If Celery is not installed
        """
        if not CELERY_AVAILABLE:
            raise RuntimeError("Celery not installed. Install with: pip install celery[redis]")

        warnings.warn(
            "CeleryExecutor is EXPERIMENTAL and may change without notice. "
            "For production use, consider LocalExecutor or MemoryExecutor.",
            stacklevel=2,
        )

        self.celery_app = celery_app
        self._name = "celery"

    @property
    def name(self) -> str:
        """Executor name for tracking."""
        return self._name

    async def submit(self, spec: WorkSpec) -> str:
        """Submit work to Celery.

        The work is sent to a Celery queue based on priority/lane configuration.
        The Celery task_id is returned as the external_ref.

        Task naming convention: spine.execute.{kind}
        - spine.execute.task
        - spine.execute.pipeline
        - spine.execute.workflow
        - spine.execute.step
        """
        # Route to queue based on priority/lane
        queue = self._get_queue(spec)

        # Build task signature
        task_name = f"spine.execute.{spec.kind}"
        task_signature = self.celery_app.signature(
            task_name,
            args=[spec.name, spec.params],
            kwargs={
                "idempotency_key": spec.idempotency_key,
                "correlation_id": spec.correlation_id,
                "parent_run_id": spec.parent_run_id,
                "metadata": spec.metadata,
            },
            queue=queue,
            priority=self._get_priority_value(spec.priority),
        )

        # Apply retry policy from spec
        if spec.max_retries > 0:
            task_signature = task_signature.set(
                retry=True,
                retry_policy={
                    "max_retries": spec.max_retries,
                    "interval_start": spec.retry_delay_seconds,
                    "interval_step": spec.retry_delay_seconds,  # Linear backoff
                    "interval_max": spec.retry_delay_seconds * 10,
                },
            )

        # Submit async
        async_result = task_signature.apply_async()
        return async_result.id  # Celery task_id is the external_ref

    async def cancel(self, external_ref: str) -> bool:
        """Cancel Celery task.

        Uses revoke with terminate=True to kill running tasks.
        Note: This requires the worker to be running with -Ofair flag
        for immediate termination.
        """
        try:
            self.celery_app.control.revoke(external_ref, terminate=True)
            return True
        except Exception:
            return False

    async def get_status(self, external_ref: str) -> str | None:
        """Get Celery task status.

        Maps Celery states to spine statuses:
        - PENDING -> queued
        - STARTED -> running
        - SUCCESS -> completed
        - FAILURE -> failed
        - REVOKED -> cancelled
        """
        result = AsyncResult(external_ref, app=self.celery_app)
        state = result.state

        if state is None:
            return None

        # Map Celery states to our status
        state_map = {
            "PENDING": "queued",
            "RECEIVED": "queued",
            "STARTED": "running",
            "SUCCESS": "completed",
            "FAILURE": "failed",
            "REVOKED": "cancelled",
            "REJECTED": "failed",
            "RETRY": "queued",
        }
        return state_map.get(state, state.lower())

    async def get_result(self, external_ref: str) -> Any:
        """Get Celery task result (if completed)."""
        result = AsyncResult(external_ref, app=self.celery_app)
        if result.ready():
            return result.result
        return None

    def _get_queue(self, spec: WorkSpec) -> str:
        """Determine queue from spec.

        Priority:
        1. If lane != "default", use lane as queue name
        2. Otherwise, map priority to queue
        """
        if spec.lane != "default":
            return spec.lane

        # Priority-based routing
        priority_queues = {
            "realtime": "realtime",
            "high": "high",
            "normal": "default",
            "low": "low",
            "slow": "slow",
        }
        return priority_queues.get(spec.priority, "default")

    def _get_priority_value(self, priority: str) -> int:
        """Convert priority string to Celery priority (0-9).

        Celery priority: 0 = lowest, 9 = highest
        """
        priority_map = {
            "realtime": 9,
            "high": 7,
            "normal": 5,
            "low": 3,
            "slow": 1,
        }
        return priority_map.get(priority, 5)
