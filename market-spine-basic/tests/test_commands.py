"""Tests for command layer."""

import pytest

from market_spine.app.commands.pipelines import (
    ListPipelinesCommand,
    ListPipelinesRequest,
    DescribePipelineCommand,
    DescribePipelineRequest,
)
from market_spine.app.models import ErrorCode
from market_spine.db import init_connection_provider

# Initialize connection provider for tests
init_connection_provider()


class TestListPipelinesCommand:
    """Test suite for ListPipelinesCommand."""

    def test_list_all_pipelines(self) -> None:
        """Should list all registered pipelines."""
        command = ListPipelinesCommand()
        result = command.execute(ListPipelinesRequest())

        assert result.success is True
        assert result.error is None
        assert len(result.pipelines) > 0
        assert result.total_count > 0

        # Verify pipeline structure
        for pipeline in result.pipelines:
            assert pipeline.name is not None
            assert len(pipeline.name) > 0

    def test_list_pipelines_with_prefix(self) -> None:
        """Should filter pipelines by prefix."""
        command = ListPipelinesCommand()
        result = command.execute(ListPipelinesRequest(prefix="finra"))

        assert result.success is True

        # All results should match the prefix
        for pipeline in result.pipelines:
            assert pipeline.name.startswith("finra")

    def test_list_pipelines_no_match(self) -> None:
        """Empty prefix filter should return empty list."""
        command = ListPipelinesCommand()
        result = command.execute(ListPipelinesRequest(prefix="nonexistent_prefix_xyz"))

        assert result.success is True
        assert len(result.pipelines) == 0


class TestDescribePipelineCommand:
    """Test suite for DescribePipelineCommand."""

    def test_describe_existing_pipeline(self) -> None:
        """Should describe an existing pipeline."""
        # First get a pipeline name
        list_cmd = ListPipelinesCommand()
        list_result = list_cmd.execute(ListPipelinesRequest())
        assert list_result.success and len(list_result.pipelines) > 0

        pipeline_name = list_result.pipelines[0].name

        # Now describe it
        command = DescribePipelineCommand()
        result = command.execute(DescribePipelineRequest(name=pipeline_name))

        assert result.success is True
        assert result.error is None
        assert result.pipeline is not None
        assert result.pipeline.name == pipeline_name

    def test_describe_nonexistent_pipeline(self) -> None:
        """Should return error for nonexistent pipeline."""
        command = DescribePipelineCommand()
        result = command.execute(DescribePipelineRequest(name="nonexistent.pipeline"))

        assert result.success is False
        assert result.error is not None
        assert result.error.code == ErrorCode.PIPELINE_NOT_FOUND
        assert result.pipeline is None

    def test_describe_includes_parameters(self) -> None:
        """Should include parameter definitions."""
        # Get a known pipeline that has parameters
        list_cmd = ListPipelinesCommand()
        list_result = list_cmd.execute(ListPipelinesRequest(prefix="finra.otc_transparency"))

        if not list_result.pipelines:
            pytest.skip("No finra.otc_transparency pipelines registered")

        pipeline_name = list_result.pipelines[0].name

        command = DescribePipelineCommand()
        result = command.execute(DescribePipelineRequest(name=pipeline_name))

        assert result.success is True
        assert result.pipeline is not None
        # Pipeline detail should have param lists (may be empty)
        assert result.pipeline.required_params is not None
        assert result.pipeline.optional_params is not None
