"""
Pure calculation functions for Exchange Calendar domain.

These functions compute trading day information from holiday data.
All functions are pure — no database dependencies.

Calculation Contracts:
- is_trading_day: Check if a date is a trading day
- trading_days_between: Count trading days in a range
- next_trading_day: Find next trading day after a date
- previous_trading_day: Find previous trading day before a date

FIELD CLASSIFICATION (for determinism tests):
- Deterministic: All outputs (is_trading_day, count, next_date, prev_date)
- Audit-only: calculated_at (varies by wall-clock)
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence


# =============================================================================
# DETERMINISM HELPERS
# =============================================================================

AUDIT_FIELDS = frozenset({
    "calculated_at",
    "computed_at",
    "id",
})


def strip_audit_fields(row: dict) -> dict:
    """Strip audit fields for deterministic comparison."""
    return {k: v for k, v in row.items() if k not in AUDIT_FIELDS}


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class Holiday:
    """A single holiday record."""
    
    date: date
    name: str
    exchange_code: str
    year: int
    
    @classmethod
    def from_dict(cls, d: dict, exchange_code: str, year: int) -> "Holiday":
        """Create Holiday from JSON dict."""
        holiday_date = date.fromisoformat(d["date"]) if isinstance(d["date"], str) else d["date"]
        return cls(
            date=holiday_date,
            name=d["name"],
            exchange_code=exchange_code,
            year=year,
        )


@dataclass
class TradingDayResult:
    """Result of a trading day calculation."""
    
    exchange_code: str
    start_date: date
    end_date: date
    trading_days: int
    calendar_days: int
    holidays_in_range: int
    weekends_in_range: int
    
    # Calc metadata
    calc_name: str = "trading_days_between"
    calc_version: str = "1.0.0"


# =============================================================================
# CORE CALCULATIONS
# =============================================================================


def is_weekend(d: date) -> bool:
    """Check if date is Saturday or Sunday."""
    return d.weekday() >= 5  # 5=Saturday, 6=Sunday


def is_trading_day(
    check_date: date,
    holidays: set[date],
) -> bool:
    """
    Check if a date is a trading day.
    
    A trading day is:
    - Not a weekend (Saturday/Sunday)
    - Not a holiday
    
    Args:
        check_date: Date to check
        holidays: Set of holiday dates for the exchange
        
    Returns:
        True if trading day, False otherwise
    """
    if is_weekend(check_date):
        return False
    if check_date in holidays:
        return False
    return True


def trading_days_between(
    start_date: date,
    end_date: date,
    holidays: set[date],
    exchange_code: str = "XNYS",
) -> TradingDayResult:
    """
    Count trading days between two dates (inclusive).
    
    Args:
        start_date: Start date (inclusive)
        end_date: End date (inclusive)
        holidays: Set of holiday dates
        exchange_code: Exchange identifier for result
        
    Returns:
        TradingDayResult with counts
    """
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    
    trading_count = 0
    weekend_count = 0
    holiday_count = 0
    
    current = start_date
    while current <= end_date:
        if is_weekend(current):
            weekend_count += 1
        elif current in holidays:
            holiday_count += 1
        else:
            trading_count += 1
        current += timedelta(days=1)
    
    calendar_days = (end_date - start_date).days + 1
    
    return TradingDayResult(
        exchange_code=exchange_code,
        start_date=start_date,
        end_date=end_date,
        trading_days=trading_count,
        calendar_days=calendar_days,
        holidays_in_range=holiday_count,
        weekends_in_range=weekend_count,
    )


def next_trading_day(
    from_date: date,
    holidays: set[date],
    include_from: bool = False,
) -> date:
    """
    Find the next trading day on or after from_date.
    
    Args:
        from_date: Starting date
        holidays: Set of holiday dates
        include_from: If True, from_date can be returned if it's a trading day
        
    Returns:
        Next trading day
    """
    current = from_date if include_from else from_date + timedelta(days=1)
    
    # Safety limit to prevent infinite loops
    for _ in range(365):
        if is_trading_day(current, holidays):
            return current
        current += timedelta(days=1)
    
    raise ValueError(f"No trading day found within 365 days of {from_date}")


def previous_trading_day(
    from_date: date,
    holidays: set[date],
    include_from: bool = False,
) -> date:
    """
    Find the previous trading day on or before from_date.
    
    Args:
        from_date: Starting date
        holidays: Set of holiday dates
        include_from: If True, from_date can be returned if it's a trading day
        
    Returns:
        Previous trading day
    """
    current = from_date if include_from else from_date - timedelta(days=1)
    
    # Safety limit to prevent infinite loops
    for _ in range(365):
        if is_trading_day(current, holidays):
            return current
        current -= timedelta(days=1)
    
    raise ValueError(f"No trading day found within 365 days before {from_date}")


# =============================================================================
# HOLIDAY PARSING
# =============================================================================


def parse_holidays(content: dict) -> list[Holiday]:
    """
    Parse holidays from JSON content.
    
    Expected format:
    {
        "year": 2025,
        "exchange_code": "XNYS",
        "holidays": [
            {"date": "2025-01-01", "name": "New Year's Day"},
            {"date": "2025-01-20", "name": "Martin Luther King Jr. Day"},
            ...
        ]
    }
    """
    year = content.get("year")
    exchange_code = content.get("exchange_code")
    
    if not year or not exchange_code:
        raise ValueError("JSON must contain 'year' and 'exchange_code' fields")
    
    holidays = []
    for h in content.get("holidays", []):
        holidays.append(Holiday.from_dict(h, exchange_code, year))
    
    return holidays


def holidays_to_set(holidays: Sequence[Holiday]) -> set[date]:
    """Convert list of Holiday objects to set of dates for fast lookup."""
    return {h.date for h in holidays}


# =============================================================================
# AGGREGATE CALCULATIONS (for pipeline use)
# =============================================================================


@dataclass
class MonthlyTradingDays:
    """Trading day counts by month for a year."""
    
    year: int
    exchange_code: str
    month: int
    trading_days: int
    calendar_days: int
    holidays: int
    
    calc_name: str = "monthly_trading_days"
    calc_version: str = "1.0.0"


def compute_monthly_trading_days(
    year: int,
    exchange_code: str,
    holidays: set[date],
) -> list[MonthlyTradingDays]:
    """
    Compute trading days for each month in a year.
    
    Args:
        year: Calendar year
        exchange_code: Exchange identifier
        holidays: Set of holiday dates
        
    Returns:
        List of 12 MonthlyTradingDays records
    """
    import calendar
    
    results = []
    
    for month in range(1, 13):
        # Get first and last day of month
        _, last_day = calendar.monthrange(year, month)
        start = date(year, month, 1)
        end = date(year, month, last_day)
        
        # Count trading days
        result = trading_days_between(start, end, holidays, exchange_code)
        
        results.append(MonthlyTradingDays(
            year=year,
            exchange_code=exchange_code,
            month=month,
            trading_days=result.trading_days,
            calendar_days=result.calendar_days,
            holidays=result.holidays_in_range,
        ))
    
    return results
