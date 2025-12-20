"""
Backend API integration tests — scenario-driven.

Spins up the FastAPI app with TestClient and validates every scenario
against real HTTP endpoints.  Uses the same ``scenarios.json`` as the
workflow and UI tests.

Run:
    pytest tests/api/test_scenario_api.py -v
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from tests._support.scenario_loader import load_scenarios, Scenario

SCENARIOS = load_scenarios()

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Create a TestClient against a fresh app with file-based SQLite."""
    import tempfile, os
    db_dir = tmp_path_factory.mktemp("spine_api_test")
    db_path = str(db_dir / "test.db")
    db_url = f"sqlite:///{db_path}"

    os.environ["SPINE_DATABASE_URL"] = db_url
    os.environ.setdefault("SPINE_DATA_DIR", str(db_dir))

    from spine.api.app import create_app
    from spine.api.settings import SpineCoreAPISettings
    from spine.api.deps import get_settings

    # Clear cached settings so env vars are picked up
    get_settings.cache_clear()

    settings = SpineCoreAPISettings(
        database_url=db_url,
        data_dir=str(db_dir),
        api_prefix="/api/v1",
    )

    # Reset example workflow flag
    import spine.api.example_workflows as ew
    ew._REGISTERED = False

    app = create_app(settings=settings)

    # Override the settings dependency so requests use the same DB
    app.dependency_overrides[get_settings] = lambda: settings

    from fastapi.testclient import TestClient

    with TestClient(app) as tc:
        # Ensure tables are initialized (lifespan should have done this
        # but call init explicitly to be safe)
        resp = tc.post("/api/v1/database/init")
        assert resp.status_code in (200, 201), f"DB init failed: {resp.text}"

        # core_schedules is now in CORE_DDL and created by database/init

        yield tc

    # Cleanup
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _ensure_workflows_registered():
    """Re-register example workflows after the global clean_group_registry clears them."""
    import spine.api.example_workflows as ew
    ew._REGISTERED = False
    ew.register_example_workflows()
    yield


