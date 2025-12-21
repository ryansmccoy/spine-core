"""Base runtime adapter with shared lifecycle logic.

Provides ``BaseRuntimeAdapter`` with common patterns (logging, error wrapping,
event recording) and ``StubRuntimeAdapter`` for unit tests.

Architecture:

    .. code-block:: text

        RuntimeAdapter (Protocol)
              │
              ▼
        BaseRuntimeAdapter (Abstract Base)
        ├── submit()  → logging + error wrapping → _do_submit()
        ├── status()  → _do_status()
        ├── cancel()  → logging + safe fallback   → _do_cancel()
        ├── logs()    → _do_logs()
        ├── cleanup() → logging + non-fatal       → _do_cleanup()
        └── health()  → latency timing            → _do_health()
              │
        ┌─────┴───────────────────────┐
        │                             │
        ▼                             ▼
    DockerAdapter              StubRuntimeAdapter
    (real containers)          (in-memory for tests)

    .. mermaid::

        classDiagram
            class BaseRuntimeAdapter {
                <<abstract>>
                +submit(spec) str
                +status(ref) JobStatus
                +cancel(ref) bool
                +logs(ref) AsyncIterator
                +cleanup(ref) None
                +health() RuntimeHealth
                #_do_submit(spec)* str
                #_do_status(ref)* JobStatus
                #_do_cancel(ref)* bool
                #_do_logs(ref)* AsyncIterator
                #_do_cleanup(ref)* None
                #_do_health()* RuntimeHealth
            }
            class DockerAdapter {
                +runtime_name = "docker"
            }
            class StubRuntimeAdapter {
                +runtime_name = "stub"
                +jobs: dict
                +fail_submit: bool
            }
            BaseRuntimeAdapter <|-- DockerAdapter
            BaseRuntimeAdapter <|-- StubRuntimeAdapter

Usage:
    # In tests:
    adapter = StubRuntimeAdapter()
    ref = await adapter.submit(spec)
    status = await adapter.status(ref)
    assert status.state == "succeeded"

    # Subclassing for real adapters:
    class DockerAdapter(BaseRuntimeAdapter):
        runtime_name = "docker"
        ...

See Also:
    _types.py — Protocol and type definitions
    docker.py — Docker adapter (MVP-1)

Manifesto:
    All runtime adapters inherit from ``BaseRuntimeAdapter``
    which enforces the protocol and provides sensible defaults
    for health checks, logging, and graceful shutdown.

Tags:
    spine-core, execution, runtimes, base, abstract, adapter-ABC

Doc-Types:
    api-reference
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobArtifact,
    JobError,
    JobStatus,
    RuntimeCapabilities,
    RuntimeConstraints,
    RuntimeHealth,
    _utcnow,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------

class BaseRuntimeAdapter:
    """Base class for runtime adapters with shared lifecycle logic.

    Subclasses MUST implement:
        _do_submit, _do_status, _do_cancel, _do_logs, _do_cleanup, _do_health

    Subclasses MAY override:
        _do_artifacts (default returns empty list)
        capabilities, constraints (default = minimal)

    The base class wraps each call with:
        - Structured logging (submit/cancel/cleanup)
        - Error conversion to JobError
        - Timing for health latency

    .. code-block:: text

        Public method call flow:

        submit(spec)
          ├── log: "Submitting job 'X' to docker"
          ├── _do_submit(spec)  ← subclass implements
          ├── log: "Job 'X' submitted: ref=abc123"
          └── on error: wrap in JobError(UNKNOWN, retryable=True)

        cancel(ref)
          ├── log: "Cancelling job abc123"
          ├── _do_cancel(ref)  ← subclass implements
          └── on error: log warning, return False

        health()
          ├── start timer
          ├── _do_health()  ← subclass implements
          ├── compute latency_ms
          └── on error: return RuntimeHealth(healthy=False)
    """

    @property
    def runtime_name(self) -> str:
        """Unique name for this runtime."""
        raise NotImplementedError

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Boolean feature flags. Override in subclass."""
        return RuntimeCapabilities()

    @property
    def constraints(self) -> RuntimeConstraints:
        """Numeric limits. Override in subclass."""
        return RuntimeConstraints()

    async def submit(self, spec: ContainerJobSpec) -> str:
        """Submit job with logging and error wrapping."""
        logger.info(
            "Submitting job '%s' to %s (image=%s)",
            spec.name, self.runtime_name, spec.image,
        )
        try:
            ref = await self._do_submit(spec)
            logger.info(
                "Job '%s' submitted to %s: external_ref=%s",
                spec.name, self.runtime_name, ref,
            )
            return ref
        except JobError:
            raise
        except Exception as exc:
            error = JobError(
                category=ErrorCategory.UNKNOWN,
                message=f"Submit failed: {exc}",
                retryable=True,
                runtime=self.runtime_name,
            )
            logger.error(
                "Submit failed for '%s' on %s: %s",
                spec.name, self.runtime_name, exc,
            )
            raise error from exc

    async def status(self, external_ref: str) -> JobStatus:
        """Get job status."""
        return await self._do_status(external_ref)

    async def cancel(self, external_ref: str) -> bool:
        """Cancel job with logging."""
        logger.info("Cancelling job %s on %s", external_ref, self.runtime_name)
        try:
            result = await self._do_cancel(external_ref)
            logger.info("Cancel result for %s: %s", external_ref, result)
            return result
        except Exception as exc:
            logger.warning("Cancel failed for %s: %s", external_ref, exc)
            return False

    async def logs(
        self,
        external_ref: str,
        *,
        follow: bool = False,
        tail: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream or fetch logs."""
        async for line in self._do_logs(external_ref, follow=follow, tail=tail):
            yield line

    async def artifacts(self, external_ref: str) -> list[JobArtifact]:
        """List output artifacts. Default returns empty list."""
        return await self._do_artifacts(external_ref)

    async def cleanup(self, external_ref: str) -> None:
        """Cleanup with logging. Idempotent."""
        logger.info("Cleaning up %s on %s", external_ref, self.runtime_name)
        try:
            await self._do_cleanup(external_ref)
            logger.info("Cleanup complete for %s", external_ref)
        except Exception as exc:
            logger.warning("Cleanup failed for %s: %s (non-fatal)", external_ref, exc)

    async def health(self) -> RuntimeHealth:
        """Health check with latency timing."""
        start = _utcnow()
        try:
            result = await self._do_health()
            elapsed = (_utcnow() - start).total_seconds() * 1000
            return RuntimeHealth(
                healthy=result.healthy,
                runtime=self.runtime_name,
                version=result.version,
                message=result.message,
                latency_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (_utcnow() - start).total_seconds() * 1000
            return RuntimeHealth(
                healthy=False,
                runtime=self.runtime_name,
                message=f"Health check failed: {exc}",
                latency_ms=elapsed,
            )

    # --- Abstract methods for subclasses ---

    async def _do_submit(self, spec: ContainerJobSpec) -> str:
        """Implement in subclass. Return external_ref."""
        raise NotImplementedError

    async def _do_status(self, external_ref: str) -> JobStatus:
        """Implement in subclass."""
        raise NotImplementedError

    async def _do_cancel(self, external_ref: str) -> bool:
        """Implement in subclass."""
        raise NotImplementedError

    async def _do_logs(
        self,
        external_ref: str,
        *,
        follow: bool = False,
        tail: int | None = None,
    ) -> AsyncIterator[str]:
        """Implement in subclass. Yield log lines."""
        raise NotImplementedError
        # Make this a proper async generator
        yield  # pragma: no cover

    async def _do_artifacts(self, external_ref: str) -> list[JobArtifact]:
        """Override in subclass for artifact support. Default: empty list."""
        return []

    async def _do_cleanup(self, external_ref: str) -> None:
        """Implement in subclass. Idempotent."""
        raise NotImplementedError

    async def _do_health(self) -> RuntimeHealth:
        """Implement in subclass."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Stub adapter for testing
# ---------------------------------------------------------------------------

@dataclass
class _StubJob:
    """Internal state for a stubbed job."""

    spec: ContainerJobSpec
    external_ref: str
    state: str = "pending"
    exit_code: int | None = None
    logs: list[str] = field(default_factory=list)
    artifacts: list[JobArtifact] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cleaned_up: bool = False


class StubRuntimeAdapter(BaseRuntimeAdapter):
    """In-memory runtime adapter for unit tests.

    All jobs immediately transition to the configured end state.
    No real containers are created.

    .. code-block:: text

        StubRuntimeAdapter behavior:

        submit(spec)
          ├── auto_succeed=True  → state="succeeded", exit_code=0
          └── auto_succeed=False → state="failed", exit_code=1

        Inject failures:
          adapter.fail_submit = True   → submit() raises JobError
          adapter.fail_cancel = True   → cancel() returns False
          adapter.fail_health = True   → health() reports unhealthy

        Track usage:
          adapter.submit_count   → number of submit calls
          adapter.cancel_count   → number of cancel calls
          adapter.cleanup_count  → number of cleanup calls

    .. mermaid::

        flowchart LR
            S[submit] --> J{auto_succeed?}
            J -->|yes| OK[state=succeeded exit=0]
            J -->|no| FAIL[state=failed exit=1]
            FI[fail_submit=True] -.->|inject| S

    Example:
        >>> adapter = StubRuntimeAdapter(auto_succeed=True)
        >>> ref = await adapter.submit(spec)
        >>> status = await adapter.status(ref)
        >>> assert status.state == "succeeded"

        >>> # Test failure:
        >>> adapter = StubRuntimeAdapter(auto_succeed=False, auto_exit_code=1)
        >>> ref = await adapter.submit(spec)
        >>> status = await adapter.status(ref)
        >>> assert status.state == "failed"

        >>> # Inject specific behaviors:
        >>> adapter = StubRuntimeAdapter()
        >>> adapter.fail_submit = True
        >>> # submit() will raise JobError
    """

    def __init__(
        self,
        *,
        auto_succeed: bool = True,
        auto_exit_code: int | None = None,
        auto_logs: list[str] | None = None,
        auto_artifacts: list[JobArtifact] | None = None,
        submit_delay_ms: int = 0,
    ) -> None:
        self.auto_succeed = auto_succeed
        self.auto_exit_code = auto_exit_code if not auto_succeed else 0
        self.auto_logs = auto_logs or ["[stub] Job started", "[stub] Job completed"]
        self.auto_artifacts = auto_artifacts or []
        self.submit_delay_ms = submit_delay_ms

        self.jobs: dict[str, _StubJob] = {}
        self.submit_count: int = 0
        self.cancel_count: int = 0
        self.cleanup_count: int = 0

        # Inject failures
        self.fail_submit: bool = False
        self.fail_cancel: bool = False
        self.fail_health: bool = False

    @property
    def runtime_name(self) -> str:
        return "stub"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            supports_gpu=True,
            supports_volumes=True,
            supports_sidecars=True,
            supports_init_containers=True,
            supports_log_streaming=True,
            supports_exec_into=True,
            supports_spot=True,
            supports_artifacts=True,
        )

    @property
    def constraints(self) -> RuntimeConstraints:
        return RuntimeConstraints()  # No limits

    async def _do_submit(self, spec: ContainerJobSpec) -> str:
        if self.fail_submit:
            raise JobError(
                category=ErrorCategory.RUNTIME_UNAVAILABLE,
                message="Stub: submit failure injected",
                retryable=True,
                runtime="stub",
            )

        self.submit_count += 1
        ref = f"stub-{uuid.uuid4().hex[:12]}"
        now = _utcnow()

        job = _StubJob(
            spec=spec,
            external_ref=ref,
            state="succeeded" if self.auto_succeed else "failed",
            exit_code=0 if self.auto_succeed else (self.auto_exit_code or 1),
            logs=list(self.auto_logs),
            artifacts=list(self.auto_artifacts),
            created_at=now,
            started_at=now,
            finished_at=now,
        )
        self.jobs[ref] = job
        return ref

    async def _do_status(self, external_ref: str) -> JobStatus:
        job = self.jobs.get(external_ref)
        if not job:
            return JobStatus(state="unknown", message=f"No stub job: {external_ref}")
        return JobStatus(
            state=job.state,
            exit_code=job.exit_code,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    async def _do_cancel(self, external_ref: str) -> bool:
        if self.fail_cancel:
            return False
        self.cancel_count += 1
        job = self.jobs.get(external_ref)
        if job and not JobStatus(state=job.state).is_terminal:
            job.state = "cancelled"
            job.finished_at = _utcnow()
        return True

    async def _do_logs(
        self,
        external_ref: str,
        *,
        follow: bool = False,
        tail: int | None = None,
    ) -> AsyncIterator[str]:
        job = self.jobs.get(external_ref)
        if not job:
            return
        lines = job.logs
        if tail is not None:
            lines = lines[-tail:]
        for line in lines:
            yield line

    async def _do_artifacts(self, external_ref: str) -> list[JobArtifact]:
        job = self.jobs.get(external_ref)
        if not job:
            return []
        return list(job.artifacts)

    async def _do_cleanup(self, external_ref: str) -> None:
        self.cleanup_count += 1
        job = self.jobs.get(external_ref)
        if job:
            job.cleaned_up = True

    async def _do_health(self) -> RuntimeHealth:
        if self.fail_health:
            return RuntimeHealth(
                healthy=False,
                runtime="stub",
                message="Stub: health failure injected",
            )
        return RuntimeHealth(
            healthy=True,
            runtime="stub",
            version="0.0.0-stub",
        )
