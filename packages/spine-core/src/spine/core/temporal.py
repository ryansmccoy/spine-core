"""
Temporal primitives for weekly/monthly workflows.

WeekEnding is the core abstraction for weekly data processing.
It validates that dates are Fridays and provides range/iteration utilities.
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
    Validated Friday date for weekly workflows.

    FINRA publishes OTC data every Friday. This value object ensures
    all week_ending values are valid Fridays.

    Examples:
        >>> WeekEnding("2025-12-26")  # OK - Friday
        WeekEnding('2025-12-26')

        >>> WeekEnding("2025-12-25")  # Raises ValueError - Thursday
        ValueError: week_ending must be Friday...

        >>> WeekEnding.from_any_date(date(2025, 12, 23))
        WeekEnding('2025-12-26')

        >>> list(WeekEnding.last_n(3, as_of=date(2025, 12, 26)))
        [WeekEnding('2025-12-12'), WeekEnding('2025-12-19'), WeekEnding('2025-12-26')]
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
            raise ValueError(
                f"week_ending must be Friday, got {parsed} ({day_name}). Nearest Friday: {nearest}"
            )

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
