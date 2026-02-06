"""
Structured error types for Spine framework.

Provides a comprehensive hierarchy of typed errors with rich metadata for
retry decisions, error categorization, alerting, reporting, and root cause
analysis through error chaining.

The error hierarchy is central to spine-core's reliability story. Instead of
generic exceptions that lose context, SpineError and its subclasses carry:
- **Category:** What kind of error (network, validation, config, etc.)
- **Retryable:** Whether the operation can be retried automatically
- **Retry-after:** How long to wait before retrying
- **Context:** Rich metadata including pipeline, source, URL, and custom fields
- **Cause:** Chained underlying exception for root cause analysis

Manifesto:
    - **Typed Error Hierarchy:** Different error types for different domains
    - **Explicit Retry Semantics:** Each error knows if it's retryable
    - **Rich Context:** Errors carry metadata for logging and alerting
    - **Error Chaining:** Preserve original exceptions while adding context

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────────┐
        │                       SpineError                                 │
        │  (category, retryable, retry_after, context, cause)             │
        ├─────────────────────────────────────────────────────────────────┤
        │                                                                  │
        │  TransientError    SourceError       ValidationError            │
        │  (retryable=True)  (SOURCE)          (VALIDATION)               │
        │       │                │                   │                     │
        │  NetworkError      ParseError        SchemaError                │
        │  TimeoutError      SourceNotFound    ConstraintError            │
        │  RateLimitError    SourceUnavailable                            │
        │                                                                  │
        │  ConfigError       AuthError         PipelineError              │
        │  (CONFIG)          (AUTH)            (PIPELINE)                 │
        │       │                │                   │                     │
        │  MissingConfig     Authentication    BadParamsError             │
        │  InvalidConfig     Authorization     PipelineNotFound           │
        │                                                                  │
        │  StorageError      DatabaseError     OrchestrationError         │
        │  (STORAGE)         (DATABASE)        (ORCHESTRATION)            │
        │                         │                   │                    │
        │                    QueryError        WorkflowError              │
        │                    IntegrityError    ScheduleError              │
        └─────────────────────────────────────────────────────────────────┘

Features:
    - **ErrorCategory enum:** Standard categories for classification and routing
    - **ErrorContext dataclass:** Structured metadata (pipeline, source, URL, etc.)
    - **SpineError base class:** Common interface for all errors
    - **Transient errors:** Network, timeout, rate limit - usually retryable
    - **Source errors:** Upstream API/file errors - context-dependent retry
    - **Validation errors:** Schema/constraint violations - never retryable
    - **Config errors:** Missing/invalid settings - never retryable
    - **Auth errors:** Authentication/authorization - never retryable
    - **Pipeline/Orchestration errors:** Execution failures

Examples:
    Creating a retryable network error:

    >>> error = TransientError("Connection timeout", retry_after=30)
    >>> error.retryable
    True
    >>> error.retry_after
    30

    Adding context to an error:

    >>> error = SourceError("API returned 500")
    >>> error.with_context(source_name="finra_api", url="https://api.finra.org")
    SourceError(...)
    >>> error.context.source_name
    'finra_api'

    Chaining errors for root cause:

    >>> try:
    ...     raise ConnectionError("DNS failure")
    ... except ConnectionError as e:
    ...     raise NetworkError("Failed to reach API", cause=e)
    Traceback (most recent call last):
    ...
    NetworkError: Failed to reach API

Performance:
    - **Error creation:** O(1), dataclass-based context
    - **to_dict():** O(n) where n is context fields
    - **Memory:** Minimal - slots not used to allow subclassing

Guardrails:
    ❌ DON'T: Use generic Exception - loses all metadata
    ✅ DO: Use appropriate SpineError subclass

    ❌ DON'T: Set retryable=True for validation/config errors
    ✅ DO: Let the error type's default_retryable handle it

    ❌ DON'T: Swallow the original exception
    ✅ DO: Pass it as cause= for error chaining

Context:
    - **Problem:** Generic exceptions lose context and retry semantics
    - **Solution:** Typed hierarchy with rich metadata and explicit retry flags
    - **Alternatives:** Plain exceptions, error codes, custom result types

Tags:
    error-handling, exception-hierarchy, retry-logic, error-context,
    spine-core, observability, alerting

Doc-Types:
    - API Reference
    - Error Handling Guide
    - Retry Strategy Documentation

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
    Standard error categories for classification and routing.

    ErrorCategory is a string enum that classifies errors into domains for
    alerting, reporting, and retry decisions. Each SpineError has a category
    that determines how it should be handled by monitoring and retry systems.

    Categories are grouped by their typical retry behavior:
    - **Infrastructure (usually transient):** NETWORK, DATABASE, STORAGE
    - **Source/data errors:** SOURCE, PARSE, VALIDATION
    - **Configuration (never retryable):** CONFIG, AUTH
    - **Application errors:** PIPELINE, ORCHESTRATION
    - **Internal errors:** INTERNAL, UNKNOWN

    Manifesto:
        - **Routing by category:** Alerts go to right team (infra vs app)
        - **Retry heuristics:** Category suggests default retry behavior
        - **Consistent classification:** Same categories across all spine projects
        - **String enum:** Category values are human-readable strings

    Architecture:
        ::

            ┌──────────────────────────────────────────────────────────┐
            │                    ErrorCategory                          │
            ├──────────────────────────────────────────────────────────┤
            │  Infrastructure    │  Data           │  Application      │
            │  ───────────────   │  ────           │  ───────────      │
            │  NETWORK           │  SOURCE         │  PIPELINE         │
            │  DATABASE          │  PARSE          │  ORCHESTRATION    │
            │  STORAGE           │  VALIDATION     │                   │
            ├──────────────────────────────────────────────────────────┤
            │  Configuration     │  Internal                           │
            │  ─────────────     │  ────────                           │
            │  CONFIG            │  INTERNAL                           │
            │  AUTH              │  UNKNOWN                            │
            └──────────────────────────────────────────────────────────┘

    Examples:
        Checking category for retry decision:

        >>> category = ErrorCategory.NETWORK
        >>> category in [ErrorCategory.NETWORK, ErrorCategory.DATABASE]
        True
        >>> category.value
        'NETWORK'

        Using in error creation:

        >>> error = SpineError("Connection failed", category=ErrorCategory.NETWORK)
        >>> error.category == ErrorCategory.NETWORK
        True

    Performance:
        - **O(1)** enum lookup
        - **String comparison:** Uses string value for serialization

    Guardrails:
        ❌ DON'T: Create custom categories as strings
        ✅ DO: Use predefined ErrorCategory values

        ❌ DON'T: Use UNKNOWN for known error types
        ✅ DO: Classify errors into appropriate categories

    Attributes:
        NETWORK: Connection, timeout, DNS errors
        DATABASE: Connection pool, query timeout
        STORAGE: Disk, S3, file system errors
        SOURCE: Upstream API, file not found
        PARSE: Data parsing, format errors
        VALIDATION: Schema, constraint violations
        CONFIG: Missing config, invalid settings
        AUTH: Authentication, authorization
        PIPELINE: Pipeline execution failures
        ORCHESTRATION: Workflow, scheduler errors
        INTERNAL: Bugs, unexpected state
        UNKNOWN: Uncategorized errors

    Tags:
        error-category, classification, alerting, retry-logic, spine-core

    Doc-Types:
        - API Reference
        - Error Handling Guide
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
    Structured metadata context for errors.

    ErrorContext provides a standardized way to attach metadata to errors for
    logging, alerting, and debugging. Instead of passing ad-hoc dictionaries,
    ErrorContext has typed fields for common metadata like pipeline name,
    execution ID, source, and HTTP details.

    Any additional metadata can be stored in the `metadata` dict for flexibility.
    The `to_dict()` method serializes all non-None fields for logging.

    Manifesto:
        - **Structured over ad-hoc:** Typed fields for common metadata
        - **Extensible:** metadata dict for custom fields
        - **Serialization-ready:** to_dict() for logging/JSON
        - **Optional fields:** Only set what's relevant

    Architecture:
        ::

            ┌─────────────────────────────────────────────────────────┐
            │                    ErrorContext                          │
            ├─────────────────────────────────────────────────────────┤
            │  Execution        │  Source         │  Request          │
            │  ──────────       │  ──────         │  ───────          │
            │  pipeline         │  source_name    │  url              │
            │  workflow         │  source_type    │  http_status      │
            │  step             │                 │                   │
            │  run_id           │                 │                   │
            │  execution_id     │                 │                   │
            ├─────────────────────────────────────────────────────────┤
            │  metadata: dict[str, Any]  (extensible)                 │
            └─────────────────────────────────────────────────────────┘

    Examples:
        Creating context with execution info:

        >>> ctx = ErrorContext(
        ...     pipeline="fetch_filings",
        ...     execution_id="abc-123",
        ...     source_name="sec_api"
        ... )
        >>> ctx.to_dict()
        {'pipeline': 'fetch_filings', 'execution_id': 'abc-123', 'source_name': 'sec_api'}

        Adding custom metadata:

        >>> ctx = ErrorContext()
        >>> ctx.metadata["filing_id"] = "0001234567-24-000001"
        >>> ctx.metadata["cik"] = "0001234567"
        >>> ctx.to_dict()
        {'filing_id': '0001234567-24-000001', 'cik': '0001234567'}

        HTTP error context:

        >>> ctx = ErrorContext(
        ...     url="https://api.sec.gov/filings",
        ...     http_status=429
        ... )
        >>> ctx.to_dict()
        {'url': 'https://api.sec.gov/filings', 'http_status': 429}

    Performance:
        - **to_dict():** O(n) where n is number of fields
        - **Memory:** Dataclass with default factory for metadata

    Guardrails:
        ❌ DON'T: Store large objects in metadata
        ✅ DO: Store IDs and small values for logging

        ❌ DON'T: Store sensitive data (passwords, tokens)
        ✅ DO: Redact sensitive values before adding

    Attributes:
        pipeline: Name of the pipeline where error occurred
        workflow: Name of the workflow
        step: Name of the step within pipeline
        run_id: Run identifier
        execution_id: Unique execution identifier (from ExecutionContext)
        source_name: Name of data source (e.g., "sec_api", "finra_api")
        source_type: Type of source (e.g., "api", "file", "database")
        url: URL that was being accessed
        http_status: HTTP status code if applicable
        metadata: Additional key-value pairs

    Tags:
        error-context, metadata, logging, observability, spine-core

    Doc-Types:
        - API Reference
        - Error Handling Guide
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

    SpineError is the foundation of spine-core's error hierarchy. Every error
    in the Spine ecosystem should extend SpineError to ensure consistent
    metadata, retry semantics, and serialization capabilities.

    All SpineError instances carry:
    - **category:** ErrorCategory enum for classification and routing
    - **retryable:** Boolean indicating if operation can be retried
    - **retry_after:** Optional seconds to wait before retry
    - **context:** ErrorContext with structured metadata
    - **cause:** Optional underlying exception for chaining

    Subclasses should set appropriate `default_category` and `default_retryable`
    class attributes to provide sensible defaults for their domain.

    Manifesto:
        - **Single base class:** All spine errors inherit from SpineError
        - **Explicit retry semantics:** Every error knows if it's retryable
        - **Rich context:** Errors carry metadata for observability
        - **Error chaining:** Preserve original exceptions as cause
        - **Fluent API:** with_context() for adding metadata after creation

    Architecture:
        ::

            ┌─────────────────────────────────────────────────────────────┐
            │                       SpineError                             │
            ├─────────────────────────────────────────────────────────────┤
            │  Class Attributes                                            │
            │  ────────────────                                            │
            │  default_category: ErrorCategory = INTERNAL                  │
            │  default_retryable: bool = False                             │
            ├─────────────────────────────────────────────────────────────┤
            │  Instance Attributes                                         │
            │  ───────────────────                                         │
            │  message: str                                                │
            │  category: ErrorCategory                                     │
            │  retryable: bool                                             │
            │  retry_after: int | None                                     │
            │  context: ErrorContext                                       │
            │  cause: Exception | None                                     │
            ├─────────────────────────────────────────────────────────────┤
            │  Methods                                                     │
            │  ───────                                                     │
            │  with_context(**kwargs) -> SpineError  # fluent context add  │
            │  to_dict() -> dict  # serialization for logging              │
            └─────────────────────────────────────────────────────────────┘

    Features:
        - **Category-based classification:** Routes to correct alerting channel
        - **Retry semantics:** Automatic retry decisions based on retryable flag
        - **Fluent context API:** Chain with_context() calls
        - **JSON serialization:** to_dict() for structured logging
        - **Error chaining:** cause attribute and __cause__ for tracebacks

    Examples:
        Basic error creation:

        >>> error = SpineError("Something went wrong")
        >>> error.category
        <ErrorCategory.INTERNAL: 'INTERNAL'>
        >>> error.retryable
        False

        Creating with custom attributes:

        >>> error = SpineError(
        ...     "API timeout",
        ...     category=ErrorCategory.NETWORK,
        ...     retryable=True,
        ...     retry_after=30
        ... )
        >>> error.retryable
        True
        >>> error.retry_after
        30

        Adding context fluently:

        >>> error = SpineError("Fetch failed")
        >>> error.with_context(
        ...     pipeline="fetch_filings",
        ...     source_name="sec_api",
        ...     url="https://api.sec.gov"
        ... )
        SpineError(...)
        >>> error.context.pipeline
        'fetch_filings'

        Chaining errors:

        >>> try:
        ...     raise ConnectionError("DNS lookup failed")
        ... except ConnectionError as e:
        ...     error = SpineError("Network error", cause=e)
        >>> error.cause
        ConnectionError('DNS lookup failed')

        Serializing for logging:

        >>> error = SpineError("Test error", category=ErrorCategory.VALIDATION)
        >>> d = error.to_dict()
        >>> d["category"]
        'VALIDATION'
        >>> d["retryable"]
        False

    Performance:
        - **O(1)** for creation
        - **to_dict():** O(n) where n is context fields
        - **with_context():** O(k) where k is kwargs count

    Guardrails:
        ❌ DON'T: Use plain Exception for expected error cases
        ✅ DO: Use appropriate SpineError subclass

        ❌ DON'T: Override retryable to True for validation/config errors
        ✅ DO: Use TransientError subclass for retryable errors

        ❌ DON'T: Forget to chain the original exception
        ✅ DO: Always pass cause= when wrapping exceptions

    Context:
        - **Problem:** Python exceptions lose retry semantics and context
        - **Solution:** Rich base exception with category, retryable, and context
        - **Alternatives:** Error codes, result types with error info

    Tags:
        exception, error-hierarchy, retry-logic, error-context,
        spine-core, observability, base-class

    Doc-Types:
        - API Reference
        - Error Handling Guide
        - Subclassing Tutorial
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

    TransientError represents errors caused by temporary conditions that may
    resolve on their own: network timeouts, rate limiting, service unavailability,
    database connection pool exhaustion, etc. These errors are retryable by
    default.

    Use TransientError when the same operation, called again after a delay,
    has a reasonable chance of succeeding. Do NOT use for permanent failures
    like "file not found" or validation errors.

    Manifesto:
        - **Transient = retryable:** Default retryable=True
        - **Network category:** Default category is NETWORK
        - **Retry guidance:** Use retry_after to suggest delay
        - **Infrastructure focus:** For infrastructure/external service issues

    Architecture:
        ::

            ┌─────────────────────────────────────────────────────────────┐
            │                    TransientError                            │
            │             (default_retryable=True)                         │
            ├─────────────────────────────────────────────────────────────┤
            │                                                              │
            │  NetworkError      TimeoutError      RateLimitError          │
            │  (NETWORK)         (NETWORK)         (NETWORK,retry_after)   │
            │                                                              │
            │  DatabaseConnectionError                                     │
            │  (DATABASE)                                                  │
            │                                                              │
            └─────────────────────────────────────────────────────────────┘

    Examples:
        Basic transient error:

        >>> error = TransientError("Service temporarily unavailable")
        >>> error.retryable
        True
        >>> error.category
        <ErrorCategory.NETWORK: 'NETWORK'>

        With retry guidance:

        >>> error = TransientError("Rate limited", retry_after=60)
        >>> error.retry_after
        60

        Converting from requests exception:

        >>> import requests
        >>> try:
        ...     # response = requests.get(url, timeout=5)
        ...     raise TimeoutError("Connection timed out")
        ... except TimeoutError as e:
        ...     error = TransientError("API timeout", cause=e, retry_after=30)
        >>> error.retryable
        True

    Performance:
        - Same as SpineError - O(1) creation

    Guardrails:
        ❌ DON'T: Use for permanent failures (file not found, invalid data)
        ✅ DO: Use SourceError or ValidationError for non-transient issues

        ❌ DON'T: Retry forever - limit retry attempts
        ✅ DO: Use exponential backoff with max attempts

        ❌ DON'T: Ignore retry_after from APIs (429 responses)
        ✅ DO: Honor retry_after when the upstream specifies it

    Context:
        - **Problem:** Need to distinguish retryable from permanent errors
        - **Solution:** TransientError with retryable=True by default
        - **Alternatives:** Check error category/message, manual retry logic

    Tags:
        transient-error, retryable, network-error, retry-logic, spine-core

    Doc-Types:
        - API Reference
        - Retry Strategy Guide
        - Error Handling Tutorial
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
