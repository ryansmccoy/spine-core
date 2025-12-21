"""Tests for timeout enforcement module."""

import asyncio
import time
import pytest
from concurrent.futures import ThreadPoolExecutor

from spine.execution.timeout import (
    TimeoutExpired,
    DeadlineContext,
    with_deadline,
    with_deadline_async,
    timeout,
    run_with_timeout,
    get_remaining_deadline,
    check_deadline,
)


class TestDeadlineContext:
    """Tests for DeadlineContext dataclass."""

    def test_deadline_context_creation(self):
        """Test creating a deadline context."""
        ctx = DeadlineContext(
            deadline=time.monotonic() + 5.0,
            timeout_seconds=5.0,
            operation="test_op",
        )
        assert ctx.operation == "test_op"
        assert ctx.timeout_seconds == 5.0

    def test_remaining_positive(self):
        """Test remaining time calculation when time left."""
        ctx = DeadlineContext(
            deadline=time.monotonic() + 5.0,
            timeout_seconds=5.0,
            operation="test",
        )
        remaining = ctx.remaining()
        assert 4.5 < remaining <= 5.0

    def test_remaining_negative(self):
        """Test remaining time calculation when expired."""
        ctx = DeadlineContext(
            deadline=time.monotonic() - 1.0,
            timeout_seconds=5.0,
            operation="test",
        )
        assert ctx.remaining() < 0

    def test_is_expired(self):
        """Test is_expired detection."""
        future_ctx = DeadlineContext(
            deadline=time.monotonic() + 5.0,
            timeout_seconds=5.0,
            operation="test",
        )
        assert not future_ctx.is_expired()

        past_ctx = DeadlineContext(
            deadline=time.monotonic() - 1.0,
            timeout_seconds=5.0,
            operation="test",
        )
        assert past_ctx.is_expired()


class TestSyncDeadline:
    """Tests for synchronous deadline context manager."""

    def test_success_within_deadline(self):
        """Test operation completing within deadline."""
        with with_deadline(5.0, "quick_op") as ctx:
            time.sleep(0.01)
            assert not ctx.is_expired()

    def test_timeout_raises_exception(self):
        """Test that timeout raises TimeoutExpired."""
        with pytest.raises(TimeoutExpired) as exc_info:
            with with_deadline(0.1, "slow_op"):
                time.sleep(1.0)

        assert exc_info.value.timeout == 0.1
        assert exc_info.value.operation == "slow_op"
        assert exc_info.value.elapsed >= 0.1

    def test_timeout_exception_message(self):
        """Test timeout exception has useful message."""
        try:
            with with_deadline(0.1, "my_operation"):
                time.sleep(0.5)
        except TimeoutExpired as e:
            assert "0.1" in str(e)
            assert "my_operation" in str(e)

    def test_nested_deadlines_shortest_wins(self):
        """Test nested deadlines use shortest timeout."""
        with with_deadline(10.0, "outer") as outer_ctx:
            with with_deadline(1.0, "inner") as inner_ctx:
                # Inner deadline should be active
                remaining = get_remaining_deadline()
                assert remaining is not None
                assert remaining <= 1.0

            # Outer deadline active again
            remaining = get_remaining_deadline()
            assert remaining is not None
            assert remaining > 1.0

    def test_zero_timeout(self):
        """Test zero timeout expires immediately."""
        with pytest.raises(TimeoutExpired):
            with with_deadline(0.0, "instant"):
                pass

    def test_negative_timeout_raises(self):
        """Test negative timeout raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            with with_deadline(-1.0, "invalid"):
                pass


class TestAsyncDeadline:
    """Tests for async deadline context manager."""

    @pytest.mark.asyncio
    async def test_async_success_within_deadline(self):
        """Test async operation completing within deadline."""
        async with with_deadline_async(5.0, "async_op") as ctx:
            await asyncio.sleep(0.01)
            assert not ctx.is_expired()

    @pytest.mark.asyncio
    async def test_async_timeout_raises_exception(self):
        """Test async timeout raises TimeoutExpired."""
        with pytest.raises(TimeoutExpired) as exc_info:
            async with with_deadline_async(0.1, "slow_async"):
                await asyncio.sleep(1.0)

        assert exc_info.value.timeout == 0.1
        assert exc_info.value.operation == "slow_async"

    @pytest.mark.asyncio
    async def test_async_nested_deadlines(self):
        """Test nested async deadlines."""
        async with with_deadline_async(10.0, "outer"):
            async with with_deadline_async(1.0, "inner"):
                remaining = get_remaining_deadline()
                assert remaining is not None
                assert remaining <= 1.0


class TestTimeoutDecorator:
    """Tests for the timeout decorator."""

    def test_sync_function_success(self):
        """Test decorator on sync function that succeeds."""

        @timeout(5.0)
        def quick_func():
            return "done"

        assert quick_func() == "done"

    def test_sync_function_timeout(self):
        """Test decorator on sync function that times out."""

        @timeout(0.1)
        def slow_func():
            time.sleep(1.0)
            return "done"

        with pytest.raises(TimeoutExpired):
            slow_func()

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test decorator on async function that succeeds."""

        @timeout(5.0)
        async def quick_async():
            return "done"

        result = await quick_async()
        assert result == "done"

    @pytest.mark.asyncio
    async def test_async_function_timeout(self):
        """Test decorator on async function that times out."""

        @timeout(0.1)
        async def slow_async():
            await asyncio.sleep(1.0)
            return "done"

        with pytest.raises(TimeoutExpired):
            await slow_async()

    def test_decorator_preserves_metadata(self):
        """Test decorator preserves function metadata."""

        @timeout(5.0)
        def my_function():
            """My docstring."""
            return "result"

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_decorator_with_operation_name(self):
        """Test decorator with custom operation name."""

        @timeout(0.1, operation="custom_op")
        def slow_func():
            time.sleep(1.0)

        try:
            slow_func()
        except TimeoutExpired as e:
            assert e.operation == "custom_op"


