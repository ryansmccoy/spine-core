"""Tests for JobEngine — central container job lifecycle facade.

Tests:
    - Submit lifecycle (validation, idempotency, ledger, adapter)
    - Status tracking and ledger sync
    - Cancel
    - Logs streaming
    - Cleanup with event recording
    - Error handling (submit failure, unknown execution)
    - list_jobs filtering
"""

import json
import sqlite3
import uuid
from datetime import UTC, datetime

import pytest

from spine.execution.ledger import ExecutionLedger
from spine.execution.models import (
    EventType,
    Execution,
    ExecutionStatus,
)
from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobError,
    ResourceRequirements,
    RuntimeCapabilities,
    RuntimeConstraints,
)
from spine.execution.runtimes._base import StubRuntimeAdapter
from spine.execution.runtimes.engine import JobEngine, SubmitResult, _map_job_status
from spine.execution.runtimes.router import RuntimeAdapterRouter
from spine.execution.runtimes.validator import SpecValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_schema(conn: sqlite3.Connection) -> None:
    """Create minimal execution tables for testing."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS core_executions (
            id TEXT PRIMARY KEY,
            workflow TEXT,
            params TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            lane TEXT DEFAULT 'default',
            trigger_source TEXT DEFAULT 'api',
            parent_execution_id TEXT,
            created_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            retry_count INTEGER DEFAULT 0,
            idempotency_key TEXT
        );
        CREATE TABLE IF NOT EXISTS core_execution_events (
            id TEXT PRIMARY KEY,
            execution_id TEXT,
            event_type TEXT,
            timestamp TEXT,
            data TEXT DEFAULT '{}'
        );
    """)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    """In-memory SQLite connection with schema."""
    connection = sqlite3.connect(":memory:")
    _create_schema(connection)
    yield connection
    connection.close()


@pytest.fixture
def ledger(conn):
    return ExecutionLedger(conn)


@pytest.fixture
def stub_adapter():
    return StubRuntimeAdapter()


@pytest.fixture
def router(stub_adapter):
    r = RuntimeAdapterRouter()
    r.register(stub_adapter)
    return r


@pytest.fixture
def engine(router, ledger):
    return JobEngine(router=router, ledger=ledger)


@pytest.fixture
def minimal_spec():
    return ContainerJobSpec(name="test-job", image="alpine:latest")


# ---------------------------------------------------------------------------
# Submit tests
# ---------------------------------------------------------------------------

class TestSubmit:
    """Test JobEngine.submit() lifecycle."""

    @pytest.mark.asyncio
    async def test_submit_returns_result(self, engine, minimal_spec):
        result = await engine.submit(minimal_spec)
        assert isinstance(result, SubmitResult)
        assert result.execution_id
        assert result.external_ref
        assert result.runtime == "stub"
        assert result.spec_hash

    @pytest.mark.asyncio
    async def test_submit_creates_execution_in_ledger(self, engine, ledger, minimal_spec):
        result = await engine.submit(minimal_spec)
        execution = ledger.get_execution(result.execution_id)
        assert execution is not None
        assert execution.workflow == "job:test-job"
        assert execution.status == ExecutionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_submit_stores_metadata_in_event(self, engine, ledger, minimal_spec):
        result = await engine.submit(minimal_spec)
        events = ledger.get_events(result.execution_id)
        container_events = [
            e for e in events
            if e.event_type.value == "container_created"
        ]
        assert len(container_events) == 1
        data = container_events[0].data
        assert data["external_ref"] == result.external_ref
        assert data["runtime"] == "stub"
        assert data["spec_hash"] == result.spec_hash

    @pytest.mark.asyncio
    async def test_submit_records_container_created_event(self, engine, ledger, minimal_spec):
        result = await engine.submit(minimal_spec)
        events = ledger.get_events(result.execution_id)
        event_types = [e.event_type.value for e in events]
        assert "container_created" in event_types

    @pytest.mark.asyncio
    async def test_submit_increments_adapter_count(self, engine, stub_adapter, minimal_spec):
        assert stub_adapter.submit_count == 0
        await engine.submit(minimal_spec)
        assert stub_adapter.submit_count == 1

    @pytest.mark.asyncio
    async def test_submit_with_lane(self, engine, ledger):
        spec = ContainerJobSpec(name="gpu-job", image="cuda:12", lane="gpu")
        result = await engine.submit(spec)
        execution = ledger.get_execution(result.execution_id)
        assert execution.lane == "gpu"

    @pytest.mark.asyncio
    async def test_submit_with_parent_execution(self, engine, ledger):
        spec = ContainerJobSpec(
            name="child-job", image="alpine",
            parent_execution_id="parent-123",
        )
        result = await engine.submit(spec)
        execution = ledger.get_execution(result.execution_id)
        assert execution.parent_execution_id == "parent-123"


