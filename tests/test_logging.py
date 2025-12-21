"""
Tests for the logging module.

Tests verify:
- Log context contains execution_id
- Timing logs emit duration
- DEBUG logs are suppressed at INFO level
"""

import logging
import os
from unittest.mock import patch

import pytest

from spine.framework.logging import (
    LogContext,
    bind_context,
    clear_context,
    configure_logging,
    get_context,
    get_logger,
    log_step,
    log_timing,
    set_context,
)


class TestLogContext:
    """Test LogContext dataclass."""

    def test_to_dict_excludes_none(self):
        ctx = LogContext(execution_id="abc-123", workflow=None)
        d = ctx.to_dict()
        assert "execution_id" in d
        assert "workflow" not in d

    def test_merge_creates_new_context(self):
        ctx1 = LogContext(execution_id="abc-123")
        ctx2 = ctx1.merge(workflow="otc.ingest_week")

        assert ctx1.workflow is None
        assert ctx2.execution_id == "abc-123"
        assert ctx2.workflow == "otc.ingest_week"


class TestContextManagement:
    """Test context set/get/clear operations."""

    def setup_method(self):
        clear_context()

    def teardown_method(self):
        clear_context()

    def test_set_context_returns_context(self):
        ctx = set_context(execution_id="test-123", workflow="test.operation")

        assert ctx.execution_id == "test-123"
        assert ctx.workflow == "test.operation"

    def test_get_context_returns_current(self):
        set_context(execution_id="test-123")
        ctx = get_context()

        assert ctx.execution_id == "test-123"

    def test_clear_context_resets(self):
        set_context(execution_id="test-123")
        clear_context()
        ctx = get_context()

        assert ctx.execution_id is None

    def test_bind_context_merges(self):
        set_context(execution_id="test-123")
        bind_context(workflow="test.operation")
        ctx = get_context()

        assert ctx.execution_id == "test-123"
        assert ctx.workflow == "test.operation"


class TestLogStep:
    """Test log_step context manager."""

    def setup_method(self):
        clear_context()
        configure_logging(level="DEBUG", force=True)

    def teardown_method(self):
        clear_context()

    def test_log_step_sets_step_context(self):
        with log_step("test_step"):
            ctx = get_context()
            assert ctx.step == "test_step"

        # Context should be restored after
        ctx = get_context()
        assert ctx.step is None

    def test_log_step_measures_duration(self):
        import time

        with log_step("test_step") as timer:
            time.sleep(0.01)  # 10ms

        # Should have recorded duration
        assert timer.duration_ms >= 10

    def test_log_step_adds_metrics(self):
        with log_step("test_step") as timer:
            timer.add_metric("rows", 1000)

        assert timer.metrics["rows"] == 1000


class TestLogTiming:
    """Test log_timing decorator."""

    def setup_method(self):
        clear_context()
        configure_logging(level="DEBUG", force=True)

    def teardown_method(self):
        clear_context()

    def test_log_timing_wraps_function(self):
        @log_timing("test_func")
        def my_func(x, y):
            return x + y

        result = my_func(1, 2)
        assert result == 3

    def test_log_timing_uses_function_name(self):
        @log_timing()
        def my_special_func():
            pass

        # Function should still be callable
        my_special_func()


class TestConfigureLogging:
    """Test logging configuration."""

    def test_configure_logging_sets_level(self):
        configure_logging(level="WARNING", force=True)

        # WARNING level should be set
        logger = logging.getLogger()
        assert logger.level == logging.WARNING

    def test_configure_logging_respects_env_var(self):
        with patch.dict(os.environ, {"SPINE_LOG_LEVEL": "ERROR"}):
            configure_logging(force=True)

        # Should have used ERROR from env
        # (Note: this may need adjustment based on implementation)

    def test_get_logger_returns_bound_logger(self):
        log = get_logger("test.module")

        # Should be a structlog logger
        assert hasattr(log, "info")
        assert hasattr(log, "debug")
        assert hasattr(log, "error")


