"""Tests for mock runtime adapters.

Covers FailingAdapter, SlowAdapter, FlakeyAdapter, SequenceAdapter,
and LatencyAdapter.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from spine.execution.runtimes._base import StubRuntimeAdapter
from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
)
from spine.execution.runtimes.mock_adapters import (
    FailingAdapter,
    FlakeyAdapter,
    LatencyAdapter,
    SequenceAdapter,
    SlowAdapter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(name: str = "test-job") -> ContainerJobSpec:
    """Create a minimal ContainerJobSpec for testing."""
    return ContainerJobSpec(name=name, image="busybox:latest")


# ---------------------------------------------------------------------------
# FailingAdapter
# ---------------------------------------------------------------------------

class TestFailingAdapter:
    """Tests for FailingAdapter."""

    @pytest.mark.asyncio
    async def test_submit_raises_job_error(self) -> None:
        adapter = FailingAdapter()
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(_make_spec())
        assert exc_info.value.category == ErrorCategory.RUNTIME_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_custom_category(self) -> None:
        adapter = FailingAdapter(category=ErrorCategory.OOM)
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(_make_spec("oom-test"))
        assert exc_info.value.category == ErrorCategory.OOM
        assert "oom-test" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_custom_message(self) -> None:
        adapter = FailingAdapter(message="disk full")
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(_make_spec())
        assert "disk full" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_retryable_flag(self) -> None:
        adapter = FailingAdapter(retryable=True)
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(_make_spec())
        assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_status_returns_failed(self) -> None:
        adapter = FailingAdapter()
        status = await adapter.status("any-ref")
        assert status.state == "failed"

    @pytest.mark.asyncio
    async def test_cancel_returns_false(self) -> None:
        adapter = FailingAdapter()
        result = await adapter.cancel("any-ref")
        assert result is False

    @pytest.mark.asyncio
    async def test_health_unhealthy(self) -> None:
        adapter = FailingAdapter()
        health = await adapter.health()
        assert health.healthy is False

    def test_runtime_name(self) -> None:
        assert FailingAdapter().runtime_name == "failing"

    @pytest.mark.asyncio
    async def test_logs_yield_message(self) -> None:
        adapter = FailingAdapter(message="broken")
        lines = []
        async for line in adapter.logs("ref"):
            lines.append(line)
        assert any("broken" in l for l in lines)


# ---------------------------------------------------------------------------
# SlowAdapter
# ---------------------------------------------------------------------------

class TestSlowAdapter:
    """Tests for SlowAdapter."""

    @pytest.mark.asyncio
    async def test_submit_succeeds(self) -> None:
        adapter = SlowAdapter(submit_delay=0.01, status_delay=0.0)
        ref = await adapter.submit(_make_spec())
        assert ref.startswith("slow-")

    @pytest.mark.asyncio
    async def test_submit_delay(self) -> None:
        adapter = SlowAdapter(submit_delay=0.2, status_delay=0.0)
        t0 = time.monotonic()
        await adapter.submit(_make_spec())
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.15

    @pytest.mark.asyncio
    async def test_auto_succeed(self) -> None:
        adapter = SlowAdapter(submit_delay=0.0, auto_succeed=True)
        ref = await adapter.submit(_make_spec())
        status = await adapter.status(ref)
        assert status.state == "succeeded"
        assert status.exit_code == 0

    @pytest.mark.asyncio
    async def test_auto_fail(self) -> None:
        adapter = SlowAdapter(submit_delay=0.0, auto_succeed=False)
        ref = await adapter.submit(_make_spec())
        status = await adapter.status(ref)
        assert status.state == "failed"
        assert status.exit_code == 1

    @pytest.mark.asyncio
    async def test_cancel(self) -> None:
        adapter = SlowAdapter(submit_delay=0.0)
        ref = await adapter.submit(_make_spec())
        result = await adapter.cancel(ref)
        assert result is True
        status = await adapter.status(ref)
        assert status.state == "cancelled"

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        adapter = SlowAdapter(submit_delay=0.0)
        ref = await adapter.submit(_make_spec())
        await adapter.cleanup(ref)
        status = await adapter.status(ref)
        assert status.state == "unknown"

    @pytest.mark.asyncio
    async def test_health(self) -> None:
        adapter = SlowAdapter(status_delay=0.0)
        health = await adapter.health()
        assert health.healthy is True

    def test_runtime_name(self) -> None:
        assert SlowAdapter().runtime_name == "slow"

    @pytest.mark.asyncio
    async def test_logs(self) -> None:
        adapter = SlowAdapter(submit_delay=0.01)
        lines = []
        async for line in adapter.logs("ref"):
            lines.append(line)
        assert len(lines) == 2


# ---------------------------------------------------------------------------
# FlakeyAdapter
# ---------------------------------------------------------------------------

class TestFlakeyAdapter:
    """Tests for FlakeyAdapter."""

    @pytest.mark.asyncio
    async def test_always_succeed(self) -> None:
        adapter = FlakeyAdapter(success_rate=1.0)
        ref = await adapter.submit(_make_spec())
        assert ref.startswith("flakey-")
        assert adapter.success_count == 1
        assert adapter.failure_count == 0

    @pytest.mark.asyncio
    async def test_always_fail(self) -> None:
        adapter = FlakeyAdapter(success_rate=0.0)
        with pytest.raises(JobError):
            await adapter.submit(_make_spec())
        assert adapter.success_count == 0
        assert adapter.failure_count == 1

    @pytest.mark.asyncio
    async def test_seeded_reproducibility(self) -> None:
        """Same seed produces same success/failure sequence."""
        results_a = []
        adapter_a = FlakeyAdapter(success_rate=0.5, seed=42)
        for _ in range(20):
            try:
                await adapter_a.submit(_make_spec())
                results_a.append(True)
            except JobError:
                results_a.append(False)

        results_b = []
        adapter_b = FlakeyAdapter(success_rate=0.5, seed=42)
        for _ in range(20):
            try:
                await adapter_b.submit(_make_spec())
                results_b.append(True)
            except JobError:
                results_b.append(False)

        assert results_a == results_b

    @pytest.mark.asyncio
    async def test_counters(self) -> None:
        adapter = FlakeyAdapter(success_rate=0.5, seed=1)
        for _ in range(10):
            try:
                await adapter.submit(_make_spec())
            except JobError:
                pass
        assert adapter.submit_count == 10
        assert adapter.success_count + adapter.failure_count == 10

    @pytest.mark.asyncio
    async def test_retryable(self) -> None:
        adapter = FlakeyAdapter(success_rate=0.0)
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(_make_spec())
        assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_custom_failure_category(self) -> None:
        adapter = FlakeyAdapter(success_rate=0.0, failure_category=ErrorCategory.OOM)
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(_make_spec())
        assert exc_info.value.category == ErrorCategory.OOM

    def test_invalid_success_rate(self) -> None:
        with pytest.raises(ValueError, match="0.0-1.0"):
            FlakeyAdapter(success_rate=1.5)
        with pytest.raises(ValueError, match="0.0-1.0"):
            FlakeyAdapter(success_rate=-0.1)

    def test_runtime_name(self) -> None:
        assert FlakeyAdapter().runtime_name == "flakey"


# ---------------------------------------------------------------------------
# SequenceAdapter
# ---------------------------------------------------------------------------

class TestSequenceAdapter:
    """Tests for SequenceAdapter."""

    @pytest.mark.asyncio
    async def test_default_sequence(self) -> None:
        adapter = SequenceAdapter()
        ref = await adapter.submit(_make_spec())
        s1 = await adapter.status(ref)
        s2 = await adapter.status(ref)
        s3 = await adapter.status(ref)
        assert s1.state == "pending"
        assert s2.state == "running"
        assert s3.state == "succeeded"

    @pytest.mark.asyncio
    async def test_stays_at_last_state(self) -> None:
        adapter = SequenceAdapter(states=["pending", "succeeded"])
        ref = await adapter.submit(_make_spec())
        await adapter.status(ref)  # pending
        await adapter.status(ref)  # succeeded
        s3 = await adapter.status(ref)  # still succeeded
        assert s3.state == "succeeded"

    @pytest.mark.asyncio
    async def test_exit_code_succeeded(self) -> None:
        adapter = SequenceAdapter(states=["succeeded"])
        ref = await adapter.submit(_make_spec())
        status = await adapter.status(ref)
        assert status.exit_code == 0

    @pytest.mark.asyncio
    async def test_exit_code_failed(self) -> None:
        adapter = SequenceAdapter(states=["failed"])
        ref = await adapter.submit(_make_spec())
        status = await adapter.status(ref)
        assert status.exit_code == 1

    @pytest.mark.asyncio
    async def test_cancel_jumps_to_end(self) -> None:
        adapter = SequenceAdapter(states=["pending", "running", "succeeded"])
        ref = await adapter.submit(_make_spec())
        await adapter.cancel(ref)
        status = await adapter.status(ref)
        assert status.state == "succeeded"  # jumped to last

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        adapter = SequenceAdapter()
        ref = await adapter.submit(_make_spec())
        await adapter.cleanup(ref)
        status = await adapter.status(ref)
        assert status.state == "pending"  # Reset to beginning

    @pytest.mark.asyncio
    async def test_logs_track_transitions(self) -> None:
        adapter = SequenceAdapter(states=["pending", "running", "succeeded"])
        ref = await adapter.submit(_make_spec())
        await adapter.status(ref)
        await adapter.status(ref)
        lines = []
        async for line in adapter.logs(ref):
            lines.append(line)
        assert len(lines) == 2  # pending, running

    @pytest.mark.asyncio
    async def test_health(self) -> None:
        adapter = SequenceAdapter()
        health = await adapter.health()
        assert health.healthy is True

    @pytest.mark.asyncio
    async def test_multiple_jobs(self) -> None:
        adapter = SequenceAdapter(states=["pending", "succeeded"])
        ref_a = await adapter.submit(_make_spec("a"))
        ref_b = await adapter.submit(_make_spec("b"))
        sa = await adapter.status(ref_a)
        sb = await adapter.status(ref_b)
        assert sa.state == "pending"
        assert sb.state == "pending"
        sa2 = await adapter.status(ref_a)
        assert sa2.state == "succeeded"

    def test_runtime_name(self) -> None:
        assert SequenceAdapter().runtime_name == "sequence"


# ---------------------------------------------------------------------------
# LatencyAdapter
# ---------------------------------------------------------------------------

class TestLatencyAdapter:
    """Tests for LatencyAdapter (decorator pattern)."""

    @pytest.mark.asyncio
    async def test_wraps_submit(self) -> None:
        inner = StubRuntimeAdapter()
        adapter = LatencyAdapter(inner=inner, latency=0.01)
        ref = await adapter.submit(_make_spec())
        assert ref.startswith("stub-")

    @pytest.mark.asyncio
    async def test_adds_latency(self) -> None:
        inner = StubRuntimeAdapter()
        adapter = LatencyAdapter(inner=inner, latency=0.2)
        t0 = time.monotonic()
        await adapter.submit(_make_spec())
        elapsed = time.monotonic() - t0
        assert elapsed >= 0.15

    @pytest.mark.asyncio
    async def test_delegates_status(self) -> None:
        inner = StubRuntimeAdapter()
        adapter = LatencyAdapter(inner=inner, latency=0.0)
        ref = await adapter.submit(_make_spec())
        status = await adapter.status(ref)
        assert status.state in ("succeeded", "completed", "running")

    @pytest.mark.asyncio
    async def test_delegates_cancel(self) -> None:
        inner = StubRuntimeAdapter()
        adapter = LatencyAdapter(inner=inner, latency=0.0)
        ref = await adapter.submit(_make_spec())
        result = await adapter.cancel(ref)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_delegates_health(self) -> None:
        inner = StubRuntimeAdapter()
        adapter = LatencyAdapter(inner=inner, latency=0.0)
        health = await adapter.health()
        assert health.healthy is True

    @pytest.mark.asyncio
    async def test_runtime_name(self) -> None:
        inner = StubRuntimeAdapter()
        adapter = LatencyAdapter(inner=inner)
        assert adapter.runtime_name == "latency(stub)"

    @pytest.mark.asyncio
    async def test_capabilities_delegation(self) -> None:
        inner = StubRuntimeAdapter()
        adapter = LatencyAdapter(inner=inner, latency=0.0)
        assert adapter.capabilities == inner.capabilities

    @pytest.mark.asyncio
    async def test_logs_delegation(self) -> None:
        inner = StubRuntimeAdapter()
        adapter = LatencyAdapter(inner=inner, latency=0.0)
        ref = await adapter.submit(_make_spec())
        lines = []
        async for line in adapter.logs(ref):
            lines.append(line)
        assert isinstance(lines, list)
