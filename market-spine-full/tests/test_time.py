"""Tests for time utilities."""

import pytest
from datetime import datetime, timedelta, UTC

from market_spine.core.time import (
    utc_now,
    utc_now_naive,
    ago,
    from_now,
    parse_iso,
    format_iso,
)


class TestUtcNow:
    """Tests for utc_now functions."""

    def test_utc_now_is_timezone_aware(self):
        """Test that utc_now returns timezone-aware datetime."""
        now = utc_now()
        assert now.tzinfo is not None
        assert now.tzinfo == UTC

    def test_utc_now_naive_has_no_timezone(self):
        """Test that utc_now_naive returns naive datetime."""
        now = utc_now_naive()
        assert now.tzinfo is None

    def test_utc_now_naive_matches_utc_now(self):
        """Test that both functions return same time (within tolerance)."""
        aware = utc_now()
        naive = utc_now_naive()

        # Should be within 1 second of each other
        aware_naive = aware.replace(tzinfo=None)
        diff = abs((aware_naive - naive).total_seconds())
        assert diff < 1


class TestAgoAndFromNow:
    """Tests for relative time functions."""

    def test_ago_days(self):
        """Test ago with days parameter."""
        result = ago(days=7)
        expected = utc_now_naive() - timedelta(days=7)

        # Within 1 second
        diff = abs((result - expected).total_seconds())
        assert diff < 1

    def test_ago_hours(self):
        """Test ago with hours parameter."""
        result = ago(hours=24)
        expected = utc_now_naive() - timedelta(hours=24)

        diff = abs((result - expected).total_seconds())
        assert diff < 1

    def test_ago_combined(self):
        """Test ago with multiple parameters."""
        result = ago(days=1, hours=2, minutes=30)
        expected = utc_now_naive() - timedelta(days=1, hours=2, minutes=30)

        diff = abs((result - expected).total_seconds())
        assert diff < 1

    def test_from_now_days(self):
        """Test from_now with days parameter."""
        result = from_now(days=7)
        expected = utc_now_naive() + timedelta(days=7)

        diff = abs((result - expected).total_seconds())
        assert diff < 1

    def test_from_now_combined(self):
        """Test from_now with multiple parameters."""
        result = from_now(hours=1, minutes=30)
        expected = utc_now_naive() + timedelta(hours=1, minutes=30)

        diff = abs((result - expected).total_seconds())
        assert diff < 1


class TestIsoFormatting:
    """Tests for ISO date formatting."""

    def test_format_iso_with_timezone(self):
        """Test formatting timezone-aware datetime."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = format_iso(dt)

        assert "2024-01-15" in result
        assert "10:30:00" in result

    def test_format_iso_naive(self):
        """Test formatting naive datetime."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        result = format_iso(dt)

        assert result == "2024-01-15T10:30:00"

    def test_parse_iso_roundtrip(self):
        """Test parsing ISO string back to datetime."""
        original = "2024-01-15T10:30:00"
        parsed = parse_iso(original)

        assert parsed.year == 2024
        assert parsed.month == 1
        assert parsed.day == 15
        assert parsed.hour == 10
        assert parsed.minute == 30

    def test_parse_iso_with_timezone(self):
        """Test parsing ISO string with timezone."""
        original = "2024-01-15T10:30:00+00:00"
        parsed = parse_iso(original)

        assert parsed.tzinfo is not None
