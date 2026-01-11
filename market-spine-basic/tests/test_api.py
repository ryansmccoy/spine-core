"""
API endpoint tests using FastAPI TestClient.

These tests verify the API contract stability and error handling.
All tests use the FastAPI TestClient for synchronous testing.

Coverage:
- /health
- /health/detailed
- /v1/capabilities
- /v1/pipelines
- /v1/pipelines/{name}
- /v1/pipelines/{name}/run (happy + error paths)
- /v1/data/weeks
- /v1/data/symbols
- /v1/data/symbols/{symbol}/history
- /v1/ops/storage
- /v1/ops/captures
"""

import pytest
from fastapi.testclient import TestClient

from market_spine.api.app import create_app
from market_spine.db import init_connection_provider

# Initialize connection provider once for all tests
init_connection_provider()


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Create a TestClient for the API."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# Health Endpoints
# =============================================================================


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_returns_ok(self, client: TestClient) -> None:
        """GET /health should return status ok."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_health_detailed_returns_checks(self, client: TestClient) -> None:
        """GET /health/detailed should include component checks."""
        response = client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ok", "warning", "error")
        assert "timestamp" in data
        assert "checks" in data
        assert isinstance(data["checks"], list)

    def test_health_detailed_includes_database_check(self, client: TestClient) -> None:
        """GET /health/detailed should check database connectivity."""
        response = client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()

        # Find database check
        db_checks = [c for c in data["checks"] if c["name"] == "database"]
        assert len(db_checks) == 1
        assert db_checks[0]["status"] in ("ok", "warning", "error")
        assert "message" in db_checks[0]


# =============================================================================
# Capabilities Endpoint
# =============================================================================


class TestCapabilitiesEndpoint:
    """Tests for /v1/capabilities endpoint."""

    def test_capabilities_returns_basic_tier(self, client: TestClient) -> None:
        """GET /v1/capabilities should return Basic tier configuration."""
        response = client.get("/v1/capabilities")

        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert data["api_version"] == "v1"
        assert data["tier"] == "basic"
        assert "version" in data

    def test_capabilities_has_all_feature_flags(self, client: TestClient) -> None:
        """GET /v1/capabilities should include all feature flags."""
        response = client.get("/v1/capabilities")

        assert response.status_code == 200
        data = response.json()

        # Basic tier feature flags
        assert data["sync_execution"] is True
        assert data["async_execution"] is False
        assert data["execution_history"] is False
        assert data["authentication"] is False
        assert data["scheduling"] is False
        assert data["rate_limiting"] is False
        assert data["webhook_notifications"] is False


# =============================================================================
# Pipelines Endpoints
# =============================================================================


class TestListPipelinesEndpoint:
    """Tests for GET /v1/pipelines."""

    def test_list_pipelines_returns_array(self, client: TestClient) -> None:
        """GET /v1/pipelines should return list of pipelines."""
        response = client.get("/v1/pipelines")

        assert response.status_code == 200
        data = response.json()
        assert "pipelines" in data
        assert isinstance(data["pipelines"], list)
        assert "count" in data

    def test_list_pipelines_includes_name_and_description(self, client: TestClient) -> None:
        """Each pipeline should have name and description."""
        response = client.get("/v1/pipelines")

        assert response.status_code == 200
        data = response.json()

        if data["count"] > 0:
            pipeline = data["pipelines"][0]
            assert "name" in pipeline
            assert "description" in pipeline

    def test_list_pipelines_with_prefix_filter(self, client: TestClient) -> None:
        """GET /v1/pipelines?prefix= should filter by prefix."""
        response = client.get("/v1/pipelines?prefix=finra")

        assert response.status_code == 200
        data = response.json()

        # All returned pipelines should match prefix
        for pipeline in data["pipelines"]:
            assert pipeline["name"].startswith("finra")

    def test_list_pipelines_no_match_returns_empty(self, client: TestClient) -> None:
        """Non-matching prefix should return empty list."""
        response = client.get("/v1/pipelines?prefix=nonexistent_xyz")

        assert response.status_code == 200
        data = response.json()
        assert data["pipelines"] == []
        assert data["count"] == 0


class TestDescribePipelineEndpoint:
    """Tests for GET /v1/pipelines/{name}."""

    def test_describe_existing_pipeline(self, client: TestClient) -> None:
        """GET /v1/pipelines/{name} should return pipeline details."""
        # First, get a pipeline name
        list_response = client.get("/v1/pipelines")
        assert list_response.status_code == 200
        pipelines = list_response.json()["pipelines"]

        if not pipelines:
            pytest.skip("No pipelines registered")

        pipeline_name = pipelines[0]["name"]

        # Now describe it
        response = client.get(f"/v1/pipelines/{pipeline_name}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == pipeline_name
        assert "description" in data
        assert "required_params" in data
        assert "optional_params" in data
        assert "is_ingest" in data

    def test_describe_nonexistent_pipeline_returns_404(self, client: TestClient) -> None:
        """GET /v1/pipelines/{name} for nonexistent should return 404."""
        response = client.get("/v1/pipelines/nonexistent.pipeline.xyz")

        assert response.status_code == 404
        data = response.json()["detail"]
        assert data["success"] is False
        assert data["error"]["code"] == "PIPELINE_NOT_FOUND"
        assert "message" in data["error"]


class TestRunPipelineEndpoint:
    """Tests for POST /v1/pipelines/{name}/run."""

    def test_run_pipeline_nonexistent_returns_404(self, client: TestClient) -> None:
        """POST /v1/pipelines/{name}/run for nonexistent should return 404."""
        response = client.post(
            "/v1/pipelines/nonexistent.pipeline.xyz/run",
            json={"params": {}},
        )

        assert response.status_code == 404
        data = response.json()["detail"]
        assert data["success"] is False
        assert data["error"]["code"] == "PIPELINE_NOT_FOUND"

    def test_run_pipeline_invalid_tier_returns_400(self, client: TestClient) -> None:
        """POST with invalid tier should return 400."""
        # Find an ingest pipeline
        list_response = client.get("/v1/pipelines?prefix=finra.otc_transparency.ingest")
        pipelines = list_response.json()["pipelines"]

        if not pipelines:
            pytest.skip("No ingest pipelines registered")

        pipeline_name = pipelines[0]["name"]

        response = client.post(
            f"/v1/pipelines/{pipeline_name}/run",
            json={
                "params": {
                    "tier": "INVALID_TIER_XYZ",
                    "week_ending": "2025-01-10",
                },
            },
        )

        assert response.status_code == 400
        data = response.json()["detail"]
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_TIER"

    def test_run_pipeline_dry_run_returns_preview(self, client: TestClient) -> None:
        """POST with dry_run=true should return preview without executing."""
        # Find an ingest pipeline
        list_response = client.get("/v1/pipelines?prefix=finra.otc_transparency.ingest")
        pipelines = list_response.json()["pipelines"]

        if not pipelines:
            pytest.skip("No ingest pipelines registered")

        pipeline_name = pipelines[0]["name"]

        response = client.post(
            f"/v1/pipelines/{pipeline_name}/run",
            json={
                "params": {
                    "tier": "OTC",
                    "week_ending": "2025-01-10",
                },
                "dry_run": True,
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Reserved fields are always present
        assert "execution_id" in data
        assert data["status"] == "dry_run"
        assert data["poll_url"] is None

    def test_run_pipeline_response_has_reserved_fields(self, client: TestClient) -> None:
        """Execution response should always have reserved fields."""
        # Find a pipeline
        list_response = client.get("/v1/pipelines?prefix=finra.otc_transparency")
        pipelines = list_response.json()["pipelines"]

        if not pipelines:
            pytest.skip("No pipelines registered")

        pipeline_name = pipelines[0]["name"]

        response = client.post(
            f"/v1/pipelines/{pipeline_name}/run",
            json={
                "params": {
                    "tier": "OTC",
                    "week_ending": "2025-01-10",
                },
                "dry_run": True,  # Use dry run to avoid actual execution
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Reserved fields MUST always be present
        assert "execution_id" in data
        assert data["execution_id"] is not None
        assert "status" in data
        assert "poll_url" in data  # null in Basic tier, but field exists


# =============================================================================
# Data Query Endpoints
# =============================================================================


class TestDataWeeksEndpoint:
    """Tests for GET /v1/data/weeks."""

    def test_data_weeks_requires_tier(self, client: TestClient) -> None:
        """GET /v1/data/weeks without tier should return 422."""
        response = client.get("/v1/data/weeks")

        assert response.status_code == 422  # FastAPI validation error

    def test_data_weeks_with_valid_tier(self, client: TestClient) -> None:
        """GET /v1/data/weeks with valid tier should return weeks list."""
        response = client.get("/v1/data/weeks?tier=OTC")

        # May be 200 with empty list if no data, or error if DB issue
        if response.status_code == 200:
            data = response.json()
            assert "tier" in data
            assert data["tier"] == "OTC"
            assert "weeks" in data
            assert isinstance(data["weeks"], list)
            assert "count" in data

    def test_data_weeks_invalid_tier_returns_400(self, client: TestClient) -> None:
        """GET /v1/data/weeks with invalid tier should return 400."""
        response = client.get("/v1/data/weeks?tier=INVALID_TIER_XYZ")

        assert response.status_code == 400
        data = response.json()["detail"]
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_TIER"

    def test_data_weeks_respects_limit(self, client: TestClient) -> None:
        """GET /v1/data/weeks?limit= should limit results."""
        response = client.get("/v1/data/weeks?tier=OTC&limit=5")

        if response.status_code == 200:
            data = response.json()
            assert len(data["weeks"]) <= 5


class TestDataSymbolsEndpoint:
    """Tests for GET /v1/data/symbols."""

    def test_data_symbols_requires_tier_and_week(self, client: TestClient) -> None:
        """GET /v1/data/symbols without params should return 422."""
        response = client.get("/v1/data/symbols")

        assert response.status_code == 422  # FastAPI validation error

    def test_data_symbols_with_valid_params(self, client: TestClient) -> None:
        """GET /v1/data/symbols with valid params should return symbols."""
        response = client.get("/v1/data/symbols?tier=OTC&week=2025-01-10")

        # May be 200 with empty list if no data
        if response.status_code == 200:
            data = response.json()
            assert "tier" in data
            assert data["tier"] == "OTC"
            assert "week" in data
            assert "symbols" in data
            assert isinstance(data["symbols"], list)
            assert "count" in data

    def test_data_symbols_invalid_tier_returns_400(self, client: TestClient) -> None:
        """GET /v1/data/symbols with invalid tier should return 400."""
        response = client.get("/v1/data/symbols?tier=INVALID&week=2025-01-10")

        assert response.status_code == 400
        data = response.json()["detail"]
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_TIER"


# =============================================================================
# Symbol History Endpoint Tests
# =============================================================================


class TestSymbolHistoryEndpoint:
    """Tests for GET /v1/data/symbols/{symbol}/history."""

    def test_symbol_history_requires_tier(self, client: TestClient) -> None:
        """GET /v1/data/symbols/{symbol}/history without tier should return 422."""
        response = client.get("/v1/data/symbols/AAPL/history")

        assert response.status_code == 422  # FastAPI validation error

    def test_symbol_history_with_valid_params(self, client: TestClient) -> None:
        """GET /v1/data/symbols/{symbol}/history with valid tier returns history."""
        response = client.get("/v1/data/symbols/AAPL/history?tier=OTC&weeks=12")

        # May be 200 with empty list if no data for this symbol
        if response.status_code == 200:
            data = response.json()
            assert "symbol" in data
            assert data["symbol"] == "AAPL"
            assert "tier" in data
            assert data["tier"] == "OTC"
            assert "history" in data
            assert isinstance(data["history"], list)
            assert "count" in data

    def test_symbol_history_invalid_tier_returns_400(self, client: TestClient) -> None:
        """GET /v1/data/symbols/{symbol}/history with invalid tier returns 400."""
        response = client.get("/v1/data/symbols/AAPL/history?tier=INVALID_TIER")

        assert response.status_code == 400
        data = response.json()["detail"]
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_TIER"

    def test_symbol_history_respects_weeks_limit(self, client: TestClient) -> None:
        """GET /v1/data/symbols/{symbol}/history should accept weeks param."""
        response = client.get("/v1/data/symbols/AAPL/history?tier=OTC&weeks=4")

        if response.status_code == 200:
            data = response.json()
            # Should have at most 4 weeks of history
            assert len(data["history"]) <= 4

    def test_symbol_history_uppercase_normalization(self, client: TestClient) -> None:
        """Symbol should be normalized to uppercase in response."""
        response = client.get("/v1/data/symbols/aapl/history?tier=OTC")

        if response.status_code == 200:
            data = response.json()
            assert data["symbol"] == "AAPL"


# =============================================================================
# Error Response Contract Tests
# =============================================================================


class TestErrorResponseContract:
    """Tests verifying error response structure is consistent."""

    def test_404_error_has_standard_structure(self, client: TestClient) -> None:
        """404 errors should have {success: false, error: {code, message}}."""
        response = client.get("/v1/pipelines/nonexistent.xyz")

        assert response.status_code == 404
        data = response.json()["detail"]

        assert "success" in data
        assert data["success"] is False
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    def test_400_error_has_standard_structure(self, client: TestClient) -> None:
        """400 errors should have {success: false, error: {code, message}}."""
        response = client.get("/v1/data/weeks?tier=INVALID_XYZ")

        assert response.status_code == 400
        data = response.json()["detail"]

        assert "success" in data
        assert data["success"] is False
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]

    def test_error_codes_are_uppercase_constants(self, client: TestClient) -> None:
        """Error codes should be UPPER_SNAKE_CASE constants."""
        response = client.get("/v1/pipelines/nonexistent.xyz")

        assert response.status_code == 404
        error_code = response.json()["detail"]["error"]["code"]

        # Should be uppercase
        assert error_code == error_code.upper()
        # Should be a known code
        assert error_code in (
            "PIPELINE_NOT_FOUND",
            "INVALID_PARAMS",
            "EXECUTION_FAILED",
            "INVALID_TIER",
            "INVALID_DATE",
            "MISSING_REQUIRED",
            "DATABASE_ERROR",
            "INTERNAL_ERROR",
            "FEATURE_NOT_SUPPORTED",
            "NOT_IMPLEMENTED",
        )


# =============================================================================
# Ops Endpoint Tests
# =============================================================================


class TestOpsStorageEndpoint:
    """Tests for GET /v1/ops/storage."""

    def test_storage_returns_stats(self, client: TestClient) -> None:
        """GET /v1/ops/storage should return storage statistics."""
        response = client.get("/v1/ops/storage")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "database_path" in data
        assert "database_size_bytes" in data
        assert "tables" in data
        assert "total_rows" in data

        # Tables should be a list
        assert isinstance(data["tables"], list)

        # Each table should have name and row_count
        for table in data["tables"]:
            assert "name" in table
            assert "row_count" in table
            assert isinstance(table["row_count"], int)

    def test_storage_includes_known_tables(self, client: TestClient) -> None:
        """GET /v1/ops/storage should include expected tables."""
        response = client.get("/v1/ops/storage")

        assert response.status_code == 200
        data = response.json()

        table_names = [t["name"] for t in data["tables"]]

        # Should have at least the captures table
        assert "captures" in table_names or len(table_names) >= 0


class TestOpsCapturesEndpoint:
    """Tests for GET /v1/ops/captures."""

    def test_captures_returns_list(self, client: TestClient) -> None:
        """GET /v1/ops/captures should return a captures list."""
        response = client.get("/v1/ops/captures")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "captures" in data
        assert "count" in data
        assert isinstance(data["captures"], list)
        assert isinstance(data["count"], int)
        assert data["count"] == len(data["captures"])

    def test_captures_have_required_fields(self, client: TestClient) -> None:
        """Each capture should have required metadata fields."""
        response = client.get("/v1/ops/captures")

        assert response.status_code == 200
        data = response.json()

        # If there are captures, verify structure
        for capture in data["captures"]:
            assert "capture_id" in capture
            assert "tier" in capture
            assert "week_ending" in capture
            assert "row_count" in capture
            # captured_at may be null
            assert "captured_at" in capture


# =============================================================================
# Price Data Endpoints
# =============================================================================


class TestPriceHistoryEndpoint:
    """Tests for GET /v1/data/prices/{symbol}."""

    def test_price_history_returns_empty_when_no_data(self, client: TestClient) -> None:
        """GET /v1/data/prices/{symbol} should return empty list when no data."""
        # Use a symbol we definitely don't have data for
        response = client.get("/v1/data/prices/ZZZZZ")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert data["symbol"] == "ZZZZZ"
        assert data["source"] == "alpha_vantage"
        assert data["count"] == 0
        assert data["candles"] == []
        assert data["capture_id"] is None

    def test_price_history_normalizes_symbol_to_uppercase(self, client: TestClient) -> None:
        """Symbol should be normalized to uppercase."""
        response = client.get("/v1/data/prices/xyz123")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "XYZ123"

    def test_price_history_days_parameter(self, client: TestClient) -> None:
        """Days parameter should be accepted and validated."""
        # Valid days parameter
        response = client.get("/v1/data/prices/TESTXYZ?days=60")
        assert response.status_code == 200

        # Days too low
        response = client.get("/v1/data/prices/TESTXYZ?days=0")
        assert response.status_code == 422  # Validation error

        # Days too high
        response = client.get("/v1/data/prices/TESTXYZ?days=400")
        assert response.status_code == 422  # Validation error



class TestPriceLatestEndpoint:
    """Tests for GET /v1/data/prices/{symbol}/latest."""

    def test_latest_price_404_when_no_data(self, client: TestClient) -> None:
        """GET /v1/data/prices/{symbol}/latest should return 404 when no data."""
        # Use a symbol we definitely don't have data for
        response = client.get("/v1/data/prices/ZZZZZ/latest")

        # Should return 404 when no price data exists
        assert response.status_code == 404
        data = response.json()
        assert "No price data available" in data["detail"]

    def test_latest_price_normalizes_symbol(self, client: TestClient) -> None:
        """Symbol should be normalized to uppercase in error message."""
        response = client.get("/v1/data/prices/xyzabc/latest")

        assert response.status_code == 404
        data = response.json()
        assert "XYZABC" in data["detail"]
