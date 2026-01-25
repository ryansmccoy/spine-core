"""Circuit breaker pattern for fault tolerance.

Prevents cascading failures by failing fast when a downstream service
is experiencing issues.

States:
    CLOSED: Normal operation, requests pass through
    OPEN: Failing fast, requests rejected immediately
    HALF_OPEN: Testing if service recovered

Example:
    >>> from spine.execution.circuit_breaker import CircuitBreaker
    >>>
    >>> breaker = CircuitBreaker(
    ...     failure_threshold=5,
    ...     recovery_timeout=30.0,
    ... )
    >>>
    >>> if breaker.allow_request():
    ...     try:
    ...         result = call_external_service()
    ...         breaker.record_success()
    ...     except Exception as e:
    ...         breaker.record_failure()
    ...         raise
    ... else:
    ...     raise CircuitOpenError("Service unavailable")
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Rejecting requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitOpenError(Exception):
    """Raised when circuit is open and rejecting requests."""

    def __init__(self, message: str = "Circuit breaker is open"):
        super().__init__(message)


@dataclass
class CircuitStats:
    """Statistics for circuit breaker monitoring."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    state_changes: int = 0
    last_failure_time: datetime | None = None
    last_success_time: datetime | None = None
    last_state_change: datetime | None = None

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        total = self.successful_requests + self.failed_requests
        if total == 0:
            return 0.0
        return (self.failed_requests / total) * 100


@dataclass
class CircuitBreaker:
    """Circuit breaker for fault tolerance.
    
    Attributes:
        name: Identifier for this circuit
        failure_threshold: Number of failures before opening
        recovery_timeout: Seconds to wait before testing recovery
        success_threshold: Successes needed in half-open to close
        half_open_max_calls: Max concurrent calls in half-open state
    """

    name: str = "default"
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 2
    half_open_max_calls: int = 1
    
    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: datetime | None = field(default=None, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _stats: CircuitStats = field(default_factory=CircuitStats, init=False)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            self._check_state_transition()
            return self._state

    @property
    def stats(self) -> CircuitStats:
        """Get circuit statistics."""
        return self._stats

    def _check_state_transition(self) -> None:
        """Check if state should transition based on timeout."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            elapsed = (utcnow() - self._last_failure_time).total_seconds()
            if elapsed >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changes += 1
        self._stats.last_state_change = utcnow()
        
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_calls = 0

    def allow_request(self) -> bool:
        """Check if a request should be allowed.
        
        Returns:
            True if request can proceed, False if circuit is open
        """
        with self._lock:
            self._check_state_transition()
            self._stats.total_requests += 1
            
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.OPEN:
                self._stats.rejected_requests += 1
                return False
            
            # Half-open: allow limited requests
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            
            self._stats.rejected_requests += 1
            return False

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            self._stats.successful_requests += 1
            self._stats.last_success_time = utcnow()
            
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def record_failure(self, error: Exception | None = None) -> None:
        """Record a failed request."""
        with self._lock:
            self._failure_count += 1
            self._stats.failed_requests += 1
            self._stats.last_failure_time = utcnow()
            self._last_failure_time = utcnow()
            
            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
            
            elif self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                self._transition_to(CircuitState.OPEN)

    def reset(self) -> None:
        """Reset circuit to closed state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._last_failure_time = None

    def force_open(self) -> None:
        """Force circuit to open state (for testing/maintenance)."""
        with self._lock:
            self._transition_to(CircuitState.OPEN)
            self._last_failure_time = utcnow()

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a function through the circuit breaker.
        
        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitOpenError: If circuit is open
        """
        if not self.allow_request():
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open, rejecting request"
            )
        
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise

    async def call_async(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute an async function through the circuit breaker."""
        if not self.allow_request():
            raise CircuitOpenError(
                f"Circuit '{self.name}' is open, rejecting request"
            )
        
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise


class CircuitBreakerRegistry:
    """Registry of named circuit breakers."""

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()

    def get(self, name: str) -> CircuitBreaker | None:
        """Get a circuit breaker by name, returns None if not found."""
        with self._lock:
            return self._breakers.get(name)

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        **kwargs: Any,
    ) -> CircuitBreaker:
        """Get or create a circuit breaker by name."""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout,
                    **kwargs,
                )
            return self._breakers[name]

    def list_all(self) -> list[str]:
        """List all registered circuit breaker names."""
        with self._lock:
            return list(self._breakers.keys())

    def remove(self, name: str) -> None:
        """Remove a circuit breaker by name."""
        with self._lock:
            self._breakers.pop(name, None)

    def clear(self) -> None:
        """Remove all circuit breakers."""
        with self._lock:
            self._breakers.clear()

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


# Global registry
_default_registry = CircuitBreakerRegistry()


def get_circuit_breaker(name: str, **kwargs: Any) -> CircuitBreaker:
    """Get a circuit breaker from the default registry."""
    return _default_registry.get_or_create(name, **kwargs)


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all circuit breakers from the default registry."""
    return {name: _default_registry.get(name) for name in _default_registry.list_all()}
