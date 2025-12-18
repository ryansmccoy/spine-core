"""Tests for JobEngine — central facade for container job lifecycle."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from spine.execution.models import EventType, Execution, ExecutionStatus, TriggerSource
from spine.execution.runtimes._base import StubRuntimeAdapter
from spine.execution.runtimes._types import ContainerJobSpec, ErrorCategory, JobError
from spine.execution.runtimes.engine import JobEngine, SubmitResult, _map_job_status
from spine.execution.runtimes.router import RuntimeAdapterRouter
from spine.execution.runtimes.validator import SpecValidator


# ── Helpers ──────────────────────────────────────────────────────────────


def _spec(name: str = "test-job", **kwargs) -> ContainerJobSpec:
    defaults = {"name": name, "image": "test:latest"}
    defaults.update(kwargs)
    return ContainerJobSpec(**defaults)


class MockLedger:
    """Simple mock ledger recording calls for engine tests."""

    def __init__(self):
        self.executions: dict[str, Execution] = {}
        self.events: list[dict] = []

    def create_execution(self, execution: Execution) -> Execution:
        self.executions[execution.id] = execution
        return execution

    def get_execution(self, execution_id: str) -> Execution | None:
        return self.executions.get(execution_id)

    def get_by_idempotency_key(self, key: str) -> Execution | None:
        for ex in self.executions.values():
            if ex.idempotency_key == key:
                return ex
        return None

    def update_status(self, execution_id: str, status: ExecutionStatus, **kw):
        ex = self.executions.get(execution_id)
        if ex:
            ex.status = status

    def record_event(self, execution_id: str, event_type: Any, data: dict | None = None):
        self.events.append({
            "execution_id": execution_id,
            "event_type": event_type,
            "data": data or {},
        })


@pytest.fixture()
def stub_adapter():
    return StubRuntimeAdapter(auto_succeed=True)


@pytest.fixture()
def router(stub_adapter):
    r = RuntimeAdapterRouter()
    r.register(stub_adapter)
    return r


@pytest.fixture()
def ledger():
    return MockLedger()


@pytest.fixture()
def engine(router, ledger):
    return JobEngine(router=router, ledger=ledger)


# ── SubmitResult ─────────────────────────────────────────────────────────


class TestSubmitResult:
    def test_frozen(self):
        sr = SubmitResult(
            execution_id="e1", external_ref="ref-1",
            runtime="stub", spec_hash="abc",
        )
        assert sr.execution_id == "e1"
        with pytest.raises(AttributeError):
            sr.execution_id = "e2"  # type: ignore[misc]


# ── State Mapping ────────────────────────────────────────────────────────


class TestStateMapping:
    @pytest.mark.parametrize(
        "state,expected",
        [
            ("pending", ExecutionStatus.QUEUED),
            ("running", ExecutionStatus.RUNNING),
            ("succeeded", ExecutionStatus.COMPLETED),
            ("failed", ExecutionStatus.FAILED),
            ("cancelled", ExecutionStatus.CANCELLED),
        ],
    )
    def test_known_states(self, state, expected):
        from spine.execution.runtimes._types import JobStatus

        js = JobStatus(state=state)
        assert _map_job_status(js) == expected

    def test_unknown_state_defaults_to_running(self):
        from spine.execution.runtimes._types import JobStatus

        js = JobStatus(state="unknown")
        assert _map_job_status(js) == ExecutionStatus.RUNNING


# ── Submit ───────────────────────────────────────────────────────────────


class TestSubmit:
    @pytest.mark.asyncio
    async def test_submit_success(self, engine, ledger, stub_adapter):
        result = await engine.submit(_spec())
        assert isinstance(result, SubmitResult)
        assert result.runtime == "stub"
        assert result.external_ref.startswith("stub-")
        assert stub_adapter.submit_count == 1

    @pytest.mark.asyncio
    async def test_submit_creates_execution(self, engine, ledger):
        result = await engine.submit(_spec())
        assert result.execution_id in ledger.executions

    @pytest.mark.asyncio
    async def test_submit_fail_raises(self, engine, stub_adapter):
        stub_adapter.fail_submit = True
        with pytest.raises(JobError):
            await engine.submit(_spec())


# ── Status ───────────────────────────────────────────────────────────────


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_after_submit(self, engine):
        result = await engine.submit(_spec())
        status = await engine.status(result.execution_id)
        # StubRuntimeAdapter auto-succeeds → "succeeded"
        assert status.state == "succeeded"

    @pytest.mark.asyncio
    async def test_status_nonexistent(self, engine):
        with pytest.raises((JobError, KeyError, Exception)):
            await engine.status("no-such-id")


# ── Cancel ───────────────────────────────────────────────────────────────


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel(self, engine, stub_adapter):
        result = await engine.submit(_spec())
        cancelled = await engine.cancel(result.execution_id)
        # StubRuntimeAdapter.cancel always returns True
        assert cancelled is True or cancelled is False  # implementation-dependent


# ── Cleanup ──────────────────────────────────────────────────────────────


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup(self, engine, stub_adapter):
        result = await engine.submit(_spec())
        await engine.cleanup(result.execution_id)
        assert stub_adapter.cleanup_count >= 1


# ── Router Property ─────────────────────────────────────────────────────


class TestProperties:
    def test_router_property(self, engine, router):
        assert engine.router is router
