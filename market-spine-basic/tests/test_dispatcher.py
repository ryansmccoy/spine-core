"""Tests for the dispatcher and pipeline execution."""

import pytest

from market_spine.db import init_connection_provider, init_db
from spine.framework.dispatcher import Dispatcher, Lane, TriggerSource
from spine.framework.exceptions import PipelineNotFoundError
from spine.framework.pipelines import PipelineStatus

# Initialize connection provider for tests
init_connection_provider()

# Create a test dispatcher instance
_test_dispatcher = None


def get_test_dispatcher():
    global _test_dispatcher
    if _test_dispatcher is None:
        _test_dispatcher = Dispatcher()
    return _test_dispatcher


class TestDispatcher:
    """Tests for the dispatcher."""

    @pytest.fixture(autouse=True)
    def setup_db(self):
        """Initialize database for tests."""
        init_db()

    def test_dispatcher_creation(self):
        """Test that dispatcher can be created."""
        d1 = get_test_dispatcher()
        d2 = get_test_dispatcher()

        # Should be same or equivalent (depending on implementation)
        assert d1 is not None
        assert d2 is not None

    def test_submit_pipeline(self):
        """Test submitting a pipeline for execution (OTC ingest)."""
        dispatcher = get_test_dispatcher()

        # Note: With the new ingestion source abstraction, week_ending alone
        # is not enough - need either file_path OR (tier + week_ending).
        # Dispatcher doesn't re-raise PipelineError, it returns failed execution.
        execution = dispatcher.submit(
            pipeline="finra.otc_transparency.ingest_week",
            params={"week_ending": "2026-01-03"},
            lane=Lane.NORMAL,
            trigger_source=TriggerSource.CLI,
        )
        assert execution.status == PipelineStatus.FAILED
        assert "source" in execution.error.lower()

    def test_submit_with_different_lanes(self):
        """Test submitting with different lanes."""
        dispatcher = get_test_dispatcher()

        for lane in [Lane.NORMAL, Lane.BACKFILL, Lane.SLOW]:
            # With new source abstraction, incomplete params cause failed execution
            execution = dispatcher.submit(
                pipeline="finra.otc_transparency.ingest_week",
                params={"week_ending": "2026-01-03"},
                lane=lane,
                trigger_source=TriggerSource.CLI,
            )
            assert execution.status == PipelineStatus.FAILED

    def test_submit_unknown_pipeline(self):
        """Test submitting unknown pipeline raises PipelineNotFoundError."""
        dispatcher = get_test_dispatcher()

        with pytest.raises(PipelineNotFoundError) as exc_info:
            dispatcher.submit(
                pipeline="nonexistent.pipeline",
                trigger_source=TriggerSource.CLI,
            )

        # Check error message
        assert "nonexistent.pipeline" in str(exc_info.value)
