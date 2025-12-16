"""
Temporal primitives for weekly/monthly workflows.

WeekEnding is the core abstraction for weekly data processing.
It validates that dates are Fridays and provides range/iteration utilities.

Manifesto:
    Financial data pipelines operate on institutional time cycles. FINRA publishes
    OTC transparency data every Friday. Market calendars follow weekly patterns.
    Using arbitrary dates leads to bugs: "Did we process 2025-12-25 (Thursday)?"

    WeekEnding solves this by making week boundaries explicit and validated:
    - Construction from non-Friday dates FAILS (explicit is better than implicit)
    - Use from_any_date() when you have an arbitrary date
    - All week comparisons, ranges, and iterations work correctly

Architecture:
    ::

        ┌───────────────────────────────────────────────────────────┐
        │                    WeekEnding Value Object                 │
        └───────────────────────────────────────────────────────────┘

        Input Validation:
        ┌────────────────────────────────────────────────────────────┐
        │ WeekEnding("2025-12-26")  → ✅ OK (Friday)                │
        │ WeekEnding("2025-12-25")  → ❌ ValueError (Thursday)      │
        │ WeekEnding.from_any_date(date(2025, 12, 23)) → ✅ 12-26   │
        └────────────────────────────────────────────────────────────┘

        6-Week Backfill Pattern:
        ┌────────────────────────────────────────────────────────────┐
        │ week = WeekEnding("2025-12-26")                           │
        │ window = week.window(6)  # Last 6 weeks                   │
        │                                                            │
        │ for w in window:                                           │
        │     process_week(w)  # Each is validated Friday           │
        └────────────────────────────────────────────────────────────┘

        Timeline:
        ──┬──────┬──────┬──────┬──────┬──────┬──────┬──
          │ 11/21│ 11/28│ 12/05│ 12/12│ 12/19│ 12/26│
          │  Fri │  Fri │  Fri │  Fri │  Fri │  Fri │
          └──────┴──────┴──────┴──────┴──────┴──────┘
                      week.window(6) returns all 6

Tags:
    temporal, weekly-workflow, value-object, finra-otc, validation,
    date-handling, spine-core

Doc-Types:
    - API Reference
    - Temporal Patterns Guide
    - FINRA OTC Pipeline Documentation
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Union


def _nearest_friday(d: date) -> date:
    """Find the Friday of the week containing date d."""
    days_ahead = 4 - d.weekday()  # Friday = 4
    if days_ahead < 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


@dataclass(frozen=True, slots=True)
class WeekEnding:
    """
    Validated Friday date value object for weekly financial workflows.

    WeekEnding ensures all temporal boundaries in weekly workflows are valid
    Fridays. It's the canonical type for week_ending columns, partition keys,
    and backfill ranges. Invalid dates fail at construction time, not runtime.

    Manifesto:
        FINRA publishes OTC transparency data every Friday. Market data pipelines
        process weekly windows. Using arbitrary dates leads to subtle bugs:
        - "2025-12-25" (Christmas, Thursday) - Wrong week boundary
        - Off-by-one errors in date arithmetic
        - Inconsistent week_ending formats across tables

        WeekEnding solves this by making Fridays a type, not a convention:
        - **Validation at construction:** Non-Fridays raise ValueError immediately
        - **Explicit conversion:** from_any_date() for arbitrary dates
        - **Range operations:** window(), range(), last_n() are always correct
        - **Comparison:** WeekEnding objects compare correctly

    Architecture:
        ```
        ┌───────────────────────────────────────────────────────────┐
        │                    WeekEnding Operations                   │
        └───────────────────────────────────────────────────────────┘

        Construction:
        ┌─────────────────────────────────────────────────────────┐
        │ WeekEnding("2025-12-26")          → OK (Friday)        │
        │ WeekEnding(date(2025, 12, 26))    → OK (Friday)        │
        │ WeekEnding("2025-12-25")          → ValueError!        │
        │ WeekEnding.from_any_date(12-23)   → 2025-12-26 (Fri)   │
        │ WeekEnding.today()                → Current week's Fri │
        └─────────────────────────────────────────────────────────┘

        Navigation:
        ┌─────────────────────────────────────────────────────────┐
        │ week.previous(1)   → Previous Friday                   │
        │ week.next(1)       → Next Friday                       │
        │ week.window(6)     → Last 6 Fridays (oldest first)     │
        │ WeekEnding.last_n(6)  → Last 6 weeks from today        │
        └─────────────────────────────────────────────────────────┘

        Iteration:
        ┌─────────────────────────────────────────────────────────┐
        │ WeekEnding.range(start, end)                           │
        │   → Generator of all Fridays from start to end         │
        └─────────────────────────────────────────────────────────┘
        ```

    Features:
        - **Validation:** Non-Fridays raise ValueError with helpful message
        - **Multiple inputs:** Accepts str, date, or WeekEnding (idempotent)
        - **Factory methods:** from_any_date(), today(), last_n()
        - **Navigation:** previous(), next(), window()
        - **Iteration:** range() generates all Fridays between two dates
        - **Comparison:** Full ordering support (<, <=, >, >=)
        - **Immutable:** Frozen dataclass with slots

    Examples:
        Basic construction:

        >>> WeekEnding("2025-12-26")  # OK - Friday
        WeekEnding('2025-12-26')

        >>> WeekEnding("2025-12-25")  # Raises ValueError - Thursday
        Traceback (most recent call last):
            ...
        ValueError: week_ending must be Friday, got 2025-12-25 (Thursday). Nearest Friday: 2025-12-26

        From arbitrary date (finds containing Friday):

        >>> WeekEnding.from_any_date(date(2025, 12, 23))  # Tuesday
        WeekEnding('2025-12-26')

        6-week backfill window:

        >>> week = WeekEnding("2025-12-26")
        >>> window = week.window(6)
        >>> [str(w) for w in window]
        ['2025-11-21', '2025-11-28', '2025-12-05', '2025-12-12', '2025-12-19', '2025-12-26']

        Last N weeks from today:

        >>> weeks = WeekEnding.last_n(3, as_of=date(2025, 12, 26))
        >>> [str(w) for w in weeks]
        ['2025-12-12', '2025-12-19', '2025-12-26']

        Range iteration:

        >>> start = WeekEnding("2025-12-12")
        >>> end = WeekEnding("2025-12-26")
        >>> [str(w) for w in WeekEnding.range(start, end)]
        ['2025-12-12', '2025-12-19', '2025-12-26']

    Performance:
        - **Construction:** O(1), ~100ns (date parsing + weekday check)
        - **Navigation:** O(1), ~50ns (timedelta arithmetic)
        - **window(n):** O(n), creates n WeekEnding objects
        - **range():** O(1) per yield (generator)

    Guardrails:
        ❌ DON'T: Pass arbitrary dates without validation
        ✅ DO: Use from_any_date() for arbitrary dates

        ❌ DON'T: Store week_ending as plain strings
        ✅ DO: Use WeekEnding type for validation guarantees

        ❌ DON'T: Manually compute previous/next week
        ✅ DO: Use previous()/next() methods

    Context:
        Problem: Weekly financial pipelines use arbitrary dates, causing
                 off-by-one errors, wrong week boundaries, and inconsistent data.
        Solution: Value object that validates Fridays at construction time,
                  with navigation and range utilities built-in.
        Alternatives: Plain date with manual validation (error-prone),
                     enum of valid dates (inflexible).

    Tags:
        temporal, value-object, validation, weekly-workflow, finra-otc,
        spine-core, immutable

    Doc-Types:
        - API Reference
        - Temporal Patterns Guide
        - FINRA OTC Pipeline Documentation

    Attributes:
        value: The validated Friday date
    """

    value: date

    def __init__(self, value: Union[str, date, "WeekEnding"]):
        if isinstance(value, WeekEnding):
            object.__setattr__(self, "value", value.value)
            return

        if isinstance(value, str):
            parsed = date.fromisoformat(value)
        elif isinstance(value, date):
            parsed = value
        else:
            raise TypeError(f"Expected str, date, or WeekEnding, got {type(value).__name__}")

        if parsed.weekday() != 4:  # Friday = 4
            day_name = parsed.strftime("%A")
            nearest = _nearest_friday(parsed)
            raise ValueError(f"week_ending must be Friday, got {parsed} ({day_name}). Nearest Friday: {nearest}")

        object.__setattr__(self, "value", parsed)

    @classmethod
    def from_any_date(cls, d: date) -> "WeekEnding":
        """Create WeekEnding from any date, finding containing week's Friday."""
        return cls(_nearest_friday(d))

    @classmethod
    def today(cls) -> "WeekEnding":
        """Get WeekEnding for current week."""
        return cls.from_any_date(date.today())

    @classmethod
    def last_n(cls, n: int, as_of: date = None) -> list["WeekEnding"]:
        """
        Get last N week endings, oldest first.

        Args:
            n: Number of weeks (1 = just the as_of week)
            as_of: Reference date (default: today)

        Returns:
            List of WeekEnding, oldest first
        """
        ref = as_of or date.today()
        latest = cls.from_any_date(ref)
        weeks = [cls(latest.value - timedelta(weeks=i)) for i in range(n)]
        return list(reversed(weeks))

    @classmethod
    def range(cls, start: "WeekEnding", end: "WeekEnding") -> Iterator["WeekEnding"]:
        """Generate all Fridays from start to end (inclusive)."""
        current = start.value
        while current <= end.value:
            yield cls(current)
            current += timedelta(weeks=1)

    def previous(self, n: int = 1) -> "WeekEnding":
        """Get N weeks before this one."""
        return WeekEnding(self.value - timedelta(weeks=n))

    def next(self, n: int = 1) -> "WeekEnding":
        """Get N weeks after this one."""
        return WeekEnding(self.value + timedelta(weeks=n))

    def window(self, size: int) -> list["WeekEnding"]:
        """Get a window of N weeks ending with this one, oldest first."""
        return [self.previous(i) for i in range(size - 1, -1, -1)]

    def __str__(self) -> str:
        return self.value.isoformat()

    def __repr__(self) -> str:
        return f"WeekEnding({self.value.isoformat()!r})"

    def __lt__(self, other: "WeekEnding") -> bool:
        if isinstance(other, WeekEnding):
            return self.value < other.value
        return NotImplemented

    def __le__(self, other: "WeekEnding") -> bool:
        if isinstance(other, WeekEnding):
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other: "WeekEnding") -> bool:
        if isinstance(other, WeekEnding):
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other: "WeekEnding") -> bool:
        if isinstance(other, WeekEnding):
            return self.value >= other.value
        return NotImplemented
