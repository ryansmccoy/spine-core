# Structured Error Framework

> **Purpose:** Define typed errors with categories for retry decisions and alerting.
> **Tier:** Basic (spine-core)
> **Module:** `spine.core.errors`
> **Last Updated:** 2026-01-11

---

## Overview

Currently, the codebase has minimal error typing:
- `SpineError` base class in `spine.framework.exceptions`
- Orchestration-specific errors in `spine.orchestration.exceptions`

This makes it hard to:
- Distinguish retryable vs permanent errors
- Route errors to appropriate handlers
- Make retry decisions automatically
- Generate meaningful alerts

The **Structured Error Framework** provides:
- Error categories for classification
- Retryable flag for retry decisions
- Error metadata for alerting
- Consistent exception hierarchy

---

## Design Principles

1. **Categorical** - Every error has a category
2. **Retryable Flag** - Clear signal for retry logic
3. **Metadata** - Rich context for debugging/alerting
4. **Hierarchical** - Inheritance for handling
5. **Errors as Values** - Use `StepResult` pattern for flow control

> **Design Principle Note: Immutability (#5)**
> 
> `SpineError.with_context()` mutates the error in place rather than returning 
> a new instance. This is a **pragmatic exception** because:
> - Python exceptions are traditionally mutable
> - Context is typically added immediately after raising
> - Copying exceptions is non-trivial due to traceback handling
> 
> For flow control (where immutability matters), use `StepResult` or `Result[T]`
> patterns instead of exceptions. See [DESIGN_PRINCIPLES.md](../../llm-prompts/reference/DESIGN_PRINCIPLES.md#7-errors-as-values).
5. **Serializable** - Can be stored/transmitted

---

## Error Categories

| Category | Description | Retryable | Examples |
|----------|-------------|-----------|----------|
| `INTERNAL` | Bug in code | No | TypeError, AttributeError |
| `CONFIGURATION` | Invalid config | No | Missing env var, bad schema |
| `VALIDATION` | Invalid input | No | Bad date format, missing field |
| `SOURCE` | Data fetch failed | Maybe | File not found, API error |
| `TRANSFORM` | Processing failed | No | Parse error, calculation error |
| `LOAD` | Data write failed | Maybe | DB constraint, disk full |
| `TRANSIENT` | Temporary failure | Yes | Network timeout, 503 error |
| `DEPENDENCY` | External system down | Yes | API unavailable, DB connection |
| `TIMEOUT` | Operation timeout | Yes | Long-running query |
| `RATE_LIMIT` | Throttled | Yes | API rate limit hit |
| `PERMISSION` | Access denied | No | Auth failure, forbidden |
| `RESOURCE` | Resource exhausted | Maybe | Memory, disk, connections |

---

## Core Types

```python
# spine/core/errors.py
"""
Structured error types for spine framework.

Every error has:
- category: Classification for handling
- retryable: Whether retry might succeed
- metadata: Additional context

Usage:
    from spine.core.errors import SourceError, TransientError
    
    try:
        data = fetch_from_api()
    except requests.Timeout:
        raise TransientError("API timeout", metadata={"url": url})
    except requests.HTTPError as e:
        if e.response.status_code >= 500:
            raise TransientError(f"Server error: {e.response.status_code}")
        else:
            raise SourceError(f"Client error: {e.response.status_code}")
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from enum import Enum


class ErrorCategory(str, Enum):
    """Error categories for classification."""
    INTERNAL = "INTERNAL"
    CONFIGURATION = "CONFIGURATION"
    VALIDATION = "VALIDATION"
    SOURCE = "SOURCE"
    TRANSFORM = "TRANSFORM"
    LOAD = "LOAD"
    TRANSIENT = "TRANSIENT"
    DEPENDENCY = "DEPENDENCY"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    PERMISSION = "PERMISSION"
    RESOURCE = "RESOURCE"


@dataclass
class ErrorContext:
    """
    Context for an error occurrence.
    
    Captured automatically when error is raised.
    """
    timestamp: datetime = field(default_factory=datetime.utcnow)
    pipeline: str | None = None
    step: str | None = None
    execution_id: str | None = None
    partition_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/transmission."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "pipeline": self.pipeline,
            "step": self.step,
            "execution_id": self.execution_id,
            "partition_key": self.partition_key,
            "metadata": self.metadata,
        }


class SpineError(Exception):
    """
    Base exception for all spine errors.
    
    Attributes:
        category: Error classification
        retryable: Whether retry might succeed
        context: Additional context
    """
    category: ErrorCategory = ErrorCategory.INTERNAL
    retryable: bool = False
    
    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory | None = None,
        retryable: bool | None = None,
        cause: Exception | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        
        # Override class defaults if provided
        if category is not None:
            self.category = category
        if retryable is not None:
            self.retryable = retryable
        
        self.cause = cause
        self.context = ErrorContext(metadata=metadata or {})
    
    def with_context(
        self,
        pipeline: str | None = None,
        step: str | None = None,
        execution_id: str | None = None,
        partition_key: str | None = None,
        **metadata,
    ) -> "SpineError":
        """Add context to error (fluent interface)."""
        if pipeline:
            self.context.pipeline = pipeline
        if step:
            self.context.step = step
        if execution_id:
            self.context.execution_id = execution_id
        if partition_key:
            self.context.partition_key = partition_key
        self.context.metadata.update(metadata)
        return self
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/alerting."""
        return {
            "type": type(self).__name__,
            "message": self.message,
            "category": self.category.value,
            "retryable": self.retryable,
            "context": self.context.to_dict(),
            "cause": str(self.cause) if self.cause else None,
        }
    
    def __str__(self) -> str:
        return f"[{self.category.value}] {self.message}"


# =============================================================================
# Specific Error Types
# =============================================================================

class ConfigurationError(SpineError):
    """Configuration is invalid or missing."""
    category = ErrorCategory.CONFIGURATION
    retryable = False


class ValidationError(SpineError):
    """Input validation failed."""
    category = ErrorCategory.VALIDATION
    retryable = False


class SourceError(SpineError):
    """Error fetching data from source."""
    category = ErrorCategory.SOURCE
    retryable = False  # Subclasses may override


class TransformError(SpineError):
    """Error during data transformation."""
    category = ErrorCategory.TRANSFORM
    retryable = False


class LoadError(SpineError):
    """Error writing data to destination."""
    category = ErrorCategory.LOAD
    retryable = False  # May be retryable for transient DB issues


class TransientError(SpineError):
    """Temporary failure - retry may succeed."""
    category = ErrorCategory.TRANSIENT
    retryable = True


class DependencyError(SpineError):
    """External dependency unavailable."""
    category = ErrorCategory.DEPENDENCY
    retryable = True


class TimeoutError(SpineError):
    """Operation timed out."""
    category = ErrorCategory.TIMEOUT
    retryable = True


class RateLimitError(SpineError):
    """Rate limit exceeded."""
    category = ErrorCategory.RATE_LIMIT
    retryable = True
    
    def __init__(
        self,
        message: str,
        *,
        retry_after: int | None = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after  # Seconds to wait


class PermissionError(SpineError):
    """Access denied."""
    category = ErrorCategory.PERMISSION
    retryable = False


class ResourceError(SpineError):
    """Resource exhausted (memory, disk, connections)."""
    category = ErrorCategory.RESOURCE
    retryable = True  # May recover after cleanup
```

---

## Error Handling Patterns

### In Pipelines

```python
# spine/domains/finra/otc_transparency/pipelines.py
from spine.core.errors import (
    SourceError,
    TransformError,
    ValidationError,
    TransientError,
)
from spine.framework.pipelines import Pipeline


@register_pipeline("finra.otc_transparency.ingest_week")
class IngestWeekPipeline(Pipeline):
    def run(self) -> PipelineResult:
        try:
            # Validate params
            tier = self.params.get("tier")
            if not tier:
                raise ValidationError("tier parameter is required")
            
            # Fetch data
            try:
                source = self._create_source()
                result = source.fetch()
            except requests.Timeout as e:
                raise TransientError(
                    "FINRA API timeout",
                    cause=e,
                    metadata={"url": source.url},
                )
            except requests.HTTPError as e:
                if e.response.status_code >= 500:
                    raise TransientError(f"FINRA API error: {e.response.status_code}")
                raise SourceError(f"FINRA API rejected request: {e.response.status_code}")
            
            # Transform data
            try:
                records = self._parse_records(result.records)
            except ValueError as e:
                raise TransformError(f"Failed to parse records: {e}", cause=e)
            
            return PipelineResult.completed(metrics={"count": len(records)})
            
        except SpineError as e:
            # Add pipeline context
            e.with_context(
                pipeline=self.name,
                execution_id=self.execution_id,
                partition_key=f"{self.params.get('week_ending')}|{tier}",
            )
            raise
```

### In Orchestration

```python
# spine/orchestration/workflow_runner.py
from spine.core.errors import SpineError, TransientError

class WorkflowRunner:
    def _execute_step(self, step: Step, context: WorkflowContext) -> StepResult:
        try:
            result = step.handler(context, step.config)
            return result
            
        except SpineError as e:
            # Add step context
            e.with_context(
                step=step.name,
                execution_id=context.run_id,
            )
            
            # Decide on retry based on error type
            if e.retryable and step.on_error == ErrorPolicy.RETRY:
                return self._retry_step(step, context, e)
            
            return StepResult.fail(
                error=str(e),
                category=e.category.value,
            )
            
        except Exception as e:
            # Wrap unexpected errors
            spine_error = SpineError(
                f"Unexpected error in step {step.name}: {e}",
                cause=e,
            )
            return StepResult.fail(error=str(spine_error))
```

### For Alerting

```python
# spine/framework/alerts/router.py
from spine.core.errors import SpineError, ErrorCategory

class AlertRouter:
    """Route errors to appropriate alert channels based on category."""
    
    def __init__(self):
        self.routes: dict[ErrorCategory, list[AlertChannel]] = {}
    
    def add_route(self, category: ErrorCategory, channel: AlertChannel):
        """Add channel for error category."""
        if category not in self.routes:
            self.routes[category] = []
        self.routes[category].append(channel)
    
    def route_error(self, error: SpineError) -> list[bool]:
        """Send error to appropriate channels."""
        channels = self.routes.get(error.category, [])
        
        alert = Alert(
            severity=self._category_to_severity(error.category),
            title=f"[{error.category.value}] Pipeline Error",
            message=error.message,
            source=error.context.pipeline or "unknown",
            execution_id=error.context.execution_id or "unknown",
            metadata={
                "category": error.category.value,
                "retryable": error.retryable,
                **error.context.metadata,
            },
        )
        
        return [channel.send(alert) for channel in channels]
    
    def _category_to_severity(self, category: ErrorCategory) -> str:
        """Map error category to alert severity."""
        severity_map = {
            ErrorCategory.INTERNAL: "CRITICAL",
            ErrorCategory.CONFIGURATION: "ERROR",
            ErrorCategory.VALIDATION: "WARNING",
            ErrorCategory.SOURCE: "ERROR",
            ErrorCategory.TRANSFORM: "ERROR",
            ErrorCategory.LOAD: "ERROR",
            ErrorCategory.TRANSIENT: "WARNING",
            ErrorCategory.DEPENDENCY: "ERROR",
            ErrorCategory.TIMEOUT: "WARNING",
            ErrorCategory.RATE_LIMIT: "INFO",
            ErrorCategory.PERMISSION: "ERROR",
            ErrorCategory.RESOURCE: "CRITICAL",
        }
        return severity_map.get(category, "ERROR")
```

---

## Error Recording

Errors are recorded in `core_anomalies` table for audit:

```python
# spine/core/anomalies.py
from spine.core.errors import SpineError, ErrorCategory

def record_error(conn, error: SpineError, domain: str):
    """Record error as anomaly for audit trail."""
    severity = _category_to_severity(error.category)
    
    conn.execute("""
        INSERT INTO core_anomalies (
            anomaly_id, domain, stage, partition_key,
            severity, category, message, detected_at, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        generate_id(),
        domain,
        error.context.step or "UNKNOWN",
        error.context.partition_key or "UNKNOWN",
        severity,
        error.category.value,
        error.message,
        datetime.utcnow().isoformat(),
        json.dumps(error.to_dict()),
    ))
    conn.commit()


def _category_to_severity(category: ErrorCategory) -> str:
    """Map error category to anomaly severity."""
    if category in (ErrorCategory.INTERNAL, ErrorCategory.RESOURCE):
        return "CRITICAL"
    elif category in (ErrorCategory.TRANSIENT, ErrorCategory.RATE_LIMIT):
        return "WARN"
    else:
        return "ERROR"
```

---

## Testing

```python
# tests/core/test_errors.py
import pytest
from spine.core.errors import (
    SpineError,
    SourceError,
    TransientError,
    RateLimitError,
    ErrorCategory,
)


class TestSpineError:
    def test_basic_error(self):
        error = SpineError("Something went wrong")
        
        assert str(error) == "[INTERNAL] Something went wrong"
        assert error.category == ErrorCategory.INTERNAL
        assert error.retryable is False
    
    def test_error_with_context(self):
        error = SourceError("File not found").with_context(
            pipeline="ingest",
            execution_id="exec-123",
            file_path="/data/missing.csv",
        )
        
        assert error.context.pipeline == "ingest"
        assert error.context.execution_id == "exec-123"
        assert error.context.metadata["file_path"] == "/data/missing.csv"
    
    def test_transient_error_is_retryable(self):
        error = TransientError("Network timeout")
        assert error.retryable is True
        assert error.category == ErrorCategory.TRANSIENT
    
    def test_rate_limit_error_has_retry_after(self):
        error = RateLimitError("Too many requests", retry_after=60)
        assert error.retry_after == 60
        assert error.retryable is True
    
    def test_error_serialization(self):
        error = SourceError("API failed").with_context(
            pipeline="fetch",
            url="https://api.example.com",
        )
        
        data = error.to_dict()
        
        assert data["type"] == "SourceError"
        assert data["category"] == "SOURCE"
        assert data["context"]["pipeline"] == "fetch"
        assert data["context"]["metadata"]["url"] == "https://api.example.com"
    
    def test_error_with_cause(self):
        original = ValueError("Bad value")
        error = TransformError("Parse failed", cause=original)
        
        assert error.cause is original
        assert "Bad value" in error.to_dict()["cause"]
```

---

## Migration Guide

### Existing Code

Before:
```python
try:
    data = fetch_data()
except Exception as e:
    log.error(f"Failed: {e}")
    raise
```

After:
```python
from spine.core.errors import SourceError, TransientError

try:
    data = fetch_data()
except requests.Timeout as e:
    raise TransientError("Fetch timeout", cause=e)
except requests.HTTPError as e:
    raise SourceError(f"Fetch failed: {e.response.status_code}", cause=e)
except Exception as e:
    raise SourceError(f"Unexpected fetch error: {e}", cause=e)
```

### Error Handling

Before:
```python
if result.status == "failed":
    return {"error": result.error}
```

After:
```python
if result.status == "failed":
    return {
        "error": result.error,
        "category": result.error_category,
        "retryable": result.error_category in ("TRANSIENT", "TIMEOUT", "RATE_LIMIT"),
    }
```

---

## Next Steps

1. Implement database adapters: [04-DATABASE-ADAPTERS.md](./04-DATABASE-ADAPTERS.md)
2. Build alerting framework: [05-ALERTING-FRAMEWORK.md](./05-ALERTING-FRAMEWORK.md)
3. Update FINRA pipelines: [10-FINRA-EXAMPLE.md](./10-FINRA-EXAMPLE.md)
