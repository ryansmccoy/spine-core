"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def api_client():
    """Create test API client.

    This uses module scope to avoid pool open/close issues between tests.
    The API creates its own pool connection internally.
    """
    from market_spine.api.main import app

    with TestClient(app) as client:
        yield client


class TestHealthEndpoints:
    """Tests for health endpoints."""

    def test_liveness(self, api_client):
        """Test liveness endpoint."""
        response = api_client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_readiness(self, api_client):
        """Test readiness endpoint."""
        response = api_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ok", "degraded"]
        assert "database" in data

    def test_health_metrics(self, api_client):
        """Test health metrics endpoint."""
        response = api_client.get("/health/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "execution_stats" in data
        assert "dead_letter_count" in data


class TestExecutionEndpoints:
    """Tests for execution endpoints."""

    def test_list_pipelines(self, api_client):
        """Test listing available pipelines."""
        response = api_client.get("/executions/pipelines")
        assert response.status_code == 200
        data = response.json()
        # May be empty until domains are registered
        assert isinstance(data, list)

    def test_submit_execution(self, api_client):
        """Test submitting an execution."""
        response = api_client.post(
            "/executions",
            json={
                "pipeline": "test_pipeline",
                "params": {"source": "synthetic", "count": 10},
            },
        )
        # May fail if Celery isn't running, but should at least validate
        assert response.status_code in [201, 500]

    def test_submit_unknown_pipeline(self, api_client):
        """Test submitting unknown pipeline."""
        response = api_client.post(
            "/executions",
            json={"pipeline": "unknown_pipeline"},
        )
        assert response.status_code == 400
        assert "Unknown pipeline" in response.json()["detail"]

    def test_list_executions(self, api_client):
        """Test listing executions."""
        response = api_client.get("/executions")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_nonexistent_execution(self, api_client):
        """Test getting nonexistent execution."""
        response = api_client.get("/executions/nonexistent-id")
        assert response.status_code == 404


class TestDLQEndpoints:
    """Tests for dead letter queue endpoints."""

    def test_list_dead_letters_empty(self, api_client):
        """Test listing dead letters when empty."""
        response = api_client.get("/dead-letters")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_nonexistent_dead_letter(self, api_client):
        """Test getting nonexistent dead letter."""
        response = api_client.get("/dead-letters/nonexistent-id")
        assert response.status_code == 404
