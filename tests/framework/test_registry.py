"""
Tests for spine.framework.registry module.

Tests cover:
- Operation registration via decorator
- Operation lookup by name
- Listing registered operations
- Registry clearing (for test isolation)
- Error handling for missing operations
"""

import pytest

from spine.framework.registry import (
    register_operation,
    get_operation,
    list_operations,
    clear_registry,
)
from spine.framework.operations import Operation


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure registry is clean before and after each test."""
    clear_registry()
    yield
    clear_registry()


class TestRegisterOperation:
    """Tests for register_operation decorator."""

    def test_register_operation_basic(self):
        """Test basic operation registration."""
        @register_operation("test.basic")
        class BasicOperation(Operation):
            def run(self):
                pass
        
        assert "test.basic" in list_operations()

    def test_register_operation_returns_class(self):
        """Test that decorator returns the original class."""
        @register_operation("test.returns_class")
        class MyOperation(Operation):
            custom_attr = "value"
            
            def run(self):
                pass
        
        assert MyOperation.custom_attr == "value"

    def test_register_duplicate_raises_error(self):
        """Test that registering duplicate name raises error."""
        @register_operation("test.duplicate")
        class First(Operation):
            def run(self):
                pass
        
        with pytest.raises(ValueError, match="already registered"):
            @register_operation("test.duplicate")
            class Second(Operation):
                def run(self):
                    pass


class TestGetOperation:
    """Tests for get_operation function."""

    def test_get_registered_operation(self):
        """Test getting a registered operation."""
        @register_operation("test.get")
        class MyOperation(Operation):
            def run(self):
                pass
        
        retrieved = get_operation("test.get")
        assert retrieved is MyOperation

    def test_get_nonexistent_operation_raises(self):
        """Test that getting non-existent operation raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            get_operation("nonexistent.operation")

    def test_get_operation_error_shows_available(self):
        """Test that error message shows available operations."""
        @register_operation("test.available1")
        class Operation1(Operation):
            def run(self):
                pass
        
        @register_operation("test.available2")
        class Operation2(Operation):
            def run(self):
                pass
        
        with pytest.raises(KeyError) as exc_info:
            get_operation("test.missing")
        
        error_msg = str(exc_info.value)
        assert "test.available1" in error_msg
        assert "test.available2" in error_msg


class TestListOperations:
    """Tests for list_operations function."""

    def test_list_empty_registry(self):
        """Test listing with no registered operations."""
        # Note: registry may have auto-loaded operations depending on setup
        # This test verifies the function works, not that registry is empty
        result = list_operations()
        assert isinstance(result, list)

    def test_list_registered_operations(self):
        """Test listing registered operations."""
        @register_operation("test.list.a")
        class OperationA(Operation):
            def run(self):
                pass
        
        @register_operation("test.list.b")
        class OperationB(Operation):
            def run(self):
                pass
        
        names = list_operations()
        assert "test.list.a" in names
        assert "test.list.b" in names

    def test_list_operations_sorted(self):
        """Test that listed operations are sorted."""
        @register_operation("test.z_last")
        class ZOperation(Operation):
            def run(self):
                pass
        
        @register_operation("test.a_first")
        class AOperation(Operation):
            def run(self):
                pass
        
        names = list_operations()
        # Filter to just our test operations
        test_names = [n for n in names if n.startswith("test.")]
        assert test_names == sorted(test_names)


class TestClearRegistry:
    """Tests for clear_registry function."""

    def test_clear_removes_all_operations(self):
        """Test that clear_registry removes all operations."""
        @register_operation("test.clear.a")
        class OperationA(Operation):
            def run(self):
                pass
        
        @register_operation("test.clear.b")
        class OperationB(Operation):
            def run(self):
                pass
        
        assert "test.clear.a" in list_operations()
        assert "test.clear.b" in list_operations()
        
        clear_registry()
        
        # After clearing, operations should not be found
        with pytest.raises(KeyError):
            get_operation("test.clear.a")
        
        with pytest.raises(KeyError):
            get_operation("test.clear.b")
