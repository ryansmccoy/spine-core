"""Tests for retry strategies."""

import pytest
import time
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from spine.execution.retry import (
    RetryStrategy,
    ExponentialBackoff,
    LinearBackoff,
    ConstantBackoff,
    NoRetry,
    RetryContext,
    with_retry,
)


class TestExponentialBackoff:
    """Tests for ExponentialBackoff strategy."""

    def test_default_configuration(self):
        """Test default configuration values."""
        strategy = ExponentialBackoff()
        assert strategy.max_retries == 3
        assert strategy.base_delay == 1.0
        assert strategy.max_delay == 60.0
        assert strategy.multiplier == 2.0
        assert strategy.jitter is True

    def test_custom_configuration(self):
        """Test custom configuration values."""
        strategy = ExponentialBackoff(
            max_retries=5,
            base_delay=0.5,
            max_delay=30.0,
            multiplier=3.0,
            jitter=False,
        )
        assert strategy.max_retries == 5
        assert strategy.base_delay == 0.5
        assert strategy.max_delay == 30.0
        assert strategy.multiplier == 3.0
        assert strategy.jitter is False

    def test_should_retry_within_limit(self):
        """Test retry allowed within max_retries."""
        strategy = ExponentialBackoff(max_retries=3)
        assert strategy.should_retry(0, ValueError()) is True
        assert strategy.should_retry(1, ValueError()) is True
        assert strategy.should_retry(2, ValueError()) is True

    def test_should_retry_at_limit(self):
        """Test retry denied at max_retries."""
        strategy = ExponentialBackoff(max_retries=3)
        assert strategy.should_retry(3, ValueError()) is False
        assert strategy.should_retry(4, ValueError()) is False

    def test_delay_calculation_no_jitter(self):
        """Test delay calculation without jitter."""
        strategy = ExponentialBackoff(
            base_delay=1.0,
            multiplier=2.0,
            max_delay=60.0,
            jitter=False,
        )
        assert strategy.next_delay(0) == 1.0   # 1 * 2^0 = 1
        assert strategy.next_delay(1) == 2.0   # 1 * 2^1 = 2
        assert strategy.next_delay(2) == 4.0   # 1 * 2^2 = 4
        assert strategy.next_delay(3) == 8.0   # 1 * 2^3 = 8
        assert strategy.next_delay(4) == 16.0  # 1 * 2^4 = 16

    def test_delay_capped_at_max(self):
        """Test delay capped at max_delay."""
        strategy = ExponentialBackoff(
            base_delay=10.0,
            multiplier=2.0,
            max_delay=30.0,
            jitter=False,
        )
        assert strategy.next_delay(0) == 10.0  # 10 * 2^0 = 10
        assert strategy.next_delay(1) == 20.0  # 10 * 2^1 = 20
        assert strategy.next_delay(2) == 30.0  # min(40, 30) = 30
        assert strategy.next_delay(3) == 30.0  # min(80, 30) = 30

    def test_delay_with_jitter(self):
        """Test delay has jitter when enabled."""
        strategy = ExponentialBackoff(
            base_delay=1.0,
            multiplier=2.0,
            max_delay=60.0,
            jitter=True,
            jitter_range=0.5,
        )
        # With jitter, delay should vary around the base calculation
        delays = [strategy.next_delay(1) for _ in range(10)]
        # All delays should be in reasonable range around 2.0
        assert all(0 <= d <= 4.0 for d in delays)
        # With 10 samples, we should see some variation (not all same)
        assert len(set(round(d, 2) for d in delays)) > 1

    def test_retryable_errors_filter(self):
        """Test filtering by retryable error types."""
        strategy = ExponentialBackoff(
            max_retries=3,
            retryable_errors={ConnectionError, TimeoutError},
        )
        # Allowed errors
        assert strategy.should_retry(0, ConnectionError()) is True
        assert strategy.should_retry(0, TimeoutError()) is True
        # Not allowed errors
        assert strategy.should_retry(0, ValueError()) is False
        assert strategy.should_retry(0, KeyError()) is False


class TestLinearBackoff:
    """Tests for LinearBackoff strategy."""

    def test_default_configuration(self):
        """Test default configuration values."""
        strategy = LinearBackoff()
        assert strategy.max_retries == 3
        assert strategy.base_delay == 1.0
        assert strategy.increment == 1.0
        assert strategy.max_delay == 30.0

    def test_delay_calculation(self):
        """Test linear delay calculation."""
        strategy = LinearBackoff(
            base_delay=1.0,
            increment=2.0,
            max_delay=20.0,
        )
        assert strategy.next_delay(0) == 1.0  # 1 + (0 * 2) = 1
        assert strategy.next_delay(1) == 3.0  # 1 + (1 * 2) = 3
        assert strategy.next_delay(2) == 5.0  # 1 + (2 * 2) = 5
        assert strategy.next_delay(3) == 7.0  # 1 + (3 * 2) = 7

    def test_delay_capped_at_max(self):
        """Test delay capped at max_delay."""
        strategy = LinearBackoff(
            base_delay=5.0,
            increment=5.0,
            max_delay=12.0,
        )
        assert strategy.next_delay(0) == 5.0   # 5 + (0 * 5) = 5
        assert strategy.next_delay(1) == 10.0  # 5 + (1 * 5) = 10
        assert strategy.next_delay(2) == 12.0  # min(15, 12) = 12
        assert strategy.next_delay(3) == 12.0  # min(20, 12) = 12


