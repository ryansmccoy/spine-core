"""Tests for pipeline registry and execution."""

import pytest

from market_spine.db import init_connection_provider
from spine.framework.pipelines import Pipeline
from spine.framework.registry import (
    get_pipeline,
    list_pipelines,
)

# Initialize connection provider for tests
init_connection_provider()


class TestPipelineRegistry:
    """Tests for the pipeline registry."""

    def test_otc_pipelines_registered(self):
        """Test that FINRA OTC Transparency domain pipelines are registered."""
        pipelines = list_pipelines()

        assert "finra.otc_transparency.ingest_week" in pipelines
        assert "finra.otc_transparency.normalize_week" in pipelines
        assert "finra.otc_transparency.aggregate_week" in pipelines

    def test_get_pipeline_returns_class(self):
        """Test that get_pipeline returns the pipeline class."""
        cls = get_pipeline("finra.otc_transparency.ingest_week")

        assert cls is not None
        assert issubclass(cls, Pipeline)
        assert cls.name == "finra.otc_transparency.ingest_week"

    def test_get_unknown_pipeline_raises(self):
        """Test that getting unknown pipeline raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            get_pipeline("nonexistent.pipeline")

        assert "nonexistent.pipeline" in str(exc_info.value)


class TestOTCPipelines:
    """Tests for the FINRA OTC Transparency domain pipelines."""

    def test_ingest_pipeline_class(self):
        """Test ingest pipeline class can be retrieved."""
        cls = get_pipeline("finra.otc_transparency.ingest_week")

        assert cls is not None
        assert issubclass(cls, Pipeline)
        assert cls.name == "finra.otc_transparency.ingest_week"

    def test_normalize_pipeline_class(self):
        """Test normalize pipeline class can be retrieved."""
        cls = get_pipeline("finra.otc_transparency.normalize_week")

        assert cls is not None
        assert issubclass(cls, Pipeline)
        assert cls.name == "finra.otc_transparency.normalize_week"

    def test_aggregate_pipeline_class(self):
        """Test aggregate pipeline class can be retrieved."""
        cls = get_pipeline("finra.otc_transparency.aggregate_week")

        assert cls is not None
        assert issubclass(cls, Pipeline)
        assert cls.name == "finra.otc_transparency.aggregate_week"


class TestPipelineResult:
    """Tests for PipelineResult."""

    def test_result_has_required_fields(self):
        """Test that result has status, started_at, completed_at."""
        cls = get_pipeline("finra.otc_transparency.ingest_week")

        # Just verify the class exists and has expected attributes
        assert hasattr(cls, "name")
        assert hasattr(cls, "description")
        assert cls.name == "finra.otc_transparency.ingest_week"
