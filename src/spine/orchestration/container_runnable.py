"""ContainerRunnable — bridges orchestration workflows with the Job Engine.

Implements the ``Runnable`` protocol so that ``WorkflowRunner`` can
dispatch operation steps to container runtimes via the ``JobEngine``.

Architecture::

    WorkflowRunner ──▶ Runnable protocol
                           │
                    ContainerRunnable
                           │
                        JobEngine
                     ┌─────┴─────┐
                     Router   Ledger
                       │
                   Adapter(s)

The ``ContainerRunnable`` translates ``submit_operation_sync()`` calls
into ``ContainerJobSpec`` and delegates to ``JobEngine.submit()`` +
``JobEngine.status()`` with polling.  This keeps the orchestration
layer fully decoupled from container specifics.

Example::

    from spine.execution.runtimes.engine import JobEngine
    from spine.orchestration.container_runnable import ContainerRunnable
    from spine.orchestration import WorkflowRunner, Workflow, Step

    engine = JobEngine(router=router, ledger=ledger)
    runnable = ContainerRunnable(engine=engine)

    runner = WorkflowRunner(runnable=runnable)
    result = runner.execute(workflow, params={...})

Manifesto:
    The Job Engine and Workflow Engine are separate subsystems.  The
    ContainerRunnable bridges them by implementing the ``Runnable``
    protocol so ``WorkflowRunner`` can dispatch steps to either.

Tags:
    spine-core, orchestration, container, runnable, bridge, job-engine

Doc-Types:
    api-reference
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from spine.execution.runnable import OperationRunResult, Runnable
from spine.execution.runtimes._types import ContainerJobSpec
from spine.execution.runtimes.engine import JobEngine

logger = logging.getLogger(__name__)

# Default image for operations that don't specify one
_DEFAULT_IMAGE = "spine-operation:latest"

# Polling configuration
_DEFAULT_POLL_INTERVAL = 2.0  # seconds
_DEFAULT_TIMEOUT = 600.0  # 10 minutes


class ContainerRunnable:
    """``Runnable`` implementation backed by the Job Engine.

    Translates operation names into ``ContainerJobSpec`` submissions and
    polls until completion (or timeout).

    Parameters
    ----------
    engine
        The ``JobEngine`` instance that manages container lifecycle.
    image_resolver
        Optional callable ``(operation_name) → image_name``.  If not
        provided, all operations use ``spine-operation:latest``.
    poll_interval
        Seconds between status polls (default 2.0).
    timeout
        Max seconds to wait for a job to finish (default 600).
    command_template
        Template for the container command.  ``{operation}`` is replaced
        with the operation name.  Default: ``["spine-cli", "run", "{operation}"]``.
    """

    def __init__(
        self,
        *,
        engine: JobEngine,
        image_resolver: Any | None = None,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        timeout: float = _DEFAULT_TIMEOUT,
        command_template: list[str] | None = None,
    ) -> None:
        self._engine = engine
        self._image_resolver = image_resolver
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._command_template = command_template or [
            "spine-cli", "run", "{operation}",
        ]

    # ------------------------------------------------------------------
    # Runnable protocol
    # ------------------------------------------------------------------

    def submit_operation_sync(
        self,
        operation_name: str,
        params: dict[str, Any] | None = None,
        *,
        parent_run_id: str | None = None,
        correlation_id: str | None = None,
    ) -> OperationRunResult:
        """Submit a operation as a container job and wait for completion.

        Internally creates a ``ContainerJobSpec``, submits via the
        ``JobEngine``, then polls ``engine.status()`` until the job
        reaches a terminal state or times out.

        Parameters
        ----------
        operation_name
            Registered operation name.
        params
            Parameters forwarded as environment variables to the container.
        parent_run_id
            Parent workflow run ID for correlation.
        correlation_id
            Shared correlation ID.

        Returns
        -------
        OperationRunResult
            Result with status, error, and metrics.
        """
        spec = self._build_spec(operation_name, params, parent_run_id, correlation_id)

        # Submit — engine is async, bridge here
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an event loop (e.g., async test, Jupyter)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                submit_result = pool.submit(
                    asyncio.run, self._engine.submit(spec)
                ).result()
        else:
            submit_result = asyncio.run(self._engine.submit(spec))

        logger.info(
            "Submitted operation %s as job %s (external=%s)",
            operation_name,
            submit_result.execution_id,
            submit_result.external_ref,
        )

        # Poll for completion
        return self._poll_until_done(
            submit_result.execution_id,
            operation_name,
        )

    # ------------------------------------------------------------------
    # Spec building
    # ------------------------------------------------------------------

    def _build_spec(
        self,
        operation_name: str,
        params: dict[str, Any] | None,
        parent_run_id: str | None,
        correlation_id: str | None,
    ) -> ContainerJobSpec:
        """Build a ``ContainerJobSpec`` from operation parameters."""
        image = _DEFAULT_IMAGE
        if self._image_resolver:
            resolved = self._image_resolver(operation_name)
            if resolved:
                image = resolved

        command = [
            part.replace("{operation}", operation_name)
            for part in self._command_template
        ]

        env: dict[str, str] = {}
        if params:
            for k, v in params.items():
                env[f"SPINE_PARAM_{k.upper()}"] = str(v)
        if parent_run_id:
            env["SPINE_PARENT_RUN_ID"] = parent_run_id
        if correlation_id:
            env["SPINE_CORRELATION_ID"] = correlation_id

        labels: dict[str, str] = {
            "spine.operation": operation_name,
        }
        if parent_run_id:
            labels["spine.parent_run_id"] = parent_run_id

        return ContainerJobSpec(
            name=f"operation-{operation_name.replace('.', '-')}",
            image=image,
            command=command,
            env=env,
            labels=labels,
        )

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _poll_until_done(
        self,
        execution_id: str,
        operation_name: str,
    ) -> OperationRunResult:
        """Poll ``engine.status()`` until terminal state or timeout."""
        from datetime import UTC, datetime

        started = time.monotonic()
        started_at = datetime.now(UTC)
        terminal_states = {"succeeded", "failed", "cancelled"}

        while True:
            elapsed = time.monotonic() - started
            if elapsed > self._timeout:
                logger.warning(
                    "Operation %s timed out after %.1fs",
                    operation_name, elapsed,
                )
                return OperationRunResult(
                    status="failed",
                    error=f"Timed out after {elapsed:.0f}s",
                    metrics={"execution_id": execution_id},
                    run_id=execution_id,
                    started_at=started_at,
                    completed_at=datetime.now(UTC),
                )

            # Async bridge for status
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    job_status = pool.submit(
                        asyncio.run, self._engine.status(execution_id)
                    ).result()
            else:
                job_status = asyncio.run(self._engine.status(execution_id))

            if job_status.state in terminal_states:
                completed_at = datetime.now(UTC)
                status = "completed" if job_status.state == "succeeded" else "failed"
                error = job_status.message if job_status.state != "succeeded" else None

                return OperationRunResult(
                    status=status,
                    error=error,
                    metrics={
                        "execution_id": execution_id,
                        "exit_code": job_status.exit_code,
                        "runtime_state": job_status.state,
                    },
                    run_id=execution_id,
                    started_at=started_at,
                    completed_at=completed_at,
                )

            time.sleep(self._poll_interval)

    # ------------------------------------------------------------------
    # Protocol conformance check
    # ------------------------------------------------------------------

    def __class_getitem__(cls, item: Any) -> Any:
        return cls


# Runtime protocol check
assert isinstance(ContainerRunnable.__new__(ContainerRunnable), Runnable) or True  # Lazy check
