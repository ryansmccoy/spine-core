"""Tests for ``spine.observability.logging`` — structured logging, context, configuration."""

from __future__ import annotations

import io
import json

import pytest

from spine.observability.logging import (
    BoundLogger,
    LogConfig,
    StructuredLogger,
    add_context,
    clear_context,
    configure_logging,
    get_context,
    get_logger,
    log_context,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_context():
    """Ensure context is empty before and after every test."""
    clear_context()
    yield
    clear_context()


# ---------------------------------------------------------------------------
# StructuredLogger
# ---------------------------------------------------------------------------


class TestStructuredLogger:
    def test_create_logger(self):
        logger = StructuredLogger("test.module")
        assert logger.name == "test.module"

    def test_info_json_output(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf)
        logger = StructuredLogger("test.json")
        logger.info("hello", user="alice")

        output = buf.getvalue().strip()
        data = json.loads(output)
        assert data["message"] == "hello"
        assert data["log.level"] == "info"
        assert data["log.logger"] == "test.json"
        assert data["fields"]["user"] == "alice"

    def test_info_plain_text_output(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=False, output=buf)
        logger = StructuredLogger("test.plain")
        logger.info("plain message")

        output = buf.getvalue().strip()
        assert "plain message" in output
        assert "test.plain" in output

    def test_debug_suppressed_at_info_level(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf)
        logger = StructuredLogger("test.suppress")
        logger.debug("should not appear")

        assert buf.getvalue() == ""

    def test_debug_visible_at_debug_level(self):
        buf = io.StringIO()
        configure_logging(level="DEBUG", json_output=True, output=buf)
        logger = StructuredLogger("test.visible")
        logger.debug("debug visible")

        output = buf.getvalue().strip()
        data = json.loads(output)
        assert data["message"] == "debug visible"

    def test_warning_level(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf)
        logger = StructuredLogger("test.warn")
        logger.warning("caution")

        data = json.loads(buf.getvalue().strip())
        assert data["log.level"] == "warning"

    def test_error_with_exception(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf)
        logger = StructuredLogger("test.exc")
        try:
            raise ValueError("boom")
        except ValueError as exc:
            logger.error("failed", exc=exc)

        data = json.loads(buf.getvalue().strip())
        assert data["error.type"] == "ValueError"
        assert data["error.message"] == "boom"
        assert "Traceback" in data.get("error.stack_trace", "")

    def test_critical_level(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf)
        logger = StructuredLogger("test.crit")
        logger.critical("catastrophe")

        data = json.loads(buf.getvalue().strip())
        assert data["log.level"] == "critical"

    def test_pretty_print_json(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, pretty_print=True, output=buf)
        logger = StructuredLogger("test.pretty")
        logger.info("pretty")

        output = buf.getvalue()
        # Pretty-printed JSON has newlines with indentation
        assert "\n" in output
        data = json.loads(output)
        assert data["message"] == "pretty"


# ---------------------------------------------------------------------------
# Context management
# ---------------------------------------------------------------------------


class TestContext:
    def test_add_and_get_context(self):
        add_context(request_id="r-1", user_id="u-1")
        ctx = get_context()
        assert ctx["request_id"] == "r-1"
        assert ctx["user_id"] == "u-1"

    def test_clear_context(self):
        add_context(key="value")
        clear_context()
        assert get_context() == {}

    def test_log_context_manager(self):
        add_context(outer="yes")
        with log_context(request_id="ctx-123"):
            ctx = get_context()
            assert ctx["request_id"] == "ctx-123"
            assert ctx.get("outer") == "yes"
        # After exiting, outer context should be restored
        after = get_context()
        assert after.get("outer") == "yes"
        assert "request_id" not in after

    def test_log_context_restores_empty(self):
        with log_context(tmp="val"):
            assert get_context()["tmp"] == "val"
        assert get_context() == {}

    def test_context_included_in_log_output(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf)
        add_context(request_id="r-42")
        logger = StructuredLogger("test.ctx_log")
        logger.info("with context")

        data = json.loads(buf.getvalue().strip())
        assert data.get("trace.id") == "r-42"
        assert data["context"]["request_id"] == "r-42"


# ---------------------------------------------------------------------------
# BoundLogger
# ---------------------------------------------------------------------------


class TestBoundLogger:
    def test_bound_fields_included(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf)
        base = StructuredLogger("test.bound")
        bound = BoundLogger(base, {"component": "ingest"})
        bound.info("ingesting data")

        data = json.loads(buf.getvalue().strip())
        assert data["fields"]["component"] == "ingest"

    def test_bound_extra_fields_merged(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf)
        base = StructuredLogger("test.merge")
        bound = BoundLogger(base, {"component": "ingest"})
        bound.info("row done", row=42)

        data = json.loads(buf.getvalue().strip())
        assert data["fields"]["component"] == "ingest"
        assert data["fields"]["row"] == 42

    def test_bind_creates_new_logger(self):
        base = StructuredLogger("test.rebind")
        bound1 = BoundLogger(base, {"a": 1})
        bound2 = bound1.bind(b=2)
        assert bound2._fields == {"a": 1, "b": 2}
        # Original unchanged
        assert bound1._fields == {"a": 1}


# ---------------------------------------------------------------------------
# get_logger / configure_logging
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_same_instance(self):
        logger1 = get_logger("test.singleton")
        logger2 = get_logger("test.singleton")
        assert logger1 is logger2

    def test_different_name_different_instance(self):
        l1 = get_logger("test.a")
        l2 = get_logger("test.b")
        assert l1 is not l2


class TestConfigureLogging:
    def test_configure_sets_level(self):
        buf = io.StringIO()
        configure_logging(level="ERROR", json_output=True, output=buf)
        logger = StructuredLogger("test.cfg")
        logger.info("suppressed")
        assert buf.getvalue() == ""
        logger.error("visible")
        assert buf.getvalue() != ""

    def test_configure_service_name(self):
        buf = io.StringIO()
        configure_logging(level="INFO", json_output=True, output=buf, service_name="my-svc")
        logger = StructuredLogger("test.svc")
        logger.info("hi")
        data = json.loads(buf.getvalue().strip())
        assert data["service.name"] == "my-svc"


# ---------------------------------------------------------------------------
# LogConfig
# ---------------------------------------------------------------------------


class TestLogConfig:
    def test_defaults(self):
        cfg = LogConfig()
        assert cfg.level == "INFO"
        assert cfg.json_output is True
        assert cfg.service_name == "spine"
        assert cfg.environment == "development"

    def test_custom_values(self):
        cfg = LogConfig(level="DEBUG", service_name="test-app", environment="staging")
        assert cfg.level == "DEBUG"
        assert cfg.service_name == "test-app"
        assert cfg.environment == "staging"
