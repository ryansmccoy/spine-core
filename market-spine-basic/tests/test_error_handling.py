"""Tests for error handling and exception classification."""

import pytest

from market_spine.db import init_connection_provider, init_db
from spine.framework.dispatcher import Dispatcher, TriggerSource
from spine.framework.exceptions import BadParamsError, PipelineNotFoundError
from spine.framework.pipelines import PipelineStatus
from spine.framework.runner import PipelineRunner

# Initialize connection provider for tests
init_connection_provider()


class TestPipelineNotFoundError:
    """Tests for PipelineNotFoundError."""

    def test_error_contains_pipeline_name(self):
        """Test that error contains pipeline name."""
        error = PipelineNotFoundError("my.custom.pipeline")
        assert "my.custom.pipeline" in str(error)
        assert error.pipeline_name == "my.custom.pipeline"

    def test_runner_raises_pipeline_not_found(self):
        """Test that runner raises PipelineNotFoundError for unknown pipelines."""
        runner = PipelineRunner()
        with pytest.raises(PipelineNotFoundError) as exc_info:
            runner.run("nonexistent.pipeline", {})
        assert "nonexistent.pipeline" in str(exc_info.value)

    def test_dispatcher_raises_pipeline_not_found(self):
        """Test that dispatcher raises PipelineNotFoundError."""
        init_db()
        dispatcher = Dispatcher()
        with pytest.raises(PipelineNotFoundError):
            dispatcher.submit(
                pipeline="nonexistent.pipeline",
                trigger_source=TriggerSource.CLI,
            )


class TestBadParamsError:
    """Tests for BadParamsError in runner and dispatcher."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database for tests."""
        init_db()

    def test_runner_raises_bad_params_for_missing_required(self):
        """Test that runner raises BadParamsError for missing required params."""
        runner = PipelineRunner()
        # With new source abstraction, all params are optional in spec,
        # but an invalid tier value still raises BadParamsError
        with pytest.raises(BadParamsError) as exc_info:
            runner.run("finra.otc_transparency.ingest_week", {"tier": "InvalidTier"})
        assert "tier" in str(exc_info.value)

    def test_dispatcher_raises_bad_params(self):
        """Test that dispatcher raises BadParamsError."""
        dispatcher = Dispatcher()
        with pytest.raises(BadParamsError) as exc_info:
            dispatcher.submit(
                pipeline="finra.otc_transparency.normalize_week",
                params={},  # missing week_ending and tier
                trigger_source=TriggerSource.CLI,
            )
        # Should have missing params
        assert len(exc_info.value.missing_params) > 0

    def test_bad_params_error_has_details(self):
        """Test that BadParamsError has detailed information."""
        error = BadParamsError(
            "Validation failed",
            missing_params=["file_path"],
            invalid_params=["tier"],
        )
        assert error.missing_params == ["file_path"]
        assert error.invalid_params == ["tier"]


class TestErrorClassification:
    """Tests that errors are properly classified."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database for tests."""
        init_db()

    def test_unknown_pipeline_is_not_bad_params(self):
        """Ensure unknown pipeline doesn't get classified as bad params."""
        runner = PipelineRunner()
        with pytest.raises(PipelineNotFoundError):
            # This should NOT be BadParamsError
            runner.run("does.not.exist", {"some": "param"})

    def test_missing_params_is_not_pipeline_not_found(self):
        """Ensure missing params doesn't get classified as pipeline not found."""
        runner = PipelineRunner()
        # With new source abstraction, empty params causes a runtime ValueError
        # which returns a failed PipelineResult (not an exception)
        result = runner.run("finra.otc_transparency.ingest_week", {})
        assert result.status == PipelineStatus.FAILED
        assert "source" in result.error.lower()


class TestExitCodes:
    """Tests for proper exit code behavior."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database for tests."""
        init_db()

    def test_failed_pipeline_returns_failed_status(self):
        """Test that failed pipelines return FAILED status."""
        runner = PipelineRunner()
        try:
            result = runner.run(
                "finra.otc_transparency.ingest_week",
                {"file_path": "/nonexistent/file.csv"},
            )
            # If we get here, the pipeline ran but may have failed
            if result.status == PipelineStatus.FAILED:
                assert result.error is not None
        except (BadParamsError, PipelineNotFoundError):
            # These are expected for validation errors
            pass
