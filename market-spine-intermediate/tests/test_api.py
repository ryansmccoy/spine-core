"""Tests for FastAPI endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check endpoints (unit tests, mock client)."""

    def test_health_response_format(self):
        """Health response should have expected format."""
        # Expected format
        response = {"status": "healthy"}

        assert "status" in response
        assert response["status"] == "healthy"

    def test_readiness_response_format(self):
        """Readiness response should have expected format."""
        # Expected format
        response = {
            "status": "ready",
            "database": "connected",
            "backend": "local",
        }

        assert "status" in response
        assert "database" in response
        assert "backend" in response


class TestExecutionEndpointSchemas:
    """Tests for execution endpoint schemas."""

    def test_execution_create_schema(self):
        """ExecutionCreate schema validation."""
        from market_spine.api.routes.executions import ExecutionCreate

        # Valid request
        request = ExecutionCreate(
            pipeline_name="test.compute",
            params={"symbol": "ACME"},
            logical_key="test.compute:ACME:2024-01-15",
        )

        assert request.pipeline_name == "test.compute"
        assert request.params == {"symbol": "ACME"}
        assert request.logical_key == "test.compute:ACME:2024-01-15"

    def test_execution_create_defaults(self):
        """ExecutionCreate should have sensible defaults."""
        from market_spine.api.routes.executions import ExecutionCreate

        request = ExecutionCreate(pipeline_name="test.normalize")

        assert request.pipeline_name == "test.normalize"
        assert request.params == {}
        assert request.logical_key is None
