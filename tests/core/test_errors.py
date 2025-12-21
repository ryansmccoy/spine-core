"""Tests for spine.core.errors module."""

import pytest

from spine.core.errors import (
    SpineError,
    ErrorCategory,
    ErrorContext,
    SourceError,
    SourceNotFoundError,
    TransientError,
    NetworkError,
    DatabaseError,
    ParseError,
    ValidationError,
    ConfigError,
    OperationError,
    is_retryable,
    get_retry_after,
)


class TestErrorCategory:
    """Test ErrorCategory enum."""

    def test_all_categories_defined(self):
        """Verify all standard categories are available."""
        categories = [
            ErrorCategory.NETWORK,
            ErrorCategory.DATABASE,
            ErrorCategory.STORAGE,
            ErrorCategory.SOURCE,
            ErrorCategory.PARSE,
            ErrorCategory.VALIDATION,
            ErrorCategory.CONFIG,
            ErrorCategory.AUTH,
            ErrorCategory.operation,
            ErrorCategory.ORCHESTRATION,
            ErrorCategory.INTERNAL,
            ErrorCategory.UNKNOWN,
        ]
        assert len(categories) == 12


class TestErrorContext:
    """Test ErrorContext dataclass."""

    def test_create_empty_context(self):
        """Create context with no fields set."""
        ctx = ErrorContext()
        assert ctx.operation is None
        assert ctx.workflow is None
        assert ctx.metadata == {}

    def test_create_context_with_fields(self):
        """Create context with specific fields."""
        ctx = ErrorContext(
            operation="my_operation",
            workflow="my_workflow",
            run_id="run_123",
            metadata={"foo": "bar"},
        )
        assert ctx.operation == "my_operation"
        assert ctx.workflow == "my_workflow"
        assert ctx.run_id == "run_123"
        assert ctx.metadata["foo"] == "bar"

    def test_to_dict_includes_set_fields(self):
        """to_dict includes only non-None fields."""
        ctx = ErrorContext(
            operation="my_operation",
            run_id="run_123",
            metadata={"key": "value"},
        )
        d = ctx.to_dict()
        assert d["operation"] == "my_operation"
        assert d["run_id"] == "run_123"
        assert d["key"] == "value"
        assert "workflow" not in d


class TestSpineError:
    """Test SpineError base class."""

    def test_create_minimal_error(self):
        """Create error with just message."""
        err = SpineError("Something failed")
        assert err.message == "Something failed"
        assert err.category == ErrorCategory.INTERNAL
        assert err.retryable is False
        assert err.retry_after is None

    def test_create_with_category(self):
        """Create error with custom category."""
        err = SpineError("Network error", category=ErrorCategory.NETWORK)
        assert err.category == ErrorCategory.NETWORK

    def test_create_retryable(self):
        """Create retryable error."""
        err = SpineError("Timeout", retryable=True, retry_after=30)
        assert err.retryable is True
        assert err.retry_after == 30

    def test_create_with_context(self):
        """Create error with context."""
        ctx = ErrorContext(operation="test_operation")
        err = SpineError("Failed", context=ctx)
        assert err.context.operation == "test_operation"

    def test_create_with_cause(self):
        """Create error with underlying cause."""
        cause = ValueError("Invalid value")
        err = SpineError("Validation failed", cause=cause)
        assert err.cause is cause
        assert err.__cause__ is cause

    def test_with_context_fluent_api(self):
        """Use with_context to add metadata."""
        err = SpineError("Failed").with_context(
            operation="test_operation",
            run_id="run_123",
        )
        assert err.context.operation == "test_operation"
        assert err.context.run_id == "run_123"

    def test_to_dict(self):
        """Convert error to dictionary."""
        err = SpineError(
            "Failed",
            category=ErrorCategory.NETWORK,
            retryable=True,
        ).with_context(operation="test_operation")
        
        d = err.to_dict()
        assert d["message"] == "Failed"
        assert d["category"] == "NETWORK"
        assert d["retryable"] is True
        assert d["context"]["operation"] == "test_operation"


