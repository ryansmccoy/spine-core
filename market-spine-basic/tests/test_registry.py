"""
Tests for pipeline registry integrity.

Ensures:
- Pipelines are registered correctly
- Names are unique
- get_pipeline() works for all registered pipelines
"""

from market_spine.db import init_connection_provider
from spine.framework.pipelines import Pipeline
from spine.framework.registry import get_pipeline, list_pipelines

# Initialize connection provider for tests
init_connection_provider()


class TestRegistryIntegrity:
    """Tests for pipeline registry integrity."""

    def test_pipelines_are_registered(self):
        """Test that expected FINRA OTC Transparency pipelines are registered."""
        pipelines = list_pipelines()

        # Should have at least the core FINRA OTC Transparency pipelines
        expected = [
            "finra.otc_transparency.ingest_week",
            "finra.otc_transparency.normalize_week",
            "finra.otc_transparency.aggregate_week",
            "finra.otc_transparency.compute_rolling",
            "finra.otc_transparency.backfill_range",
        ]

        for name in expected:
            assert name in pipelines, f"Expected pipeline '{name}' not registered"

    def test_pipeline_names_are_unique(self):
        """Test that all pipeline names are unique (no duplicates)."""
        pipelines = list_pipelines()

        # Convert to set and compare lengths
        assert len(pipelines) == len(set(pipelines)), (
            "Duplicate pipeline names detected in registry"
        )

    def test_get_pipeline_works_for_all(self):
        """Test that get_pipeline() works for every registered pipeline."""
        pipelines = list_pipelines()

        for name in pipelines:
            cls = get_pipeline(name)
            assert cls is not None, f"get_pipeline('{name}') returned None"
            assert issubclass(cls, Pipeline), (
                f"Pipeline '{name}' does not inherit from Pipeline base class"
            )

    def test_pipeline_classes_have_required_attributes(self):
        """Test that all pipeline classes have name and description."""
        pipelines = list_pipelines()

        for name in pipelines:
            cls = get_pipeline(name)

            # Check for required class attributes
            assert hasattr(cls, "name"), f"Pipeline '{name}' missing 'name' attribute"
            assert hasattr(cls, "description"), f"Pipeline '{name}' missing 'description' attribute"

            # Verify name matches registry key
            assert cls.name == name, (
                f"Pipeline class name '{cls.name}' doesn't match registry key '{name}'"
            )

    def test_no_duplicate_class_registrations(self):
        """Test that no pipeline class is registered under multiple names."""
        pipelines = list_pipelines()

        class_to_names = {}
        for name in pipelines:
            cls = get_pipeline(name)
            cls_id = id(cls)

            if cls_id not in class_to_names:
                class_to_names[cls_id] = []
            class_to_names[cls_id].append(name)

        # Check for duplicates
        duplicates = {names[0]: names for names in class_to_names.values() if len(names) > 1}

        assert len(duplicates) == 0, (
            f"Some pipeline classes are registered multiple times: {duplicates}"
        )