class TestRunWithTimeout:
    """Tests for run_with_timeout helper."""

    def test_success_within_timeout(self):
        """Test function completing within timeout."""

        def quick():
            return 42

        result = run_with_timeout(quick, timeout_seconds=5.0)
        assert result == 42

    def test_timeout_exception(self):
        """Test timeout raises exception."""

        def slow():
            time.sleep(1.0)
            return 42

        with pytest.raises(TimeoutExpired):
            run_with_timeout(slow, timeout_seconds=0.1, operation="slow_op")

    def test_with_args_and_kwargs(self):
        """Test passing args and kwargs."""

        def add(a, b, c=0):
            return a + b + c

        result = run_with_timeout(add, timeout_seconds=5.0, args=(1, 2), kwargs={"c": 3})
        assert result == 6

    def test_exception_propagation(self):
        """Test that function exceptions are propagated."""

        def failing():
            raise ValueError("intentional")

        with pytest.raises(ValueError, match="intentional"):
            run_with_timeout(failing, timeout_seconds=5.0)


class TestDeadlineHelpers:
    """Tests for deadline helper functions."""

    def test_get_remaining_deadline_none_outside_context(self):
        """Test get_remaining_deadline returns None outside context."""
        remaining = get_remaining_deadline()
        assert remaining is None

    def test_get_remaining_deadline_inside_context(self):
        """Test get_remaining_deadline returns value inside context."""
        with with_deadline(5.0, "test"):
            remaining = get_remaining_deadline()
            assert remaining is not None
            assert 4.5 < remaining <= 5.0

    def test_check_deadline_no_raise_when_valid(self):
        """Test check_deadline doesn't raise when time remaining."""
        with with_deadline(5.0, "test"):
            check_deadline()  # Should not raise

    def test_check_deadline_raises_when_expired(self):
        """Test check_deadline raises when deadline expired."""
        # Create an already-expired context by manipulating the deadline
        with with_deadline(0.001, "test"):
            time.sleep(0.1)  # generous sleep to avoid Windows timing flakes
            with pytest.raises(TimeoutExpired):
                check_deadline()

    def test_check_deadline_outside_context(self):
        """Test check_deadline does nothing outside context."""
        check_deadline()  # Should not raise


class TestTimeoutExpiredException:
    """Tests for TimeoutExpired exception."""

    def test_exception_attributes(self):
        """Test exception has correct attributes."""
        exc = TimeoutExpired(
            timeout=5.0,
            elapsed=5.1,
            operation="my_op",
        )
        assert exc.timeout == 5.0
        assert exc.elapsed == 5.1
        assert exc.operation == "my_op"

    def test_exception_str(self):
        """Test exception string representation."""
        exc = TimeoutExpired(timeout=5.0, elapsed=5.1, operation="my_op")
        s = str(exc)
        assert "5.0" in s
        assert "my_op" in s

    def test_exception_default_operation(self):
        """Test exception default operation name."""
        exc = TimeoutExpired(timeout=5.0)
        assert exc.operation == "operation"

    def test_exception_is_timeout_error(self):
        """Test exception inherits from TimeoutError."""
        exc = TimeoutExpired(timeout=5.0)
        assert isinstance(exc, TimeoutError)
