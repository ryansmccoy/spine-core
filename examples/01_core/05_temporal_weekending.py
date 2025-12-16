#!/usr/bin/env python3
"""WeekEnding — Friday-Anchored Temporal Primitive for Financial Data.

================================================================================
WHY WEEKENDING?
================================================================================

Financial data is often reported on a weekly basis, but "week" is ambiguous:

    - What day does the week start? Sunday? Monday?
    - What day defines the week? The start? The end?
    - What timezone? Market hours?

**WeekEnding** eliminates this ambiguity by defining every week by its
**Friday**. This choice is deliberate:

    1. **Friday** is the last trading day of the week for US markets
    2. **Weekly options** expire on Fridays
    3. **OTC Markets** reports weekly volume data "week-ending Friday"
    4. **SEC filings** often reference "week ended Friday"

Without WeekEnding::

    # Ambiguous - is this Monday's week or Friday's week?
    week = "2024-01-17"  # Wednesday
    
    # Different interpretations:
    analyst_a.report(week)  # Thinks this means Jan 15-21 (Mon-Sun)
    analyst_b.report(week)  # Thinks this means Jan 14-20 (Sun-Sat)
    
    # Data mismatch! Reports don't align.

With WeekEnding::

    # Unambiguous - the week ending Friday Jan 19
    week = WeekEnding.from_any_date(date(2024, 1, 17))  # → 2024-01-19
    
    # Everyone agrees: this represents Jan 13-19 (Sat-Fri)
    analyst_a.report(week)  # Same week
    analyst_b.report(week)  # Same week


================================================================================
TEMPORAL SNAPPING RULES
================================================================================

Any date "snaps" to its week-ending Friday::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Input Date           │  WeekEnding        │  Rule                      │
    ├───────────────────────┼────────────────────┼────────────────────────────┤
    │  2024-01-15 (Mon)     │  2024-01-19 (Fri)  │  Forward to Friday         │
    │  2024-01-16 (Tue)     │  2024-01-19 (Fri)  │  Forward to Friday         │
    │  2024-01-17 (Wed)     │  2024-01-19 (Fri)  │  Forward to Friday         │
    │  2024-01-18 (Thu)     │  2024-01-19 (Fri)  │  Forward to Friday         │
    │  2024-01-19 (Fri)     │  2024-01-19 (Fri)  │  Already Friday            │
    │  2024-01-20 (Sat)     │  2024-01-26 (Fri)  │  Forward to NEXT Friday    │
    │  2024-01-21 (Sun)     │  2024-01-26 (Fri)  │  Forward to NEXT Friday    │
    └───────────────────────┴────────────────────┴────────────────────────────┘

    Saturday and Sunday belong to the FOLLOWING week, not the preceding one.
    This matches how financial weekends are treated (post-close Friday until
    pre-open Monday belongs to the new week).


================================================================================
DATABASE SCHEMA: WEEK-PARTITIONED DATA
================================================================================

WeekEnding enables efficient week-based partitioning::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: otc_weekly_volume                                               │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  week_ending     DATE          NOT NULL  -- Always a Friday            │
    │  tier           VARCHAR(20)    NOT NULL  -- NMS_TIER_1, OTCQB, etc.    │
    │  symbol         VARCHAR(10)    NOT NULL                                 │
    │  mpid           VARCHAR(10)    NOT NULL  -- Market participant ID      │
    │  total_shares   BIGINT         NOT NULL                                 │
    │  total_trades   INTEGER        NOT NULL                                 │
    │                                                                         │
    │  PRIMARY KEY (week_ending, tier, symbol, mpid)                          │
    └─────────────────────────────────────────────────────────────────────────┘

    Index: idx_volume_week ON otc_weekly_volume(week_ending)
    
    Constraints:
    - CHECK (EXTRACT(DOW FROM week_ending) = 5)  -- Must be Friday (PostgreSQL)
    - or CHECK (strftime('%w', week_ending) = '5')  -- SQLite


================================================================================
COMMON OPERATIONS
================================================================================

Creation::

    we = WeekEnding.from_any_date(date(2024, 1, 17))  # → 2024-01-19
    we = WeekEnding.current()                         # This week's Friday
    we = WeekEnding.parse("2024-01-19")               # From string

Arithmetic::

    we.previous()       # Last week: 2024-01-12
    we.next()           # Next week: 2024-01-26
    we.previous(4)      # 4 weeks ago
    we.window(4)        # [4 weeks ago, 3 weeks ago, 2 weeks ago, last week]

Ranges::

    # Generate all weeks in Q1 2024
    weeks = WeekEnding.range(
        start=WeekEnding.parse("2024-01-05"),
        end=WeekEnding.parse("2024-03-29")
    )

    # Last 4 weeks from today
    recent = WeekEnding.last_n(4)


================================================================================
USE CASES
================================================================================

1. **Data Partitioning**: Partition tables by week_ending for efficient queries
2. **Backfill Logic**: "Backfill weeks 2024-01-05 through 2024-02-02"
3. **Rolling Windows**: "4-week moving average ending this Friday"
4. **Temporal Joins**: Join data from different sources using common week key
5. **Scheduling**: "Run aggregation every Friday at 6pm ET"


================================================================================
BEST PRACTICES
================================================================================

1. **Always store week_ending as DATE, not string**::

       # BAD
       row["week"] = "2024-01-19"  # String comparison issues
       
       # GOOD
       row["week_ending"] = we.value  # date object

2. **Use WeekEnding for all week references in code**::

       # BAD - manual date arithmetic
       friday = today + timedelta(days=(4 - today.weekday()) % 7)
       
       # GOOD - semantic and tested
       friday = WeekEnding.from_any_date(today)

3. **Name columns `week_ending`, not `week`**::

       # Ambiguous
       SELECT * FROM data WHERE week = '2024-01-19'
       
       # Clear
       SELECT * FROM data WHERE week_ending = '2024-01-19'

4. **Validate on load**::

       def load_weekly_data(week_ending: date, data: list):
           we = WeekEnding.from_any_date(week_ending)
           if we.value != week_ending:
               raise ValidationError(
                   f"{week_ending} is not a Friday, did you mean {we.value}?"
               )


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/05_temporal_weekending.py

See Also:
    - :mod:`spine.core.temporal` — WeekEnding, TemporalEnvelope
    - :mod:`spine.core.backfill` — Backfill utilities using WeekEnding
    - :mod:`spine.core.watermarks` — High-water mark tracking
"""
from datetime import date, timedelta
from spine.core import WeekEnding


