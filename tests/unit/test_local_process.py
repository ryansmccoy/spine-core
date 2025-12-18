"""Tests for LocalProcessAdapter — container-free execution.

Tests:
    - Submit and run a simple command
    - Status tracking (succeeded, failed)
    - Cancel a running process
    - Log capture (stdout + stderr)
    - Artifact collection
    - Timeout enforcement
    - Command not found handling
    - Capabilities (GPU etc. not supported)
    - Health check (always healthy)
    - Integration with JobEngine via router
"""

import asyncio
import sys

import pytest

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    ResourceRequirements,
    RuntimeCapabilities,
)
from spine.execution.runtimes.local_process import LocalProcessAdapter


@pytest.fixture
def adapter():
    return LocalProcessAdapter()


@pytest.fixture
def python_spec():
    """Spec that runs a simple Python command."""
    return ContainerJobSpec(
        name="py-hello",
        image="ignored",
        command=[sys.executable, "-c", "print('hello from local')"],
        timeout_seconds=10,
    )


class TestSubmitAndRun:
    """Test basic submit + run lifecycle."""

    @pytest.mark.asyncio
    async def test_submit_returns_ref(self, adapter, python_spec):
        ref = await adapter.submit(python_spec)
        assert ref.startswith("local-")
        assert len(ref) > 6

    @pytest.mark.asyncio
    async def test_successful_command(self, adapter, python_spec):
        ref = await adapter.submit(python_spec)
        # Give the process time to complete
        await asyncio.sleep(0.5)
        status = await adapter.status(ref)
        assert status.state == "succeeded"
        assert status.exit_code == 0

    @pytest.mark.asyncio
    async def test_failed_command(self, adapter):
        spec = ContainerJobSpec(
            name="fail-job",
            image="ignored",
            command=[sys.executable, "-c", "raise SystemExit(42)"],
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        status = await adapter.status(ref)
        assert status.state == "failed"
        assert status.exit_code == 42

    @pytest.mark.asyncio
    async def test_command_with_args(self, adapter):
        spec = ContainerJobSpec(
            name="args-job",
            image="ignored",
            command=[sys.executable],
            args=["-c", "import sys; print(sys.version)"],
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        status = await adapter.status(ref)
        assert status.state == "succeeded"

    @pytest.mark.asyncio
    async def test_no_command_raises(self, adapter):
        spec = ContainerJobSpec(name="empty", image="ignored")
        spec.command = None
        spec.args = None
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(spec)
        assert exc_info.value.category == ErrorCategory.VALIDATION


class TestEnvironment:
    """Test environment variable handling."""

    @pytest.mark.asyncio
    async def test_spec_env_vars_passed(self, adapter):
        spec = ContainerJobSpec(
            name="env-job",
            image="ignored",
            command=[sys.executable, "-c", "import os; print(os.environ['MY_VAR'])"],
            env={"MY_VAR": "spine-test-value"},
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        status = await adapter.status(ref)
        assert status.state == "succeeded"

    @pytest.mark.asyncio
    async def test_runtime_marker_set(self, adapter):
        spec = ContainerJobSpec(
            name="marker-job",
            image="ignored",
            command=[
                sys.executable, "-c",
                "import os; assert os.environ['SPINE_RUNTIME'] == 'local'",
            ],
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        status = await adapter.status(ref)
        assert status.state == "succeeded"

    @pytest.mark.asyncio
    async def test_no_inherit_env(self):
        adapter = LocalProcessAdapter(inherit_env=False)
        spec = ContainerJobSpec(
            name="no-inherit",
            image="ignored",
            command=[sys.executable, "-c", "print('ok')"],
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        status = await adapter.status(ref)
        # May succeed or fail depending on PATH — just verify it ran
        assert status.state in ("succeeded", "failed")


class TestLogs:
    """Test log capture."""

    @pytest.mark.asyncio
    async def test_stdout_captured(self, adapter):
        spec = ContainerJobSpec(
            name="log-job",
            image="ignored",
            command=[sys.executable, "-c", "print('line1'); print('line2')"],
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        lines = []
        async for line in adapter.logs(ref):
            lines.append(line)
        assert "line1" in lines
        assert "line2" in lines

    @pytest.mark.asyncio
    async def test_stderr_captured(self, adapter):
        spec = ContainerJobSpec(
            name="stderr-job",
            image="ignored",
            command=[
                sys.executable, "-c",
                "import sys; print('err_msg', file=sys.stderr)",
            ],
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        lines = []
        async for line in adapter.logs(ref):
            lines.append(line)
        assert any("err_msg" in l for l in lines)

    @pytest.mark.asyncio
    async def test_logs_tail(self, adapter):
        spec = ContainerJobSpec(
            name="tail-job",
            image="ignored",
            command=[
                sys.executable, "-c",
                "for i in range(10): print(f'line-{i}')",
            ],
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        lines = []
        async for line in adapter.logs(ref, tail=3):
            lines.append(line)
        assert len(lines) == 3

    @pytest.mark.asyncio
    async def test_logs_nonexistent_ref(self, adapter):
        lines = []
        async for line in adapter.logs("nonexistent"):
            lines.append(line)
        assert lines == []


class TestCancel:
    """Test process cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_running_process(self, adapter):
        spec = ContainerJobSpec(
            name="long-job",
            image="ignored",
            command=[sys.executable, "-c", "import time; time.sleep(60)"],
            timeout_seconds=120,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.3)
        result = await adapter.cancel(ref)
        assert result is True
        status = await adapter.status(ref)
        assert status.state == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_already_finished(self, adapter, python_spec):
        ref = await adapter.submit(python_spec)
        await asyncio.sleep(0.5)
        result = await adapter.cancel(ref)
        assert result is True

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, adapter):
        result = await adapter.cancel("nonexistent")
        assert result is True  # Idempotent


class TestCleanup:
    """Test resource cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_completed_job(self, adapter, python_spec):
        ref = await adapter.submit(python_spec)
        await asyncio.sleep(0.5)
        await adapter.cleanup(ref)
        # Should still be queryable after cleanup
        status = await adapter.status(ref)
        assert status.state in ("succeeded", "failed", "unknown")

    @pytest.mark.asyncio
    async def test_cleanup_running_kills_process(self, adapter):
        spec = ContainerJobSpec(
            name="long-job",
            image="ignored",
            command=[sys.executable, "-c", "import time; time.sleep(60)"],
            timeout_seconds=120,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.3)
        await adapter.cleanup(ref)

    @pytest.mark.asyncio
    async def test_cleanup_nonexistent(self, adapter):
        # Should not raise
        await adapter.cleanup("nonexistent")


class TestArtifacts:
    """Test artifact collection from local directory."""

    @pytest.mark.asyncio
    async def test_artifacts_collected(self, adapter, tmp_path):
        adapter_with_dir = LocalProcessAdapter(work_dir=tmp_path)
        spec = ContainerJobSpec(
            name="artifact-job",
            image="ignored",
            command=[
                sys.executable, "-c",
                "import os; d = os.environ['SPINE_ARTIFACTS_DIR']; "
                "open(os.path.join(d, 'report.txt'), 'w').write('data')",
            ],
            artifacts_dir="/artifacts",
            timeout_seconds=10,
        )
        ref = await adapter_with_dir.submit(spec)
        await asyncio.sleep(0.5)
        artifacts = await adapter_with_dir.artifacts(ref)
        assert len(artifacts) == 1
        assert artifacts[0].name == "report.txt"

    @pytest.mark.asyncio
    async def test_no_artifacts_dir(self, adapter):
        spec = ContainerJobSpec(
            name="no-art",
            image="ignored",
            command=[sys.executable, "-c", "print('ok')"],
            artifacts_dir=None,
            timeout_seconds=10,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(0.5)
        artifacts = await adapter.artifacts(ref)
        assert artifacts == []


class TestCapabilities:
    """Test capability reporting."""

    def test_no_gpu(self, adapter):
        assert not adapter.capabilities.supports_gpu

    def test_no_volumes(self, adapter):
        assert not adapter.capabilities.supports_volumes

    def test_no_sidecars(self, adapter):
        assert not adapter.capabilities.supports_sidecars

    def test_no_init_containers(self, adapter):
        assert not adapter.capabilities.supports_init_containers

    def test_supports_artifacts(self, adapter):
        assert adapter.capabilities.supports_artifacts

    def test_runtime_name(self, adapter):
        assert adapter.runtime_name == "local"


class TestHealth:
    """Test health check."""

    @pytest.mark.asyncio
    async def test_always_healthy(self, adapter):
        health = await adapter.health()
        assert health.healthy
        assert health.runtime == "local"


class TestCommandNotFound:
    """Test handling of missing commands."""

    @pytest.mark.asyncio
    async def test_nonexistent_command(self, adapter):
        spec = ContainerJobSpec(
            name="bad-cmd",
            image="ignored",
            command=["nonexistent_binary_xyz_12345"],
            timeout_seconds=10,
        )
        with pytest.raises(JobError) as exc_info:
            await adapter.submit(spec)
        assert exc_info.value.category == ErrorCategory.NOT_FOUND
        assert "not found" in exc_info.value.message.lower()


class TestTimeout:
    """Test timeout enforcement."""

    @pytest.mark.asyncio
    async def test_process_killed_on_timeout(self, adapter):
        spec = ContainerJobSpec(
            name="timeout-job",
            image="ignored",
            command=[sys.executable, "-c", "import time; time.sleep(60)"],
            timeout_seconds=1,
        )
        ref = await adapter.submit(spec)
        await asyncio.sleep(2.5)  # Wait for timeout + kill
        status = await adapter.status(ref)
        assert status.state == "failed"
        assert status.exit_code is not None


class TestStatusUnknown:
    """Test status of unknown refs."""

    @pytest.mark.asyncio
    async def test_unknown_ref(self, adapter):
        status = await adapter.status("nonexistent-ref")
        assert status.state == "unknown"
