"""Mock Runtime Adapters — test doubles for edge-case simulation.

Provides purpose-built adapters that extend ``BaseRuntimeAdapter`` for
testing timeout handling, flaky deployments, error recovery, and
state-machine transitions without real container infrastructure.

Architecture::

    BaseRuntimeAdapter
    ├── StubRuntimeAdapter    (existing — always succeeds/fails)
    ├── FailingAdapter        (always raises a specific JobError)
    ├── SlowAdapter           (configurable latency injection)
    ├── FlakeyAdapter         (probabilistic failures)
    ├── SequenceAdapter       (scripted state progression)
    └── LatencyAdapter        (wraps another adapter + adds delay)

    Usage with JobEngine:

        router = RuntimeAdapterRouter()
        router.register("flaky", FlakeyAdapter(success_rate=0.7))
        router.register("slow", SlowAdapter(submit_delay=5.0))

        engine = JobEngine(router=router)
        result = engine.submit(spec, runtime="flaky")

Example::

    from spine.execution.runtimes.mock_adapters import (
        FailingAdapter,
        SlowAdapter,
        FlakeyAdapter,
        SequenceAdapter,
    )

    # Always fail with OOM
    adapter = FailingAdapter(category=ErrorCategory.OOM)

    # Add 2-second delay to every submit
    adapter = SlowAdapter(submit_delay=2.0)

    # 70% success rate — flaky deployment
    adapter = FlakeyAdapter(success_rate=0.7, seed=42)

    # Scripted: pending → running → succeeded
    adapter = SequenceAdapter(states=["pending", "running", "succeeded"])

See Also:
    spine.execution.runtimes._base — BaseRuntimeAdapter and StubRuntimeAdapter
    spine.execution.runtimes._types — Protocol and type definitions
    spine.execution.runtimes.engine — JobEngine facade
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from spine.execution.runtimes._base import BaseRuntimeAdapter
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
# FailingAdapter — always raises a specific JobError
# ---------------------------------------------------------------------------

class FailingAdapter(BaseRuntimeAdapter):
    """Adapter that always fails with a configurable error category.

    Useful for testing error-handling paths, retry logic, and
    error-category-specific behavior in the ``JobEngine``.

    Parameters
    ----------
    category
        The ``ErrorCategory`` to raise (default: ``RUNTIME_UNAVAILABLE``).
    message
        Custom error message.
    retryable
        Whether the error should be marked as retryable.

    Example::

        adapter = FailingAdapter(category=ErrorCategory.OOM)
        # Every submit() call raises JobError(OOM)
    """

    def __init__(
        self,
        *,
        category: ErrorCategory = ErrorCategory.RUNTIME_UNAVAILABLE,
        message: str = "Simulated failure",
        retryable: bool = False,
    ) -> None:
        self._category = category
        self._message = message
        self._retryable = retryable

    @property
    def runtime_name(self) -> str:
        return "failing"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities()

    @property
    def constraints(self) -> RuntimeConstraints:
        return RuntimeConstraints()

    async def _do_submit(self, spec: ContainerJobSpec) -> str:
        raise JobError(
            category=self._category,
            message=f"{self._message}: {spec.name}",
            retryable=self._retryable,
            runtime=self.runtime_name,
        )

    async def _do_status(self, external_ref: str) -> JobStatus:
        return JobStatus(state="failed", message=self._message)

    async def _do_cancel(self, external_ref: str) -> bool:
        return False

    async def _do_logs(self, external_ref: str, *, follow: bool = False, tail: int | None = None) -> AsyncIterator[str]:
        yield f"[failing] {self._message}"

    async def _do_cleanup(self, external_ref: str) -> None:
        pass

    async def _do_health(self) -> RuntimeHealth:
        return RuntimeHealth(healthy=False, runtime=self.runtime_name, message=self._message)


# ---------------------------------------------------------------------------
# SlowAdapter — configurable latency injection
# ---------------------------------------------------------------------------

class SlowAdapter(BaseRuntimeAdapter):
    """Adapter that adds configurable delays to operations.

    Useful for testing timeout handling, progress indicators, and
    long-poll behavior.

    Parameters
    ----------
    submit_delay
        Seconds to wait before returning from ``submit()``.
    status_delay
        Seconds to wait before returning from ``status()``.
    auto_succeed
        Whether the job eventually succeeds after the delay.

    Example::

        adapter = SlowAdapter(submit_delay=5.0)
        # submit() takes 5 seconds before returning
    """

    def __init__(
        self,
        *,
        submit_delay: float = 1.0,
        status_delay: float = 0.1,
        auto_succeed: bool = True,
    ) -> None:
        self._submit_delay = submit_delay
        self._status_delay = status_delay
        self._auto_succeed = auto_succeed
        self._jobs: dict[str, str] = {}

    @property
    def runtime_name(self) -> str:
        return "slow"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities()

    @property
    def constraints(self) -> RuntimeConstraints:
        return RuntimeConstraints()

    async def _do_submit(self, spec: ContainerJobSpec) -> str:
        await asyncio.sleep(self._submit_delay)
        ref = f"slow-{uuid.uuid4().hex[:12]}"
        state = "succeeded" if self._auto_succeed else "failed"
        self._jobs[ref] = state
        return ref

    async def _do_status(self, external_ref: str) -> JobStatus:
        await asyncio.sleep(self._status_delay)
        state = self._jobs.get(external_ref, "unknown")
        return JobStatus(
            state=state,
            exit_code=0 if state == "succeeded" else 1,
            finished_at=_utcnow(),
        )

    async def _do_cancel(self, external_ref: str) -> bool:
        self._jobs[external_ref] = "cancelled"
        return True

    async def _do_logs(self, external_ref: str, *, follow: bool = False, tail: int | None = None) -> AsyncIterator[str]:
        yield "[slow] Processing..."
        yield f"[slow] Completed with delay={self._submit_delay}s"

    async def _do_cleanup(self, external_ref: str) -> None:
        self._jobs.pop(external_ref, None)

    async def _do_health(self) -> RuntimeHealth:
        await asyncio.sleep(self._status_delay)
        return RuntimeHealth(healthy=True, runtime=self.runtime_name, version="slow-1.0")


# ---------------------------------------------------------------------------
# FlakeyAdapter — probabilistic failures
# ---------------------------------------------------------------------------

class FlakeyAdapter(BaseRuntimeAdapter):
    """Adapter that succeeds with a configurable probability.

    Useful for testing retry logic, circuit breakers, and resilience
    patterns under unreliable infrastructure.

    Parameters
    ----------
    success_rate
        Probability of success (0.0 to 1.0).  Default is 0.5.
    failure_category
        Error category when failure occurs.
    seed
        Optional random seed for reproducible test runs.

    Example::

        adapter = FlakeyAdapter(success_rate=0.7, seed=42)
        # ~70% of submit() calls succeed, ~30% raise JobError
    """

    def __init__(
        self,
        *,
        success_rate: float = 0.5,
        failure_category: ErrorCategory = ErrorCategory.RUNTIME_UNAVAILABLE,
        seed: int | None = None,
    ) -> None:
        if not 0.0 <= success_rate <= 1.0:
            raise ValueError(f"success_rate must be 0.0-1.0, got {success_rate}")
        self._success_rate = success_rate
        self._failure_category = failure_category
        self._rng = random.Random(seed)
        self._jobs: dict[str, str] = {}
        self.submit_count: int = 0
        self.success_count: int = 0
        self.failure_count: int = 0

    @property
    def runtime_name(self) -> str:
        return "flakey"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities()

    @property
    def constraints(self) -> RuntimeConstraints:
        return RuntimeConstraints()

    async def _do_submit(self, spec: ContainerJobSpec) -> str:
        self.submit_count += 1
        if self._rng.random() < self._success_rate:
            self.success_count += 1
            ref = f"flakey-{uuid.uuid4().hex[:12]}"
            self._jobs[ref] = "succeeded"
            return ref
        else:
            self.failure_count += 1
            raise JobError(
                category=self._failure_category,
                message=f"Flakey failure (rate={1 - self._success_rate:.0%}): {spec.name}",
                retryable=True,
                runtime=self.runtime_name,
            )

    async def _do_status(self, external_ref: str) -> JobStatus:
        state = self._jobs.get(external_ref, "unknown")
        return JobStatus(state=state, exit_code=0 if state == "succeeded" else None)

    async def _do_cancel(self, external_ref: str) -> bool:
        self._jobs[external_ref] = "cancelled"
        return True

    async def _do_logs(self, external_ref: str, *, follow: bool = False, tail: int | None = None) -> AsyncIterator[str]:
        yield f"[flakey] success_rate={self._success_rate:.0%}"

    async def _do_cleanup(self, external_ref: str) -> None:
        self._jobs.pop(external_ref, None)

    async def _do_health(self) -> RuntimeHealth:
        healthy = self._rng.random() < self._success_rate
        return RuntimeHealth(
            healthy=healthy,
            runtime=self.runtime_name,
            message="flakey health" if not healthy else "ok",
        )


# ---------------------------------------------------------------------------
# SequenceAdapter — scripted state progression
# ---------------------------------------------------------------------------

class SequenceAdapter(BaseRuntimeAdapter):
    """Adapter that returns a scripted sequence of states.

    Each call to ``status()`` advances to the next state in the
    sequence.  Useful for testing state-machine transitions, polling
    loops, and progress tracking.

    Parameters
    ----------
    states
        Ordered list of states to return.  The last state is returned
        for all subsequent calls.

    Example::

        adapter = SequenceAdapter(states=["pending", "running", "succeeded"])
        ref = await adapter.submit(spec)
        s1 = await adapter.status(ref)  # pending
        s2 = await adapter.status(ref)  # running
        s3 = await adapter.status(ref)  # succeeded
        s4 = await adapter.status(ref)  # succeeded (stays at last)
    """

    def __init__(self, *, states: list[str] | None = None) -> None:
        self._states = states or ["pending", "running", "succeeded"]
        self._jobs: dict[str, int] = {}  # ref → current index

    @property
    def runtime_name(self) -> str:
        return "sequence"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return RuntimeCapabilities()

    @property
    def constraints(self) -> RuntimeConstraints:
        return RuntimeConstraints()

    async def _do_submit(self, spec: ContainerJobSpec) -> str:
        ref = f"seq-{uuid.uuid4().hex[:12]}"
        self._jobs[ref] = 0  # Start at first state
        return ref

    async def _do_status(self, external_ref: str) -> JobStatus:
        idx = self._jobs.get(external_ref, 0)
        state = self._states[min(idx, len(self._states) - 1)]

        # Advance to next state for next call
        self._jobs[external_ref] = idx + 1

        # Derive exit code from terminal states
        exit_code = None
        if state == "succeeded":
            exit_code = 0
        elif state == "failed":
            exit_code = 1

        return JobStatus(state=state, exit_code=exit_code)

    async def _do_cancel(self, external_ref: str) -> bool:
        self._jobs[external_ref] = len(self._states)
        return True

    async def _do_logs(self, external_ref: str, *, follow: bool = False, tail: int | None = None) -> AsyncIterator[str]:
        idx = self._jobs.get(external_ref, 0)
        for i, state in enumerate(self._states[:idx]):
            yield f"[sequence] State transition {i}: {state}"

    async def _do_cleanup(self, external_ref: str) -> None:
        self._jobs.pop(external_ref, None)

    async def _do_health(self) -> RuntimeHealth:
        return RuntimeHealth(healthy=True, runtime=self.runtime_name, version="sequence-1.0")


# ---------------------------------------------------------------------------
# LatencyAdapter — wraps another adapter with delay injection
# ---------------------------------------------------------------------------

class LatencyAdapter(BaseRuntimeAdapter):
    """Decorator adapter that adds latency to an inner adapter.

    Wraps any ``BaseRuntimeAdapter`` and injects a configurable delay
    before delegating each call.  Useful for simulating network latency
    or slow container registries without changing the inner adapter.

    Parameters
    ----------
    inner
        The adapter to wrap.
    latency
        Seconds of delay to add to every call.

    Example::

        from spine.execution.runtimes._base import StubRuntimeAdapter
        real = StubRuntimeAdapter()
        slow = LatencyAdapter(inner=real, latency=2.0)
        # Every call to slow.submit() takes real.submit() + 2 seconds
    """

    def __init__(self, *, inner: BaseRuntimeAdapter, latency: float = 0.5) -> None:
        self._inner = inner
        self._latency = latency

    @property
    def runtime_name(self) -> str:
        return f"latency({self._inner.runtime_name})"

    @property
    def capabilities(self) -> RuntimeCapabilities:
        return self._inner.capabilities

    @property
    def constraints(self) -> RuntimeConstraints:
        return self._inner.constraints

    async def _do_submit(self, spec: ContainerJobSpec) -> str:
        await asyncio.sleep(self._latency)
        return await self._inner._do_submit(spec)

    async def _do_status(self, external_ref: str) -> JobStatus:
        await asyncio.sleep(self._latency)
        return await self._inner._do_status(external_ref)

    async def _do_cancel(self, external_ref: str) -> bool:
        await asyncio.sleep(self._latency)
        return await self._inner._do_cancel(external_ref)

    async def _do_logs(self, external_ref: str, *, follow: bool = False, tail: int | None = None) -> AsyncIterator[str]:
        await asyncio.sleep(self._latency)
        async for line in self._inner._do_logs(external_ref, follow=follow, tail=tail):
            yield line

    async def _do_cleanup(self, external_ref: str) -> None:
        await asyncio.sleep(self._latency)
        await self._inner._do_cleanup(external_ref)

    async def _do_health(self) -> RuntimeHealth:
        await asyncio.sleep(self._latency)
        return await self._inner._do_health()
