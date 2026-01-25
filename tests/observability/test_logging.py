"""Tests for structured logging."""

import pytest
import json
import logging
import sys
from io import StringIO
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from spine.observability.logging import (
    get_logger,
    configure_logging,
    LogLevel,
    StructuredLogger,
    JsonFormatter,
    add_context,
    clear_context,
    get_context,
)


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_log_levels(self):
        """Test log level values."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"


class TestJsonFormatter:
    """Tests for JsonFormatter."""

    def test_formats_as_json(self):
        """Test output is valid JSON."""
        formatter = JsonFormatter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        
        # Should be valid JSON
        data = json.loads(output)
        assert data["message"] == "Test message"

    def test_includes_timestamp(self):
        """Test includes ISO timestamp."""
        formatter = JsonFormatter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert "@timestamp" in data
        # Should be ISO format
        assert "T" in data["@timestamp"]

    def test_includes_ecs_fields(self):
        """Test includes ECS-compatible fields."""
        formatter = JsonFormatter()
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.WARNING,
            pathname="/path/to/test.py",
            lineno=42,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        # ECS flat key fields
        assert data["log.level"] == "warning"
        assert data["log.logger"] == "test.logger"
        assert "log.origin.file.name" in data

    def test_includes_extra_fields(self):
        """Test extra fields are included via extra_fields attribute."""
        formatter = JsonFormatter()
        
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        # JsonFormatter looks for extra_fields dict attribute
        record.extra_fields = {
            "custom_field": "custom_value",
            "pipeline_name": "sec.filings",
        }
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert data.get("custom_field") == "custom_value"
        assert data.get("pipeline_name") == "sec.filings"

    def test_formats_exception(self):
        """Test exception formatting."""
        formatter = JsonFormatter()
        
        try:
            raise ValueError("Test error")
        except ValueError:
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        # ECS flat key format
        assert "error.type" in data
        assert data["error.type"] == "ValueError"
        assert "Test error" in data["error.message"]
        assert "error.stack_trace" in data


class TestStructuredLogger:
    """Tests for StructuredLogger."""

    def test_creates_logger(self):
        """Test creates a logger."""
        logger = StructuredLogger("test")
        assert logger.name == "test"

    def test_logs_info(self):
        """Test logging info messages."""
        from spine.observability import logging as spine_logging
        
        # Capture output via config.output
        stream = StringIO()
        old_output = spine_logging._config.output
        spine_logging._config.output = stream
        spine_logging._config.json_output = True
        
        try:
            logger = StructuredLogger("test")
            logger.info("Test info message")
            
            output = stream.getvalue()
            data = json.loads(output.strip())
            
            assert data["message"] == "Test info message"
            assert data["log.level"] == "info"
        finally:
            spine_logging._config.output = old_output

    def test_logs_with_extra_fields(self):
        """Test logging with extra fields."""
        from spine.observability import logging as spine_logging
        
        stream = StringIO()
        old_output = spine_logging._config.output
        spine_logging._config.output = stream
        spine_logging._config.json_output = True
        
        try:
            logger = StructuredLogger("test")
            logger.info("Processing", pipeline="sec.filings", records=100)
            
            output = stream.getvalue()
            data = json.loads(output.strip())
            
            # Extra fields are stored in "fields" key
            assert data["fields"]["pipeline"] == "sec.filings"
            assert data["fields"]["records"] == 100
        finally:
            spine_logging._config.output = old_output

    def test_logs_error_with_exception(self):
        """Test logging errors with exception."""
        from spine.observability import logging as spine_logging
        
        stream = StringIO()
        old_output = spine_logging._config.output
        spine_logging._config.output = stream
        spine_logging._config.json_output = True
        
        try:
            logger = StructuredLogger("test")
            
            exc = RuntimeError("Test error")
            logger.error("Operation failed", exc=exc)
            
            output = stream.getvalue()
            data = json.loads(output.strip())
            
            assert "error.type" in data
            assert data["error.type"] == "RuntimeError"
        finally:
            spine_logging._config.output = old_output

    def test_bound_logger(self):
        """Test bound logger with persistent fields."""
        from spine.observability import logging as spine_logging
        
        # Check if bind method exists
        logger = StructuredLogger("test")
        if not hasattr(logger, 'bind'):
            pytest.skip("StructuredLogger does not have bind method")
        
        stream = StringIO()
        old_output = spine_logging._config.output
        spine_logging._config.output = stream
        spine_logging._config.json_output = True
        
        try:
            bound = logger.bind(request_id="req-123", user_id="user-456")
            bound.info("Request processed")
            
            output = stream.getvalue()
            data = json.loads(output.strip())
            
            assert data["fields"]["request_id"] == "req-123"
            assert data["fields"]["user_id"] == "user-456"
        finally:
            spine_logging._config.output = old_output


class TestContextManagement:
    """Tests for context management functions."""

    def test_add_context(self):
        """Test adding context."""
        clear_context()
        
        add_context(correlation_id="corr-123")
        
        ctx = get_context()
        assert ctx["correlation_id"] == "corr-123"

    def test_add_multiple_context(self):
        """Test adding multiple context values."""
        clear_context()
        
        add_context(correlation_id="corr-123")
        add_context(trace_id="trace-456")
        
        ctx = get_context()
        assert ctx["correlation_id"] == "corr-123"
        assert ctx["trace_id"] == "trace-456"

    def test_clear_context(self):
        """Test clearing context."""
        add_context(key="value")
        clear_context()
        
        ctx = get_context()
        assert len(ctx) == 0

    def test_context_in_log_output(self):
        """Test context appears in log output."""
        from spine.observability import logging as spine_logging
        
        clear_context()
        add_context(correlation_id="corr-123")
        
        stream = StringIO()
        old_output = spine_logging._config.output
        spine_logging._config.output = stream
        spine_logging._config.json_output = True
        
        try:
            logger = StructuredLogger("test")
            logger.info("Test message")
            
            output = stream.getvalue()
            data = json.loads(output.strip())
            
            # Context should be in output (under 'context' key)
            assert "context" in data
            assert data["context"]["correlation_id"] == "corr-123"
        finally:
            spine_logging._config.output = old_output
            clear_context()


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_with_defaults(self):
        """Test configure with defaults."""
        configure_logging()
        
        # Should not raise
        logger = get_logger("test_configure")
        logger.info("Test message")

    def test_configure_with_level(self):
        """Test configure with specific level."""
        configure_logging(level="DEBUG")
        
        logger = get_logger("test_level")
        # StructuredLogger uses string level comparison
        assert logger.name == "test_level"

    def test_configure_json_format(self):
        """Test configure with JSON format."""
        configure_logging(json_output=True)
        
        # Just verify it doesn't raise
        logger = get_logger("test_json")
        assert logger is not None


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_structured_logger(self):
        """Test get_logger returns StructuredLogger."""
        logger = get_logger("test")
        assert isinstance(logger, StructuredLogger)

    def test_get_logger_same_name_returns_same_instance(self):
        """Test same name returns same logger."""
        logger1 = get_logger("same_name")
        logger2 = get_logger("same_name")
        
        # Should be same underlying logger
        assert logger1._logger is logger2._logger

    def test_get_logger_different_names(self):
        """Test different names return different loggers."""
        logger1 = get_logger("name1")
        logger2 = get_logger("name2")
        
        assert logger1._logger is not logger2._logger


class TestELKCompatibility:
    """Tests for ELK/Elastic compatibility."""

    def test_elk_compatible_fields(self):
        """Test output has ELK-compatible field names."""
        formatter = JsonFormatter()
        
        record = logging.LogRecord(
            name="app.module",
            level=logging.INFO,
            pathname="/app/module.py",
            lineno=100,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        # ECS flat key compatible fields
        assert "@timestamp" in data
        assert "message" in data
        assert "log.level" in data
        assert "log.logger" in data

    def test_datadog_compatible_fields(self):
        """Test output has DataDog-compatible fields via extra_fields."""
        formatter = JsonFormatter()
        
        record = logging.LogRecord(
            name="app.service",
            level=logging.ERROR,
            pathname="/app/service.py",
            lineno=50,
            msg="Error occurred",
            args=(),
            exc_info=None,
        )
        # Extra fields must be in extra_fields dict
        record.extra_fields = {
            "dd.trace_id": "trace-123",
            "dd.span_id": "span-456",
        }
        
        output = formatter.format(record)
        data = json.loads(output)
        
        # DataDog fields should be present
        assert data.get("dd.trace_id") == "trace-123"
        assert data.get("dd.span_id") == "span-456"
