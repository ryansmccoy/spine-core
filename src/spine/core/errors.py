"""
Structured error types for Spine framework.

Provides a hierarchy of typed errors with metadata for:
- Retry decisions (retryable flag)
- Error categorization (for alerting and reporting)
- Root cause analysis (error chaining)

Design Principles:
- #3 Registry-Driven: Error types registered with categories
- #7 Explicit over Implicit: Clear error categorization
- #13 Observable: Errors carry metadata for logging/alerting

Usage:
    from spine.core.errors import SourceError, TransientError
    
    try:
        fetch_data()
    except requests.Timeout:
        raise TransientError("API timeout", retryable=True, retry_after=30)
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            raise SourceError("Resource not found", retryable=False)
        raise TransientError("API error", retryable=True, cause=e)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    """
    Standard error categories for classification.
    
    Used by alerting framework to route notifications
    and by retry logic to determine if retry is sensible.
    """
    
    # Infrastructure errors (usually transient)
    NETWORK = "NETWORK"           # Connection, timeout, DNS
    DATABASE = "DATABASE"         # Connection pool, query timeout
    STORAGE = "STORAGE"           # Disk, S3, file system
    
    # Source/data errors
    SOURCE = "SOURCE"             # Upstream API, file not found
    PARSE = "PARSE"               # Data parsing, format errors
    VALIDATION = "VALIDATION"     # Schema, constraint violations
    
    # Configuration errors (never retryable)
    CONFIG = "CONFIG"             # Missing config, invalid settings
    AUTH = "AUTH"                 # Authentication, authorization
    
    # Application errors
    PIPELINE = "PIPELINE"         # Pipeline execution failures
    ORCHESTRATION = "ORCHESTRATION"  # Workflow, scheduler errors
    
    # Internal errors
    INTERNAL = "INTERNAL"         # Bugs, unexpected state
    UNKNOWN = "UNKNOWN"           # Uncategorized errors


@dataclass
class ErrorContext:
    """
    Additional context for an error.
    
    Provides structured metadata for logging and alerting.
    """
    
    # Execution context
    pipeline: str | None = None
    workflow: str | None = None
    step: str | None = None
    run_id: str | None = None
    execution_id: str | None = None
    
    # Source context
    source_name: str | None = None
    source_type: str | None = None
    
    # Request context
    url: str | None = None
    http_status: int | None = None
    
    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging."""
        result = {}
        for key in ["pipeline", "workflow", "step", "run_id", "execution_id",
                    "source_name", "source_type", "url", "http_status"]:
            value = getattr(self, key)
            if value is not None:
                result[key] = value
        if self.metadata:
            result.update(self.metadata)
        return result


class SpineError(Exception):
    """
    Base exception for all Spine framework errors.
    
    All Spine errors have:
    - category: ErrorCategory for classification
    - retryable: Whether the operation can be retried
    - retry_after: Optional seconds to wait before retry
    - context: Optional ErrorContext with metadata
    - cause: Optional underlying exception
    
    Subclasses should set appropriate defaults for their domain.
    """
    
    # Default category for this error type
    default_category: ErrorCategory = ErrorCategory.INTERNAL
    # Default retryable setting
    default_retryable: bool = False
    
    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory | None = None,
        retryable: bool | None = None,
        retry_after: int | None = None,
        context: ErrorContext | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.category = category or self.default_category
        self.retryable = retryable if retryable is not None else self.default_retryable
        self.retry_after = retry_after
        self.context = context or ErrorContext()
        self.cause = cause
        
        # Chain the cause if provided
        if cause is not None:
            self.__cause__ = cause
    
    def with_context(self, **kwargs: Any) -> SpineError:
        """
        Add context to this error (fluent API).
        
        Usage:
            raise SourceError("Failed").with_context(
                source_name="finra_api",
                url="https://api.finra.org/data"
            )
        """
        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)
            else:
                self.context.metadata[key] = value
        return self
    
    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        result = {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "category": self.category.value,
            "retryable": self.retryable,
        }
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        if self.context:
            context_dict = self.context.to_dict()
            if context_dict:
                result["context"] = context_dict
        if self.cause is not None:
            result["cause"] = str(self.cause)
        return result
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r}, category={self.category.value})"


# =============================================================================
# TRANSIENT ERRORS (Usually Retryable)
# =============================================================================


class TransientError(SpineError):
    """
    Temporary error that may succeed on retry.
    
    Examples:
    - Network timeout
    - Rate limiting (429)
    - Service unavailable (503)
    - Database connection pool exhausted
    """
    
    default_category = ErrorCategory.NETWORK
    default_retryable = True


class NetworkError(TransientError):
    """Network-related transient error."""
    
    default_category = ErrorCategory.NETWORK


class TimeoutError(TransientError):
    """Operation timed out."""
    
    default_category = ErrorCategory.NETWORK


class RateLimitError(TransientError):
    """Rate limit exceeded."""
    
    default_category = ErrorCategory.NETWORK
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after: int = 60,
        **kwargs: Any,
    ):
        super().__init__(message, retry_after=retry_after, **kwargs)


class DatabaseConnectionError(TransientError):
    """Database connection or pool error."""
    
    default_category = ErrorCategory.DATABASE


# =============================================================================
# SOURCE ERRORS
# =============================================================================


class SourceError(SpineError):
    """
    Error from a data source.
    
    Default not retryable (e.g., file not found, 404).
    Subclasses may override for specific cases.
    """
    
    default_category = ErrorCategory.SOURCE
    default_retryable = False


class SourceNotFoundError(SourceError):
    """Source data not found (file, API endpoint, etc.)."""
    
    pass


class SourceUnavailableError(SourceError):
    """Source temporarily unavailable (may be retryable)."""
    
    default_retryable = True


