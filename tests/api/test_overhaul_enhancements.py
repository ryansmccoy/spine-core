"""
Backend API tests for the frontend overhaul enhancements.

Tests:
  - WorkflowDetailSchema extended fields (domain, version, policy, tags, defaults)
  - ExecutionPolicySchema serialization
  - core_schedules table creation via database/init (now in CORE_DDL)
  - WorkflowStepSchema extended fields (operation, depends_on, params)
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """TestClient with fresh SQLite database."""
    db_dir = tmp_path_factory.mktemp("overhaul")
    db_path = str(db_dir / "test.db")
    db_url = f"sqlite:///{db_path}"

    os.environ["SPINE_DATABASE_URL"] = db_url
    os.environ.setdefault("SPINE_DATA_DIR", str(db_dir))

    from spine.api.app import create_app
    from spine.api.settings import SpineCoreAPISettings
    from spine.api.deps import get_settings

    get_settings.cache_clear()

    settings = SpineCoreAPISettings(
        database_url=db_url,
        data_dir=str(db_dir),
        api_prefix="/api/v1",
    )

    import spine.api.example_workflows as ew
    ew._REGISTERED = False

    app = create_app(settings=settings)
    app.dependency_overrides[get_settings] = lambda: settings

    from fastapi.testclient import TestClient

    with TestClient(app) as tc:
        resp = tc.post("/api/v1/database/init")
        assert resp.status_code in (200, 201), f"DB init failed: {resp.text}"
        yield tc

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _ensure_workflows_registered():
    """Ensure example workflows are registered before each test."""
    import spine.api.example_workflows as ew
    ew._REGISTERED = False
    ew.register_example_workflows()
    yield


class TestWorkflowDetailSchema:
    """Verify GET /workflows/{name} returns extended fields."""

    def test_workflow_detail_has_domain(self, client):
        resp = client.get("/api/v1/workflows/etl.daily_ingest")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "domain" in data
        assert data["domain"] == "core"

    def test_workflow_detail_has_version(self, client):
        resp = client.get("/api/v1/workflows/etl.daily_ingest")
        data = resp.json()["data"]
        assert "version" in data
        assert isinstance(data["version"], int)

    def test_workflow_detail_has_policy(self, client):
        resp = client.get("/api/v1/workflows/etl.daily_ingest")
        data = resp.json()["data"]
        assert "policy" in data
        policy = data["policy"]
        assert "mode" in policy
        assert "max_concurrency" in policy
        assert "on_failure" in policy
        assert "timeout_minutes" in policy
        assert policy["mode"] in ("sequential", "parallel", "adaptive")

    def test_workflow_detail_has_tags(self, client):
        resp = client.get("/api/v1/workflows/etl.daily_ingest")
        data = resp.json()["data"]
        assert "tags" in data
        assert isinstance(data["tags"], list)

    def test_workflow_detail_has_defaults(self, client):
        resp = client.get("/api/v1/workflows/etl.daily_ingest")
        data = resp.json()["data"]
        assert "defaults" in data
        assert isinstance(data["defaults"], dict)

    def test_workflow_steps_have_operation(self, client):
        resp = client.get("/api/v1/workflows/etl.daily_ingest")
        data = resp.json()["data"]
        steps = data["steps"]
        assert len(steps) > 0
        for step in steps:
            assert "operation" in step
            assert isinstance(step["operation"], str)

    def test_workflow_steps_have_depends_on(self, client):
        resp = client.get("/api/v1/workflows/etl.daily_ingest")
        data = resp.json()["data"]
        for step in data["steps"]:
            assert "depends_on" in step
            assert isinstance(step["depends_on"], list)

    def test_workflow_steps_have_params(self, client):
        resp = client.get("/api/v1/workflows/etl.daily_ingest")
        data = resp.json()["data"]
        for step in data["steps"]:
            assert "params" in step
            assert isinstance(step["params"], dict)


class TestCoreSchedulesDDL:
    """Verify core_schedules is created by database/init (now in CORE_DDL)."""

    def test_schedules_table_exists_after_init(self, client):
        """database/init should create core_schedules table."""
        resp = client.get("/api/v1/database/tables")
        assert resp.status_code == 200
        tables = resp.json()["data"]
        table_names = [t["table"] for t in tables]
        assert "core_schedules" in table_names

    def test_schedule_crud_works(self, client):
        """Create, read, delete a schedule using the API."""
        # Create
        resp = client.post("/api/v1/schedules", json={
            "name": "etl.daily_ingest",
            "target_type": "workflow",
            "target_name": "etl.daily_ingest",
            "cron_expression": "0 * * * *",
        })
        assert resp.status_code in (200, 201), f"Create failed: {resp.json()}"
        schedule = resp.json()["data"]
        schedule_id = schedule["schedule_id"]

        # Read
        resp = client.get("/api/v1/schedules")
        assert resp.status_code == 200
        schedules = resp.json()["data"]
        assert any(s["schedule_id"] == schedule_id for s in schedules)

        # Delete
        resp = client.delete(f"/api/v1/schedules/{schedule_id}")
        assert resp.status_code in (200, 204)

    def test_core_ddl_includes_schedules(self):
        """CORE_DDL dict should contain 'schedules' key."""
        from spine.core.schema import CORE_DDL, CORE_TABLES
        assert "schedules" in CORE_DDL
        assert "schedules" in CORE_TABLES
        assert CORE_TABLES["schedules"] == "core_schedules"

    def test_created_at_has_default(self):
        """core_schedules DDL should have DEFAULT for created_at."""
        from spine.core.schema import CORE_DDL
        ddl = CORE_DDL["schedules"]
        assert "DEFAULT" in ddl
        assert "datetime('now')" in ddl
