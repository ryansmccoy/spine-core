#!/usr/bin/env python3
"""RollingWindow — Time-Series Aggregations Over Sliding Periods.

================================================================================
WHY ROLLING WINDOWS?
================================================================================

Financial analytics rely heavily on rolling (sliding) window computations:

    - **Moving averages** — 4-week avg volume smooths out single-week spikes
    - **Trend detection** — Is volume increasing or decreasing over time?
    - **Volatility** — Standard deviation over trailing 12 weeks
    - **Completeness checks** — Do we have data for all 6 weeks in the window?

The challenge is handling **missing data** correctly::

    Week    Volume
    W1      1000
    W2      (missing — holiday week)
    W3      800
    W4      1500

    Naive average: (1000 + 800 + 1500) / 4 = 825    ← WRONG (divided by 4)
    Naive average: (1000 + 0 + 800 + 1500) / 4 = 825 ← WRONG (zero ≠ missing)
    Correct:       (1000 + 800 + 1500) / 3 = 1100   ← Only count present data

RollingWindow tracks ``periods_present`` vs ``periods_total`` so you can
distinguish between "data was zero" and "data was absent".


================================================================================
ARCHITECTURE
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  RollingWindow(size=6, step_back=lambda w: w.previous())               │
    │                                                                         │
    │  .compute(as_of, fetch_fn, aggregate_fn)                                │
    │       │                                                                 │
    │       ├─ Step 1: Generate 6 period keys from as_of                      │
    │       │          [W6, W5, W4, W3, W2, W1]                               │
    │       │                                                                 │
    │       ├─ Step 2: Call fetch_fn(period) for each                         │
    │       │          [1300, 1100, 1500, 800, None, 1000]                    │
    │       │                                                                 │
    │       ├─ Step 3: Filter to present data (skip None)                     │
    │       │          [(W6,1300), (W5,1100), (W4,1500), (W3,800), (W1,1000)]│
    │       │                                                                 │
    │       ├─ Step 4: Call aggregate_fn(present_data)                        │
    │       │          → {avg: 1140, min: 800, max: 1500, sum: 5700}         │
    │       │                                                                 │
    │       └─ Step 5: Return RollingResult                                  │
    │                  periods_present=5, periods_total=6, is_complete=False  │
    └─────────────────────────────────────────────────────────────────────────┘


================================================================================
KEY DESIGN CHOICES
================================================================================

**Generic period type** — Works with WeekEnding, date, month, or any type::

    # Weekly rolling window (financial data)
    RollingWindow(size=6, step_back=lambda w: w.previous())

    # Daily rolling window
    RollingWindow(size=30, step_back=lambda d: d - timedelta(days=1))

**Custom aggregation** — You define what "aggregate" means::

    # Simple average
    def avg(data): return sum(v for _, v in data) / len(data)

    # Weighted by recency
    def weighted(data):
        weights = range(1, len(data) + 1)
        return sum(w * v for w, (_, v) in zip(weights, sorted(data)))

**Completeness tracking** — Never silently compute over gaps::

    result = window.compute(...)
    if not result.is_complete:
        logger.warning(f"Only {result.periods_present}/{result.periods_total}")


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/07_rolling_windows.py

See Also:
    - :mod:`spine.core` — RollingWindow, RollingResult
    - :mod:`spine.core.temporal` — WeekEnding (the natural period type)
    - ``examples/01_core/05_temporal_weekending.py`` — WeekEnding basics
"""

from datetime import date

from spine.core import WeekEnding, RollingWindow, RollingResult