class ParseError(SourceError):
    """Error parsing source data."""
    
    default_category = ErrorCategory.PARSE
    default_retryable = False


# =============================================================================
# VALIDATION ERRORS
# =============================================================================


class ValidationError(SpineError):
    """
    Data validation error.
    
    Never retryable - data must be fixed.
    """
    
    default_category = ErrorCategory.VALIDATION
    default_retryable = False
    
    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: Any = None,
        constraint: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value
        self.constraint = constraint
    
    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.field:
            result["field"] = self.field
        if self.value is not None:
            result["value"] = repr(self.value)
        if self.constraint:
            result["constraint"] = self.constraint
        return result


class SchemaError(ValidationError):
    """Schema validation error."""
    
    pass


class ConstraintError(ValidationError):
    """Constraint violation error."""
    
    pass


# =============================================================================
# CONFIGURATION ERRORS
# =============================================================================


class ConfigError(SpineError):
    """
    Configuration error.
    
    Never retryable - configuration must be fixed.
    """
    
    default_category = ErrorCategory.CONFIG
    default_retryable = False


class MissingConfigError(ConfigError):
    """Required configuration is missing."""
    
    def __init__(self, key: str, message: str | None = None):
        self.key = key
        super().__init__(message or f"Missing required configuration: {key}")


class InvalidConfigError(ConfigError):
    """Configuration value is invalid."""
    
    def __init__(self, key: str, value: Any, message: str | None = None):
        self.key = key
        self.value = value
        super().__init__(message or f"Invalid configuration for {key}: {value!r}")


# =============================================================================
# AUTHENTICATION/AUTHORIZATION ERRORS
# =============================================================================


class AuthError(SpineError):
    """Authentication or authorization error."""
    
    default_category = ErrorCategory.AUTH
    default_retryable = False


class AuthenticationError(AuthError):
    """Failed to authenticate."""
    
    pass


class AuthorizationError(AuthError):
    """Not authorized to perform action."""
    
    pass


# =============================================================================
# PIPELINE/ORCHESTRATION ERRORS
# =============================================================================


class PipelineError(SpineError):
    """Pipeline execution error."""
    
    default_category = ErrorCategory.PIPELINE
    default_retryable = False


class PipelineNotFoundError(PipelineError):
    """Pipeline not found in registry."""
    
    def __init__(self, name: str):
        self.pipeline_name = name
        super().__init__(f"Pipeline not found: {name}")


class BadParamsError(PipelineError):
    """Invalid pipeline parameters."""
    
    def __init__(
        self,
        message: str,
        *,
        missing_params: list[str] | None = None,
        invalid_params: list[str] | None = None,
        **kwargs: Any,
    ):
        super().__init__(message, **kwargs)
        self.missing_params = missing_params or []
        self.invalid_params = invalid_params or []


class OrchestrationError(SpineError):
    """Workflow or scheduler error."""
    
    default_category = ErrorCategory.ORCHESTRATION
    default_retryable = False


class WorkflowError(OrchestrationError):
    """Workflow execution error."""
    
    pass


class ScheduleError(OrchestrationError):
    """Schedule configuration or execution error."""
    
    pass


# =============================================================================
# STORAGE ERRORS
# =============================================================================


class StorageError(SpineError):
    """Storage-related error (disk, S3, etc.)."""
    
    default_category = ErrorCategory.STORAGE
    default_retryable = False


class DatabaseError(SpineError):
    """Database query or transaction error."""
    
    default_category = ErrorCategory.DATABASE
    default_retryable = False


class QueryError(DatabaseError):
    """SQL query error."""
    
    pass


class IntegrityError(DatabaseError):
    """Database integrity constraint violation."""
    
    pass


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def is_retryable(error: Exception) -> bool:
    """Check if an error is retryable."""
    if isinstance(error, SpineError):
        return error.retryable
    # Common Python exceptions that are usually retryable
    retryable_types = (
        ConnectionError,
        ConnectionResetError,
        ConnectionRefusedError,
        BrokenPipeError,
        OSError,  # Includes network errors
    )
    return isinstance(error, retryable_types)


def get_retry_after(error: Exception) -> int | None:
    """Get retry delay from error, if specified."""
    if isinstance(error, SpineError):
        return error.retry_after
    return None


def categorize_error(error: Exception) -> ErrorCategory:
    """Get the category of an error."""
    if isinstance(error, SpineError):
        return error.category
    # Map common exceptions to categories
    if isinstance(error, (ConnectionError, OSError)):
        return ErrorCategory.NETWORK
    if isinstance(error, ValueError):
        return ErrorCategory.VALIDATION
    if isinstance(error, (KeyError, AttributeError)):
        return ErrorCategory.CONFIG
    return ErrorCategory.UNKNOWN


__all__ = [
    # Category enum
    "ErrorCategory",
    # Context
    "ErrorContext",
    # Base
    "SpineError",
    # Transient
    "TransientError",
    "NetworkError",
    "TimeoutError",
    "RateLimitError",
    "DatabaseConnectionError",
    # Source
    "SourceError",
    "SourceNotFoundError",
    "SourceUnavailableError",
    "ParseError",
    # Validation
    "ValidationError",
    "SchemaError",
    "ConstraintError",
    # Config
    "ConfigError",
    "MissingConfigError",
    "InvalidConfigError",
    # Auth
    "AuthError",
    "AuthenticationError",
    "AuthorizationError",
    # Pipeline/Orchestration
    "PipelineError",
    "PipelineNotFoundError",
    "BadParamsError",
    "OrchestrationError",
    "WorkflowError",
    "ScheduleError",
    # Storage
    "StorageError",
    "DatabaseError",
    "QueryError",
    "IntegrityError",
    # Utilities
    "is_retryable",
    "get_retry_after",
    "categorize_error",
]
