"""
Rolling window utilities for time-series calculations.

RollingWindow provides a generic pattern for computing
aggregates over a sliding window of time buckets.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")  # Time bucket type (WeekEnding, date, etc.)
V = TypeVar("V")  # Value type


@dataclass
class RollingResult:
    """
    Result of a rolling window computation.

    Attributes:
        aggregates: Domain-specific computed values
        periods_present: How many periods had data
        periods_total: Window size
        is_complete: True if all periods have data
    """

    aggregates: dict[str, Any]
    periods_present: int
    periods_total: int
    is_complete: bool


class RollingWindow(Generic[T]):
    """
    Generic rolling window over time buckets.

    Example:
        from spine.core.temporal import WeekEnding

        # 6-week rolling window
        window = RollingWindow(size=6, step_back=lambda w: w.previous())

        result = window.compute(
            as_of=WeekEnding("2025-12-26"),
            fetch_fn=lambda w: get_volume(w, symbol),
            aggregate_fn=lambda data: {
                "avg_volume": sum(v for _, v in data) / len(data),
                "max_volume": max(v for _, v in data),
            }
        )

        print(result.aggregates["avg_volume"])
        print(result.is_complete)  # True if all 6 weeks have data
    """

    def __init__(self, size: int, step_back: Callable[[T], T]):
        """
        Args:
            size: Number of periods in window
            step_back: Function to get previous period (e.g., week.previous())
        """
        self.size = size
        self.step_back = step_back

    def get_window(self, as_of: T) -> list[T]:
        """Get all periods in the window, oldest first."""
        periods = []
        current = as_of
        for _ in range(self.size):
            periods.append(current)
            current = self.step_back(current)
        return list(reversed(periods))

    def compute(
        self,
        as_of: T,
        fetch_fn: Callable[[T], V | None],
        aggregate_fn: Callable[[list[tuple[T, V]]], dict[str, Any]],
    ) -> RollingResult:
        """
        Compute rolling aggregate.

        Args:
            as_of: Current period (end of window)
            fetch_fn: Get value for period (returns None if no data)
            aggregate_fn: Combine (period, value) pairs into result dict

        Returns:
            RollingResult with aggregates and completeness info
        """
        periods = self.get_window(as_of)
        values = [(p, fetch_fn(p)) for p in periods]
        present = [(p, v) for p, v in values if v is not None]

        aggregates = aggregate_fn(present) if present else {}

        return RollingResult(
            aggregates=aggregates,
            periods_present=len(present),
            periods_total=self.size,
            is_complete=len(present) == self.size,
        )


def compute_trend(
    first_values: list, last_values: list, threshold_pct: float = 5.0
) -> tuple[str, float]:
    """
    Compute trend direction from first N and last N values.

    Args:
        first_values: Values from start of window
        last_values: Values from end of window
        threshold_pct: Percentage threshold for UP/DOWN (default 5%)

    Returns:
        Tuple of (direction, percentage)
        direction is "UP", "DOWN", or "FLAT"
    """
    if not first_values or not last_values:
        return "FLAT", 0.0

    first_avg = sum(first_values) / len(first_values)
    last_avg = sum(last_values) / len(last_values)

    if first_avg == 0:
        return "FLAT", 0.0

    pct = ((last_avg - first_avg) / first_avg) * 100

    if pct > threshold_pct:
        return "UP", round(pct, 2)
    elif pct < -threshold_pct:
        return "DOWN", round(pct, 2)
    return "FLAT", round(pct, 2)