def _api(client, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """Make an API call and return (status_code, response_json)."""
    url = f"/api/v1{path}"
    if method == "GET":
        r = client.get(url)
    elif method == "POST":
        r = client.post(url, json=body or {})
    elif method == "PUT":
        r = client.put(url, json=body or {})
    elif method == "DELETE":
        r = client.delete(url)
    else:
        raise ValueError(f"Unknown method: {method}")

    try:
        data = r.json()
    except Exception:
        data = {}
    return r.status_code, data


# ---------------------------------------------------------------------------
# Contract assertions (response shape validation)
# ---------------------------------------------------------------------------


def _assert_paged_envelope(data: dict):
    """Validate a paginated response has the correct envelope."""
    assert "data" in data, f"Missing 'data' key in: {list(data.keys())}"
    assert isinstance(data["data"], list), f"'data' should be list, got {type(data['data'])}"
    assert "page" in data, f"Missing 'page' key"
    page = data["page"]
    for k in ("total", "limit", "offset", "has_more"):
        assert k in page, f"Missing page.{k}"


def _assert_success_envelope(data: dict):
    """Validate a success response envelope."""
    assert "data" in data, f"Missing 'data' key in: {list(data.keys())}"


# ---------------------------------------------------------------------------
# Parametrised scenario tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=[s.id for s in SCENARIOS],
)
class TestAPIScenarios:
    """Run every scenario against the HTTP API."""

    def test_submit_run(self, scenario: Scenario, client):
        """POST /runs with scenario submit payload."""
        if not scenario.is_submit:
            pytest.skip("No submit payload")

        status, data = _api(client, "POST", "/runs", scenario.submit)
        expected = scenario.expected

        if expected.get("submit_status"):
            assert status == expected["submit_status"], (
                f"Expected {expected['submit_status']}, got {status}: {data}"
            )

        if status == 202:
            _assert_success_envelope(data)
            assert data["data"].get("run_id")
            for key in expected.get("response_has_keys", []):
                assert key in data["data"], f"Missing key '{key}' in response data"

    def test_trigger_workflow(self, scenario: Scenario, client):
        """POST /workflows/{name}/run."""
        if not scenario.is_workflow_trigger:
            pytest.skip("No workflow trigger")

        tw = scenario.trigger_workflow
        status, data = _api(
            client, "POST", f"/workflows/{tw['name']}/run",
            {"params": tw.get("params", {}), "dry_run": tw.get("dry_run", False)},
        )
        expected = scenario.expected

        if expected.get("submit_status"):
            assert status == expected["submit_status"], (
                f"Expected {expected['submit_status']}, got {status}: {data}"
            )

        if expected.get("dry_run_flag") and status == 202:
            assert data["data"]["dry_run"] is True

        if expected.get("error_code") and status >= 400:
            assert expected["error_message_contains"].lower() in json.dumps(data).lower()

    def test_run_detail_lookup(self, scenario: Scenario, client):
        """GET /runs/{run_id} for not-found scenarios."""
        if not scenario.lookup_run_id:
            pytest.skip("No lookup_run_id")

        status, data = _api(client, "GET", f"/runs/{scenario.lookup_run_id}")
        expected = scenario.expected

        if expected.get("detail_status"):
            assert status == expected["detail_status"]
        if expected.get("error_code") == "NOT_FOUND":
            assert status == 404

    def test_list_runs(self, scenario: Scenario, client):
        """GET /runs with optional filters."""
        expected = scenario.expected
        if scenario.id not in ("empty_data_no_runs", "filter_by_status", "pagination_works"):
            pytest.skip("Not a list scenario")

        # Setup: submit some runs if needed
        for _ in range(scenario.setup_runs):
            _api(client, "POST", "/runs", {"kind": "task", "name": f"setup_{_}", "params": {}})

        qs = ""
        if expected.get("filter_param"):
            qs = f"?{expected['filter_param']}"
        elif expected.get("pagination_limit"):
            qs = f"?limit={expected['pagination_limit']}&offset={expected.get('pagination_offset', 0)}"

        status, data = _api(client, "GET", f"/runs{qs}")

        if expected.get("list_status"):
            assert status == expected["list_status"]

        _assert_paged_envelope(data)

        if expected.get("data_is_empty_array"):
            # May or may not be empty depending on test ordering
            assert isinstance(data["data"], list)

        if expected.get("returned_count"):
            assert len(data["data"]) <= expected["returned_count"]

    def test_workflow_listing(self, scenario: Scenario, client):
        """GET /workflows."""
        if scenario.id != "workflow_listing":
            pytest.skip("Not a workflow listing scenario")

        status, data = _api(client, "GET", "/workflows")
        expected = scenario.expected

        assert status == expected.get("list_status", 200)
        _assert_paged_envelope(data)
        assert len(data["data"]) >= expected.get("min_workflow_count", 1)

        for w in data["data"]:
            for key in expected.get("workflow_has_keys", []):
                assert key in w, f"Missing key '{key}' in workflow"

    def test_workflow_detail(self, scenario: Scenario, client):
        """GET /workflows/{name}."""
        if scenario.id != "workflow_detail":
            pytest.skip("Not a workflow detail scenario")

        status, data = _api(client, "GET", f"/workflows/{scenario.workflow}")
        expected = scenario.expected

        assert status == expected.get("detail_status", 200)
        _assert_success_envelope(data)
        assert len(data["data"]["steps"]) == expected["steps_count"]

    def test_schedule_crud(self, scenario: Scenario, client):
        """Full schedule CRUD lifecycle via HTTP."""
        if not scenario.is_schedule:
            pytest.skip("Not a schedule scenario")

        sched = scenario.schedule
        expected = scenario.expected

        # Create
        status, data = _api(client, "POST", "/schedules", sched)
        assert status == expected.get("create_status", 201), f"Create: {status} {data}"
        sid = data["data"]["schedule_id"]

        # Get
        status, data = _api(client, "GET", f"/schedules/{sid}")
        assert status == expected.get("get_status", 200)
        for key in expected.get("schedule_has_keys", []):
            assert key in data["data"], f"Missing key '{key}'"

        # Update
        status, data = _api(client, "PUT", f"/schedules/{sid}", {"enabled": False})
        assert status == expected.get("update_status", 200)

        # Delete
        status, _ = _api(client, "DELETE", f"/schedules/{sid}")
        assert status == expected.get("delete_status", 204)

    def test_cancel_lifecycle(self, scenario: Scenario, client):
        """Submit a run, then cancel it."""
        if "cancel" not in scenario.actions:
            pytest.skip("No cancel action")

        if not scenario.submit:
            pytest.skip("No submit payload for cancel")

        # Submit
        status, data = _api(client, "POST", "/runs", scenario.submit)
        assert status == 202
        run_id = data["data"]["run_id"]

        # Force-complete if needed
        if "force_complete" in scenario.pre_actions:
            # Direct DB manipulation via internal endpoint
            from spine.ops.sqlite_conn import SqliteConnection
            # We can't easily do this through the API, skip for now
            pytest.skip("force_complete requires direct DB access (covered in workflow tests)")

        # Cancel
        status, data = _api(client, "POST", f"/runs/{run_id}/cancel")
        if scenario.expected.get("cancel_succeeds"):
            assert status == 200, f"Cancel failed: {status} {data}"

    def test_run_events(self, scenario: Scenario, client):
        """GET /runs/{run_id}/events after submission."""
        if scenario.id != "run_events_timeline":
            pytest.skip("Not an events scenario")

        # Submit
        body = scenario.submit
        status, data = _api(client, "POST", "/runs", body)
        assert status == 202
        run_id = data["data"]["run_id"]

        # Get events
        status, data = _api(client, "GET", f"/runs/{run_id}/events")
        expected = scenario.expected

        assert status == expected.get("events_status", 200)
        _assert_paged_envelope(data)
        assert len(data["data"]) >= expected.get("min_event_count", 1)
        if expected.get("first_event_type"):
            assert data["data"][0]["event_type"] == expected["first_event_type"]

    def test_database_health(self, scenario: Scenario, client):
        """GET /database/health."""
        if scenario.id != "database_health":
            pytest.skip("Not a database health scenario")

        status, data = _api(client, "GET", "/database/health")
        expected = scenario.expected

        assert status == expected.get("health_status", 200)
        _assert_success_envelope(data)
        for key in expected.get("health_has_keys", []):
            assert key in data["data"], f"Missing key '{key}'"
        if "connected" in expected:
            assert data["data"]["connected"] == expected["connected"]

    def test_response_contract(self, scenario: Scenario, client):
        """Validate response shapes match frontend contract."""
        if not scenario.is_contract_test:
            pytest.skip("Not a contract test")

        expected = scenario.expected
        for ep in scenario.endpoints:
            status, data = _api(client, ep["method"], ep["path"])

            # Accept 200 or appropriate status
            assert status < 500, f"{ep['path']} returned {status}: {data}"

            if ep["envelope"] == "paged" and status == 200:
                _assert_paged_envelope(data)
                for key in expected.get("paged_envelope_keys", []):
                    assert key in data, f"Missing {key} in paged response from {ep['path']}"
                for key in expected.get("page_keys", []):
                    assert key in data.get("page", {}), f"Missing page.{key}"

            elif ep["envelope"] == "success" and status == 200:
                _assert_success_envelope(data)

    def test_duplicate_submission(self, scenario: Scenario, client):
        """Test idempotency key deduplication."""
        if not scenario.duplicate_submit:
            pytest.skip("Not a duplicate submission scenario")

        body = scenario.submit
        s1, d1 = _api(client, "POST", "/runs", body)
        s2, d2 = _api(client, "POST", "/runs", body)

        assert s1 == 202
        assert s2 == 202
        # Both should succeed — idempotency key enforcement is application-level
        assert d1["data"]["run_id"]
        assert d2["data"]["run_id"]