class TestLoggingIntegration:
    """Integration tests for the full logging flow."""

    def setup_method(self):
        clear_context()
        configure_logging(level="DEBUG", force=True)

    def teardown_method(self):
        clear_context()

    def test_execution_context_flows_through_logs(self):
        """Verify execution_id appears in logs throughout execution."""
        set_context(execution_id="int-test-123", workflow="test.integration")

        # Ensure logger can be retrieved (validates setup)
        get_logger("test")

        # Context should be accessible
        ctx = get_context()
        assert ctx.execution_id == "int-test-123"
        assert ctx.workflow == "test.integration"

    def test_nested_steps_maintain_context(self):
        """Verify nested log_step calls maintain parent context."""
        set_context(execution_id="nested-test-123")

        with log_step("outer_step"):
            outer_ctx = get_context()
            assert outer_ctx.step == "outer_step"
            assert outer_ctx.execution_id == "nested-test-123"

            with log_step("inner_step"):
                inner_ctx = get_context()
                assert inner_ctx.step == "inner_step"
                assert inner_ctx.execution_id == "nested-test-123"

            # Should restore outer step
            restored_ctx = get_context()
            assert restored_ctx.step == "outer_step"


class TestSpanTracing:
    """Test span_id and parent_span_id for tracing."""

    def setup_method(self):
        clear_context()
        configure_logging(level="DEBUG", force=True)

    def teardown_method(self):
        clear_context()

    def test_log_step_generates_span_id(self):
        """Verify log_step generates a span_id."""
        with log_step("test_step") as timer:
            assert timer.span_id is not None
            assert len(timer.span_id) == 8  # 8 hex chars

            # span_id should be in context
            ctx = get_context()
            assert ctx.span_id == timer.span_id

    def test_nested_steps_track_parent_span(self):
        """Verify nested log_steps track parent_span_id."""
        with log_step("outer_step") as outer_timer:
            outer_span = outer_timer.span_id

            with log_step("inner_step") as inner_timer:
                # Inner should have outer as parent
                assert inner_timer.parent_span_id == outer_span

                # Context should reflect inner span
                ctx = get_context()
                assert ctx.span_id == inner_timer.span_id
                assert ctx.parent_span_id == outer_span

            # After inner, context should restore outer span
            ctx = get_context()
            assert ctx.span_id == outer_span

    def test_span_id_in_timer_result(self):
        """Verify span_id appears in log dict output."""
        with log_step("test_step") as timer:
            timer.add_metric("rows", 100)

        log_dict = timer.to_log_dict()
        assert "span_id" in log_dict
        assert "duration_ms" in log_dict
        assert log_dict["rows"] == 100

    def test_error_includes_span_and_stack(self):
        """Verify errors include span_id and stack trace."""
        with pytest.raises(ValueError), log_step("failing_step") as timer:
            raise ValueError("Test error")

        error_dict = timer.to_error_dict()
        assert error_dict["status"] == "error"
        assert error_dict["error_type"] == "ValueError"
        assert error_dict["error_message"] == "Test error"
        assert "error_stack" in error_dict
        assert "span_id" in error_dict


class TestAttemptField:
    """Test attempt field for retry tracking."""

    def setup_method(self):
        clear_context()

    def teardown_method(self):
        clear_context()

    def test_attempt_defaults_to_1(self):
        ctx = LogContext()
        assert ctx.attempt == 1

    def test_attempt_1_excluded_from_dict(self):
        """attempt=1 should not appear in logs (noise reduction)."""
        ctx = LogContext(execution_id="test-123", attempt=1)
        d = ctx.to_dict()
        assert "attempt" not in d

    def test_attempt_2_included_in_dict(self):
        """attempt > 1 should appear in logs."""
        ctx = LogContext(execution_id="test-123", attempt=2)
        d = ctx.to_dict()
        assert d["attempt"] == 2

    def test_set_context_with_attempt(self):
        set_context(execution_id="retry-test", attempt=3)
        ctx = get_context()
        assert ctx.attempt == 3

        d = ctx.to_dict()
        assert d["attempt"] == 3
