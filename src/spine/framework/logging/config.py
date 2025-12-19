"""
Logging configuration.

Provides a single entry point for configuring structured logging.
Supports environment-based configuration for:
- Log level (DEBUG, INFO, WARNING, ERROR)
- Output format (json, console)
- Workflow-specific debug filtering

Configuration is read from environment variables:
- SPINE_LOG_LEVEL: DEBUG | INFO | WARNING | ERROR (default: INFO)
- SPINE_LOG_FORMAT: json | console (default: console)
- SPINE_LOG_WORKFLOW_DEBUG: comma-separated workflow names for verbose debug

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
from typing import Any, Literal

try:
    import structlog
    from structlog.types import Processor

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    structlog = None  # type: ignore

from spine.framework.logging.context import add_context_processor

# Track if logging has been configured
_configured = False


def configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] | None = None,
    format: Literal["json", "console"] | None = None,
    workflow_debug: list[str] | None = None,
    force: bool = False,
) -> None:
    """
    Configure structured logging for the application.

    Should be called once at application startup (CLI entry, worker startup, etc.).
    Subsequent calls are no-ops unless force=True.

    Falls back to stdlib logging.basicConfig() if structlog is not installed.

    Args:
        level: Log level (overrides SPINE_LOG_LEVEL env var)
        format: Output format (overrides SPINE_LOG_FORMAT env var)
        workflow_debug: Workflow names for verbose debug logging
        force: Reconfigure even if already configured
    """
    global _configured

    if _configured and not force:
        return

    # Resolve configuration from args or environment
    log_level = level or os.environ.get("SPINE_LOG_LEVEL", "INFO").upper()
    log_format = format or os.environ.get("SPINE_LOG_FORMAT", "console").lower()

    # Workflow-specific debug filter (comma-separated list)
    debug_workflows = workflow_debug
    if debug_workflows is None:
        env_workflows = os.environ.get("SPINE_LOG_WORKFLOW_DEBUG", "")
        debug_workflows = [p.strip() for p in env_workflows.split(",") if p.strip()]

    if not STRUCTLOG_AVAILABLE:
        # Fallback: stdlib-only logging
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            stream=sys.stderr,
            level=getattr(logging, log_level),
            force=True,
        )
        _configured = True
        return

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

    # Add workflow debug filter if specified
    if debug_workflows:
        processors.insert(0, _make_workflow_filter(debug_workflows, log_level))
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
    for logger_name in ["spine"]:
        logging.getLogger(logger_name).setLevel(getattr(logging, log_level))

    _configured = True


def _make_workflow_filter(debug_workflows: list[str], default_level: str):
    """
    Create a processor that enables DEBUG for specific workflows.

    For listed workflows, always allow DEBUG.
    For others, use the default level.
    """
    default_level_num = getattr(logging, default_level)

    def workflow_debug_filter(
        logger: Any,
        method_name: str,
        event_dict: dict,
    ) -> dict:
        # Get the workflow from event or context
        workflow = event_dict.get("workflow")

        # Get log level
        level = event_dict.get("level", method_name)
        level_num = getattr(logging, level.upper(), logging.DEBUG)

        # Allow if workflow matches debug list
        if workflow and any(w in workflow for w in debug_workflows):
            return event_dict

        # Otherwise apply default filter
        if level_num < default_level_num:
            raise structlog.DropEvent

        return event_dict

    return workflow_debug_filter


def is_debug_enabled() -> bool:
    """Check if DEBUG level logging is enabled."""
    return logging.getLogger().isEnabledFor(logging.DEBUG)


def is_configured() -> bool:
    """Check if logging has been configured."""
    return _configured