class TestSourceError:
    """Test SourceError subclass."""

    def test_defaults(self):
        """SourceError has correct defaults."""
        err = SourceError("Source failed")
        assert err.category == ErrorCategory.SOURCE
        assert err.retryable is False

    def test_override_retryable(self):
        """Can override retryable for specific cases."""
        err = SourceError("API rate limited", retryable=True, retry_after=60)
        assert err.retryable is True
        assert err.retry_after == 60


class TestSourceNotFoundError:
    """Test SourceNotFoundError subclass."""

    def test_defaults(self):
        """SourceNotFoundError is non-retryable."""
        err = SourceNotFoundError("File not found")
        assert err.category == ErrorCategory.SOURCE
        assert err.retryable is False


class TestTransientError:
    """Test TransientError subclass."""

    def test_defaults(self):
        """TransientError is retryable by default."""
        err = TransientError("Temporary failure")
        assert err.category == ErrorCategory.NETWORK
        assert err.retryable is True

    def test_with_retry_delay(self):
        """Can specify retry delay."""
        err = TransientError("Timeout", retry_after=30)
        assert err.retry_after == 30


class TestNetworkError:
    """Test NetworkError subclass."""

    def test_defaults(self):
        """NetworkError is retryable by default."""
        err = NetworkError("Connection timeout")
        assert err.category == ErrorCategory.NETWORK
        assert err.retryable is True


class TestDatabaseError:
    """Test DatabaseError subclass."""

    def test_defaults(self):
        """DatabaseError is non-retryable by default."""
        err = DatabaseError("Connection pool exhausted")
        assert err.category == ErrorCategory.DATABASE
        assert err.retryable is False

    def test_retryable_database_error(self):
        """Some database errors are retryable."""
        err = DatabaseError("Connection timeout", retryable=True)
        assert err.retryable is True


class TestParseError:
    """Test ParseError subclass."""

    def test_defaults(self):
        """ParseError is non-retryable."""
        err = ParseError("Invalid JSON")
        assert err.category == ErrorCategory.PARSE
        assert err.retryable is False


class TestValidationError:
    """Test ValidationError subclass."""

    def test_defaults(self):
        """ValidationError is non-retryable."""
        err = ValidationError("Schema validation failed")
        assert err.category == ErrorCategory.VALIDATION
        assert err.retryable is False


class TestConfigError:
    """Test ConfigError subclass."""

    def test_defaults(self):
        """ConfigError is non-retryable."""
        err = ConfigError("Missing required setting")
        assert err.category == ErrorCategory.CONFIG
        assert err.retryable is False


class TestOperationError:
    """Test OperationError subclass."""

    def test_defaults(self):
        """OperationError is non-retryable by default."""
        err = OperationError("Operation failed")
        assert err.category == ErrorCategory.operation
        assert err.retryable is False


class TestUtilityFunctions:
    """Test utility functions."""

    def test_is_retryable_with_spine_error(self):
        """is_retryable checks SpineError.retryable."""
        err = TransientError("Timeout")
        assert is_retryable(err) is True
        
        err = SourceNotFoundError("Not found")
        assert is_retryable(err) is False

    def test_is_retryable_with_standard_exception(self):
        """is_retryable returns False for standard exceptions."""
        err = ValueError("Bad value")
        assert is_retryable(err) is False

    def test_get_retry_after_with_spine_error(self):
        """get_retry_after extracts retry_after."""
        err = TransientError("Timeout", retry_after=30)
        assert get_retry_after(err) == 30

    def test_get_retry_after_with_no_delay(self):
        """get_retry_after returns None when no delay set."""
        err = TransientError("Timeout")
        assert get_retry_after(err) is None

    def test_get_retry_after_with_standard_exception(self):
        """get_retry_after returns None for standard exceptions."""
        err = ValueError("Bad value")
        assert get_retry_after(err) is None
