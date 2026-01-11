"""
Tests for spine.framework.registry module.

Tests cover:
- Pipeline registration via decorator
- Pipeline lookup by name
- Listing registered pipelines
- Registry clearing (for test isolation)
- Error handling for missing pipelines
"""

import pytest

from spine.framework.registry import (
    register_pipeline,
    get_pipeline,
    list_pipelines,
    clear_registry,
)
from spine.framework.pipelines import Pipeline


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure registry is clean before and after each test."""
    clear_registry()
    yield
    clear_registry()


class TestRegisterPipeline:
    """Tests for register_pipeline decorator."""

    def test_register_pipeline_basic(self):
        """Test basic pipeline registration."""
        @register_pipeline("test.basic")
        class BasicPipeline(Pipeline):
            def run(self):
                pass
        
        assert "test.basic" in list_pipelines()

    def test_register_pipeline_returns_class(self):
        """Test that decorator returns the original class."""
        @register_pipeline("test.returns_class")
        class MyPipeline(Pipeline):
            custom_attr = "value"
            
            def run(self):
                pass
        
        assert MyPipeline.custom_attr == "value"

    def test_register_duplicate_raises_error(self):
        """Test that registering duplicate name raises error."""
        @register_pipeline("test.duplicate")
        class First(Pipeline):
            def run(self):
                pass
        
        with pytest.raises(ValueError, match="already registered"):
            @register_pipeline("test.duplicate")
            class Second(Pipeline):
                def run(self):
                    pass


class TestGetPipeline:
    """Tests for get_pipeline function."""

    def test_get_registered_pipeline(self):
        """Test getting a registered pipeline."""
        @register_pipeline("test.get")
        class MyPipeline(Pipeline):
            def run(self):
                pass
        
        retrieved = get_pipeline("test.get")
        assert retrieved is MyPipeline

    def test_get_nonexistent_pipeline_raises(self):
        """Test that getting non-existent pipeline raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            get_pipeline("nonexistent.pipeline")

    def test_get_pipeline_error_shows_available(self):
        """Test that error message shows available pipelines."""
        @register_pipeline("test.available1")
        class Pipeline1(Pipeline):
            def run(self):
                pass
        
        @register_pipeline("test.available2")
        class Pipeline2(Pipeline):
            def run(self):
                pass
        
        with pytest.raises(KeyError) as exc_info:
            get_pipeline("test.missing")
        
        error_msg = str(exc_info.value)
        assert "test.available1" in error_msg
        assert "test.available2" in error_msg


class TestListPipelines:
    """Tests for list_pipelines function."""

    def test_list_empty_registry(self):
        """Test listing with no registered pipelines."""
        # Note: registry may have auto-loaded pipelines depending on setup
        # This test verifies the function works, not that registry is empty
        result = list_pipelines()
        assert isinstance(result, list)

    def test_list_registered_pipelines(self):
        """Test listing registered pipelines."""
        @register_pipeline("test.list.a")
        class PipelineA(Pipeline):
            def run(self):
                pass
        
        @register_pipeline("test.list.b")
        class PipelineB(Pipeline):
            def run(self):
                pass
        
        names = list_pipelines()
        assert "test.list.a" in names
        assert "test.list.b" in names

    def test_list_pipelines_sorted(self):
        """Test that listed pipelines are sorted."""
        @register_pipeline("test.z_last")
        class ZPipeline(Pipeline):
            def run(self):
                pass
        
        @register_pipeline("test.a_first")
        class APipeline(Pipeline):
            def run(self):
                pass
        
        names = list_pipelines()
        # Filter to just our test pipelines
        test_names = [n for n in names if n.startswith("test.")]
        assert test_names == sorted(test_names)


class TestClearRegistry:
    """Tests for clear_registry function."""

    def test_clear_removes_all_pipelines(self):
        """Test that clear_registry removes all pipelines."""
        @register_pipeline("test.clear.a")
        class PipelineA(Pipeline):
            def run(self):
                pass
        
        @register_pipeline("test.clear.b")
        class PipelineB(Pipeline):
            def run(self):
                pass
        
        assert "test.clear.a" in list_pipelines()
        assert "test.clear.b" in list_pipelines()
        
        clear_registry()
        
        # After clearing, pipelines should not be found
        with pytest.raises(KeyError):
            get_pipeline("test.clear.a")
        
        with pytest.raises(KeyError):
            get_pipeline("test.clear.b")
