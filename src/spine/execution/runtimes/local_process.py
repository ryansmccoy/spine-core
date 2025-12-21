"""Local process adapter — runs jobs as local subprocesses.

A ``RuntimeAdapter`` that executes ``ContainerJobSpec`` commands as local
OS processes instead of containers. Provides the exact same lifecycle
(submit / status / cancel / logs / cleanup) so users without Docker,
Podman, or Kubernetes can still develop, test, and run Job Engine
workflows.

Architecture:

    .. code-block:: text

        LocalProcessAdapter — Container-Free Execution
        ┌──────────────────────────────────────────────────────────────┐
        │                                                              │
        │  Translates ContainerJobSpec → asyncio.subprocess            │
        │                                                              │
        │  ContainerJobSpec field      │ Local process equivalent      │
        │  ────────────────────────────┼───────────────────────────────│
        │  image                       │ ignored (runs local binary)   │
        │  command + args              │ subprocess argv               │
        │  env                         │ os.environ overlay            │
        │  working_dir                 │ subprocess cwd                │
        │  timeout_seconds             │ asyncio wait timeout          │
        │  artifacts_dir               │ local directory               │
        │                              │                               │
        │  NOT supported locally:                                      │
        │  - GPU, volumes, sidecars, init containers                   │
        │  - Image pulling (no images)                                 │
        │  - Resource limits (CPU/memory caps)                         │
        │  - Network isolation                                         │
        │                                                              │
        └──────────────────────────────────────────────────────────────┘

    .. mermaid::

        flowchart LR
            SPEC[ContainerJobSpec] --> LPA[LocalProcessAdapter]
            LPA --> PROC[asyncio.subprocess]
            PROC --> STDOUT[stdout → logs]
            PROC --> RC[returncode → status]
            PROC --> ART[artifacts_dir → artifacts]

Use cases:
    - **Development**: Run operations locally without Docker installed
    - **CI without Docker**: GitHub Actions runners or restricted CI
    - **Quick testing**: Faster feedback loop (no image pull)
    - **Fallback**: Auto-fallback when Docker daemon is unavailable

Example:
    >>> from spine.execution.runtimes.local_process import LocalProcessAdapter
    >>> from spine.execution.runtimes import ContainerJobSpec
    >>>
    >>> adapter = LocalProcessAdapter()
    >>> spec = ContainerJobSpec(
    ...     name="local-task",
    ...     image="ignored",  # No image needed
    ...     command=["python", "-c", "print('hello from local')"],
    ...     timeout_seconds=30,
    ... )
    >>> ref = await adapter.submit(spec)
    >>> status = await adapter.status(ref)
    >>> assert status.state == "succeeded"

Manifesto:
    The local-process adapter runs operations as subprocesses
    on the same machine.  It is the default for development
    and CI, giving full isolation without container overhead.

Tags:
    spine-core, execution, runtimes, local-process, subprocess, development

Doc-Types:
    api-reference
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from spine.execution.runtimes._base import BaseRuntimeAdapter
from spine.execution.runtimes._types import (
    ErrorCategory,
    JobArtifact,
    JobError,
    JobStatus,
    RuntimeCapabilities,
    RuntimeConstraints,
    RuntimeHealth,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Internal process record
# ---------------------------------------------------------------------------

@dataclass
class _LocalJob:
    """Tracks a local subprocess spawned by the adapter."""

    ref: str
    spec_name: str
    process: asyncio.subprocess.Process | None = None
    state: str = "pending"
    exit_code: int | None = None
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)
    artifacts_dir: Path | None = None
    created_at: datetime = field(default_factory=_utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancelled: bool = False
    cleaned_up: bool = False

    @property
    def all_log_lines(self) -> list[str]:
        """Combined stdout + stderr lines for log streaming."""
        return self.stdout_lines + self.stderr_lines


# ---------------------------------------------------------------------------
# LocalProcessAdapter
# ---------------------------------------------------------------------------

class LocalProcessAdapter(BaseRuntimeAdapter):
    """Runs ContainerJobSpec commands as local OS subprocesses.

    This adapter translates container job specifications into local process
    invocations. It uses ``asyncio.create_subprocess_exec`` for non-blocking
    execution with timeout support.

    The ``image`` field is **ignored** — commands run against whatever is
    installed on the local system. This means ``command`` must reference
    binaries available in ``$PATH`` (e.g., ``python``, ``node``, etc.).

    Capabilities:
        - ✓ Command execution with args
        - ✓ Environment variables
        - ✓ Working directory
        - ✓ Timeout enforcement
        - ✓ Cancellation (SIGTERM → SIGKILL)
        - ✓ Log capture (stdout + stderr)
        - ✓ Artifact collection from local directory
        - ✗ GPU, volumes, sidecars, init containers
        - ✗ Image pulling, resource limits, network isolation

    Example:
        >>> adapter = LocalProcessAdapter(work_dir="/tmp/spine-jobs")
        >>> ref = await adapter.submit(spec)
        >>> async for line in adapter.logs(ref):
        ...     print(line)
        >>> await adapter.cleanup(ref)
    """

    def __init__(
        self,
        *,
        work_dir: str | Path | None = None,
        inherit_env: bool = True,
        kill_timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the local process adapter.

        Args:
            work_dir: Base directory for job working dirs. If None,
                uses a temp directory.
            inherit_env: If True, child processes inherit the current
                environment (with spec.env overlaid). If False, only
                spec.env is passed.
            kill_timeout_seconds: Seconds to wait after SIGTERM before
                sending SIGKILL on cancellation.
        """
        self._work_dir = Path(work_dir) if work_dir else None
        self._inherit_env = inherit_env
        self._kill_timeout = kill_timeout_seconds
        self._jobs: dict[str, _LocalJob] = {}

    @property
    def runtime_name(self) -> str:
        return "local"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """Local processes don't support container-specific features."""
        return RuntimeCapabilities(
            supports_gpu=False,
            supports_volumes=False,
            supports_sidecars=False,
            supports_init_containers=False,
            supports_log_streaming=False,
            supports_exec_into=False,
            supports_spot=False,
            supports_artifacts=True,
            supports_health_check=False,
        )

    @property
    def constraints(self) -> RuntimeConstraints:
        """No hard numeric limits for local processes."""
        return RuntimeConstraints()

    # ------------------------------------------------------------------
    # Core lifecycle
    # ------------------------------------------------------------------

    async def _do_submit(self, spec) -> str:
        """Spawn a local subprocess for the spec."""
        ref = f"local-{uuid.uuid4().hex[:12]}"
        job = _LocalJob(ref=ref, spec_name=spec.name)

        # Build command
        cmd = self._build_command(spec)
        if not cmd:
            raise JobError(
                category=ErrorCategory.VALIDATION,
                message="No command specified in ContainerJobSpec",
                retryable=False,
                runtime="local",
            )

        # Build environment
        env = self._build_env(spec)

        # Working directory
        cwd = self._resolve_cwd(spec, ref)

        # Artifacts directory
        if spec.artifacts_dir:
            artifacts_path = cwd / "artifacts"
            artifacts_path.mkdir(parents=True, exist_ok=True)
            job.artifacts_dir = artifacts_path
            env["SPINE_ARTIFACTS_DIR"] = str(artifacts_path)

        job.started_at = _utcnow()
        job.state = "running"

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=str(cwd),
            )
            job.process = process
        except FileNotFoundError as exc:
            job.state = "failed"
            job.finished_at = _utcnow()
            job.exit_code = 127
            job.stderr_lines.append(f"Command not found: {cmd[0]}")
            self._jobs[ref] = job
            raise JobError(
                category=ErrorCategory.NOT_FOUND,
                message=f"Command not found: {cmd[0]} ({exc})",
                retryable=False,
                runtime="local",
            ) from exc
        except Exception as exc:
            job.state = "failed"
            job.finished_at = _utcnow()
            self._jobs[ref] = job
            raise JobError(
                category=ErrorCategory.UNKNOWN,
                message=f"Failed to start process: {exc}",
                retryable=True,
                runtime="local",
            ) from exc

        self._jobs[ref] = job

        # Schedule background task to wait for completion + apply timeout
        asyncio.create_task(
            self._wait_for_completion(ref, spec.timeout_seconds),
        )

        return ref

    async def _do_status(self, external_ref: str) -> JobStatus:
        """Check subprocess status."""
        job = self._jobs.get(external_ref)
        if not job:
            return JobStatus(state="unknown", message=f"No local job: {external_ref}")

        # If process is still tracked and running, poll it
        if job.process and job.state == "running":
            if job.process.returncode is not None:
                await self._finalize_job(job)

        return JobStatus(
            state=job.state,
            exit_code=job.exit_code,
            started_at=job.started_at,
            finished_at=job.finished_at,
            message=job.stderr_lines[-1] if job.stderr_lines else None,
        )

    async def _do_cancel(self, external_ref: str) -> bool:
        """Cancel a running subprocess (SIGTERM → SIGKILL)."""
        job = self._jobs.get(external_ref)
        if not job or not job.process:
            return True  # Already done or never started

        if job.process.returncode is not None:
            return True  # Already exited

        job.cancelled = True
        try:
            job.process.terminate()
            try:
                await asyncio.wait_for(
                    job.process.wait(), timeout=self._kill_timeout,
                )
            except TimeoutError:
                job.process.kill()
                await job.process.wait()
        except ProcessLookupError:
            pass  # Process already gone

        job.state = "cancelled"
        job.finished_at = _utcnow()
        job.exit_code = job.process.returncode
        return True

    async def _do_logs(
        self,
        external_ref: str,
        *,
        follow: bool = False,
        tail: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield captured log lines."""
        job = self._jobs.get(external_ref)
        if not job:
            return

        # If process is still running, read what we have so far
        if job.process and job.state == "running":
            await self._collect_output(job)

        lines = job.all_log_lines
        if tail is not None:
            lines = lines[-tail:]
        for line in lines:
            yield line

    async def _do_artifacts(self, external_ref: str) -> list[JobArtifact]:
        """List files in the job's artifacts directory."""
        job = self._jobs.get(external_ref)
        if not job or not job.artifacts_dir or not job.artifacts_dir.exists():
            return []

        artifacts: list[JobArtifact] = []
        for path in job.artifacts_dir.iterdir():
            if path.is_file():
                stat = path.stat()
                artifacts.append(JobArtifact(
                    name=path.name,
                    path=str(path),
                    size_bytes=stat.st_size,
                ))
        return artifacts

    async def _do_cleanup(self, external_ref: str) -> None:
        """Kill process if still running and remove job record."""
        job = self._jobs.get(external_ref)
        if not job:
            return

        # Ensure process is dead
        if job.process and job.process.returncode is None:
            try:
                job.process.kill()
                await job.process.wait()
            except ProcessLookupError:
                pass

        job.cleaned_up = True
        # Don't remove from _jobs — allows post-cleanup status queries
        logger.debug("Local job %s cleaned up", external_ref)

    async def _do_health(self) -> RuntimeHealth:
        """Local process adapter is always healthy."""
        return RuntimeHealth(
            healthy=True,
            runtime="local",
            version="1.0.0",
            message="Local process execution (no container runtime required)",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_command(self, spec) -> list[str]:
        """Extract command + args from spec."""
        cmd: list[str] = []
        if spec.command:
            cmd.extend(spec.command)
        if spec.args:
            cmd.extend(spec.args)
        return cmd

    def _build_env(self, spec) -> dict[str, str]:
        """Build environment dict for the subprocess."""
        if self._inherit_env:
            env = dict(os.environ)
        else:
            env = {}
        # Overlay spec env vars
        env.update(spec.env)
        # Add runtime marker so user code knows it's running locally
        env["SPINE_RUNTIME"] = "local"
        env["SPINE_JOB_NAME"] = spec.name
        return env

    def _resolve_cwd(self, spec, ref: str) -> Path:
        """Determine working directory for the subprocess."""
        if spec.working_dir:
            cwd = Path(spec.working_dir)
            cwd.mkdir(parents=True, exist_ok=True)
            return cwd

        if self._work_dir:
            cwd = self._work_dir / ref
        else:
            cwd = Path(tempfile.mkdtemp(prefix=f"spine-local-{ref[:8]}-"))

        cwd.mkdir(parents=True, exist_ok=True)
        return cwd

    async def _wait_for_completion(self, ref: str, timeout_seconds: int) -> None:
        """Background task: wait for subprocess exit with timeout."""
        job = self._jobs.get(ref)
        if not job or not job.process:
            return

        try:
            await asyncio.wait_for(
                job.process.wait(),
                timeout=timeout_seconds,
            )
            await self._collect_output(job)
            await self._finalize_job(job)
        except TimeoutError:
            # Timeout — kill the process
            logger.warning(
                "Local job %s timed out after %ds, killing",
                ref, timeout_seconds,
            )
            try:
                job.process.kill()
                await job.process.wait()
            except ProcessLookupError:
                pass
            job.state = "failed"
            job.exit_code = -1
            job.finished_at = _utcnow()
            job.stderr_lines.append(
                f"Process killed: exceeded timeout of {timeout_seconds}s"
            )
        except Exception as exc:
            logger.error("Error waiting for local job %s: %s", ref, exc)
            job.state = "failed"
            job.finished_at = _utcnow()

    async def _collect_output(self, job: _LocalJob) -> None:
        """Read stdout/stderr from the process."""
        if not job.process:
            return

        if job.process.stdout:
            try:
                data = await asyncio.wait_for(
                    job.process.stdout.read(), timeout=1.0,
                )
                if data:
                    lines = data.decode(errors="replace").splitlines()
                    job.stdout_lines.extend(lines)
            except (TimeoutError, Exception):
                pass

        if job.process.stderr:
            try:
                data = await asyncio.wait_for(
                    job.process.stderr.read(), timeout=1.0,
                )
                if data:
                    lines = data.decode(errors="replace").splitlines()
                    job.stderr_lines.extend(lines)
            except (TimeoutError, Exception):
                pass

    async def _finalize_job(self, job: _LocalJob) -> None:
        """Set final state based on return code."""
        if not job.process:
            return

        await self._collect_output(job)
        job.exit_code = job.process.returncode
        job.finished_at = _utcnow()

        if job.cancelled:
            job.state = "cancelled"
        elif job.exit_code == 0:
            job.state = "succeeded"
        else:
            job.state = "failed"
