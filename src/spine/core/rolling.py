"""
Rolling window utilities for time-series calculations.

Provides a generic pattern for computing aggregates over sliding windows of
time buckets. RollingWindow works with any temporal type (WeekEnding, date, etc.)
and any value type, making it suitable for financial time-series analysis.

Rolling windows are fundamental to financial analytics: 6-week volume averages,
52-week highs, moving averages, trend detection. This module provides a
type-safe, composable abstraction that works with spine-core's WeekEnding
and other temporal types.

Manifesto:
    Financial analysis requires window functions: "What's the average volume
    over the last 6 weeks?" "Is the trend up or down?" "Did we have data for
    all periods?"
    
    RollingWindow encapsulates this pattern:
    - **Generic over time:** Works with WeekEnding, date, month, etc.
    - **Completeness tracking:** Know if window has gaps
    - **Separation of concerns:** Fetch data, aggregate separately
    - **Trend detection:** Built-in UP/DOWN/FLAT classification

Architecture:
    ::
    
        ┌────────────────────────────────────────────────────────────┐
        │                    RollingWindow Pattern                    │
        └────────────────────────────────────────────────────────────┘
        
        Input: as_of=WeekEnding("2025-12-26"), size=6
        
        ┌─────┬─────┬─────┬─────┬─────┬─────┐
        │11/21│11/28│12/05│12/12│12/19│12/26│  ← window periods
        └─────┴─────┴─────┴─────┴─────┴─────┘
              │     │     │     │     │
              ▼     ▼     ▼     ▼     ▼
            fetch_fn(period) → value or None
              │     │     │     │     │
              └──────────┬──────────────┘
                         │
                    aggregate_fn([(period, value), ...])
                         │
                         ▼
                   RollingResult
                    • aggregates: {avg: 1000, max: 1500}
                    • periods_present: 5
                    • periods_total: 6
                    • is_complete: False

Features:
    - **RollingWindow:** Generic rolling window computation
    - **RollingResult:** Structured result with completeness tracking
    - **compute_trend():** Trend direction from first/last N values
    - **Works with any temporal type:** WeekEnding, date, etc.

Examples:
    6-week volume average:
    
    >>> from spine.core.temporal import WeekEnding
    >>> window = RollingWindow(size=6, step_back=lambda w: w.previous())
    >>> result = window.compute(
    ...     as_of=WeekEnding("2025-12-26"),
    ...     fetch_fn=lambda w: get_volume(w),
    ...     aggregate_fn=lambda data: {"avg": sum(v for _, v in data) / len(data)}
    ... )
    >>> result.is_complete
    True

Tags:
    rolling-window, time-series, aggregation, financial-analytics,
    trend-detection, spine-core

Doc-Types:
    - API Reference
    - Financial Analytics Guide
    - Time-Series Patterns
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")  # Time bucket type (WeekEnding, date, etc.)
V = TypeVar("V")  # Value type


@dataclass
class RollingResult:
    """
    Result of a rolling window computation with completeness tracking.
    
    RollingResult captures both the computed aggregates and metadata about
    how complete the window was. This is critical for financial analytics
    where missing data affects interpretation.
    
    Manifesto:
        A 6-week average with only 3 weeks of data is unreliable. RollingResult
        makes this explicit:
        - **periods_present:** How many periods actually had data
        - **periods_total:** Window size (how many should have data)
        - **is_complete:** Quick check if window is full
        
        This enables data quality checks in downstream analysis:
        "Only report averages where is_complete=True"
    
    Architecture:
        ```
        ┌──────────────────────────────────────────────────────────┐
        │                    RollingResult                          │
        ├──────────────────────────────────────────────────────────┤
        │  aggregates: dict[str, Any]                              │
        │      └─ Domain-specific computed values                  │
        │         {"avg_volume": 1234, "max_volume": 5678}         │
        │                                                          │
        │  periods_present: int                                    │
        │      └─ How many periods had data (e.g., 5)             │
        │                                                          │
        │  periods_total: int                                      │
        │      └─ Window size (e.g., 6)                           │
        │                                                          │
        │  is_complete: bool                                       │
        │      └─ True if periods_present == periods_total         │
        └──────────────────────────────────────────────────────────┘
        ```
    
    Examples:
        Complete window (all 6 weeks have data):
        
        >>> result = RollingResult(
        ...     aggregates={"avg": 1000.0, "max": 1500},
        ...     periods_present=6,
        ...     periods_total=6,
        ...     is_complete=True
        ... )
        >>> result.is_complete
        True
        
        Incomplete window (only 4 of 6 weeks):
        
        >>> result = RollingResult(
        ...     aggregates={"avg": 800.0},
        ...     periods_present=4,
        ...     periods_total=6,
        ...     is_complete=False
        ... )
        >>> result.is_complete
        False
        >>> result.periods_present / result.periods_total
        0.666...
    
    Guardrails:
        ❌ DON'T: Ignore is_complete for financial reporting
        ✅ DO: Check is_complete or periods_present before using aggregates
        
        ❌ DON'T: Assume aggregates exist if periods_present=0
        ✅ DO: Check if aggregates is non-empty before accessing
    
    Tags:
        rolling-result, completeness, data-quality, time-series, spine-core
    
    Doc-Types:
        - API Reference
    
    Attributes:
        aggregates: Domain-specific computed values (e.g., avg, sum, max)
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
    Generic rolling window over time buckets for time-series calculations.
    
    RollingWindow computes aggregates over a sliding window of time periods.
    It's generic over the time bucket type (WeekEnding, date, month) and
    separates data fetching from aggregation for maximum flexibility.
    
    Manifesto:
        Financial time-series analysis needs rolling calculations:
        - "6-week rolling average volume"
        - "52-week high/low"
        - "30-day moving average"
        
        RollingWindow provides a composable pattern:
        1. **Define window:** size and how to step back
        2. **Fetch data:** per-period retrieval (may return None for gaps)
        3. **Aggregate:** combine available data into result
        4. **Check completeness:** is_complete tells you if all periods had data
        
        This separation of concerns enables:
        - Different fetch strategies (DB, cache, API)
        - Custom aggregations (avg, sum, percentiles, trend)
        - Reusable window definitions
    
    Architecture:
        ```
        ┌──────────────────────────────────────────────────────────┐
        │                   RollingWindow[T]                        │
        └──────────────────────────────────────────────────────────┘
        
        Construction:
        ┌────────────────────────────────────────────────────────┐
        │ window = RollingWindow(                                │
        │     size=6,                                            │
        │     step_back=lambda w: w.previous()  # WeekEnding     │
        │ )                                                      │
        └────────────────────────────────────────────────────────┘
        
        Computation Flow:
        ┌────────────────────────────────────────────────────────┐
        │ as_of = WeekEnding("2025-12-26")                       │
        │                                                        │
        │ 1. get_window(as_of)                                   │
        │    → [11/21, 11/28, 12/05, 12/12, 12/19, 12/26]       │
        │                                                        │
        │ 2. fetch_fn(period) for each                          │
        │    → [(11/21, 100), (11/28, None), ...]               │
        │                                                        │
        │ 3. Filter to present values                            │
        │    → [(11/21, 100), (12/05, 150), ...]               │
        │                                                        │
        │ 4. aggregate_fn(present)                               │
        │    → {"avg": 125.0, "count": 5}                       │
        │                                                        │
        │ 5. Return RollingResult                                │
        │    → aggregates, periods_present=5, is_complete=False │
        └────────────────────────────────────────────────────────┘
        ```
    
    Features:
        - **Generic over time type:** Works with WeekEnding, date, etc.
        - **Custom step_back:** Define how to move to previous period
        - **Completeness tracking:** Know how many periods had data
        - **Separation of concerns:** Fetch and aggregate are separate
        - **Composable:** Reuse window definition with different aggregations
    
    Examples:
        6-week rolling volume average:
        
        >>> from spine.core.temporal import WeekEnding
        >>> window = RollingWindow(size=6, step_back=lambda w: w.previous())
        >>> result = window.compute(
        ...     as_of=WeekEnding("2025-12-26"),
        ...     fetch_fn=lambda w: get_volume(w, "AAPL"),
        ...     aggregate_fn=lambda data: {
        ...         "avg_volume": sum(v for _, v in data) / len(data),
        ...         "max_volume": max(v for _, v in data),
        ...     }
        ... )
        >>> result.is_complete
        True
        >>> result.aggregates["avg_volume"]
        1234567.0
        
        Get just the window periods:
        
        >>> window = RollingWindow(size=4, step_back=lambda w: w.previous())
        >>> week = WeekEnding("2025-12-26")
        >>> periods = window.get_window(week)
        >>> [str(p) for p in periods]
        ['2025-12-05', '2025-12-12', '2025-12-19', '2025-12-26']
        
        Monthly window with date:
        
        >>> from datetime import date
        >>> from dateutil.relativedelta import relativedelta
        >>> window = RollingWindow(
        ...     size=3,
        ...     step_back=lambda d: d - relativedelta(months=1)
        ... )
    
    Performance:
        - **get_window():** O(size), builds list of periods
        - **compute():** O(size) fetches + O(present) aggregation
        - **Memory:** O(size) for period list
    
    Guardrails:
        ❌ DON'T: Do heavy computation in step_back
        ✅ DO: Keep step_back simple (e.g., week.previous())
        
        ❌ DON'T: Throw exceptions in fetch_fn for missing data
        ✅ DO: Return None for missing periods
        
        ❌ DON'T: Assume aggregates exist if window is empty
        ✅ DO: Check periods_present > 0 before accessing aggregates
    
    Context:
        Problem: Need to compute rolling aggregates over time-series
                 with potential data gaps.
        Solution: Generic window with separation of fetch and aggregate,
                  plus completeness tracking.
        Alternatives: pandas rolling functions (heavier dependency),
                     manual loops (error-prone).
    
    Tags:
        rolling-window, time-series, generic, aggregation, financial-analytics,
        spine-core
    
    Doc-Types:
        - API Reference
        - Financial Analytics Guide
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
    
    Compares the average of values at the start of a window to the average
    at the end, returning a trend direction (UP, DOWN, FLAT) and percentage.
    
    Manifesto:
        "Is volume trending up or down?" requires comparing window segments.
        Simply comparing first vs last value is noisy. Averaging segments
        provides stability:
        - First 2 weeks avg: 1000
        - Last 2 weeks avg: 1200
        - Trend: UP (+20%)
        
        The threshold parameter controls sensitivity: 5% default means
        small changes are classified as FLAT.
    
    Architecture:
        ```
        ┌─────────────────────────────────────────────────────────┐
        │                   Trend Computation                      │
        └─────────────────────────────────────────────────────────┘
        
        Window: [w1, w2, w3, w4, w5, w6]
                 ├─────┤     ├─────┤
                 first_values last_values
        
        1. first_avg = mean(first_values)
        2. last_avg = mean(last_values)
        3. pct = (last_avg - first_avg) / first_avg * 100
        
        4. Classification:
           pct > +5%  → "UP"
           pct < -5%  → "DOWN"
           else       → "FLAT"
        ```
    
    Examples:
        Upward trend:
        
        >>> compute_trend([100, 110], [150, 160])
        ('UP', 40.48)
        
        Downward trend:
        
        >>> compute_trend([200, 190], [100, 95])
        ('DOWN', -50.0)
        
        Flat (within threshold):
        
        >>> compute_trend([100, 102], [103, 101])
        ('FLAT', 1.0)
        
        Custom threshold:
        
        >>> compute_trend([100], [108], threshold_pct=10.0)
        ('FLAT', 8.0)
        >>> compute_trend([100], [108], threshold_pct=5.0)
        ('UP', 8.0)
        
        Empty values:
        
        >>> compute_trend([], [100])
        ('FLAT', 0.0)
    
    Performance:
        - **O(n + m)** where n = len(first_values), m = len(last_values)
    
    Guardrails:
        ❌ DON'T: Pass single value lists (noisy)
        ✅ DO: Pass 2-3 values for stable comparison
        
        ❌ DON'T: Use with highly volatile data without smoothing
        ✅ DO: Pre-smooth data or use larger segments
    
    Args:
        first_values: Values from start of window
        last_values: Values from end of window
        threshold_pct: Percentage threshold for UP/DOWN (default 5%)

    Returns:
        Tuple of (direction, percentage) where direction is "UP", "DOWN", or "FLAT"
    
    Tags:
        trend-detection, time-series, analytics, spine-core
    
    Doc-Types:
        - API Reference
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
