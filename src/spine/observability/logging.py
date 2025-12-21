"""Structured JSON logging for ELK/DataDog/OpenTelemetry ingestion.

Provides standardized structured logging that can be ingested by:
- Elasticsearch/Logstash/Kibana (ELK Stack)
- DataDog Log Management
- Grafana Loki
- OpenTelemetry Collector
- Splunk
- Any JSON-based log aggregator

Features:
- JSON formatted output (machine-readable)
- Correlation IDs for request tracing
- Context propagation (request_id, user_id, etc.)
- Standard fields (timestamp, level, logger, message)
- Exception formatting with stack traces
- Performance timing helpers

Example:
    >>> from spine.observability.logging import get_logger, configure_logging
    >>>
    >>> configure_logging(level="INFO", json_output=True)
    >>> logger = get_logger("my.module")
    >>>
    >>> logger.info("Processing started", operation="sec.filings", records=100)
    >>> # Output: {"timestamp": "2024-01-01T00:00:00Z", "level": "INFO", ...}
"""

import json
import logging
import os
import sys
import threading
import traceback
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, TextIO


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class LogLevel(str, Enum):
    """Log levels matching Python logging."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# Context variables for correlation
_request_context: ContextVar[dict[str, Any]] = ContextVar("request_context")  # noqa: B039


def add_context(**kwargs: Any) -> None:
    """Add values to the current logging context.

    Values added here will be included in all log messages
    for the current async context/thread.

    Example:
        >>> add_context(request_id="abc-123", user_id="user-456")
        >>> logger.info("Processing")  # includes request_id, user_id
    """
    ctx = dict(_request_context.get({}))
    ctx.update(kwargs)
    _request_context.set(ctx)


def clear_context() -> None:
    """Clear the current logging context."""
    _request_context.set({})


def get_context() -> dict[str, Any]:
    """Get the current logging context."""
    return dict(_request_context.get({}))


@dataclass
class LogConfig:
    """Logging configuration."""

    level: str = "INFO"
    json_output: bool = True
    include_timestamp: bool = True
    include_hostname: bool = True
    include_process: bool = True
    include_thread: bool = False
    pretty_print: bool = False  # For development
    output: TextIO = field(default_factory=lambda: sys.stdout)

    # Standard fields
    service_name: str = "spine"
    environment: str = "development"
    version: str = "1.0.0"


# Global config
_config = LogConfig()


def configure_logging(
    level: str = "INFO",
    json_output: bool = True,
    service_name: str = "spine",
    environment: str | None = None,
    version: str = "1.0.0",
    pretty_print: bool = False,
    **kwargs: Any,
) -> None:
    """Configure global logging settings.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: Output JSON (True) or plain text (False)
        service_name: Name of the service for log aggregation
        environment: Environment name (auto-detected if None)
        version: Application version
        pretty_print: Pretty-print JSON (for development)
        **kwargs: Additional config options
    """
    global _config

    env = environment or os.environ.get("ENVIRONMENT", "development")

    _config = LogConfig(
        level=level.upper(),
        json_output=json_output,
        service_name=service_name,
        environment=env,
        version=version,
        pretty_print=pretty_print,
        **kwargs,
    )

    # Also configure Python's logging
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level)


class JsonFormatter(logging.Formatter):
    """JSON formatter for standard logging handlers.

    Formats log records as JSON for ingestion by log aggregators.
    Compatible with ELK, DataDog, Loki, etc.
    """

    def __init__(
        self,
        service_name: str = "spine",
        environment: str = "development",
        include_stack: bool = True,
    ):
        super().__init__()
        self.service_name = service_name
        self.environment = environment
        self.include_stack = include_stack

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Base fields (ECS-compatible)
        log_dict: dict[str, Any] = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "log.level": record.levelname.lower(),
            "log.logger": record.name,
            "message": record.getMessage(),
            # Service info
            "service.name": self.service_name,
            "service.environment": self.environment,
            # Source location
            "log.origin.file.name": record.filename,
            "log.origin.file.line": record.lineno,
            "log.origin.function": record.funcName,
        }

        # Add process/thread info
        log_dict["process.pid"] = record.process
        log_dict["process.thread.id"] = record.thread

        # Add exception info
        if record.exc_info and self.include_stack:
            log_dict["error.type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            log_dict["error.message"] = str(record.exc_info[1]) if record.exc_info[1] else None
            log_dict["error.stack_trace"] = "".join(traceback.format_exception(*record.exc_info))

        # Add context from contextvars
        ctx = get_context()
        if ctx:
            log_dict["context"] = ctx

        # Add any extra fields
        if hasattr(record, "extra_fields"):
            log_dict.update(record.extra_fields)

        return json.dumps(log_dict, default=str)


class StructuredLogger:
    """Structured logger with JSON output and context support.

    This is the recommended logger for spine applications.
    """

    def __init__(self, name: str):
        """Initialize logger with a name.

        Args:
            name: Logger name (typically __name__)
        """
        self.name = name
        self._logger = logging.getLogger(name)
        self._local = threading.local()

    def _should_log(self, level: str) -> bool:
        """Check if message should be logged at given level."""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        config_level = level_map.get(_config.level, logging.INFO)
        msg_level = level_map.get(level, logging.INFO)
        return msg_level >= config_level

    def _format_message(
        self,
        level: str,
        message: str,
        exc_info: Exception | None = None,
        **fields: Any,
    ) -> str:
        """Format a log message as JSON."""
        log_dict: dict[str, Any] = {
            # ECS-compatible timestamp
            "@timestamp": utcnow().isoformat(),
            # Log fields
            "log.level": level.lower(),
            "log.logger": self.name,
            "message": message,
            # Service metadata
            "service.name": _config.service_name,
            "service.environment": _config.environment,
            "service.version": _config.version,
        }

        # Add hostname
        if _config.include_hostname:
            import socket

            log_dict["host.name"] = socket.gethostname()

        # Add process info
        if _config.include_process:
            log_dict["process.pid"] = os.getpid()

        # Add thread info
        if _config.include_thread:
            log_dict["process.thread.name"] = threading.current_thread().name

        # Add context
        ctx = get_context()
        if ctx:
            # Flatten common fields to top level for better searching
            if "request_id" in ctx:
                log_dict["trace.id"] = ctx["request_id"]
            if "user_id" in ctx:
                log_dict["user.id"] = ctx["user_id"]
            if "execution_id" in ctx:
                log_dict["execution.id"] = ctx["execution_id"]
            log_dict["context"] = ctx

        # Add extra fields
        if fields:
            log_dict["fields"] = fields

        # Add exception info
        if exc_info:
            log_dict["error.type"] = type(exc_info).__name__
            log_dict["error.message"] = str(exc_info)
            log_dict["error.stack_trace"] = "".join(
                traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__)
            )

        if _config.json_output:
            if _config.pretty_print:
                return json.dumps(log_dict, indent=2, default=str)
            return json.dumps(log_dict, default=str)
        else:
            # Plain text format for development
            timestamp = log_dict["@timestamp"]
            fields_str = " ".join(f"{k}={v}" for k, v in fields.items())
            return f"{timestamp} [{level}] {self.name}: {message} {fields_str}".strip()

    def _log(
        self,
        level: str,
        message: str,
        exc_info: Exception | None = None,
        **fields: Any,
    ) -> None:
        """Internal log method."""
        if not self._should_log(level):
            return

        formatted = self._format_message(level, message, exc_info, **fields)
        print(formatted, file=_config.output)

    def debug(self, message: str, **fields: Any) -> None:
        """Log at DEBUG level."""
        self._log("DEBUG", message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        """Log at INFO level."""
        self._log("INFO", message, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        """Log at WARNING level."""
        self._log("WARNING", message, **fields)

    def warn(self, message: str, **fields: Any) -> None:
        """Alias for warning."""
        self.warning(message, **fields)

    def error(self, message: str, exc: Exception | None = None, **fields: Any) -> None:
        """Log at ERROR level, optionally with exception."""
        self._log("ERROR", message, exc_info=exc, **fields)

    def critical(self, message: str, exc: Exception | None = None, **fields: Any) -> None:
        """Log at CRITICAL level."""
        self._log("CRITICAL", message, exc_info=exc, **fields)

    def exception(self, message: str, exc: Exception, **fields: Any) -> None:
        """Log an exception at ERROR level."""
        self.error(message, exc=exc, **fields)

    def bind(self, **fields: Any) -> "BoundLogger":
        """Create a bound logger with preset fields.

        Example:
            >>> log = logger.bind(operation="sec.filings", execution_id="abc")
            >>> log.info("Started")  # includes operation and execution_id
        """
        return BoundLogger(self, fields)


class BoundLogger:
    """Logger with preset fields that are included in every message."""

    def __init__(self, logger: StructuredLogger, fields: dict[str, Any]):
        self._logger = logger
        self._fields = fields

    def _merge_fields(self, **extra: Any) -> dict[str, Any]:
        """Merge preset fields with extra fields."""
        merged = dict(self._fields)
        merged.update(extra)
        return merged

    def debug(self, message: str, **fields: Any) -> None:
        self._logger.debug(message, **self._merge_fields(**fields))

    def info(self, message: str, **fields: Any) -> None:
        self._logger.info(message, **self._merge_fields(**fields))

    def warning(self, message: str, **fields: Any) -> None:
        self._logger.warning(message, **self._merge_fields(**fields))

    def error(self, message: str, exc: Exception | None = None, **fields: Any) -> None:
        self._logger.error(message, exc=exc, **self._merge_fields(**fields))

    def critical(self, message: str, exc: Exception | None = None, **fields: Any) -> None:
        self._logger.critical(message, exc=exc, **self._merge_fields(**fields))

    def bind(self, **fields: Any) -> "BoundLogger":
        """Create a new bound logger with additional fields."""
        merged = dict(self._fields)
        merged.update(fields)
        return BoundLogger(self._logger, merged)


# Logger cache
_loggers: dict[str, StructuredLogger] = {}
_logger_lock = threading.Lock()


def get_logger(name: str) -> StructuredLogger:
    """Get or create a structured logger by name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        StructuredLogger instance
    """
    with _logger_lock:
        if name not in _loggers:
            _loggers[name] = StructuredLogger(name)
        return _loggers[name]


# Convenience functions for request context
def log_context(**kwargs: Any):
    """Context manager for temporary logging context.

    Example:
        >>> with log_context(request_id="abc-123"):
        ...     logger.info("Processing")  # includes request_id
    """
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        old_ctx = get_context()
        add_context(**kwargs)
        try:
            yield
        finally:
            clear_context()
            if old_ctx:
                add_context(**old_ctx)

    return _ctx()
