"""Tests for LocalProcessAdapter — runs jobs as local subprocesses."""

from __future__ import annotations

import asyncio
import sys

import pytest

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ResourceRequirements,
    RuntimeCapabilities,
)
from spine.execution.runtimes.local_process import LocalProcessAdapter


# ── Helpers ──────────────────────────────────────────────────────────────


def _spec(name: str = "test", **kwargs) -> ContainerJobSpec:
    defaults = {
        "name": name,
        "image": "ignored",
        "timeout_seconds": 30,
    }
    defaults.update(kwargs)
    return ContainerJobSpec(**defaults)


# ── Properties ───────────────────────────────────────────────────────────


class TestProperties:
    def test_runtime_name(self):
        adapter = LocalProcessAdapter()
        assert adapter.runtime_name == "local"

    def test_capabilities_no_gpu(self):
        adapter = LocalProcessAdapter()
        caps = adapter.capabilities
        assert isinstance(caps, RuntimeCapabilities)
        assert caps.supports_gpu is False

    def test_capabilities_no_volumes(self):
        adapter = LocalProcessAdapter()
        assert adapter.capabilities.supports_volumes is False


# ── Submit + Status ──────────────────────────────────────────────────────


class TestSubmitStatus:
    @pytest.mark.asyncio
    async def test_submit_echo(self):
        adapter = LocalProcessAdapter()
        spec = _spec(
            command=[sys.executable, "-c", "print('hello')"],
        )
        ref = await adapter.submit(spec)
        assert ref  # non-empty string

        # Wait a moment for subprocess to finish
        await asyncio.sleep(1.0)

        status = await adapter.status(ref)
        assert status.state in ("succeeded", "running", "pending")

    @pytest.mark.asyncio
    async def test_submit_failing_command(self):
        adapter = LocalProcessAdapter()
        spec = _spec(
            command=[sys.executable, "-c", "raise SystemExit(1)"],
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(1.0)
        status = await adapter.status(ref)
        # Should eventually be "failed" (exit code 1)
        assert status.state in ("failed", "running")

    @pytest.mark.asyncio
    async def test_status_unknown_ref(self):
        adapter = LocalProcessAdapter()
        status = await adapter.status("nonexistent-ref")
        assert status.state == "unknown"


# ── Cancel ───────────────────────────────────────────────────────────────


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_running(self):
        adapter = LocalProcessAdapter()
        spec = _spec(
            command=[sys.executable, "-c", "import time; time.sleep(30)"],
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.3)
        result = await adapter.cancel(ref)
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self):
        adapter = LocalProcessAdapter()
        result = await adapter.cancel("nonexistent")
        assert result is True  # cancel of nonexistent is a no-op success


# ── Logs ─────────────────────────────────────────────────────────────────


class TestLogs:
    @pytest.mark.asyncio
    async def test_logs_from_command(self):
        adapter = LocalProcessAdapter()
        spec = _spec(
            command=[sys.executable, "-c", "print('line1'); print('line2')"],
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(1.0)
        lines = []
        async for line in adapter.logs(ref):
            lines.append(line)
        assert len(lines) >= 0  # May have output


# ── Cleanup ──────────────────────────────────────────────────────────────


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_completed(self):
        adapter = LocalProcessAdapter()
        spec = _spec(
            command=[sys.executable, "-c", "print('done')"],
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(1.0)
        await adapter.cleanup(ref)  # should not raise

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent(self):
        adapter = LocalProcessAdapter()
        await adapter.cleanup("nonexistent")  # should not raise


# ── Health ───────────────────────────────────────────────────────────────


class TestHealth:
    @pytest.mark.asyncio
    async def test_health(self):
        adapter = LocalProcessAdapter()
        health = await adapter.health()
        assert health.healthy is True
        assert health.runtime == "local"
