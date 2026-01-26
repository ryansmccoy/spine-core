"""Retry strategies with exponential backoff, jitter, and configurable policies.

Provides flexible retry configuration for resilient pipeline execution.

Example:
    >>> from spine.execution.retry import RetryStrategy, ExponentialBackoff
    >>>
    >>> strategy = ExponentialBackoff(max_retries=5, base_delay=1.0, max_delay=60.0)
    >>> for attempt in range(5):
    ...     delay = strategy.next_delay(attempt)
    ...     print(f"Attempt {attempt}: wait {delay:.2f}s")
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, TypeVar, Any

T = TypeVar("T")


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class RetryStrategy(ABC):
    """Abstract base for retry strategies."""

    @abstractmethod
    def next_delay(self, attempt: int) -> float:
        """Calculate delay before next retry attempt.
        
        Args:
            attempt: Zero-based attempt number (0 = first retry)
            
        Returns:
            Delay in seconds before next attempt
        """
        ...

    @abstractmethod
    def should_retry(self, attempt: int, error: Exception | None = None) -> bool:
        """Determine if another retry should be attempted.
        
        Args:
            attempt: Current attempt number
            error: The exception that caused the failure
            
        Returns:
            True if should retry, False otherwise
        """
        ...


@dataclass
class ExponentialBackoff(RetryStrategy):
    """Exponential backoff with optional jitter.
    
    Delay = min(base_delay * (multiplier ** attempt), max_delay) + jitter
    
    Attributes:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        multiplier: Exponential multiplier (default: 2)
        jitter: Add randomness to prevent thundering herd
        jitter_range: Range of jitter as fraction of delay (0.0-1.0)
        retryable_errors: Set of exception types that are retryable (None = all)
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    multiplier: float = 2.0
    jitter: bool = True
    jitter_range: float = 0.25
    retryable_errors: set[type] | None = None

    def next_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay."""
        delay = min(
            self.base_delay * (self.multiplier ** attempt),
            self.max_delay,
        )
        
        if self.jitter:
            jitter_amount = delay * self.jitter_range
            delay += random.uniform(-jitter_amount, jitter_amount)
            delay = max(0, delay)  # Ensure non-negative
        
        return delay

    def should_retry(self, attempt: int, error: Exception | None = None) -> bool:
        """Check if retry should be attempted."""
        if attempt >= self.max_retries:
            return False
        
        if error is not None and self.retryable_errors is not None:
            return type(error) in self.retryable_errors
        
        return True


@dataclass
class LinearBackoff(RetryStrategy):
    """Linear backoff strategy.
    
    Delay = base_delay + (increment * attempt)
    """

    max_retries: int = 3
    base_delay: float = 1.0
    increment: float = 1.0
    max_delay: float = 30.0

    def next_delay(self, attempt: int) -> float:
        """Calculate linear backoff delay."""
        return min(
            self.base_delay + (self.increment * attempt),
            self.max_delay,
        )

    def should_retry(self, attempt: int, error: Exception | None = None) -> bool:
        """Check if retry should be attempted."""
        return attempt < self.max_retries


@dataclass
class ConstantBackoff(RetryStrategy):
    """Constant delay between retries."""

    max_retries: int = 3
    delay: float = 1.0

    def next_delay(self, attempt: int) -> float:
        """Return constant delay."""
        return self.delay

    def should_retry(self, attempt: int, error: Exception | None = None) -> bool:
        """Check if retry should be attempted."""
        return attempt < self.max_retries


@dataclass
class NoRetry(RetryStrategy):
    """No retry - fail immediately."""

    def next_delay(self, attempt: int) -> float:
        """No delay needed."""
        return 0.0

    def should_retry(self, attempt: int, error: Exception | None = None) -> bool:
        """Never retry."""
        return False


@dataclass
class RetryContext:
    """Context tracking retry state.
    
    Provides both state tracking and execution helpers.
    
    Example:
        >>> ctx = RetryContext(ExponentialBackoff(max_retries=3))
        >>> result = ctx.run(lambda: call_api())
    """

    strategy: RetryStrategy
    on_retry: Callable[[int, Exception, float], None] | None = None
    attempt: int = field(default=0, init=False)
    last_error: Exception | None = field(default=None, init=False)
    started_at: datetime = field(default_factory=utcnow, init=False)
    errors: list[tuple[int, Exception, datetime]] = field(default_factory=list, init=False)

    def record_failure(self, error: Exception) -> None:
        """Record a failed attempt."""
        self.errors.append((self.attempt, error, utcnow()))
        self.last_error = error
        self.attempt += 1

    def should_retry(self) -> bool:
        """Check if another retry is allowed."""
        return self.strategy.should_retry(self.attempt, self.last_error)

    def next_delay(self) -> float:
        """Get delay before next retry."""
        return self.strategy.next_delay(self.attempt)

    @property
    def elapsed_seconds(self) -> float:
        """Total elapsed time since first attempt."""
        return (utcnow() - self.started_at).total_seconds()

    @property
    def attempts(self) -> int:
        """Number of attempts made."""
        return self.attempt

    def run(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function with retry logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from successful function call
            
        Raises:
            Last exception if all retries exhausted
        """
        import time
        
        while True:
            self.attempt += 1
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.last_error = e
                self.errors.append((self.attempt, e, utcnow()))
                
                if not self.strategy.should_retry(self.attempt, e):
                    raise
                
                delay = self.strategy.next_delay(self.attempt - 1)
                
                if self.on_retry:
                    self.on_retry(self.attempt, e, delay)
                
                time.sleep(delay)

    async def run_async(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute async function with retry logic.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from successful function call
            
        Raises:
            Last exception if all retries exhausted
        """
        import asyncio
        
        while True:
            self.attempt += 1
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                self.last_error = e
                self.errors.append((self.attempt, e, utcnow()))
                
                if not self.strategy.should_retry(self.attempt, e):
                    raise
                
                delay = self.strategy.next_delay(self.attempt - 1)
                
                if self.on_retry:
                    self.on_retry(self.attempt, e, delay)
                
                await asyncio.sleep(delay)


def with_retry(
    strategy: RetryStrategy | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator factory to add retry logic to a function.
    
    Args:
        strategy: Retry strategy (default: ExponentialBackoff)
        on_retry: Callback called before each retry (attempt, error, delay)
        
    Returns:
        Decorator that wraps function with retry logic
        
    Example:
        >>> @with_retry(ExponentialBackoff(max_retries=3))
        ... def flaky_operation():
        ...     return call_api()
    """
    import functools
    import inspect

    if strategy is None:
        strategy = ExponentialBackoff()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> T:
                ctx = RetryContext(strategy=strategy, on_retry=on_retry)
                return await ctx.run_async(func, *args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> T:
                ctx = RetryContext(strategy=strategy, on_retry=on_retry)
                return ctx.run(func, *args, **kwargs)
            return sync_wrapper

    return decorator