class TestIdempotency:
    """Test idempotency key handling."""

    @pytest.mark.asyncio
    async def test_idempotent_submit_returns_same_id(self, engine, minimal_spec):
        minimal_spec.idempotency_key = "dedup-key-1"
        result1 = await engine.submit(minimal_spec)
        result2 = await engine.submit(minimal_spec)
        assert result1.execution_id == result2.execution_id

    @pytest.mark.asyncio
    async def test_idempotent_submit_does_not_create_duplicate(self, engine, ledger, minimal_spec):
        minimal_spec.idempotency_key = "dedup-key-2"
        await engine.submit(minimal_spec)
        await engine.submit(minimal_spec)
        # Should only have 1 execution
        all_execs = ledger.list_executions()
        assert len(all_execs) == 1

    @pytest.mark.asyncio
    async def test_different_keys_create_separate_executions(self, engine, ledger):
        spec1 = ContainerJobSpec(name="job1", image="x", idempotency_key="key-a")
        spec2 = ContainerJobSpec(name="job2", image="x", idempotency_key="key-b")
        r1 = await engine.submit(spec1)
        r2 = await engine.submit(spec2)
        assert r1.execution_id != r2.execution_id


class TestValidation:
    """Test validation integration."""

    @pytest.mark.asyncio
    async def test_submit_rejects_invalid_spec(self, ledger):
        """GPU required but adapter doesn't support it."""
        class NoGpuAdapter(StubRuntimeAdapter):
            @property
            def capabilities(self):
                return RuntimeCapabilities(supports_gpu=False)

        router = RuntimeAdapterRouter()
        router.register(NoGpuAdapter())
        engine = JobEngine(router=router, ledger=ledger)

        spec = ContainerJobSpec(
            name="gpu-job", image="cuda:12",
            resources=ResourceRequirements(gpu=1),
        )
        with pytest.raises(JobError) as exc_info:
            await engine.submit(spec)
        assert exc_info.value.category == ErrorCategory.VALIDATION


class TestSubmitFailure:
    """Test submit error handling."""

    @pytest.mark.asyncio
    async def test_submit_failure_marks_execution_failed(self, ledger):
        adapter = StubRuntimeAdapter()
        adapter.fail_submit = True
        router = RuntimeAdapterRouter()
        router.register(adapter)
        engine = JobEngine(router=router, ledger=ledger)

        spec = ContainerJobSpec(name="fail-job", image="alpine")
        with pytest.raises(JobError):
            await engine.submit(spec)

        # Should have one failed execution
        all_execs = ledger.list_executions()
        assert len(all_execs) == 1
        assert all_execs[0].status == ExecutionStatus.FAILED


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------

