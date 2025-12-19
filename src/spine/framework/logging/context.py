"""
Logging context management using contextvars.

This module provides execution-aware context that automatically attaches
to all log entries. Context is propagated through the call stack without
explicit parameter passing.

Design choice: contextvars
- Thread-safe and asyncio-compatible
- No need to pass context through every function
- Clean integration with structlog processors
- Works with Celery task context

Alternative approaches considered:
- logging.LoggerAdapter: Requires passing adapter instances everywhere
- Thread-local: Not asyncio-safe
- Global dict: Race conditions in concurrent scenarios
"""

import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    structlog = None  # type: ignore


def _utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 format with Z suffix."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _generate_span_id() -> str:
    """Generate a short span ID (8 hex chars)."""
    return uuid.uuid4().hex[:8]


@dataclass
class LogContext:
    """
    Execution context attached to all log entries.

    Core identifiers (always present in workflow execution):
        execution_id: Unique workflow execution ID
        workflow: Workflow name (e.g., "otc.ingest_week")

    Tracing (for nested timing blocks):
        span_id: Current span identifier
        parent_span_id: Parent span for nested operations

    Domain context:
        capture_id: Data capture identifier
        batch_id: Batch operation identifier
        domain: Domain name (e.g., "otc")

    Execution metadata:
        backend: Execution backend ("sync", "celery", etc.)
        attempt: Retry attempt number (default 1)

    Step context:
        step: Current processing step name

    Data context (normalized field names):
        week_ending: Week ending date
        tier: Data tier
    """

    # Core identifiers
    execution_id: str | None = None
    workflow: str | None = None

    # Tracing
    span_id: str | None = None
    parent_span_id: str | None = None

    # Domain context
    capture_id: str | None = None
    batch_id: str | None = None
    domain: str | None = None

    # Execution metadata
    backend: str | None = None
    attempt: int = 1

    # Step context
    step: str | None = None

    # Data context (normalized field names)
    week_ending: str | None = None
    tier: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return non-None fields as dict (excludes attempt=1 default)."""
        result = {}
        for k, v in asdict(self).items():
            if v is None:
                continue
            if k == "attempt" and v == 1:
                continue  # Don't include default attempt=1
            result[k] = v
        return result

    def merge(self, **kwargs) -> "LogContext":
        """Create new context with merged values."""
        current = asdict(self)
        current.update({k: v for k, v in kwargs.items() if v is not None})
        return LogContext(**current)


# Context variable for the current execution context
_log_context: ContextVar[LogContext] = ContextVar("log_context")  # noqa: B039


def get_context() -> LogContext:
    """Get the current log context."""
    return _log_context.get(LogContext())


def set_context(
    execution_id: str | None = None,
    workflow: str | None = None,
    capture_id: str | None = None,
    batch_id: str | None = None,
    backend: str | None = None,
    step: str | None = None,
    domain: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    attempt: int = 1,
    week_ending: str | None = None,
    tier: str | None = None,
    **kwargs,  # Allow additional fields for flexibility
) -> LogContext:
    """
    Set the current log context.

    This replaces the current context. Use bind_context() to add to existing.

    Returns:
        The new context
    """
    ctx = LogContext(
        execution_id=execution_id,
        workflow=workflow,
        capture_id=capture_id,
        batch_id=batch_id,
        backend=backend,
        step=step,
        domain=domain,
        span_id=span_id,
        parent_span_id=parent_span_id,
        attempt=attempt,
        week_ending=week_ending,
        tier=tier,
    )
    _log_context.set(ctx)
    return ctx


def bind_context(**kwargs) -> LogContext:
    """
    Bind additional values to current context.

    This merges with the existing context rather than replacing it.

    Returns:
        The updated context
    """
    current = get_context()
    updated = current.merge(**kwargs)
    _log_context.set(updated)
    return updated


def clear_context() -> None:
    """Clear the current context (reset to empty)."""
    _log_context.set(LogContext())


class _ContextToken:
    """Token for restoring context after a scoped operation."""

    def __init__(self, token):
        self._token = token

    def restore(self):
        """Restore the previous context."""
        _log_context.reset(self._token)


def push_context(**kwargs) -> _ContextToken:
    """
    Push new context values, returning a token to restore later.

    Usage:
        token = push_context(step="normalize")
        try:
            do_work()
        finally:
            token.restore()
    """
    current = get_context()
    updated = current.merge(**kwargs)
    token = _log_context.set(updated)
    return _ContextToken(token)


def add_context_processor(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """
    Structlog processor that adds execution context to every log entry.

    This is registered in configure_logging() and runs for every log call.
    """
    ctx = get_context()
    ctx_dict = ctx.to_dict()

    # Add context fields (don't override existing keys)
    for key, value in ctx_dict.items():
        if key not in event_dict:
            event_dict[key] = value

    return event_dict


def get_logger(name: str | None = None) -> Any:
    """
    Get a structured logger.

    The logger automatically includes execution context in all log entries.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger if available, else stdlib Logger
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    import logging
    return logging.getLogger(name)
