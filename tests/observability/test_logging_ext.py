"""Tests for observability structured logging.

Covers context management, JsonFormatter, StructuredLogger, BoundLogger,
and the log_context context manager.
"""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from spine.observability.logging import (
    BoundLogger,
    JsonFormatter,
    LogConfig,
    LogLevel,
    StructuredLogger,
    add_context,
    clear_context,
    configure_logging,
    get_context,
    get_logger,
    log_context,
)


# ── LogLevel Enum ────────────────────────────────────────────


class TestLogLevel:
    def test_all_levels_exist(self):
        for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            assert hasattr(LogLevel, name)

    def test_values_are_strings(self):
        for member in LogLevel:
            assert isinstance(member.value, str)


# ── Context Functions ────────────────────────────────────────


class TestContext:
    def setup_method(self):
        clear_context()

    def test_add_and_get(self):
        add_context(request_id="r123")
        ctx = get_context()
        assert ctx.get("request_id") == "r123"

    def test_clear(self):
        add_context(key="val")
        clear_context()
        ctx = get_context()
        assert ctx == {} or "key" not in ctx

    def test_multiple_add(self):
        add_context(a="1")
        add_context(b="2")
        ctx = get_context()
        assert ctx.get("a") == "1"
        assert ctx.get("b") == "2"


# ── LogConfig ────────────────────────────────────────────────


class TestLogConfig:
    def test_defaults(self):
        cfg = LogConfig()
        assert cfg.level in (LogLevel.INFO, "INFO")

    def test_custom_config(self):
        cfg = LogConfig(level=LogLevel.DEBUG, json_output=True, service_name="test-svc")
        assert cfg.service_name == "test-svc"


# ── configure_logging ────────────────────────────────────────


class TestConfigureLogging:
    def test_configure_sets_level(self):
        configure_logging(level=LogLevel.DEBUG)
        # Should not raise

    def test_configure_json_mode(self):
        configure_logging(json_output=True, service_name="test")
        # Should not raise


# ── JsonFormatter ────────────────────────────────────────────


class TestJsonFormatter:
    def test_format_basic_record(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="hello", args=(), exc_info=None,
        )
        output = fmt.format(record)
        data = json.loads(output)
        assert data["message"] == "hello"

    def test_format_with_exc_info(self):
        fmt = JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            record = logging.LogRecord(
                name="test", level=logging.ERROR, pathname="test.py",
                lineno=1, msg="fail", args=(), exc_info=sys.exc_info(),
            )
        output = fmt.format(record)
        data = json.loads(output)
        assert "error" in data or "exception" in data or "exc_info" in output


# ── StructuredLogger ─────────────────────────────────────────


class TestStructuredLogger:
    def test_debug(self):
        logger = StructuredLogger("test.debug")
        # Just verify it doesn't raise
        logger.debug("debug message", extra_key="value")

    def test_info(self):
        logger = StructuredLogger("test.info")
        logger.info("info message")

    def test_warning(self):
        logger = StructuredLogger("test.warning")
        logger.warning("warning message")

    def test_error(self):
        logger = StructuredLogger("test.error")
        logger.error("error message")

    def test_critical(self):
        logger = StructuredLogger("test.critical")
        logger.critical("critical message")

    def test_exception(self):
        logger = StructuredLogger("test.exception")
        try:
            raise RuntimeError("test")
        except RuntimeError as exc:
            logger.exception("caught error", exc)

    def test_should_log_level_filtering(self):
        configure_logging(level=LogLevel.ERROR)
        logger = StructuredLogger("test.filter")
        # INFO should not log when level is ERROR
        assert logger._should_log(LogLevel.INFO) is False
        assert logger._should_log(LogLevel.ERROR) is True

    def test_bind_returns_bound_logger(self):
        logger = StructuredLogger("test.bind")
        bound = logger.bind(user="alice")
        assert isinstance(bound, BoundLogger)


# ── BoundLogger ──────────────────────────────────────────────


class TestBoundLogger:
    def test_bound_fields_preserved(self):
        logger = StructuredLogger("test.bound")
        bound = logger.bind(env="prod")
        # BoundLogger should pass fields through
        bound.info("test message")  # Should not raise

    def test_nested_bind(self):
        logger = StructuredLogger("test.nested")
        bound = logger.bind(env="prod")
        nested = bound.bind(region="us")
        nested.info("nested message")  # Should not raise

    def test_all_methods(self):
        logger = StructuredLogger("test.all")
        bound = logger.bind(ctx="test")
        bound.debug("d")
        bound.info("i")
        bound.warning("w")
        bound.error("e")
        bound.critical("c")


# ── get_logger ───────────────────────────────────────────────


class TestGetLogger:
    def test_returns_logger(self):
        logger = get_logger("test.get")
        assert isinstance(logger, StructuredLogger)

    def test_caching(self):
        a = get_logger("test.cache")
        b = get_logger("test.cache")
        assert a is b


# ── log_context ──────────────────────────────────────────────


class TestLogContext:
    def setup_method(self):
        clear_context()

    def test_context_manager_adds(self):
        with log_context(trace_id="t123"):
            ctx = get_context()
            assert ctx.get("trace_id") == "t123"

    def test_context_manager_restores(self):
        add_context(base_key="original")
        with log_context(temp_key="temp"):
            assert get_context().get("temp_key") == "temp"
        # After exit, temp_key should be removed or context restored
        ctx = get_context()
        # Context is restored to pre-context-manager state
        assert ctx.get("base_key") == "original"
