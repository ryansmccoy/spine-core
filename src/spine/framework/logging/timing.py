"""
Timing utilities for performance logging.

Provides reusable helpers for logging step durations:
- Context manager: with log_step("step_name"):
- Decorator: @log_timing("step_name")
- Manual: with timed_block() as timer; timer.duration_ms

Design:
- Logs start at DEBUG, end at INFO (with duration)
- Includes execution context automatically
- Supports row counts and custom metrics
- Lightweight tracing with span_id/parent_span_id
- Minimal overhead when not in DEBUG mode

Performance safety:
- Timer overhead is ~1μs (time.perf_counter)
- No logging inside loops
- DEBUG-level start logs are skipped if DEBUG disabled
"""

import functools
import time
import traceback
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

from spine.framework.logging.context import get_context, get_logger, push_context

# Type variable for decorated functions
F = TypeVar("F", bound=Callable[..., Any])


def _generate_span_id() -> str:
    """Generate a short span ID (8 hex chars)."""
    return uuid.uuid4().hex[:8]


@dataclass
class TimingResult:
    """Result of a timed operation with tracing support."""

    step: str
    span_id: str = field(default_factory=_generate_span_id)
    parent_span_id: str | None = None
    started_at: float = field(default_factory=time.perf_counter)
    ended_at: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"  # ok, error
    error_info: dict[str, Any] | None = None

    def stop(self) -> "TimingResult":
        """Record end time."""
        self.ended_at = time.perf_counter()
        return self

    @property
    def duration_seconds(self) -> float:
        """Duration in seconds."""
        if self.ended_at is None:
            return time.perf_counter() - self.started_at
        return self.ended_at - self.started_at

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        return self.duration_seconds * 1000

    def add_metric(self, key: str, value: Any) -> "TimingResult":
        """Add a metric to include in the log output."""
        self.metrics[key] = value
        return self

    def set_error(self, e: Exception) -> "TimingResult":
        """Record error information."""
        self.status = "error"
        self.error_info = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "error_stack": traceback.format_exc(),
        }
        return self

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to dict for logging."""
        result = {
            "duration_ms": round(self.duration_ms, 2),
            "span_id": self.span_id,
        }
        if self.parent_span_id:
            result["parent_span_id"] = self.parent_span_id
        result.update(self.metrics)
        return result

    def to_error_dict(self) -> dict[str, Any]:
        """Convert to dict for error logging."""
        result = self.to_log_dict()
        result["status"] = "error"
        if self.error_info:
            result.update(self.error_info)
        return result


@contextmanager
def timed_block(step: str = "unnamed") -> Iterator[TimingResult]:
    """
    Low-level timing context manager.

    Returns a TimingResult that can be used to add metrics.
    Does not log automatically - use log_step for that.

    Usage:
        with timed_block("process_data") as timer:
            result = process()
            timer.add_metric("rows", len(result))
        print(f"Took {timer.duration_ms}ms")
    """
    # Get parent span from context
    ctx = get_context()
    parent_span = ctx.span_id

    timer = TimingResult(step=step, parent_span_id=parent_span)
    try:
        yield timer
    finally:
        timer.stop()


@contextmanager
def log_step(event: str, log_start: bool = True, level: str = "info", **extra_metrics) -> Iterator[TimingResult]:
    """
    Context manager that logs step start/end with timing and tracing.

    Logs:
    - Start: DEBUG level (event.start) with span_id
    - End: INFO level (event.end) with duration_ms, span_id

    The span_id is propagated to nested steps as parent_span_id.

    Usage:
        with log_step("normalize.validate", rows_in=50000) as timer:
            result = validate(records)
            timer.add_metric("rows_out", len(result.accepted))

        # Logs:
        # DEBUG normalize.validate.start span_id=a1b2c3d4 rows_in=50000
        # INFO  normalize.validate.end   span_id=a1b2c3d4 duration_ms=423.5 rows_out=49500

    Args:
        event: Event name (e.g., "normalize.validate")
        log_start: Whether to log at start (DEBUG)
        level: Log level for end message ("info" or "debug")
        **extra_metrics: Additional metrics to include in logs
    """
    log = get_logger("timing")

    # Get parent span from current context
    ctx = get_context()
    parent_span = ctx.span_id

    # Create timer with new span
    timer = TimingResult(step=event, parent_span_id=parent_span, metrics=dict(extra_metrics))

    # Push span_id to context so nested logs include it
    context_token = push_context(span_id=timer.span_id, parent_span_id=parent_span, step=event)

    try:
        # Log start (DEBUG only)
        if log_start:
            start_fields = {"span_id": timer.span_id}
            if parent_span:
                start_fields["parent_span_id"] = parent_span
            start_fields.update(extra_metrics)
            log.debug(f"{event}.start", **start_fields)

        yield timer

    except Exception as e:
        # Log error with timing and full error details
        timer.stop()
        timer.set_error(e)
        log.error(f"{event}.error", **timer.to_error_dict())
        raise

    finally:
        timer.stop()
        context_token.restore()

    # Log completion
    log_method = getattr(log, level)
    log_method(f"{event}.end", **timer.to_log_dict())


def log_timing(
    step: str | None = None,
    log_start: bool = True,
    level: str = "info",
) -> Callable[[F], F]:
    """
    Decorator that logs function execution time.

    Usage:
        @log_timing("compute_summaries")
        def compute_summaries(records):
            return aggregate(records)

        # Or use function name as step
        @log_timing()
        def compute_summaries(records):
            return aggregate(records)

    Args:
        step: Step name (defaults to function name)
        log_start: Whether to log at start
        level: Log level for completion message
    """

    def decorator(func: F) -> F:
        step_name = step or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with log_step(step_name, log_start=log_start, level=level):
                return func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


# =============================================================================
# Specialized timing utilities for common patterns
# =============================================================================


@contextmanager
def log_db_operation(operation: str, table: str, **extra) -> Iterator[TimingResult]:
    """
    Log a database operation with table context.

    Logs at DEBUG level to avoid noise.

    Usage:
        with log_db_operation("insert", "otc_raw", rows=50000):
            conn.executemany(sql, data)
    """
    step = f"db.{operation}.{table}"
    with log_step(step, level="debug", **extra) as timer:
        yield timer


@contextmanager
def log_workflow_stage(stage: str, **extra) -> Iterator[TimingResult]:
    """
    Log a major workflow stage.

    Logs at INFO level - use for major stages like:
    - ingest
    - normalize
    - aggregate
    - compute

    Usage:
        with log_workflow_stage("normalize", week="2025-12-20"):
            result = normalize_week(data)
            # Returns timer for adding metrics
    """
    with log_step(f"stage.{stage}", level="info", **extra) as timer:
        yield timer


def log_row_counts(
    log,
    step: str,
    *,
    rows_in: int | None = None,
    rows_out: int | None = None,
    rows_rejected: int | None = None,
    **extra,
) -> None:
    """
    Log row count transformation for a processing step.

    Usage:
        log_row_counts(log, "normalize",
                      rows_in=50000, rows_out=49500, rows_rejected=500)
    """
    metrics = {
        k: v
        for k, v in [
            ("rows_in", rows_in),
            ("rows_out", rows_out),
            ("rows_rejected", rows_rejected),
        ]
        if v is not None
    }
    metrics.update(extra)

    log.info(f"{step}.rows", **metrics)
