"""
Tests for spine.framework.exceptions module.

Tests cover:
- Custom exception classes
- Exception attributes and inheritance
- Error message formatting
"""

import pytest

from spine.framework.exceptions import (
    SpineError,
    OperationNotFoundError,
    BadParamsError,
    ValidationError,
    OperationError,
)


class TestSpineError:
    """Tests for base SpineError exception."""

    def test_spine_error_is_exception(self):
        """Test that SpineError inherits from Exception."""
        assert issubclass(SpineError, Exception)

    def test_spine_error_message(self):
        """Test SpineError with message."""
        error = SpineError("Test error message")
        assert str(error) == "Test error message"


class TestOperationNotFoundError:
    """Tests for OperationNotFoundError exception."""

    def test_inherits_from_spine_error(self):
        """Test inheritance from SpineError."""
        assert issubclass(OperationNotFoundError, SpineError)

    def test_stores_operation_name(self):
        """Test that operation name is stored."""
        error = OperationNotFoundError("my.operation")
        assert error.operation_name == "my.operation"

    def test_error_message_includes_name(self):
        """Test that error message includes operation name."""
        error = OperationNotFoundError("my.missing.operation")
        assert "my.missing.operation" in str(error)

    def test_can_be_caught_as_spine_error(self):
        """Test that it can be caught as SpineError."""
        with pytest.raises(SpineError):
            raise OperationNotFoundError("test.operation")


class TestBadParamsError:
    """Tests for BadParamsError exception."""

    def test_inherits_from_spine_error(self):
        """Test inheritance from SpineError."""
        assert issubclass(BadParamsError, SpineError)

    def test_basic_message(self):
        """Test BadParamsError with just a message."""
        error = BadParamsError("Invalid parameters")
        assert str(error) == "Invalid parameters"
        assert error.missing_params == []
        assert error.invalid_params == []

    def test_with_missing_params(self):
        """Test BadParamsError with missing parameters."""
        error = BadParamsError(
            "Missing required parameters",
            missing_params=["param1", "param2"],
        )
        assert error.missing_params == ["param1", "param2"]
        assert error.invalid_params == []

    def test_with_invalid_params(self):
        """Test BadParamsError with invalid parameters."""
        error = BadParamsError(
            "Invalid parameter values",
            invalid_params=["param3"],
        )
        assert error.missing_params == []
        assert error.invalid_params == ["param3"]

    def test_with_both_missing_and_invalid(self):
        """Test BadParamsError with both missing and invalid params."""
        error = BadParamsError(
            "Parameter validation failed",
            missing_params=["required_param"],
            invalid_params=["bad_value_param"],
        )
        assert error.missing_params == ["required_param"]
        assert error.invalid_params == ["bad_value_param"]


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_inherits_from_spine_error(self):
        """Test inheritance from SpineError."""
        assert issubclass(ValidationError, SpineError)

    def test_error_message(self):
        """Test ValidationError message."""
        error = ValidationError("Data validation failed: missing column 'id'")
        assert "validation failed" in str(error).lower()


class TestOperationError:
    """Tests for OperationError exception."""

    def test_inherits_from_spine_error(self):
        """Test inheritance from SpineError."""
        assert issubclass(OperationError, SpineError)

    def test_error_message(self):
        """Test OperationError message."""
        error = OperationError("Operation execution failed at step 3")
        assert "Operation execution failed" in str(error)


class TestExceptionHierarchy:
    """Tests for exception class hierarchy."""

    def test_all_exceptions_are_spine_errors(self):
        """Test that all custom exceptions inherit from SpineError."""
        exceptions = [
            OperationNotFoundError,
            BadParamsError,
            ValidationError,
            OperationError,
        ]
        
        for exc_class in exceptions:
            assert issubclass(exc_class, SpineError), (
                f"{exc_class.__name__} should inherit from SpineError"
            )

    def test_exceptions_can_be_caught_selectively(self):
        """Test that exceptions can be caught selectively."""
        # Specific catch
        with pytest.raises(OperationNotFoundError):
            raise OperationNotFoundError("test")
        
        # Should not catch different exception types
        with pytest.raises(BadParamsError):
            raise BadParamsError("test")
