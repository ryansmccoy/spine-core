"""Tests for circuit breaker pattern."""

import pytest
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from spine.execution.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitStats,
    CircuitBreakerRegistry,
    CircuitOpenError,
    get_circuit_breaker,
)


class TestCircuitState:
    """Tests for CircuitState enum."""

    def test_state_values(self):
        """Test circuit state enum values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    def test_default_configuration(self):
        """Test default configuration values."""
        cb = CircuitBreaker("test")
        assert cb.name == "test"
        assert cb.failure_threshold == 5
        assert cb.recovery_timeout == 30.0
        assert cb.success_threshold == 2
        assert cb.state == CircuitState.CLOSED

    def test_custom_configuration(self):
        """Test custom configuration values."""
        cb = CircuitBreaker(
            name="custom",
            failure_threshold=3,
            recovery_timeout=10.0,
            success_threshold=1,
        )
        assert cb.failure_threshold == 3
        assert cb.recovery_timeout == 10.0
        assert cb.success_threshold == 1

    def test_starts_closed(self):
        """Test circuit starts in closed state."""
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED

    def test_allows_request_when_closed(self):
        """Test allows requests when circuit is closed."""
        cb = CircuitBreaker("test")
        assert cb.allow_request() is True

    def test_opens_after_failure_threshold(self):
        """Test circuit opens after reaching failure threshold."""
        cb = CircuitBreaker("test", failure_threshold=3)
        
        assert cb.state == CircuitState.CLOSED
        
        # Record failures
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()  # Third failure hits threshold
        assert cb.state == CircuitState.OPEN

    def test_denies_request_when_open(self):
        """Test denies requests when circuit is open."""
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()  # Opens circuit
        
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_transitions_to_half_open_after_timeout(self):
        """Test circuit transitions to half-open after recovery timeout."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()  # Opens circuit
        
        assert cb.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        time.sleep(0.15)
        
        # Should allow one request (triggers half-open check)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Test success in half-open state closes circuit."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1, success_threshold=2)
        cb.record_failure()  # Opens circuit
        
        time.sleep(0.15)  # Wait for recovery
        cb.allow_request()  # Triggers transition to half-open
        
        assert cb.state == CircuitState.HALF_OPEN
        
        # Record successes
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # Need 2 successes
        
        cb.record_success()
        assert cb.state == CircuitState.CLOSED  # Now closed

    def test_half_open_failure_reopens_circuit(self):
        """Test failure in half-open state reopens circuit."""
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()  # Opens circuit
        
        time.sleep(0.15)  # Wait for recovery
        cb.allow_request()  # Triggers transition to half-open
        
        assert cb.state == CircuitState.HALF_OPEN
        
        cb.record_failure()  # Should reopen
        assert cb.state == CircuitState.OPEN

    def test_manual_reset(self):
        """Test manual reset closes circuit."""
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()  # Opens circuit
        
        assert cb.state == CircuitState.OPEN
        
        cb.reset()
        
        assert cb.state == CircuitState.CLOSED

    def test_call_method_success(self):
        """Test call() method on success."""
        cb = CircuitBreaker("test")
        
        def operation():
            return "result"
        
        result = cb.call(operation)
        
        assert result == "result"
        assert cb.stats.successful_requests == 1
        assert cb.stats.failed_requests == 0

    def test_call_method_failure(self):
        """Test call() method on failure."""
        cb = CircuitBreaker("test", failure_threshold=3)
        
        def failing_operation():
            raise ValueError("error")
        
        with pytest.raises(ValueError):
            cb.call(failing_operation)
        
        assert cb.stats.failed_requests == 1
        assert cb.stats.successful_requests == 0

    def test_call_method_circuit_open(self):
        """Test call() raises when circuit is open."""
        cb = CircuitBreaker("test", failure_threshold=1)
        cb.record_failure()  # Open circuit
        
        def operation():
            return "result"
        
        with pytest.raises(CircuitOpenError):
            cb.call(operation)

    def test_stats_tracking(self):
        """Test stats are properly tracked."""
        cb = CircuitBreaker("test")
        
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        
        assert cb.stats.successful_requests == 2
        assert cb.stats.failed_requests == 1


class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry."""

    def test_get_or_create_circuit_breaker(self):
        """Test get_or_create returns same instance."""
        registry = CircuitBreakerRegistry()
        
        cb1 = registry.get_or_create("test")
        cb2 = registry.get_or_create("test")
        
        assert cb1 is cb2

    def test_get_or_create_with_config(self):
        """Test get_or_create with custom config."""
        registry = CircuitBreakerRegistry()
        
        cb = registry.get_or_create(
            "test",
            failure_threshold=10,
            recovery_timeout=60.0,
        )
        
        assert cb.failure_threshold == 10
        assert cb.recovery_timeout == 60.0

    def test_get_nonexistent_returns_none(self):
        """Test get returns None for nonexistent circuit."""
        registry = CircuitBreakerRegistry()
        
        assert registry.get("nonexistent") is None

    def test_get_existing_returns_circuit(self):
        """Test get returns existing circuit."""
        registry = CircuitBreakerRegistry()
        
        created = registry.get_or_create("test")
        fetched = registry.get("test")
        
        assert fetched is created

    def test_list_circuits(self):
        """Test listing all circuits."""
        registry = CircuitBreakerRegistry()
        
        registry.get_or_create("circuit1")
        registry.get_or_create("circuit2")
        
        circuits = registry.list_all()
        
        assert "circuit1" in circuits
        assert "circuit2" in circuits

    def test_remove_circuit(self):
        """Test removing a circuit."""
        registry = CircuitBreakerRegistry()
        
        registry.get_or_create("test")
        assert registry.get("test") is not None
        
        registry.remove("test")
        assert registry.get("test") is None

    def test_clear_all_circuits(self):
        """Test clearing all circuits."""
        registry = CircuitBreakerRegistry()
        
        registry.get_or_create("circuit1")
        registry.get_or_create("circuit2")
        
        registry.clear()
        
        assert len(registry.list_all()) == 0


class TestGlobalCircuitBreaker:
    """Tests for global circuit breaker function."""

    def test_get_circuit_breaker_creates_new(self):
        """Test get_circuit_breaker creates new circuit."""
        # Use unique name to avoid interference
        cb = get_circuit_breaker(f"global_test_{time.time()}")
        assert cb is not None
        assert cb.state == CircuitState.CLOSED

    def test_get_circuit_breaker_returns_same(self):
        """Test get_circuit_breaker returns same instance."""
        name = f"global_same_{time.time()}"
        cb1 = get_circuit_breaker(name)
        cb2 = get_circuit_breaker(name)
        assert cb1 is cb2
