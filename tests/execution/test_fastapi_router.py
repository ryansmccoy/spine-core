"""Tests for FastAPI router integration.

Tests cover all /runs endpoints using httpx TestClient:
- GET /runs (list with filters)
- GET /runs/{run_id}
- POST /runs (canonical submit)
- POST /runs/task (convenience)
- POST /runs/operation (convenience)
- POST /runs/{run_id}/cancel
- POST /runs/{run_id}/retry
- GET /runs/{run_id}/events
- GET /runs/{run_id}/children
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

try:
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from spine.execution.runs import RunRecord, RunStatus, RunSummary
from spine.execution.spec import WorkSpec

pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(**kw) -> WorkSpec:
    defaults = dict(kind="task", name="test_handler", params={"x": 1})
    defaults.update(kw)
    return WorkSpec(**defaults)


def _make_run(run_id: str = "run-001", **kw) -> RunRecord:
    defaults = dict(
        run_id=run_id,
        spec=_make_spec(),
        status=RunStatus.COMPLETED,
        created_at=datetime(2026, 1, 15, 12, 0, 0),
        started_at=datetime(2026, 1, 15, 12, 0, 1),
        completed_at=datetime(2026, 1, 15, 12, 0, 5),
        duration_seconds=4.0,
        attempt=1,
        tags={},
    )
    defaults.update(kw)
    return RunRecord(**defaults)


def _make_summary(run_id: str = "run-001", **kw) -> RunSummary:
    defaults = dict(
        run_id=run_id,
        kind="task",
        name="test_handler",
        status=RunStatus.COMPLETED,
        created_at=datetime(2026, 1, 15, 12, 0, 0),
        duration_seconds=4.0,
    )
    defaults.update(kw)
    return RunSummary(**defaults)


@dataclass
class FakeEvent:
    event_id: str = "evt-001"
    run_id: str = "run-001"
    event_type: str = "CREATED"
    timestamp: datetime = field(default_factory=lambda: datetime(2026, 1, 15, 12, 0, 0))
    data: dict = field(default_factory=dict)
    source: str = "dispatcher"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_dispatcher():
    """Create a mock Dispatcher with all async methods."""
    d = AsyncMock()
    d.submit = AsyncMock(return_value="run-001")
    d.submit_task = AsyncMock(return_value="run-001")
    d.submit_operation = AsyncMock(return_value="run-001")
    d.get_run = AsyncMock(return_value=_make_run())
    d.list_runs = AsyncMock(return_value=[_make_summary()])
    d.cancel = AsyncMock(return_value=True)
    d.retry = AsyncMock(return_value="run-002")
    d.get_events = AsyncMock(return_value=[FakeEvent()])
    d.get_children = AsyncMock(return_value=[_make_summary("child-001")])
    return d


@pytest.fixture
def client(mock_dispatcher):
    """Create a test client with the runs router."""
    from spine.execution.fastapi import create_runs_router

    app = FastAPI()
    router = create_runs_router(mock_dispatcher, prefix="/api/v1/runs")
    app.include_router(router)

    # Return a sync-friendly wrapper
    return app, mock_dispatcher


def _run_async(coro):
    """Run async function in event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Tests: List runs
# ---------------------------------------------------------------------------