class TestStatus:
    """Test JobEngine.status()."""

    @pytest.mark.asyncio
    async def test_status_returns_job_status(self, engine, minimal_spec):
        result = await engine.submit(minimal_spec)
        status = await engine.status(result.execution_id)
        assert status.state == "succeeded"  # StubAdapter auto-succeeds

    @pytest.mark.asyncio
    async def test_status_unknown_execution_raises(self, engine):
        with pytest.raises(JobError) as exc_info:
            await engine.status("nonexistent-id")
        assert exc_info.value.category == ErrorCategory.NOT_FOUND

    @pytest.mark.asyncio
    async def test_status_syncs_ledger(self, engine, ledger, minimal_spec):
        """Status check should update ledger if runtime state changed."""
        result = await engine.submit(minimal_spec)
        # After submit, execution is RUNNING in ledger
        # After status check, stub says "succeeded" → ledger should sync
        await engine.status(result.execution_id)
        execution = ledger.get_execution(result.execution_id)
        assert execution.status == ExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# Cancel tests
# ---------------------------------------------------------------------------

class TestCancel:
    """Test JobEngine.cancel()."""

    @pytest.mark.asyncio
    async def test_cancel_running_job(self, engine, ledger, minimal_spec):
        result = await engine.submit(minimal_spec)
        cancelled = await engine.cancel(result.execution_id)
        assert cancelled is True

    @pytest.mark.asyncio
    async def test_cancel_already_terminal_is_noop(self, engine, ledger, minimal_spec):
        result = await engine.submit(minimal_spec)
        # Status check syncs to COMPLETED (stub auto-succeeds)
        await engine.status(result.execution_id)
        execution = ledger.get_execution(result.execution_id)
        assert execution.status == ExecutionStatus.COMPLETED

        # Cancel should be no-op on completed
        cancelled = await engine.cancel(result.execution_id)
        assert cancelled is True

    @pytest.mark.asyncio
    async def test_cancel_unknown_execution_raises(self, engine):
        with pytest.raises(JobError) as exc_info:
            await engine.cancel("nonexistent-id")
        assert exc_info.value.category == ErrorCategory.NOT_FOUND

    @pytest.mark.asyncio
    async def test_cancel_failure(self, ledger):
        adapter = StubRuntimeAdapter()
        adapter.fail_cancel = True
        router = RuntimeAdapterRouter()
        router.register(adapter)
        engine = JobEngine(router=router, ledger=ledger)

        spec = ContainerJobSpec(name="test", image="alpine")
        result = await engine.submit(spec)
        cancelled = await engine.cancel(result.execution_id)
        assert cancelled is False


# ---------------------------------------------------------------------------
# Logs tests
# ---------------------------------------------------------------------------

class TestLogs:
    """Test JobEngine.logs()."""

    @pytest.mark.asyncio
    async def test_logs_streams_lines(self, engine, minimal_spec):
        result = await engine.submit(minimal_spec)
        lines = []
        async for line in engine.logs(result.execution_id):
            lines.append(line)
        assert len(lines) == 2  # StubAdapter default: 2 lines
        assert "[stub] Job started" in lines[0]

    @pytest.mark.asyncio
    async def test_logs_with_tail(self, engine, minimal_spec):
        result = await engine.submit(minimal_spec)
        lines = []
        async for line in engine.logs(result.execution_id, tail=1):
            lines.append(line)
        assert len(lines) == 1

    @pytest.mark.asyncio
    async def test_logs_unknown_execution_raises(self, engine):
        with pytest.raises(JobError):
            async for _ in engine.logs("nonexistent-id"):
                pass


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------

class TestCleanup:
    """Test JobEngine.cleanup()."""

    @pytest.mark.asyncio
    async def test_cleanup_records_events(self, engine, ledger, minimal_spec):
        result = await engine.submit(minimal_spec)
        await engine.cleanup(result.execution_id)
        events = ledger.get_events(result.execution_id)
        event_types = [e.event_type.value for e in events]
        assert "cleanup_started" in event_types
        assert "cleanup_completed" in event_types

    @pytest.mark.asyncio
    async def test_cleanup_increments_adapter_count(self, engine, stub_adapter, minimal_spec):
        result = await engine.submit(minimal_spec)
        assert stub_adapter.cleanup_count == 0
        await engine.cleanup(result.execution_id)
        assert stub_adapter.cleanup_count == 1

    @pytest.mark.asyncio
    async def test_cleanup_unknown_execution_raises(self, engine):
        with pytest.raises(JobError):
            await engine.cleanup("nonexistent-id")


