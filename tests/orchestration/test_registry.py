"""
Tests for spine.orchestration.registry module.

Tests cover:
- Group registration
- Group lookup
- Listing groups with filtering
- Registry clearing
- Decorator-style registration
"""

import pytest

from spine.orchestration import (
    PipelineGroup,
    PipelineStep,
    register_group,
    get_group,
    list_groups,
    clear_group_registry,
    group_exists,
)
from spine.orchestration.exceptions import GroupNotFoundError


# Note: clean_group_registry fixture is auto-applied from conftest.py


class TestRegisterGroup:
    """Tests for register_group function."""

    def test_register_group_basic(self, simple_linear_group):
        """Test basic group registration."""
        register_group(simple_linear_group)
        
        assert group_exists("test.simple_linear")

    def test_register_multiple_groups(self, simple_linear_group, diamond_dependency_group):
        """Test registering multiple groups."""
        register_group(simple_linear_group)
        register_group(diamond_dependency_group)
        
        assert group_exists("test.simple_linear")
        assert group_exists("test.diamond")

    def test_duplicate_registration_rejected(self, simple_linear_group):
        """Test that registering duplicate name raises error."""
        register_group(simple_linear_group)
        
        with pytest.raises(ValueError, match="already registered"):
            register_group(simple_linear_group)

    def test_register_as_decorator(self):
        """Test using register_group as a decorator."""
        @register_group
        def my_group():
            return PipelineGroup(
                name="test.decorated",
                steps=[PipelineStep("a", "pipeline.a")],
            )
        
        assert group_exists("test.decorated")


class TestGetGroup:
    """Tests for get_group function."""

    def test_get_registered_group(self, simple_linear_group):
        """Test getting a registered group."""
        register_group(simple_linear_group)
        
        retrieved = get_group("test.simple_linear")
        
        assert retrieved.name == simple_linear_group.name
        assert len(retrieved.steps) == len(simple_linear_group.steps)

    def test_get_nonexistent_group_raises(self):
        """Test that getting non-existent group raises error."""
        with pytest.raises(GroupNotFoundError):
            get_group("nonexistent.group")

    def test_group_not_found_error_includes_name(self):
        """Test that error includes the missing group name."""
        try:
            get_group("missing.group")
            pytest.fail("Should have raised GroupNotFoundError")
        except GroupNotFoundError as e:
            assert "missing.group" in str(e)


class TestListGroups:
    """Tests for list_groups function."""

    def test_list_empty_registry(self):
        """Test listing when no groups registered."""
        names = list_groups()
        
        assert names == []

    def test_list_registered_groups(self, simple_linear_group, diamond_dependency_group):
        """Test listing registered groups."""
        register_group(simple_linear_group)
        register_group(diamond_dependency_group)
        
        names = list_groups()
        
        assert "test.simple_linear" in names
        assert "test.diamond" in names

    def test_list_groups_by_domain(self):
        """Test filtering groups by domain."""
        register_group(PipelineGroup(
            name="domain1.group",
            domain="domain1",
            steps=[PipelineStep("a", "pipeline.a")],
        ))
        register_group(PipelineGroup(
            name="domain2.group",
            domain="domain2",
            steps=[PipelineStep("a", "pipeline.a")],
        ))
        
        domain1_groups = list_groups(domain="domain1")
        
        assert "domain1.group" in domain1_groups
        assert "domain2.group" not in domain1_groups


class TestGroupExists:
    """Tests for group_exists function."""

    def test_exists_returns_true_for_registered(self, simple_linear_group):
        """Test group_exists returns True for registered group."""
        register_group(simple_linear_group)
        
        assert group_exists("test.simple_linear") is True

    def test_exists_returns_false_for_unregistered(self):
        """Test group_exists returns False for unregistered group."""
        assert group_exists("not.registered") is False


class TestClearGroupRegistry:
    """Tests for clear_group_registry function."""

    def test_clear_removes_all_groups(self, simple_linear_group, diamond_dependency_group):
        """Test that clear removes all groups."""
        register_group(simple_linear_group)
        register_group(diamond_dependency_group)
        
        assert group_exists("test.simple_linear")
        assert group_exists("test.diamond")
        
        clear_group_registry()
        
        assert not group_exists("test.simple_linear")
        assert not group_exists("test.diamond")

    def test_clear_allows_reregistration(self, simple_linear_group):
        """Test that clear allows re-registration of same name."""
        register_group(simple_linear_group)
        clear_group_registry()
        
        # Should not raise now
        register_group(simple_linear_group)
        
        assert group_exists("test.simple_linear")