class TestListRuns:
    def test_list_runs_default(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["run_id"] == "run-001"

        _run_async(_test())

    def test_list_runs_with_kind_filter(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs?kind=operation")
            assert resp.status_code == 200
            dispatcher.list_runs.assert_called_once()
            call_kw = dispatcher.list_runs.call_args[1]
            assert call_kw["kind"] == "operation"

        _run_async(_test())

    def test_list_runs_with_status_filter(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs?status=completed")
            assert resp.status_code == 200

        _run_async(_test())

    def test_list_runs_invalid_status(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs?status=bogus")
            assert resp.status_code == 400

        _run_async(_test())


# ---------------------------------------------------------------------------
# Tests: Get run
# ---------------------------------------------------------------------------


class TestGetRun:
    def test_get_run_found(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs/run-001")
            assert resp.status_code == 200
            data = resp.json()
            assert data["run_id"] == "run-001"
            assert data["status"] == "completed"
            assert data["name"] == "test_handler"

        _run_async(_test())

    def test_get_run_not_found(self, client):
        app, dispatcher = client
        dispatcher.get_run = AsyncMock(return_value=None)

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs/nonexistent")
            assert resp.status_code == 404

        _run_async(_test())


# ---------------------------------------------------------------------------
# Tests: Submit
# ---------------------------------------------------------------------------


class TestSubmitRun:
    def test_submit_canonical(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    "/api/v1/runs",
                    json={
                        "kind": "task",
                        "name": "send_email",
                        "params": {"to": "user@test.com"},
                        "priority": "high",
                    },
                )
            assert resp.status_code == 200
            dispatcher.submit.assert_called_once()
            data = resp.json()
            assert data["run_id"] == "run-001"

        _run_async(_test())

    def test_submit_task_convenience(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    "/api/v1/runs/task",
                    json={"name": "process_file", "params": {"path": "/data/file.csv"}},
                )
            assert resp.status_code == 200
            dispatcher.submit_task.assert_called_once()

        _run_async(_test())

    def test_submit_operation_convenience(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post(
                    "/api/v1/runs/operation",
                    json={"name": "ingest_otc", "params": {"date": "2026-01-15"}},
                )
            assert resp.status_code == 200
            dispatcher.submit_operation.assert_called_once()

        _run_async(_test())


# ---------------------------------------------------------------------------
# Tests: Cancel
# ---------------------------------------------------------------------------


class TestCancelRun:
    def test_cancel_success(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post("/api/v1/runs/run-001/cancel")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "cancelled"

        _run_async(_test())

    def test_cancel_failure_not_found(self, client):
        app, dispatcher = client
        dispatcher.cancel = AsyncMock(return_value=False)
        dispatcher.get_run = AsyncMock(return_value=None)

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post("/api/v1/runs/nonexistent/cancel")
            assert resp.status_code == 404

        _run_async(_test())

    def test_cancel_failure_wrong_status(self, client):
        app, dispatcher = client
        dispatcher.cancel = AsyncMock(return_value=False)

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post("/api/v1/runs/run-001/cancel")
            assert resp.status_code == 400

        _run_async(_test())


# ---------------------------------------------------------------------------
# Tests: Retry
# ---------------------------------------------------------------------------


class TestRetryRun:
    def test_retry_success(self, client):
        app, dispatcher = client
        # retry returns new run_id, get_run returns new record
        dispatcher.retry = AsyncMock(return_value="run-002")
        new_run = _make_run("run-002", status=RunStatus.PENDING, attempt=2)
        dispatcher.get_run = AsyncMock(return_value=new_run)

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post("/api/v1/runs/run-001/retry")
            assert resp.status_code == 200
            data = resp.json()
            assert data["run_id"] == "run-002"

        _run_async(_test())

    def test_retry_not_found(self, client):
        app, dispatcher = client
        dispatcher.retry = AsyncMock(side_effect=ValueError("Run not found"))

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.post("/api/v1/runs/nonexistent/retry")
            assert resp.status_code == 404

        _run_async(_test())


# ---------------------------------------------------------------------------
# Tests: Events
# ---------------------------------------------------------------------------


class TestRunEvents:
    def test_get_events(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs/run-001/events")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["event_id"] == "evt-001"

        _run_async(_test())

    def test_get_events_not_found(self, client):
        app, dispatcher = client
        dispatcher.get_run = AsyncMock(return_value=None)

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs/nonexistent/events")
            assert resp.status_code == 404

        _run_async(_test())


# ---------------------------------------------------------------------------
# Tests: Children
# ---------------------------------------------------------------------------


class TestRunChildren:
    def test_get_children(self, client):
        app, dispatcher = client

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs/run-001/children")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["run_id"] == "child-001"

        _run_async(_test())

    def test_get_children_not_found(self, client):
        app, dispatcher = client
        dispatcher.get_run = AsyncMock(return_value=None)

        async def _test():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/v1/runs/nonexistent/children")
            assert resp.status_code == 404

        _run_async(_test())


# ---------------------------------------------------------------------------
# Tests: Router factory
# ---------------------------------------------------------------------------


class TestRouterFactory:
    def test_create_runs_router_returns_router(self, mock_dispatcher):
        from spine.execution.fastapi import create_runs_router

        router = create_runs_router(mock_dispatcher)
        assert router is not None
        assert router.prefix == "/api/v1/runs"

    def test_create_runs_router_custom_prefix(self, mock_dispatcher):
        from spine.execution.fastapi import create_runs_router

        router = create_runs_router(mock_dispatcher, prefix="/v2/runs")
        assert router.prefix == "/v2/runs"

    def test_create_runs_router_custom_tags(self, mock_dispatcher):
        from spine.execution.fastapi import create_runs_router

        router = create_runs_router(mock_dispatcher, tags=["execution"])
        assert "execution" in router.tags


class TestPydanticModels:
    def test_work_spec_request_to_spec(self):
        from spine.execution.fastapi import WorkSpecRequest

        req = WorkSpecRequest(
            kind="task",
            name="test",
            params={"a": 1},
            priority="high",
            lane="gpu",
        )
        spec = req.to_spec()
        assert isinstance(spec, WorkSpec)
        assert spec.kind == "task"
        assert spec.name == "test"
        assert spec.priority == "high"
        assert spec.lane == "gpu"

    def test_run_response_from_record(self):
        from spine.execution.fastapi import RunResponse

        record = _make_run()
        resp = RunResponse.from_record(record)
        assert resp.run_id == "run-001"
        assert resp.status == "completed"

    def test_run_summary_response_from_summary(self):
        from spine.execution.fastapi import RunSummaryResponse

        summary = _make_summary()
        resp = RunSummaryResponse.from_summary(summary)
        assert resp.run_id == "run-001"
        assert resp.status == "completed"