def main():
    print("=" * 60)
    print("Temporal WeekEnding Examples")
    print("=" * 60)
    
    # === 1. Create WeekEnding from date ===
    print("\n[1] Create WeekEnding from Date")
    
    # Any date snaps to its week-ending Friday
    monday = date(2024, 1, 15)  # Monday
    we = WeekEnding.from_any_date(monday)
    print(f"  Input: {monday} (Monday)")
    print(f"  WeekEnding: {we}")
    print(f"  As date: {we.value}")
    
    # Friday stays on Friday
    friday = date(2024, 1, 19)
    we_friday = WeekEnding.from_any_date(friday)
    print(f"\n  Input: {friday} (Friday)")
    print(f"  WeekEnding: {we_friday}")
    
    # === 2. WeekEnding arithmetic ===
    print("\n[2] WeekEnding Arithmetic")
    
    we = WeekEnding.from_any_date(date(2024, 1, 19))
    print(f"  Current: {we}")
    print(f"  Previous week: {we.previous()}")
    print(f"  Next week: {we.next()}")
    print(f"  4 weeks ago: {we.previous(4)}")
    print(f"  4 weeks ahead: {we.next(4)}")
    
    # === 3. Week window ===
    print("\n[3] Week Window")
    
    we = WeekEnding.from_any_date(date(2024, 1, 19))
    window = we.window(4)  # 4-week window ending with this week
    print(f"  WeekEnding: {we}")
    print(f"  4-week window:")
    for w in window:
        print(f"    {w}")
    
    # === 4. Range generation ===
    print("\n[4] Generate Range of Weeks")
    
    start = WeekEnding.from_any_date(date(2024, 1, 5))
    end = WeekEnding.from_any_date(date(2024, 2, 2))
    
    weeks = list(WeekEnding.range(start, end))
    print(f"  From {start} to {end}:")
    for we in weeks:
        print(f"    {we}")
    
    # === 5. Last N weeks ===
    print("\n[5] Last N Weeks")
    
    # Get last 4 weeks from a reference date
    ref_date = date(2024, 1, 19)
    last_4 = WeekEnding.last_n(4, as_of=ref_date)
    print(f"  Last 4 weeks as of {ref_date}:")
    for we in last_4:
        print(f"    {we}")
    
    # === 6. Comparison and sorting ===
    print("\n[6] Comparison and Sorting")
    
    weeks = [
        WeekEnding.from_any_date(date(2024, 3, 15)),
        WeekEnding.from_any_date(date(2024, 1, 5)),
        WeekEnding.from_any_date(date(2024, 2, 23)),
    ]
    
    print("  Unsorted:")
    for we in weeks:
        print(f"    {we}")
    
    print("  Sorted:")
    for we in sorted(weeks):
        print(f"    {we}")
    
    # === 7. Real-world: Data partitioning ===
    print("\n[7] Real-world: Data Partitioning")
    
    # Simulate records with various dates
    records = [
        {"symbol": "AAPL", "trade_date": date(2024, 1, 15)},
        {"symbol": "MSFT", "trade_date": date(2024, 1, 16)},
        {"symbol": "GOOGL", "trade_date": date(2024, 1, 22)},
        {"symbol": "AMZN", "trade_date": date(2024, 1, 23)},
    ]
    
    # Partition by week ending
    from collections import defaultdict
    partitions = defaultdict(list)
    
    for record in records:
        we = WeekEnding.from_any_date(record["trade_date"])
        partitions[we].append(record)
    
    print("  Records partitioned by week:")
    for we, recs in sorted(partitions.items()):
        symbols = [r["symbol"] for r in recs]
        print(f"    {we}: {symbols}")
    
    # === 8. Current week ===
    print("\n[8] Current Week")
    
    today = date.today()
    current_we = WeekEnding.today()
    print(f"  Today: {today}")
    print(f"  Current week ending: {current_we}")
    
    print("\n" + "=" * 60)
    print("[OK] Temporal WeekEnding Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
