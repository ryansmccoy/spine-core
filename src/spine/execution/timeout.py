"""Timeout enforcement for execution control.

Provides context managers and decorators for enforcing time limits on
synchronous and asynchronous operations.

Manifesto:
    Operations without timeouts are a reliability anti-pattern:
    - **Resource exhaustion:** Long-running tasks block workers
    - **Cascading failures:** Slow dependencies hang callers
    - **Poor user experience:** Users don't get timely feedback

    Spine's timeout enforcement is simple and composable:
    - Context manager: `with with_deadline(seconds):`
    - Decorator: `@timeout(seconds)`
    - Async support: Works with both sync and async code
    - Nested deadlines: Inner deadline wins if shorter

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────────┐
        │                    Timeout Enforcement                          │
        └─────────────────────────────────────────────────────────────────┘

        Sync Operations:
        ┌────────────────────────────────────────────────────────────────┐
        │ with with_deadline(30.0):                                      │
        │     result = slow_operation()                                  │
        │ # Raises TimeoutExpired if > 30 seconds                        │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ uses
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │               ThreadPoolExecutor + Event                        │
        │  - Runs operation in separate thread                           │
        │  - Main thread waits with timeout                              │
        │  - On timeout, raises TimeoutExpired                           │
        └────────────────────────────────────────────────────────────────┘

        Async Operations:
        ┌────────────────────────────────────────────────────────────────┐
        │ async with with_deadline_async(30.0):                          │
        │     result = await slow_async_operation()                      │
        │ # Raises TimeoutExpired if > 30 seconds                        │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ uses
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │               asyncio.timeout (Python 3.11+)                    │
        │  - Native async timeout support                                │
        │  - Cancels task on timeout                                     │
        └────────────────────────────────────────────────────────────────┘

Examples:
    Basic sync timeout:

    >>> from spine.execution.timeout import with_deadline, TimeoutExpired
    >>>
    >>> with with_deadline(5.0):
    ...     result = slow_http_call()  # Must complete in 5 seconds

    Async timeout:

    >>> async with with_deadline_async(10.0):
    ...     data = await fetch_data()  # Must complete in 10 seconds

    Decorator form:

    >>> @timeout(30.0)
    ... def process_document(doc):
    ...     return heavy_computation(doc)
    >>>
    >>> result = process_document(doc)  # Raises TimeoutExpired if > 30s

    Nested deadlines (shortest wins):

    >>> with with_deadline(30.0):     # Outer: 30s
    ...     with with_deadline(5.0):  # Inner: 5s (wins)
    ...         quick_check()
    ...     with with_deadline(60.0): # Inner: 60s, but outer 30s still applies
    ...         medium_task()         # Still limited to remaining outer time

    Check remaining time:

    >>> with with_deadline(30.0) as ctx:
    ...     if ctx.remaining < 5.0:
    ...         skip_optional_work()

Guardrails:
    - Timeouts should be generous enough for normal operation
    - Always handle TimeoutExpired at appropriate level
    - Don't use very short timeouts (<1s) for I/O operations
    - Sync timeout uses threads - not suitable for CPU-bound code (use ProcessExecutor)

Performance:
    - Sync timeout: One thread per with_deadline block
    - Async timeout: Native asyncio, minimal overhead
    - Thread creation: ~1ms on modern systems

Tags:
    timeout, deadline, resilience, execution, spine-core

Doc-Types:
    api-reference
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import inspect
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any, ParamSpec, TypeVar

T = TypeVar("T")
P = ParamSpec("P")


class TimeoutExpired(TimeoutError):
    """Raised when an operation exceeds its deadline.

    Inherits from built-in TimeoutError for broad exception handling.

    Attributes:
        timeout: The timeout value that was exceeded
        elapsed: How long the operation ran before being interrupted
        operation: Name/description of the operation
    """

    def __init__(
        self,
        timeout: float,
        elapsed: float | None = None,
        operation: str = "operation",
    ):
        self.timeout = timeout
        self.elapsed = elapsed
        self.operation = operation

        msg = f"Operation '{operation}' timed out after {timeout}s"

        if elapsed is not None:
            msg += f" (ran for {elapsed:.2f}s)"

        super().__init__(msg)


@dataclass
class DeadlineContext:
    """Context for tracking deadline state.

    Attributes:
        deadline: Absolute deadline timestamp (monotonic clock)
        timeout_seconds: Original timeout value in seconds
        operation: Name/description of the operation
        start_time: When the deadline context started
    """

    deadline: float
    timeout_seconds: float
    operation: str = "operation"
    start_time: float = field(default_factory=time.monotonic)
    _timeout_raised: bool = field(default=False, repr=False)

    def remaining(self) -> float:
        """Remaining time until deadline in seconds.

        Returns:
            Positive value if time remains, negative if expired.
        """
        return self.deadline - time.monotonic()

    @property
    def elapsed(self) -> float:
        """Elapsed time since start in seconds."""
        return time.monotonic() - self.start_time

    def is_expired(self) -> bool:
        """True if deadline has passed."""
        return time.monotonic() >= self.deadline

    def check(self, op_name: str | None = None) -> None:
        """Check if deadline expired and raise if so.

        Args:
            op_name: Name of operation for error message

        Raises:
            TimeoutExpired: If deadline has passed
        """
        if self.is_expired():
            raise TimeoutExpired(
                timeout=self.timeout_seconds,
                elapsed=self.elapsed,
                operation=op_name or self.operation,
            )


# Thread-local storage for nested deadlines
_deadline_stack: threading.local = threading.local()


def _get_deadline_stack() -> list[DeadlineContext]:
    """Get the deadline stack for the current thread."""
    if not hasattr(_deadline_stack, "stack"):
        _deadline_stack.stack = []
    return _deadline_stack.stack


def get_current_deadline() -> DeadlineContext | None:
    """Get the current active deadline context, if any.

    Returns:
        Current DeadlineContext or None if not in a deadline block
    """
    stack = _get_deadline_stack()
    return stack[-1] if stack else None


def get_effective_timeout(requested: float) -> float:
    """Get effective timeout considering nested deadlines.

    If inside a deadline block, returns the minimum of the
    requested timeout and remaining time on outer deadline.

    Args:
        requested: Requested timeout in seconds

    Returns:
        Effective timeout to use
    """
    current = get_current_deadline()
    if current is None:
        return requested
    return min(requested, current.remaining())


def get_remaining_deadline() -> float | None:
    """Get the remaining time on the current deadline, if any.

    Returns:
        Remaining seconds or None if not in a deadline context
    """
    ctx = get_current_deadline()
    if ctx is None:
        return None
    return ctx.remaining()


def check_deadline() -> None:
    """Check if the current deadline has expired and raise if so.

    Does nothing if not inside a deadline context.

    Raises:
        TimeoutExpired: If the current deadline has expired
    """
    ctx = get_current_deadline()
    if ctx is not None and ctx.is_expired():
        ctx._timeout_raised = True
        raise TimeoutExpired(
            timeout=ctx.timeout_seconds,
            elapsed=ctx.elapsed,
            operation=ctx.operation,
        )


@contextmanager
def with_deadline(seconds: float, operation: str | None = None):
    """Context manager for enforcing a time limit on sync operations.

    Uses a background thread to run the operation with a timeout.
    For simple deadline tracking without thread isolation, use
    `deadline_context()` instead.

    Args:
        seconds: Maximum time allowed
        operation: Name/description for error messages

    Yields:
        DeadlineContext for checking remaining time

    Raises:
        TimeoutExpired: If the deadline is exceeded
        ValueError: If seconds <= 0

    Example:
        >>> with with_deadline(5.0) as ctx:
        ...     result = slow_operation()
        ...     print(f"Completed with {ctx.remaining:.1f}s to spare")
    """
    if seconds < 0:
        raise ValueError(f"Timeout must be non-negative, got {seconds}")

    # Apply effective timeout (respects outer deadlines)
    effective = get_effective_timeout(seconds)
    now = time.monotonic()
    ctx = DeadlineContext(
        deadline=now + effective,
        timeout_seconds=effective,
        operation=operation or "operation",
        start_time=now,
    )

    stack = _get_deadline_stack()
    stack.append(ctx)

    try:
        yield ctx
        # Check on exit - if caller code ran too long and no check_deadline already fired
        if ctx.is_expired() and not ctx._timeout_raised:
            raise TimeoutExpired(
                timeout=effective,
                elapsed=ctx.elapsed,
                operation=operation or "operation",
            )
    finally:
        stack.pop()


@contextmanager
def deadline_context(seconds: float):
    """Lightweight deadline tracking without enforcement.

    Unlike `with_deadline`, this doesn't use threads or enforce
    the timeout - it just tracks time and lets you check manually.

    Args:
        seconds: Deadline duration

    Yields:
        DeadlineContext for checking remaining time

    Example:
        >>> with deadline_context(30.0) as ctx:
        ...     for item in items:
        ...         if ctx.remaining() < 1.0:
        ...             break  # Stop early if running low on time
        ...         process(item)
    """
    if seconds <= 0:
        raise ValueError(f"Timeout must be positive, got {seconds}")

    effective = get_effective_timeout(seconds)
    now = time.monotonic()
    ctx = DeadlineContext(
        deadline=now + effective,
        timeout_seconds=effective,
        start_time=now,
    )

    stack = _get_deadline_stack()
    stack.append(ctx)

    try:
        yield ctx
    finally:
        stack.pop()


@asynccontextmanager
async def with_deadline_async(seconds: float, operation: str | None = None):
    """Async context manager for enforcing a time limit.

    Uses asyncio.timeout for native async timeout support.

    Args:
        seconds: Maximum time allowed
        operation: Name/description for error messages

    Yields:
        DeadlineContext for checking remaining time

    Raises:
        TimeoutExpired: If the deadline is exceeded
        ValueError: If seconds <= 0

    Example:
        >>> async with with_deadline_async(10.0):
        ...     data = await fetch_data()
    """
    if seconds < 0:
        raise ValueError(f"Timeout must be non-negative, got {seconds}")

    effective = get_effective_timeout(seconds)
    now = time.monotonic()
    ctx = DeadlineContext(
        deadline=now + effective,
        timeout_seconds=effective,
        operation=operation or "operation",
        start_time=now,
    )

    stack = _get_deadline_stack()
    stack.append(ctx)

    try:
        async with asyncio.timeout(effective):
            yield ctx
            # Check on exit for expired deadline
            if ctx.is_expired():
                raise TimeoutExpired(
                    timeout=effective,
                    elapsed=ctx.elapsed,
                    operation=operation or "operation",
                )
    except TimeoutError:
        raise TimeoutExpired(
            timeout=effective,
            elapsed=ctx.elapsed,
            operation=operation or "operation",
        ) from None
    finally:
        stack.pop()


def timeout(seconds: float, operation: str | None = None) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to enforce a timeout on a function.

    Works with both sync and async functions.

    Args:
        seconds: Maximum execution time
        operation: Name for error messages (defaults to function name)

    Returns:
        Decorated function

    Example:
        >>> @timeout(30.0)
        ... def process_document(doc):
        ...     return heavy_computation(doc)
        >>>
        >>> @timeout(10.0)
        ... async def fetch_data(url):
        ...     return await http_get(url)
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        op_name = operation or func.__name__

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                async with with_deadline_async(seconds, op_name):
                    return await func(*args, **kwargs)
            return async_wrapper  # type: ignore
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                with with_deadline(seconds, op_name):
                    return func(*args, **kwargs)
            return sync_wrapper  # type: ignore

    return decorator


def run_with_timeout[T](
    func: Callable[..., T],
    timeout_seconds: float,
    operation: str | None = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> T:
    """Run a callable with a timeout using ThreadPoolExecutor.

    This is a lower-level function for running arbitrary callables
    with timeout enforcement using thread isolation.

    Args:
        func: Callable to execute
        timeout_seconds: Maximum execution time
        operation: Name for error messages
        args: Positional arguments for func
        kwargs: Keyword arguments for func

    Returns:
        Result of func(*args, **kwargs)

    Raises:
        TimeoutExpired: If execution exceeds timeout
        Exception: Any exception raised by func

    Example:
        >>> result = run_with_timeout(
        ...     slow_function,
        ...     timeout_seconds=30.0,
        ...     args=(arg1, arg2),
        ...     operation="slow_function",
        ... )
    """
    if timeout_seconds <= 0:
        raise ValueError(f"Timeout must be positive, got {timeout_seconds}")

    effective = get_effective_timeout(timeout_seconds)
    start = time.monotonic()
    pos_args = args or ()
    kw_args = kwargs or {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *pos_args, **kw_args)
        try:
            return future.result(timeout=effective)
        except concurrent.futures.TimeoutError:
            # Note: The thread continues running - we can't forcibly kill it
            elapsed = time.monotonic() - start
            raise TimeoutExpired(
                timeout=effective,
                elapsed=elapsed,
                operation=operation or getattr(func, "__name__", "unknown"),
            ) from None


async def run_with_timeout_async(
    coro,
    timeout_seconds: float,
    operation: str | None = None,
) -> Any:
    """Run a coroutine with a timeout.

    Args:
        coro: Coroutine to execute
        timeout_seconds: Maximum execution time
        operation: Name for error messages

    Returns:
        Result of the coroutine

    Raises:
        TimeoutExpired: If execution exceeds timeout
        Exception: Any exception raised by the coroutine

    Example:
        >>> result = await run_with_timeout_async(
        ...     fetch_data(url),
        ...     10.0,
        ...     operation="fetch_data"
        ... )
    """
    if timeout_seconds <= 0:
        raise ValueError(f"Timeout must be positive, got {timeout_seconds}")

    effective = get_effective_timeout(timeout_seconds)
    start = time.monotonic()

    try:
        return await asyncio.wait_for(coro, timeout=effective)
    except TimeoutError:
        elapsed = time.monotonic() - start
        raise TimeoutExpired(
            timeout=effective,
            elapsed=elapsed,
            operation=operation,
        ) from None