# ---------------------------------------------------------------------------
# list_jobs tests
# ---------------------------------------------------------------------------

class TestListJobs:
    """Test JobEngine.list_jobs()."""

    @pytest.mark.asyncio
    async def test_list_jobs_filters_by_prefix(self, engine, ledger, minimal_spec):
        # Submit via engine (creates job: prefixed execution)
        await engine.submit(minimal_spec)

        # Create a non-job execution directly in ledger
        non_job = Execution.create(workflow="task:echo")
        ledger.create_execution(non_job)

        jobs = engine.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].workflow.startswith("job:")

    @pytest.mark.asyncio
    async def test_list_jobs_with_limit(self, engine, minimal_spec):
        for i in range(5):
            spec = ContainerJobSpec(name=f"job-{i}", image="alpine")
            await engine.submit(spec)
        jobs = engine.list_jobs(limit=3)
        assert len(jobs) == 3


# ---------------------------------------------------------------------------
# State mapping
# ---------------------------------------------------------------------------

class TestStateMapping:
    """Test runtime status → execution status mapping."""

    def test_succeeded_maps_to_completed(self):
        from spine.execution.runtimes._types import JobStatus
        js = JobStatus(state="succeeded")
        assert _map_job_status(js) == ExecutionStatus.COMPLETED

    def test_failed_maps_to_failed(self):
        from spine.execution.runtimes._types import JobStatus
        js = JobStatus(state="failed")
        assert _map_job_status(js) == ExecutionStatus.FAILED

    def test_running_maps_to_running(self):
        from spine.execution.runtimes._types import JobStatus
        js = JobStatus(state="running")
        assert _map_job_status(js) == ExecutionStatus.RUNNING

    def test_pending_maps_to_queued(self):
        from spine.execution.runtimes._types import JobStatus
        js = JobStatus(state="pending")
        assert _map_job_status(js) == ExecutionStatus.QUEUED

    def test_cancelled_maps_to_cancelled(self):
        from spine.execution.runtimes._types import JobStatus
        js = JobStatus(state="cancelled")
        assert _map_job_status(js) == ExecutionStatus.CANCELLED

    def test_unknown_defaults_to_running(self):
        from spine.execution.runtimes._types import JobStatus
        js = JobStatus(state="unknown")
        assert _map_job_status(js) == ExecutionStatus.RUNNING


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Test edge cases and error paths."""

    @pytest.mark.asyncio
    async def test_engine_with_no_adapters(self, ledger):
        router = RuntimeAdapterRouter()
        engine = JobEngine(router=router, ledger=ledger)
        spec = ContainerJobSpec(name="test", image="alpine")
        with pytest.raises(JobError) as exc_info:
            await engine.submit(spec)
        assert exc_info.value.category == ErrorCategory.NOT_FOUND

    @pytest.mark.asyncio
    async def test_engine_with_explicit_missing_runtime(self, engine, ledger):
        spec = ContainerJobSpec(name="test", image="alpine", runtime="k8s")
        with pytest.raises(JobError) as exc_info:
            await engine.submit(spec)
        assert exc_info.value.category == ErrorCategory.NOT_FOUND

    @pytest.mark.asyncio
    async def test_multiple_submits_different_specs(self, engine, ledger):
        spec1 = ContainerJobSpec(name="job-a", image="img-a")
        spec2 = ContainerJobSpec(name="job-b", image="img-b")
        r1 = await engine.submit(spec1)
        r2 = await engine.submit(spec2)
        assert r1.execution_id != r2.execution_id
        assert r1.external_ref != r2.external_ref

    @pytest.mark.asyncio
    async def test_submit_result_has_spec_hash(self, engine, minimal_spec):
        result = await engine.submit(minimal_spec)
        assert len(result.spec_hash) == 64  # SHA-256 hex