class TestConstantBackoff:
    """Tests for ConstantBackoff strategy."""

    def test_default_configuration(self):
        """Test default configuration values."""
        strategy = ConstantBackoff()
        assert strategy.max_retries == 3
        assert strategy.delay == 1.0

    def test_constant_delay(self):
        """Test delay is always constant."""
        strategy = ConstantBackoff(delay=5.0)
        assert strategy.next_delay(0) == 5.0
        assert strategy.next_delay(1) == 5.0
        assert strategy.next_delay(2) == 5.0
        assert strategy.next_delay(10) == 5.0


class TestNoRetry:
    """Tests for NoRetry strategy."""

    def test_never_retries(self):
        """Test never allows retry."""
        strategy = NoRetry()
        assert strategy.should_retry(0, ValueError()) is False
        assert strategy.should_retry(1, ValueError()) is False

    def test_zero_delay(self):
        """Test delay is always zero."""
        strategy = NoRetry()
        assert strategy.next_delay(0) == 0.0
        assert strategy.next_delay(1) == 0.0


class TestRetryContext:
    """Tests for RetryContext."""

    def test_successful_operation(self):
        """Test successful operation without retry."""
        strategy = ExponentialBackoff(max_retries=3)
        context = RetryContext(strategy)
        
        def successful_op():
            return "success"
        
        result = context.run(successful_op)
        assert result == "success"
        assert context.attempts == 1
        assert context.last_error is None

    def test_operation_succeeds_after_retries(self):
        """Test operation that succeeds after failures."""
        strategy = ExponentialBackoff(max_retries=3, base_delay=0.01, jitter=False)
        context = RetryContext(strategy)
        
        call_count = 0
        def flaky_op():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary error")
            return "success"
        
        result = context.run(flaky_op)
        assert result == "success"
        assert context.attempts == 3
        assert call_count == 3

    def test_operation_fails_all_retries(self):
        """Test operation that fails all retries."""
        strategy = ExponentialBackoff(max_retries=3, base_delay=0.01, jitter=False)
        context = RetryContext(strategy)
        
        def always_fails():
            raise ValueError("permanent error")
        
        with pytest.raises(ValueError, match="permanent error"):
            context.run(always_fails)
        
        assert context.attempts == 3  # max_retries attempts total
        assert isinstance(context.last_error, ValueError)

    def test_callback_on_retry(self):
        """Test on_retry callback is called."""
        strategy = ExponentialBackoff(max_retries=3, base_delay=0.01, jitter=False)
        
        retry_calls = []
        def on_retry(attempt: int, error: Exception, delay: float):
            retry_calls.append((attempt, str(error), delay))
        
        context = RetryContext(strategy, on_retry=on_retry)
        
        call_count = 0
        def flaky_op():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"error {call_count}")
            return "success"
        
        result = context.run(flaky_op)
        assert result == "success"
        assert len(retry_calls) == 2
        assert retry_calls[0][0] == 1  # First retry
        assert retry_calls[1][0] == 2  # Second retry

    @pytest.mark.asyncio
    async def test_async_execution(self):
        """Test async operation execution."""
        strategy = ExponentialBackoff(max_retries=3, base_delay=0.01, jitter=False)
        context = RetryContext(strategy)
        
        call_count = 0
        async def flaky_async_op():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary error")
            return "async success"
        
        result = await context.run_async(flaky_async_op)
        assert result == "async success"
        assert context.attempts == 2


class TestWithRetryDecorator:
    """Tests for @with_retry decorator."""

    def test_decorator_with_default_strategy(self):
        """Test decorator with default strategy."""
        @with_retry()
        def simple_op():
            return "result"
        
        assert simple_op() == "result"

    def test_decorator_with_custom_strategy(self):
        """Test decorator with custom strategy."""
        strategy = ExponentialBackoff(max_retries=5, base_delay=0.01, jitter=False)
        
        call_count = 0
        @with_retry(strategy)
        def flaky_op():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temp")
            return "success"
        
        result = flaky_op()
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_decorator_with_async_function(self):
        """Test decorator works with async functions."""
        strategy = ExponentialBackoff(max_retries=3, base_delay=0.01, jitter=False)
        
        call_count = 0
        @with_retry(strategy)
        async def async_flaky_op():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temp")
            return "async result"
        
        result = await async_flaky_op()
        assert result == "async result"
        assert call_count == 2

    def test_decorator_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""
        @with_retry()
        def documented_function():
            """This is a docstring."""
            return "result"
        
        assert documented_function.__name__ == "documented_function"
        assert "docstring" in documented_function.__doc__
