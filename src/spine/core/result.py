"""
Result envelope for consistent success/failure handling.

Provides a typed Result[T] pattern that makes success/failure explicit in the type
system, carries error context for failures, enables functional composition through
map/flatMap operations, and avoids exception-based control flow for expected errors.

The Result pattern is central to spine-core's design philosophy. Instead of throwing
exceptions that callers might forget to catch, operations return Ok[T] for success
or Err[T] for failure. This makes error handling explicit and composable, critical
for batch processing where one bad record shouldn't abort the entire job.

Manifesto:
    - **Explicit over Implicit:** No hidden exceptions that callers might miss
    - **Fail-fast discovery:** Type checker catches unhandled error paths
    - **Functional composition:** Chain operations with map/flat_map without
      nested try/except blocks
    - **Batch-friendly:** Collect results from many operations, handle errors
      at the end using collect_results() or partition_results()

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                     Result[T]                                │
        │                    (Type Alias)                              │
        ├─────────────────┬─────────────────┬─────────────────────────┤
        │     Ok[T]       │     Err[T]      │     Utilities           │
        │   (Success)     │   (Failure)     │                         │
        ├─────────────────┼─────────────────┼─────────────────────────┤
        │ • value: T      │ • error: Exc    │ • try_result()          │
        │ • map()         │ • map_err()     │ • collect_results()     │
        │ • flat_map()    │ • or_else()     │ • partition_results()   │
        │ • unwrap()      │ • unwrap_or()   │ • from_optional()       │
        └─────────────────┴─────────────────┴─────────────────────────┘

Features:
    - **Type-safe success/failure:** Ok[T] and Err[T] with pattern matching
    - **Functional combinators:** map, flat_map, or_else for chaining
    - **Safe value extraction:** unwrap_or, unwrap_or_else for defaults
    - **Batch collection:** collect_results, collect_all_errors, partition_results
    - **Conversion utilities:** from_optional, from_bool, try_result

Examples:
    Basic usage with pattern matching:

    >>> from spine.core.result import Ok, Err, Result
    >>> def divide(a: int, b: int) -> Result[float]:
    ...     if b == 0:
    ...         return Err(ValueError("Division by zero"))
    ...     return Ok(a / b)
    >>> result = divide(10, 2)
    >>> match result:
    ...     case Ok(value):
    ...         print(f"Result: {value}")
    ...     case Err(error):
    ...         print(f"Error: {error}")
    Result: 5.0

    Chaining with map and flat_map:

    >>> ok_result = Ok(10)
    >>> chained = ok_result.map(lambda x: x * 2).map(lambda x: x + 1)
    >>> chained.unwrap()
    21
    >>> err_result = Err(ValueError("oops"))
    >>> err_result.map(lambda x: x * 2).unwrap_or(0)
    0

Performance:
    - **Time complexity:** All operations are O(1) except collect_* which are O(n)
    - **Memory:** Ok/Err are frozen dataclasses with __slots__, minimal overhead
    - **No overhead for success path:** map/flat_map on Err is a no-op

Guardrails:
    ❌ DON'T: Use unwrap() without checking is_ok() first
    ✅ DO: Use unwrap_or() or pattern matching for safe extraction

    ❌ DON'T: Raise exceptions inside map/flat_map functions
    ✅ DO: Return Err from flat_map if the operation can fail

    ❌ DON'T: Store mutable values in Ok (frozen dataclass)
    ✅ DO: Use immutable types or create copies

Context:
    - **Problem:** Exception-based error handling is implicit and easy to miss
    - **Solution:** Explicit Result type that forces callers to handle both paths
    - **Alternatives:** Python's try/except, Optional[T], or third-party result libs

Tags:
    result-pattern, error-handling, functional-programming, monadic,
    batch-processing, spine-core, type-safety

Doc-Types:
    - API Reference
    - Design Patterns Guide
    - Error Handling Tutorial

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

    Ok[T] represents the success case of the Result[T] pattern, wrapping a value
    of type T. It is immutable (frozen dataclass) and uses __slots__ for memory
    efficiency. If the wrapped value is hashable, Ok[T] is also hashable.

    The Ok class provides a fluent API for transforming values while staying in
    the Result context. Operations like map() apply a function to the value and
    return a new Ok with the transformed value. Operations like flat_map() allow
    chaining to other Result-returning functions.

    Manifesto:
        - **Value presence guaranteed:** Unlike Optional, Ok always has a value
        - **Transformation without unwrapping:** Use map/flat_map to stay in Result
        - **Explicit success:** The type tells you the operation succeeded
        - **Immutability:** Frozen dataclass prevents accidental mutation

    Architecture:
        ::

            ┌─────────────────────────────────────────────────────────┐
            │                        Ok[T]                             │
            ├─────────────────────────────────────────────────────────┤
            │  value: T                                                │
            ├─────────────────────────────────────────────────────────┤
            │  Inspection     │  Extraction    │  Transformation      │
            │  • is_ok()      │  • unwrap()    │  • map()             │
            │  • is_err()     │  • unwrap_or() │  • flat_map()        │
            │                 │                │  • and_then()        │
            │                 │                │  • inspect()         │
            └─────────────────────────────────────────────────────────┘

    Features:
        - **Type inspection:** is_ok(), is_err() for runtime checking
        - **Safe extraction:** unwrap(), unwrap_or(), unwrap_or_else()
        - **Value transformation:** map() for simple transforms
        - **Result chaining:** flat_map()/and_then() for fallible operations
        - **Side effects:** inspect() for logging/debugging without unwrapping
        - **Serialization:** to_dict() for JSON conversion

    Examples:
        Creating and inspecting Ok:

        >>> ok = Ok(42)
        >>> ok.is_ok()
        True
        >>> ok.is_err()
        False
        >>> ok.unwrap()
        42

        Transforming values with map:

        >>> Ok(10).map(lambda x: x * 2).unwrap()
        20
        >>> Ok("hello").map(str.upper).unwrap()
        'HELLO'

        Chaining fallible operations with flat_map:

        >>> def validate_positive(x: int) -> Result[int]:
        ...     return Ok(x) if x > 0 else Err(ValueError("Must be positive"))
        >>> Ok(5).flat_map(validate_positive).unwrap()
        5
        >>> Ok(-1).flat_map(validate_positive).is_err()
        True

        Using inspect for debugging:

        >>> Ok(42).inspect(lambda x: print(f"Got: {x}")).unwrap()
        Got: 42
        42

    Performance:
        - **O(1)** for all operations
        - **Memory:** Single slot for value, frozen dataclass overhead minimal
        - **No allocation on map:** Creates new Ok, but cheap

    Guardrails:
        ❌ DON'T: Mutate the value inside Ok (it's frozen)
        ✅ DO: Use map() to create a new Ok with transformed value

        ❌ DON'T: Assume map() modifies in place
        ✅ DO: Chain or assign the result: result = ok.map(f)

    Context:
        - **Problem:** Need to wrap success values in a type-safe envelope
        - **Solution:** Frozen dataclass with fluent transformation API
        - **Alternatives:** Plain tuples, custom success classes

    Tags:
        result-pattern, success-type, functional-programming, immutable,
        monadic, spine-core

    Doc-Types:
        - API Reference
        - Result Pattern Guide
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

    Err[T] represents the failure case of the Result[T] pattern, wrapping an
    Exception (preferably a SpineError subclass for rich metadata). Like Ok[T],
    it is immutable (frozen dataclass) and uses __slots__ for memory efficiency.

    The Err class short-circuits transformation operations: map() and flat_map()
    return the same Err unchanged, allowing error propagation through chains.
    Recovery operations like or_else() and unwrap_or() provide escape hatches.

    Manifesto:
        - **Error as a value:** Errors are first-class values, not control flow
        - **Propagation without throwing:** Err flows through map chains unchanged
        - **Rich context:** Prefer SpineError with category, retryable, context
        - **Recovery points:** or_else() provides structured error recovery

    Architecture:
        ::

            ┌─────────────────────────────────────────────────────────┐
            │                        Err[T]                            │
            ├─────────────────────────────────────────────────────────┤
            │  error: Exception                                        │
            ├─────────────────────────────────────────────────────────┤
            │  Inspection     │  Recovery      │  Transformation      │
            │  • is_ok()      │  • unwrap_or() │  • map_err()         │
            │  • is_err()     │  • or_else()   │  • map() → no-op     │
            │                 │                │  • flat_map() → no-op│
            │                 │                │  • inspect_err()     │
            └─────────────────────────────────────────────────────────┘

    Features:
        - **Short-circuit propagation:** map/flat_map pass Err through unchanged
        - **Error transformation:** map_err() to wrap/convert errors
        - **Recovery operations:** or_else() for fallback, unwrap_or() for default
        - **Side effects:** inspect_err() for logging without unwrapping
        - **Serialization:** to_dict() converts SpineError to structured dict

    Examples:
        Creating and inspecting Err:

        >>> err = Err(ValueError("something went wrong"))
        >>> err.is_ok()
        False
        >>> err.is_err()
        True
        >>> err.unwrap_or("default")
        'default'

        Error propagation through map:

        >>> Err(ValueError("x")).map(lambda x: x * 2).is_err()
        True

        Recovering from errors with or_else:

        >>> def try_backup(e):
        ...     return Ok("backup value")
        >>> Err(ValueError("x")).or_else(try_backup).unwrap()
        'backup value'

        Transforming errors with map_err:

        >>> from spine.core.errors import SourceError
        >>> err = Err(ValueError("raw error"))
        >>> wrapped = err.map_err(lambda e: SourceError(f"Wrapped: {e}"))
        >>> wrapped.error.message
        'Wrapped: raw error'

        Logging errors with inspect_err:

        >>> errors = []
        >>> Err(ValueError("x")).inspect_err(lambda e: errors.append(e)).is_err()
        True
        >>> len(errors)
        1

    Performance:
        - **O(1)** for all operations
        - **map/flat_map:** Immediate return, no function call
        - **Memory:** Single slot for error

    Guardrails:
        ❌ DON'T: Call unwrap() on Err - it raises the error
        ✅ DO: Use unwrap_or() or pattern matching to handle errors

        ❌ DON'T: Use plain Exception - loses metadata
        ✅ DO: Use SpineError subclasses with category/retryable

        ❌ DON'T: Ignore Err in chains - they propagate silently
        ✅ DO: Check is_err() or use partition_results() at the end

    Context:
        - **Problem:** Need to represent failures without throwing exceptions
        - **Solution:** Err type that propagates through chains and carries context
        - **Alternatives:** Raising exceptions, returning None

    Tags:
        result-pattern, error-type, functional-programming, error-handling,
        monadic, spine-core

    Doc-Types:
        - API Reference
        - Result Pattern Guide
        - Error Handling Tutorial
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

    Converts exception-throwing code into the Result pattern. If the function
    executes successfully, returns Ok with the return value. If it raises any
    exception, returns Err with that exception.

    This is the primary bridge between exception-based code and Result-based
    code. Use it to wrap calls to libraries or APIs that throw exceptions.

    Manifesto:
        - **Bridge pattern:** Convert exception world to Result world
        - **Catch-all:** Captures any exception, not just specific types
        - **Zero-argument:** Function must be callable with no args (use lambda)

    Architecture:
        ::

            ┌─────────────┐         ┌─────────────┐
            │ f() raises  │ ──────> │  Err(exc)   │
            └─────────────┘         └─────────────┘
            ┌─────────────┐         ┌─────────────┐
            │ f() returns │ ──────> │  Ok(value)  │
            └─────────────┘         └─────────────┘

    Examples:
        Wrapping JSON parsing:

        >>> import json
        >>> try_result(lambda: json.loads('{"a": 1}')).unwrap()
        {'a': 1}
        >>> try_result(lambda: json.loads('invalid')).is_err()
        True

        Wrapping file operations:

        >>> def read_config():
        ...     # Would read from file
        ...     raise FileNotFoundError("config.json")
        >>> result = try_result(read_config)
        >>> result.is_err()
        True

    Performance:
        - **O(1)** overhead plus cost of f()
        - **Exception path:** Standard Python exception handling cost

    Guardrails:
        ❌ DON'T: Pass functions with arguments directly
        ✅ DO: Wrap in lambda: try_result(lambda: fetch(url))

        ❌ DON'T: Use for operations you control - return Result directly
        ✅ DO: Use for third-party/stdlib code that throws

    Args:
        f: Zero-argument callable that may raise exceptions

    Returns:
        Ok[T] if f() succeeds, Err[T] with the exception if f() raises

    Tags:
        result-constructor, exception-bridge, try-catch, spine-core

    Doc-Types:
        - API Reference
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
    Execute function and map exceptions to custom error types.

    Like try_result(), but allows transforming caught exceptions into
    domain-specific SpineError types. This provides richer error context
    for downstream handling.

    Manifesto:
        - **Typed errors:** Convert generic exceptions to SpineError hierarchy
        - **Context enrichment:** Add source, URL, or other metadata via mapper
        - **Consistent error types:** All errors in your domain use SpineError

    Architecture:
        ::

            f() raises ────┐
                           │
                      ┌────▼────┐        ┌─────────────┐
                      │ mapper  │ ─────> │ Err(mapped) │
                      └─────────┘        └─────────────┘
            
            f() returns ──────────────────> Ok(value)

    Examples:
        Converting to SourceError:

        >>> from spine.core.errors import SourceError
        >>> def fetch():
        ...     raise ConnectionError("timeout")
        >>> result = try_result_with(
        ...     fetch,
        ...     lambda e: SourceError(f"Fetch failed: {e}", retryable=True)
        ... )
        >>> result.error.retryable
        True

        Without mapper (same as try_result):

        >>> try_result_with(lambda: 1 / 0).error
        ZeroDivisionError('division by zero')

    Performance:
        - **O(1)** overhead plus cost of f() and optional mapper
        - **Mapper only called on error path**

    Guardrails:
        ❌ DON'T: Re-raise inside the mapper
        ✅ DO: Return a new exception from the mapper

        ❌ DON'T: Do expensive operations in mapper
        ✅ DO: Keep mapper lightweight - just create error

    Args:
        f: Zero-argument callable that may raise exceptions
        error_mapper: Optional function to transform exceptions

    Returns:
        Ok[T] if f() succeeds, Err with mapped exception if f() raises

    Tags:
        result-constructor, exception-bridge, error-mapping, spine-core

    Doc-Types:
        - API Reference
    """
    try:
        return Ok(f())
    except Exception as e:
        if error_mapper:
            return Err(error_mapper(e))
        return Err(e)


