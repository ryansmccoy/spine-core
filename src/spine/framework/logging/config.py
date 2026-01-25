"""
Logging configuration.

Provides a single entry point for configuring structured logging.
Supports environment-based configuration for:
- Log level (DEBUG, INFO, WARNING, ERROR)
- Output format (json, console)
- Pipeline-specific debug filtering

Configuration is read from environment variables:
- SPINE_LOG_LEVEL: DEBUG | INFO | WARNING | ERROR (default: INFO)
- SPINE_LOG_FORMAT: json | console (default: console)
- SPINE_LOG_PIPELINE_DEBUG: comma-separated pipeline names for verbose debug

Usage:
    # Configure at application startup
    from spine.framework.logging import configure_logging
    configure_logging()

    # Or with explicit settings
    configure_logging(level="DEBUG", format="json")
"""

import logging
import os
import sys
from typing import Literal

import structlog
from structlog.types import Processor

from spine.framework.logging.context import add_context_processor

# Track if logging has been configured
_configured = False


def configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None = None,
    format: Literal["json", "console"] | None = None,
    pipeline_debug: list[str] | None = None,
    force: bool = False,
) -> None:
    """
    Configure structured logging for the application.

    Should be called once at application startup (CLI entry, worker startup, etc.).
    Subsequent calls are no-ops unless force=True.

    Args:
        level: Log level (overrides SPINE_LOG_LEVEL env var)
        format: Output format (overrides SPINE_LOG_FORMAT env var)
        pipeline_debug: Pipeline names for verbose debug logging
        force: Reconfigure even if already configured
    """
    global _configured

    if _configured and not force:
        return

    # Resolve configuration from args or environment
    log_level = level or os.environ.get("SPINE_LOG_LEVEL", "INFO").upper()
    log_format = format or os.environ.get("SPINE_LOG_FORMAT", "console").lower()

    # Pipeline-specific debug filter (comma-separated list)
    debug_pipelines = pipeline_debug
    if debug_pipelines is None:
        env_pipelines = os.environ.get("SPINE_LOG_PIPELINE_DEBUG", "")
        debug_pipelines = [p.strip() for p in env_pipelines.split(",") if p.strip()]

    # Build processor chain
    processors: list[Processor] = [
        # Add log level to stdlib logger
        structlog.stdlib.add_log_level,
        # Add logger name
        structlog.stdlib.add_logger_name,
        # Add timestamp in UTC ISO-8601 with Z suffix
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Add execution context from contextvars
        add_context_processor,
        # Format exception info with full details for ERROR logs
        structlog.processors.format_exc_info,
        # Stack info if requested
        structlog.processors.StackInfoRenderer(),
    ]

    # Add pipeline debug filter if specified
    if debug_pipelines:
        processors.insert(0, _make_pipeline_filter(debug_pipelines, log_level))
    else:
        # Standard level filter
        processors.insert(0, structlog.stdlib.filter_by_level)

    # Choose renderer based on format
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            )
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to match
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, log_level),
        force=True,  # Override any existing config
    )

    # Also configure specific loggers we care about
    for logger_name in ["market_spine", "spine"]:
        logging.getLogger(logger_name).setLevel(getattr(logging, log_level))

    _configured = True


def _make_pipeline_filter(debug_pipelines: list[str], default_level: str):
    """
    Create a processor that enables DEBUG for specific pipelines.

    For listed pipelines, always allow DEBUG.
    For others, use the default level.
    """
    default_level_num = getattr(logging, default_level)

    def pipeline_debug_filter(
        logger: structlog.types.WrappedLogger,
        method_name: str,
        event_dict: dict,
    ) -> dict:
        # Get the pipeline from event or context
        pipeline = event_dict.get("pipeline")

        # Get log level
        level = event_dict.get("level", method_name)
        level_num = getattr(logging, level.upper(), logging.DEBUG)

        # Allow if pipeline matches debug list
        if pipeline and any(p in pipeline for p in debug_pipelines):
            return event_dict

        # Otherwise apply default filter
        if level_num < default_level_num:
            raise structlog.DropEvent

        return event_dict

    return pipeline_debug_filter


def is_debug_enabled() -> bool:
    """Check if DEBUG level logging is enabled."""
    return logging.getLogger().isEnabledFor(logging.DEBUG)


def is_configured() -> bool:
    """Check if logging has been configured."""
    return _configured