def main():
    """Demonstrate RollingWindow for time-series calculations."""
    print("=" * 60)
    print("RollingWindow - Time-Series Aggregations")
    print("=" * 60)
    
    # Sample volume data by week
    volume_data = {
        WeekEnding.from_any_date(date(2025, 11, 21)): 1000,
        WeekEnding.from_any_date(date(2025, 11, 28)): 1200,
        WeekEnding.from_any_date(date(2025, 12, 5)): 800,
        WeekEnding.from_any_date(date(2025, 12, 12)): 1500,
        WeekEnding.from_any_date(date(2025, 12, 19)): 1100,
        WeekEnding.from_any_date(date(2025, 12, 26)): 1300,
    }
    
    print("\n1. Sample volume data:")
    for week, volume in sorted(volume_data.items(), key=lambda x: x[0].value):
        print(f"   {week}: {volume:,} shares")
    
    # Create a 6-week rolling window
    print("\n2. Creating 6-week rolling window...")
    
    window = RollingWindow(
        size=6,
        step_back=lambda w: w.previous(),
    )
    
    # Fetch function retrieves data for a period
    def fetch_volume(week: WeekEnding) -> int | None:
        return volume_data.get(week)
    
    # Aggregate function computes statistics
    def compute_stats(data: list[tuple[WeekEnding, int]]) -> dict:
        values = [v for _, v in data]
        return {
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "sum": sum(values),
        }
    
    # Compute rolling window as of 2025-12-26
    as_of = WeekEnding.from_any_date(date(2025, 12, 26))
    result = window.compute(
        as_of=as_of,
        fetch_fn=fetch_volume,
        aggregate_fn=compute_stats,
    )
    
    print(f"\n3. Rolling window result (as of {as_of}):")
    print(f"   Periods present: {result.periods_present}/{result.periods_total}")
    print(f"   Is complete: {result.is_complete}")
    print(f"   Aggregates:")
    print(f"     Average: {result.aggregates['avg']:,.0f}")
    print(f"     Min: {result.aggregates['min']:,}")
    print(f"     Max: {result.aggregates['max']:,}")
    print(f"     Sum: {result.aggregates['sum']:,}")
    
    # Demonstrate incomplete window
    print("\n4. Incomplete window example...")
    
    # Only have data for 3 weeks
    sparse_data = {
        WeekEnding.from_any_date(date(2025, 12, 12)): 1500,
        WeekEnding.from_any_date(date(2025, 12, 19)): 1100,
        WeekEnding.from_any_date(date(2025, 12, 26)): 1300,
    }
    
    sparse_result = window.compute(
        as_of=as_of,
        fetch_fn=lambda w: sparse_data.get(w),
        aggregate_fn=compute_stats,
    )
    
    print(f"   Periods present: {sparse_result.periods_present}/{sparse_result.periods_total}")
    print(f"   Is complete: {sparse_result.is_complete}")
    print(f"   Average (incomplete): {sparse_result.aggregates['avg']:,.0f}")
    
    # Trend detection
    print("\n5. Trend detection...")
    
    def compute_with_trend(data: list[tuple[WeekEnding, int]]) -> dict:
        values = [v for _, v in sorted(data, key=lambda x: x[0].value)]
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]
        
        first_avg = sum(first_half) / len(first_half) if first_half else 0
        second_avg = sum(second_half) / len(second_half) if second_half else 0
        
        if second_avg > first_avg * 1.05:
            trend = "UP"
        elif second_avg < first_avg * 0.95:
            trend = "DOWN"
        else:
            trend = "FLAT"
        
        return {
            "trend": trend,
            "first_half_avg": first_avg,
            "second_half_avg": second_avg,
        }
    
    trend_result = window.compute(
        as_of=as_of,
        fetch_fn=fetch_volume,
        aggregate_fn=compute_with_trend,
    )
    
    print(f"   Trend: {trend_result.aggregates['trend']}")
    print(f"   First half avg: {trend_result.aggregates['first_half_avg']:,.0f}")
    print(f"   Second half avg: {trend_result.aggregates['second_half_avg']:,.0f}")
    
    print("\n" + "=" * 60)
    print("RollingWindow demo complete!")


if __name__ == "__main__":
    main()
