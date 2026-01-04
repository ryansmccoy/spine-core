"""Tests for pipeline registry and execution."""

import pytest
from market_spine.registry import registry


class TestPipelineRegistry:
    """Tests for the pipeline registry."""

    def test_example_pipelines_registered(self):
        """Test that example domain pipelines are auto-discovered."""
        pipelines = registry.list_pipelines()
        names = [p["name"] for p in pipelines]

        assert "example.hello" in names
        assert "example.count" in names
        assert "example.fail" in names

    def test_get_pipeline_returns_instance(self):
        """Test that registry.get returns a pipeline instance."""
        pipeline = registry.get("example.hello")

        assert pipeline is not None
        assert pipeline.name == "example.hello"

    def test_get_unknown_pipeline_returns_none(self):
        """Test that getting unknown pipeline returns None."""
        pipeline = registry.get("nonexistent.pipeline")

        assert pipeline is None


class TestExamplePipelines:
    """Tests for the example domain pipelines."""

    def test_hello_pipeline_default(self):
        """Test hello pipeline with default params."""
        from market_spine.domains.example.pipelines import ExampleHelloPipeline

        pipeline = ExampleHelloPipeline()
        result = pipeline.execute({})

        assert result["message"] == "Hello, World!"
        assert result["name_length"] == 5

    def test_hello_pipeline_with_name(self):
        """Test hello pipeline with custom name."""
        from market_spine.domains.example.pipelines import ExampleHelloPipeline

        pipeline = ExampleHelloPipeline()
        result = pipeline.execute({"name": "Market Spine"})

        assert result["message"] == "Hello, Market Spine!"
        assert result["name_length"] == 12

    def test_count_pipeline(self):
        """Test count pipeline."""
        from market_spine.domains.example.pipelines import ExampleCountPipeline

        pipeline = ExampleCountPipeline()
        result = pipeline.execute({"n": 5})

        assert result["n"] == 5
        assert result["total"] == 15  # 1+2+3+4+5

    def test_fail_pipeline(self):
        """Test fail pipeline raises RuntimeError."""
        from market_spine.domains.example.pipelines import ExampleFailPipeline

        pipeline = ExampleFailPipeline()

        with pytest.raises(RuntimeError) as exc_info:
            pipeline.execute({})

        assert "Intentional failure" in str(exc_info.value)


class TestPipelineResult:
    """Tests for pipeline results."""

    def test_result_is_dict(self):
        """Test that result is a dict."""
        from market_spine.domains.example.pipelines import ExampleHelloPipeline

        pipeline = ExampleHelloPipeline()
        result = pipeline.execute({})

        assert isinstance(result, dict)

    def test_result_metrics_are_accessible(self):
        """Test that metrics dict is accessible."""
        from market_spine.domains.example.pipelines import ExampleCountPipeline

        pipeline = ExampleCountPipeline()
        result = pipeline.execute({"n": 100})

        assert "total" in result
        assert result["total"] == 5050
