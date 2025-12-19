"""
Spine Framework Logging - Structured, execution-aware logging.

This module provides:
- Structured logging with structlog
- Execution context propagation via contextvars
- Timing utilities for performance tracking
- Environment-based configuration

Usage:
    from spine.framework.logging import get_logger, configure_logging, log_step, set_context

    # Configure once at startup
    configure_logging()

    # Get a logger
    log = get_logger(__name__)

    # Set execution context (automatically attached to all logs)
    set_context(execution_id="abc-123", workflow="otc.ingest_week")

    # Log with timing
    with log_step("normalize_trades"):
        do_normalization()

    # Or use decorator
    @log_timing("compute_summaries")
    def compute_summaries():
        pass
"""

from spine.framework.logging.config import configure_logging
from spine.framework.logging.context import (
    LogContext,
    bind_context,
    clear_context,
    get_context,
    get_logger,
    set_context,
)
from spine.framework.logging.timing import log_db_operation, log_step, log_timing, timed_block

__all__ = [
    # Configuration
    "configure_logging",
    # Context
    "get_logger",
    "set_context",
    "clear_context",
    "get_context",
    "bind_context",
    "LogContext",
    # Timing
    "log_step",
    "log_timing",
    "timed_block",
    "log_db_operation",
]