def collect_results(results: list[Result[T]]) -> Result[list[T]]:
    """
    Collect a list of Results into a Result of list (fail-fast).

    Iterates through results in order. If all are Ok, returns Ok with a list
    of all values. If any is Err, immediately returns that Err (first error
    encountered). This is fail-fast behavior - processing stops at first error.

    Use collect_results() when you want to abort on first failure. Use
    collect_all_errors() if you want to accumulate all errors for reporting.

    Manifesto:
        - **Fail-fast:** Stop processing as soon as an error is encountered
        - **All-or-nothing:** Either all succeed or you get an error
        - **Order preserved:** Values in result list match input order

    Architecture:
        ::

            [Ok(1), Ok(2), Ok(3)] ──────> Ok([1, 2, 3])
            
            [Ok(1), Err(x), Ok(3)] ─────> Err(x)  # stops at Err

    Examples:
        All successes:

        >>> results = [Ok(1), Ok(2), Ok(3)]
        >>> collect_results(results).unwrap()
        [1, 2, 3]

        First error wins:

        >>> results = [Ok(1), Err(ValueError("a")), Err(ValueError("b"))]
        >>> str(collect_results(results).error)
        'a'

        Empty list:

        >>> collect_results([]).unwrap()
        []

    Performance:
        - **O(n)** where n is number of results
        - **Short-circuit:** Stops at first Err, doesn't iterate remaining

    Guardrails:
        ❌ DON'T: Use when you need to report ALL errors
        ✅ DO: Use collect_all_errors() for comprehensive error reporting

        ❌ DON'T: Assume all results were processed on Err
        ✅ DO: Use partition_results() if you need partial results

    Args:
        results: List of Result[T] to collect

    Returns:
        Ok[list[T]] with all values if all Ok, Err with first error otherwise

    Tags:
        result-collector, batch-processing, fail-fast, spine-core

    Doc-Types:
        - API Reference
        - Batch Processing Guide
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
    Collect results, accumulating ALL errors for comprehensive reporting.

    Unlike collect_results() which stops at the first error, this function
    processes ALL results and accumulates every error. If any errors occurred,
    returns an Err with an aggregated SpineError containing all error messages.
    If all succeeded, returns Ok with all values.

    This is ideal for batch validation where you want to report all problems
    at once rather than making the user fix them one at a time.

    Manifesto:
        - **Complete reporting:** User sees ALL errors, not just the first
        - **Batch-friendly:** Process entire batch before reporting failures
        - **Error aggregation:** Multiple errors combined into one SpineError

    Architecture:
        ::

            [Ok(1), Err(a), Err(b)] ───> Err(SpineError("Multiple errors (2): a; b"))
            
            [Ok(1), Ok(2), Ok(3)] ─────> Ok([1, 2, 3])

    Examples:
        Accumulating all errors:

        >>> from spine.core.errors import ValidationError
        >>> results = [
        ...     Ok(1),
        ...     Err(ValidationError("field1 invalid")),
        ...     Err(ValidationError("field2 invalid"))
        ... ]
        >>> err = collect_all_errors(results)
        >>> "Multiple errors (2)" in str(err.error)
        True

        Single error (no aggregation needed):

        >>> results = [Ok(1), Err(ValueError("x"))]
        >>> collect_all_errors(results).error
        ValueError('x')

        All successes:

        >>> results = [Ok(1), Ok(2)]
        >>> collect_all_errors(results).unwrap()
        [1, 2]

    Performance:
        - **O(n)** - always processes all results
        - **Memory:** Stores all errors until aggregation

    Guardrails:
        ❌ DON'T: Use for large batches where fail-fast is acceptable
        ✅ DO: Use for validation where complete error reporting matters

        ❌ DON'T: Parse the aggregated message for individual errors
        ✅ DO: Access error.context.metadata["errors"] for error list

    Args:
        results: List of Result[T] to collect

    Returns:
        Ok[list[T]] if all succeeded, Err with aggregated error if any failed

    Tags:
        result-collector, batch-processing, error-aggregation, validation, spine-core

    Doc-Types:
        - API Reference
        - Batch Processing Guide
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

    Separates a list of Results into two lists: one containing all successful
    values and one containing all errors. This is useful when you want to
    process successful results while also handling/logging errors separately.

    Unlike collect_* functions that return a Result, this always returns both
    lists, letting you decide how to handle partial success scenarios.

    Manifesto:
        - **Partial success:** Continue with successful results even if some failed
        - **Complete visibility:** See both successes and failures
        - **Flexible handling:** Caller decides policy for mixed results

    Architecture:
        ::

            [Ok(1), Err(a), Ok(2), Err(b)]
                        │
                        ▼
            values:  [1, 2]      # All Ok values
            errors:  [a, b]      # All Err errors

    Examples:
        Basic partitioning:

        >>> results = [Ok(1), Err(ValueError("a")), Ok(2)]
        >>> values, errors = partition_results(results)
        >>> values
        [1, 2]
        >>> len(errors)
        1

        Processing partial success:

        >>> results = [Ok(item) if item > 0 else Err(ValueError(f"Invalid: {item}"))
        ...           for item in [1, -2, 3, -4]]
        >>> values, errors = partition_results(results)
        >>> sum(values)  # Process successful items
        4
        >>> len(errors)  # Log failed items
        2

    Performance:
        - **O(n)** - processes all results
        - **Memory:** Two lists allocated for values and errors

    Guardrails:
        ❌ DON'T: Ignore the errors list without logging
        ✅ DO: Log or handle errors appropriately

        ❌ DON'T: Use when any error should abort the operation
        ✅ DO: Use collect_results() for fail-fast behavior

    Args:
        results: List of Result[T] to partition

    Returns:
        Tuple of (list of successful values, list of errors)

    Tags:
        result-collector, batch-processing, partial-success, spine-core

    Doc-Types:
        - API Reference
        - Batch Processing Guide
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

    Bridges Python's Optional[T] pattern to the Result pattern. If value is
    not None, wraps it in Ok. If value is None, returns Err with the provided
    error. This is useful for integrating with APIs that return None for
    missing data.

    Manifesto:
        - **None to Err:** Convert "absence" to explicit error
        - **Meaningful errors:** Provide domain-specific error instead of None
        - **Bridge pattern:** Connect Optional-based code to Result-based code

    Architecture:
        ::

            value: T ──────> Ok(value)
            value: None ───> Err(error)

    Examples:
        Converting cache lookup:

        >>> from spine.core.errors import SourceNotFoundError
        >>> cache = {"key1": "value1"}
        >>> result = from_optional(
        ...     cache.get("key1"),
        ...     SourceNotFoundError("Cache miss")
        ... )
        >>> result.unwrap()
        'value1'
        >>> result = from_optional(
        ...     cache.get("missing"),
        ...     SourceNotFoundError("Cache miss: missing")
        ... )
        >>> result.is_err()
        True

        With dict.get default:

        >>> user = {"name": "Alice"}
        >>> from_optional(user.get("email"), ValueError("Email required")).is_err()
        True

    Performance:
        - **O(1)** - simple None check

    Guardrails:
        ❌ DON'T: Use for values where None is valid
        ✅ DO: Only use when None truly means "error"

        ❌ DON'T: Use generic Exception - loses context
        ✅ DO: Use specific SpineError with meaningful message

    Args:
        value: Optional value that may be None
        error: Exception to use if value is None

    Returns:
        Ok[T] if value is not None, Err with provided error otherwise

    Tags:
        result-constructor, optional-bridge, null-handling, spine-core

    Doc-Types:
        - API Reference
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

    Converts a boolean check into a Result. If condition is True, returns Ok
    with ok_value. If condition is False, returns Err with the provided error.
    Useful for validations and authorization checks.

    Manifesto:
        - **Boolean to Result:** Convert validation checks to Result pattern
        - **Explicit errors:** Provide meaningful error for False condition
        - **Authorization pattern:** Check permissions and return typed result

    Architecture:
        ::

            condition: True  ──────> Ok(ok_value)
            condition: False ──────> Err(error)

    Examples:
        Authorization check:

        >>> from spine.core.errors import AuthorizationError
        >>> user = {"role": "admin", "name": "Alice"}
        >>> result = from_bool(
        ...     user["role"] == "admin",
        ...     user,
        ...     AuthorizationError("Admin access required")
        ... )
        >>> result.unwrap()["name"]
        'Alice'

        Validation:

        >>> from spine.core.errors import ValidationError
        >>> age = 15
        >>> result = from_bool(
        ...     age >= 18,
        ...     age,
        ...     ValidationError("Must be 18 or older")
        ... )
        >>> result.is_err()
        True

    Performance:
        - **O(1)** - simple boolean check

    Guardrails:
        ❌ DON'T: Evaluate condition with side effects
        ✅ DO: Keep condition pure - no I/O or mutations

        ❌ DON'T: Use for complex multi-step validation
        ✅ DO: Chain multiple from_bool with flat_map for complex validation

    Args:
        condition: Boolean condition to check
        ok_value: Value to wrap in Ok if condition is True
        error: Exception to use if condition is False

    Returns:
        Ok[T] with ok_value if condition is True, Err otherwise

    Tags:
        result-constructor, validation, authorization, spine-core

    Doc-Types:
        - API Reference
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
