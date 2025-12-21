"""Tests for spine.api.routers.playground — schemas, sessions & endpoints.

Strategy: Pydantic schema unit tests + properly-mocked endpoint tests.
The router functions call ``session.playground.summary()`` (returns dict),
``session.playground.step()`` (returns StepSnapshot dataclass), etc.
Mocks must provide correctly-typed return values to pass Pydantic validation.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from spine.api.routers.playground import (
    ContextSnapshot,
    CreateSessionRequest,
    PlaygroundExample,
    PlaygroundWorkflow,
    RunToRequest,
    SessionSummary,
    SetParamsRequest,
    StepPreview,
    StepSnapshotSchema,
    _PlaygroundSession,
    _get_session,
    _sessions,
    router,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _summary_dict(**overrides) -> dict:
    """Return a valid summary dict like WorkflowPlayground.summary()."""
    base = {"total_steps": 4, "executed": 0, "remaining": 4, "is_complete": False}
    base.update(overrides)
    return base


def _mock_session(sid: str = "s-1", wf: str = "etl") -> MagicMock:
    """Build a mock _PlaygroundSession with valid .playground.summary()."""
    s = MagicMock()
    s.session_id = sid
    s.workflow_name = wf
    s.created_at = 1_000_000.0
    s.last_accessed = 1_000_001.0
    s.is_expired = False
    s.playground.summary.return_value = _summary_dict()
    return s


def _mock_snapshot(**overrides) -> SimpleNamespace:
    """Return a StepSnapshot-like object for _snapshot_to_schema."""
    base = dict(
        step_name="extract",
        step_type=SimpleNamespace(value="operation"),
        status="completed",
        result=None,
        context_before={},
        context_after={"rows": 10},
        duration_ms=3.5,
        error=None,
        step_index=0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _mock_step_obj(**overrides) -> SimpleNamespace:
    """Return a step-like object for ``playground.peek()``."""
    base = dict(
        name="transform",
        step_type=SimpleNamespace(value="operation"),
        operation_name=None,
        depends_on=[],
        config={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def _clear_sessions():
    _sessions.clear()
    yield
    _sessions.clear()


# ── Pydantic Schema Tests ───────────────────────────────────────────────

class TestSessionSummarySchema:
    def test_valid(self):
        s = SessionSummary(
            session_id="a", workflow_name="etl", total_steps=4,
            executed=2, remaining=2, is_complete=False,
            created_at=1.0, last_accessed=2.0,
        )
        assert s.remaining == 2

    def test_complete(self):
        s = SessionSummary(
            session_id="b", workflow_name="etl", total_steps=3,
            executed=3, remaining=0, is_complete=True,
            created_at=1.0, last_accessed=2.0,
        )
        assert s.is_complete is True


class TestStepSnapshotSchemaModel:
    def test_minimal(self):
        s = StepSnapshotSchema(
            step_name="x", step_type="operation", status="completed", duration_ms=1.0,
        )
        assert s.result is None
        assert s.step_index == 0

    def test_with_result(self):
        s = StepSnapshotSchema(
            step_name="x", step_type="operation", status="completed",
            result={"success": True, "output": {}, "error": None}, duration_ms=1.0,
        )
        assert s.result["success"] is True


class TestStepPreviewSchema:
    def test_defaults(self):
        sp = StepPreview(name="t", step_type="operation")
        assert sp.depends_on == []
        assert sp.config == {}


class TestContextSnapshotSchema:
    def test_valid(self):
        cs = ContextSnapshot(run_id="r1", workflow_name="w", params={"a": 1}, outputs={})
        assert cs.params == {"a": 1}


class TestPlaygroundWorkflowSchema:
    def test_valid(self):
        pw = PlaygroundWorkflow(name="etl", description="d", step_count=4, domain="core")
        assert pw.steps == []


class TestPlaygroundExampleSchema:
    def test_defaults(self):
        pe = PlaygroundExample(id="e1", title="T", description="D", workflow_name="w")
        assert pe.category == "general"


class TestRequestSchemas:
    def test_create_session(self):
        r = CreateSessionRequest(workflow_name="w")
        assert r.params == {}

    def test_set_params(self):
        r = SetParamsRequest(params={"x": 1})
        assert r.params["x"] == 1

    def test_run_to(self):
        r = RunToRequest(step_name="load")
        assert r.step_name == "load"


# ── Endpoint Tests (with properly-typed mocks) ──────────────────────────

class TestListSessions:
    def test_empty(self):
        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/sessions")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestCreateSession:
    @patch("spine.api.routers.playground._PlaygroundSession")
    def test_create_success(self, MockCls):
        MockCls.return_value = _mock_session()
        client = TestClient(_make_app())
        resp = client.post("/api/v1/playground/sessions", json={"workflow_name": "etl"})
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert body["data"]["workflow_name"] == "etl"

    def test_create_unknown_workflow(self):
        with patch("spine.orchestration.workflow_registry.get_workflow", return_value=None):
            client = TestClient(_make_app())
            resp = client.post("/api/v1/playground/sessions", json={"workflow_name": "nope"})
            assert resp.status_code in (400, 404, 422, 500)


class TestGetSession:
    def test_not_found(self):
        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/sessions/missing")
        assert resp.status_code == 404

    @patch("spine.api.routers.playground._get_session")
    def test_found(self, mock_get):
        mock_get.return_value = _mock_session("s-1", "etl")
        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/sessions/s-1")
        assert resp.status_code == 200
        assert resp.json()["data"]["session_id"] == "s-1"


class TestDeleteSession:
    def test_not_found(self):
        client = TestClient(_make_app())
        resp = client.delete("/api/v1/playground/sessions/missing")
        assert resp.status_code == 404


class TestSessionStep:
    @patch("spine.api.routers.playground._get_session")
    def test_step_forward(self, mock_get):
        mock_s = _mock_session()
        mock_s.playground.step.return_value = _mock_snapshot()
        mock_get.return_value = mock_s

        client = TestClient(_make_app())
        resp = client.post("/api/v1/playground/sessions/s-1/step")
        assert resp.status_code == 200
        assert resp.json()["data"]["step_name"] == "extract"


class TestSessionPeek:
    @patch("spine.api.routers.playground._get_session")
    def test_peek_returns_preview(self, mock_get):
        mock_s = _mock_session()
        mock_s.playground.peek.return_value = _mock_step_obj()
        mock_get.return_value = mock_s

        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/sessions/s-1/peek")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "transform"

    @patch("spine.api.routers.playground._get_session")
    def test_peek_none(self, mock_get):
        mock_s = _mock_session()
        mock_s.playground.peek.return_value = None
        mock_get.return_value = mock_s

        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/sessions/s-1/peek")
        assert resp.status_code == 200
        assert resp.json()["data"] is None


class TestSessionContext:
    @patch("spine.api.routers.playground._get_session")
    def test_context(self, mock_get):
        mock_s = _mock_session()
        mock_s.playground.context = SimpleNamespace(
            run_id="r1", workflow_name="etl", params={"a": 1}, outputs={"b": 2},
        )
        mock_get.return_value = mock_s

        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/sessions/s-1/context")
        assert resp.status_code == 200
        assert resp.json()["data"]["run_id"] == "r1"


class TestSessionHistory:
    @patch("spine.api.routers.playground._get_session")
    def test_empty_history(self, mock_get):
        mock_s = _mock_session()
        mock_s.playground.history = []
        mock_get.return_value = mock_s

        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/sessions/s-1/history")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @patch("spine.api.routers.playground._get_session")
    def test_history_with_entries(self, mock_get):
        mock_s = _mock_session()
        mock_s.playground.history = [_mock_snapshot(), _mock_snapshot(step_name="load", step_index=1)]
        mock_get.return_value = mock_s

        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/sessions/s-1/history")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2


class TestSessionReset:
    @patch("spine.api.routers.playground._get_session")
    def test_reset(self, mock_get):
        mock_s = _mock_session()
        mock_get.return_value = mock_s

        client = TestClient(_make_app())
        resp = client.post("/api/v1/playground/sessions/s-1/reset")
        assert resp.status_code == 200
        mock_s.playground.reset.assert_called_once()


class TestSessionRunAll:
    @patch("spine.api.routers.playground._get_session")
    def test_run_all(self, mock_get):
        mock_s = _mock_session()
        mock_s.playground.run_all.return_value = [_mock_snapshot(), _mock_snapshot(step_name="load")]
        mock_get.return_value = mock_s

        client = TestClient(_make_app())
        resp = client.post("/api/v1/playground/sessions/s-1/run-all")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2


class TestListPlaygroundWorkflows:
    @patch("spine.orchestration.workflow_registry.get_workflow")
    @patch("spine.orchestration.workflow_registry.list_workflows")
    def test_list(self, mock_list, mock_get):
        mock_step = SimpleNamespace(
            name="extract", step_type=SimpleNamespace(value="operation"),
            operation_name=None, depends_on=[],
        )
        mock_wf = SimpleNamespace(
            name="daily_etl", description="Daily ingest", steps=[mock_step],
            domain="core", tags=["etl"],
        )
        mock_list.return_value = ["daily_etl"]
        mock_get.return_value = mock_wf

        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/workflows")
        assert resp.status_code == 200
        assert resp.json()["data"][0]["name"] == "daily_etl"


class TestExamples:
    def test_list_examples(self):
        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/examples")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

    def test_filter_by_category(self):
        client = TestClient(_make_app())
        resp = client.get("/api/v1/playground/examples?category=quality")
        assert resp.status_code == 200


# ── _PlaygroundSession unit tests ────────────────────────────────────────

class TestPlaygroundSessionClass:
    def test_is_expired_false_initially(self):
        with patch("spine.orchestration.workflow_registry.get_workflow") as mock_wf, \
             patch("spine.orchestration.playground.WorkflowPlayground"):
            mock_wf.return_value = MagicMock()
            session = _PlaygroundSession("s-1", "test", {})
            assert session.is_expired is False

    def test_touch_resets_timeout(self):
        with patch("spine.orchestration.workflow_registry.get_workflow") as mock_wf, \
             patch("spine.orchestration.playground.WorkflowPlayground"):
            mock_wf.return_value = MagicMock()
            session = _PlaygroundSession("s-1", "test", {})
            old = session.last_accessed
            time.sleep(0.01)
            session.touch()
            assert session.last_accessed >= old

    def test_workflow_not_found_raises(self):
        with patch("spine.orchestration.workflow_registry.get_workflow", return_value=None):
            with pytest.raises(ValueError, match="not found"):
                _PlaygroundSession("s-1", "missing", {})


class TestGetSessionHelper:
    def test_missing_raises_404(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _get_session("nonexistent")
        assert exc_info.value.status_code == 404
