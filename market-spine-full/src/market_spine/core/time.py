"""Time utilities with timezone-aware datetimes.

This module provides timezone-aware datetime utilities to replace
deprecated datetime.utcnow() calls throughout the codebase.
"""

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime.

    Returns:
        Timezone-aware datetime in UTC.
    """
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    """Get current UTC time as naive datetime (for DB compatibility).

    Some databases expect naive datetimes. This returns a naive datetime
    representing the current UTC time.

    Returns:
        Naive datetime representing current UTC time.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def parse_iso(value: str) -> datetime:
    """Parse ISO format datetime string.

    Args:
        value: ISO format datetime string.

    Returns:
        Parsed datetime (timezone-aware if input had timezone).
    """
    return datetime.fromisoformat(value)


def format_iso(dt: datetime) -> str:
    """Format datetime as ISO string.

    Args:
        dt: Datetime to format.

    Returns:
        ISO format string.
    """
    return dt.isoformat()


def ago(days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> datetime:
    """Get a datetime in the past relative to now.

    Args:
        days: Days ago.
        hours: Hours ago.
        minutes: Minutes ago.
        seconds: Seconds ago.

    Returns:
        Naive datetime representing the time in the past.
    """
    return utc_now_naive() - timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def from_now(days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> datetime:
    """Get a datetime in the future relative to now.

    Args:
        days: Days from now.
        hours: Hours from now.
        minutes: Minutes from now.
        seconds: Seconds from now.

    Returns:
        Naive datetime representing the time in the future.
    """
    return utc_now_naive() + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
