"""
Result envelope for consistent success/failure handling.

Provides a typed Result[T] pattern that:
- Makes success/failure explicit
- Carries error context for failures
- Enables functional composition
- Avoids exception-based control flow

Design Principles:
- #7 Explicit over Implicit: No hidden exceptions
- #5 Pure Transformations: Map/flatMap for chaining
- #13 Observable: Errors carry context

Usage:
    from spine.core.result import Result, Ok, Err
    
    def fetch_data(url: str) -> Result[dict]:
        try:
            response = requests.get(url)
            response.raise_for_status()
            return Ok(response.json())
        except requests.HTTPError as e:
            return Err(SourceError("API error", cause=e))
    
    # Pattern matching
    result = fetch_data("https://api.example.com/data")
    match result:
        case Ok(data):
            process(data)
        case Err(error):
            log_error(error)
    
    # Chaining
    result = (
        fetch_data("https://api.example.com/data")
        .map(lambda d: d["items"])
        .flat_map(validate_items)
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar, overload

from spine.core.errors import SpineError, ErrorCategory


T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E", bound=Exception)


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """
    Successful result containing a value.
    
    Immutable and hashable (if value is hashable).
    """
    
    value: T
    
    def is_ok(self) -> bool:
        return True
    
    def is_err(self) -> bool:
        return False
    
    def unwrap(self) -> T:
        """Get the value. Safe for Ok."""
        return self.value
    
    def unwrap_or(self, default: T) -> T:
        """Get value or default (always returns value for Ok)."""
        return self.value
    
    def unwrap_or_else(self, f: Callable[[Exception], T]) -> T:
        """Get value or call f with error (always returns value for Ok)."""
        return self.value
    
    def map(self, f: Callable[[T], U]) -> Result[U]:
        """Transform the value if Ok."""
        return Ok(f(self.value))
    
    def flat_map(self, f: Callable[[T], Result[U]]) -> Result[U]:
        """Chain to another Result-returning function."""
        return f(self.value)
    
    def map_err(self, f: Callable[[Exception], Exception]) -> Result[T]:
        """Transform error if Err (no-op for Ok)."""
        return self
    
    def or_else(self, f: Callable[[Exception], Result[T]]) -> Result[T]:
        """Return self if Ok, otherwise call f with error."""
        return self
    
    def and_then(self, f: Callable[[T], Result[U]]) -> Result[U]:
        """Alias for flat_map."""
        return f(self.value)
    
    def inspect(self, f: Callable[[T], None]) -> Result[T]:
        """Call f with value for side effects, return self."""
        f(self.value)
        return self
    
    def inspect_err(self, f: Callable[[Exception], None]) -> Result[T]:
        """Call f with error for side effects (no-op for Ok)."""
        return self
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {"ok": True, "value": self.value}
    
    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass(frozen=True, slots=True)
class Err(Generic[T]):
    """
    Failed result containing an error.
    
    The error should be an Exception (preferably SpineError).
    """
    
    error: Exception
    
    def is_ok(self) -> bool:
        return False
    
    def is_err(self) -> bool:
        return True
    
    def unwrap(self) -> T:
        """Raise the error. Use only when you're sure it's Ok."""
        raise self.error
    
    def unwrap_or(self, default: T) -> T:
        """Get default since this is Err."""
        return default
    
    def unwrap_or_else(self, f: Callable[[Exception], T]) -> T:
        """Call f with error to get value."""
        return f(self.error)
    
    def map(self, f: Callable[[T], U]) -> Result[U]:
        """No-op for Err."""
        return Err(self.error)
    
    def flat_map(self, f: Callable[[T], Result[U]]) -> Result[U]:
        """No-op for Err."""
        return Err(self.error)
    
    def map_err(self, f: Callable[[Exception], Exception]) -> Result[T]:
        """Transform the error."""
        return Err(f(self.error))
    
    def or_else(self, f: Callable[[Exception], Result[T]]) -> Result[T]:
        """Call f with error to try recovery."""
        return f(self.error)
    
    def and_then(self, f: Callable[[T], Result[U]]) -> Result[U]:
        """No-op for Err."""
        return Err(self.error)
    
    def inspect(self, f: Callable[[T], None]) -> Result[T]:
        """No-op for Err."""
        return self
    
    def inspect_err(self, f: Callable[[Exception], None]) -> Result[T]:
        """Call f with error for side effects, return self."""
        f(self.error)
        return self
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        if isinstance(self.error, SpineError):
            return {"ok": False, "error": self.error.to_dict()}
        return {
            "ok": False,
            "error": {
                "error_type": type(self.error).__name__,
                "message": str(self.error),
            },
        }
    
    def __repr__(self) -> str:
        return f"Err({self.error!r})"


# Type alias for Result
Result = Ok[T] | Err[T]


# =============================================================================
# RESULT CONSTRUCTORS AND UTILITIES
# =============================================================================


def try_result(f: Callable[[], T]) -> Result[T]:
    """
    Execute a function and wrap result in Result.
    
    Usage:
        result = try_result(lambda: json.loads(data))
    """
    try:
        return Ok(f())
    except Exception as e:
        return Err(e)


def try_result_with(
    f: Callable[[], T],
    error_mapper: Callable[[Exception], Exception] | None = None,
) -> Result[T]:
    """
    Execute function and map exceptions.
    
    Usage:
        result = try_result_with(
            lambda: fetch_url(url),
            lambda e: SourceError("Fetch failed", cause=e)
        )
    """
    try:
        return Ok(f())
    except Exception as e:
        if error_mapper:
            return Err(error_mapper(e))
        return Err(e)


def collect_results(results: list[Result[T]]) -> Result[list[T]]:
    """
    Collect a list of Results into a Result of list.
    
    Returns Err if any result is Err (first error).
    Returns Ok with all values if all are Ok.
    
    Usage:
        results = [fetch(url) for url in urls]
        combined = collect_results(results)
    """
    values = []
    for result in results:
        match result:
            case Ok(value):
                values.append(value)
            case Err(error):
                return Err(error)
    return Ok(values)


def collect_all_errors(results: list[Result[T]]) -> Result[list[T]]:
    """
    Collect results, accumulating ALL errors.
    
    Returns Err with aggregated error if any failed.
    Returns Ok with all values if all succeeded.
    
    Usage:
        results = [validate(item) for item in items]
        combined = collect_all_errors(results)
    """
    values = []
    errors = []
    for result in results:
        match result:
            case Ok(value):
                values.append(value)
            case Err(error):
                errors.append(error)
    
    if errors:
        if len(errors) == 1:
            return Err(errors[0])
        # Aggregate multiple errors
        messages = [str(e) for e in errors]
        aggregated = SpineError(
            f"Multiple errors ({len(errors)}): {'; '.join(messages[:3])}{'...' if len(messages) > 3 else ''}",
            category=ErrorCategory.INTERNAL,
        )
        aggregated.context.metadata["error_count"] = len(errors)
        aggregated.context.metadata["errors"] = [str(e) for e in errors]
        return Err(aggregated)
    
    return Ok(values)


def partition_results(
    results: list[Result[T]],
) -> tuple[list[T], list[Exception]]:
    """
    Partition results into successes and failures.
    
    Returns (values, errors) tuple.
    
    Usage:
        values, errors = partition_results(results)
        if errors:
            log_errors(errors)
        process(values)
    """
    values = []
    errors = []
    for result in results:
        match result:
            case Ok(value):
                values.append(value)
            case Err(error):
                errors.append(error)
    return values, errors


@overload
def from_optional(value: T, error: Exception) -> Ok[T]: ...

@overload
def from_optional(value: None, error: Exception) -> Err[T]: ...

def from_optional(value: T | None, error: Exception) -> Result[T]:
    """
    Convert optional value to Result.
    
    Usage:
        result = from_optional(
            cache.get(key),
            SourceNotFoundError(f"Cache miss: {key}")
        )
    """
    if value is None:
        return Err(error)
    return Ok(value)


def from_bool(
    condition: bool,
    ok_value: T,
    error: Exception,
) -> Result[T]:
    """
    Create Result from boolean condition.
    
    Usage:
        result = from_bool(
            user.is_admin,
            user,
            AuthorizationError("Admin required")
        )
    """
    if condition:
        return Ok(ok_value)
    return Err(error)


__all__ = [
    # Types
    "Result",
    "Ok",
    "Err",
    # Constructors
    "try_result",
    "try_result_with",
    "from_optional",
    "from_bool",
    # Collectors
    "collect_results",
    "collect_all_errors",
    "partition_results",
]
