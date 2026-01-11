"""
CLI / API parity tests.

These tests verify that CLI and API produce compatible Result shapes
when executing the same pipeline, ensuring the command layer is truly
unified across both interfaces.
"""

import pytest
from fastapi.testclient import TestClient

from market_spine.api.app import create_app
from market_spine.app.commands.executions import RunPipelineCommand, RunPipelineRequest
from market_spine.db import init_connection_provider

# Initialize connection provider once for all tests
init_connection_provider()


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Create a TestClient for the API."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=False)


class TestCLIAPIParity:
    """
    Tests verifying CLI and API produce compatible results.

    Both interfaces use the same command layer, so their outputs
    should be structurally compatible.
    """

    def test_dry_run_produces_same_shape(self, client: TestClient) -> None:
        """CLI and API dry_run should produce compatible Result shapes."""
        # Find a pipeline to test with
        list_response = client.get("/v1/pipelines?prefix=finra.otc_transparency")
        pipelines = list_response.json()["pipelines"]

        if not pipelines:
            pytest.skip("No finra.otc_transparency pipelines registered")

        pipeline_name = pipelines[0]["name"]
        params = {"tier": "OTC", "week_ending": "2025-01-10"}

        # Execute via CLI command layer (simulating CLI)
        command = RunPipelineCommand()
        cli_result = command.execute(
            RunPipelineRequest(
                pipeline=pipeline_name,
                params=params,
                dry_run=True,
                trigger_source="cli",
            )
        )

        # Execute via API
        api_response = client.post(
            f"/v1/pipelines/{pipeline_name}/run",
            json={"params": params, "dry_run": True},
        )

        # Both should succeed
        assert cli_result.success is True
        assert api_response.status_code == 200

        api_data = api_response.json()

        # Verify compatible shapes
        # CLI Result has execution_id (may be None for dry_run)
        # API always has execution_id (generated if needed)
        assert "execution_id" in api_data
        assert api_data["execution_id"] is not None  # API always generates

        # Both have status
        assert cli_result.status is not None
        assert cli_result.status.value == api_data["status"]
        assert api_data["status"] == "dry_run"

        # API always has poll_url (null in Basic)
        assert "poll_url" in api_data
        assert api_data["poll_url"] is None

    def test_error_produces_compatible_error_codes(self, client: TestClient) -> None:
        """CLI and API errors should use same ErrorCode values."""
        # Try to run nonexistent pipeline via both

        # CLI command layer
        command = RunPipelineCommand()
        cli_result = command.execute(
            RunPipelineRequest(
                pipeline="nonexistent.pipeline.xyz",
                params={},
                trigger_source="cli",
            )
        )

        # API
        api_response = client.post(
            "/v1/pipelines/nonexistent.pipeline.xyz/run",
            json={"params": {}},
        )

        # Both should fail with same error code
        assert cli_result.success is False
        assert api_response.status_code == 404

        api_error = api_response.json()["detail"]["error"]

        # Error codes should match
        assert cli_result.error.code.value == api_error["code"]
        assert api_error["code"] == "PIPELINE_NOT_FOUND"

    def test_invalid_tier_error_parity(self, client: TestClient) -> None:
        """Invalid tier errors should be consistent across CLI and API."""
        # Find an ingest pipeline
        list_response = client.get("/v1/pipelines?prefix=finra.otc_transparency.ingest")
        pipelines = list_response.json()["pipelines"]

        if not pipelines:
            pytest.skip("No ingest pipelines registered")

        pipeline_name = pipelines[0]["name"]
        invalid_params = {"tier": "INVALID_TIER_XYZ", "week_ending": "2025-01-10"}

        # CLI command layer
        command = RunPipelineCommand()
        cli_result = command.execute(
            RunPipelineRequest(
                pipeline=pipeline_name,
                params=invalid_params,
                trigger_source="cli",
            )
        )

        # API
        api_response = client.post(
            f"/v1/pipelines/{pipeline_name}/run",
            json={"params": invalid_params},
        )

        # Both should fail with INVALID_TIER
        assert cli_result.success is False
        assert api_response.status_code == 400

        api_error = api_response.json()["detail"]["error"]

        # Error codes should match
        assert cli_result.error.code.value == api_error["code"]
        assert api_error["code"] == "INVALID_TIER"

    def test_reserved_fields_always_present_in_api(self, client: TestClient) -> None:
        """API responses must always include reserved async fields."""
        # Find a pipeline
        list_response = client.get("/v1/pipelines?prefix=finra.otc_transparency")
        pipelines = list_response.json()["pipelines"]

        if not pipelines:
            pytest.skip("No pipelines registered")

        pipeline_name = pipelines[0]["name"]

        # Dry run to avoid actual execution
        api_response = client.post(
            f"/v1/pipelines/{pipeline_name}/run",
            json={
                "params": {"tier": "OTC", "week_ending": "2025-01-10"},
                "dry_run": True,
            },
        )

        assert api_response.status_code == 200
        data = api_response.json()

        # These fields MUST always be present per contract
        assert "execution_id" in data, "execution_id must always be present"
        assert data["execution_id"] is not None, "execution_id must not be None"

        assert "status" in data, "status must always be present"
        assert data["status"] in (
            "completed",
            "failed",
            "dry_run",
        ), f"Invalid status: {data['status']}"

        assert "poll_url" in data, "poll_url must always be present"
        assert data["poll_url"] is None, "poll_url must be null in Basic tier"
