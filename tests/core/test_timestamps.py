"""Tests for spine.core.timestamps — ULID generation + UTC helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from spine.core.timestamps import from_iso8601, generate_ulid, to_iso8601, utc_now


class TestUtcNow:
    """Tests for utc_now()."""

    def test_returns_datetime(self):
        result = utc_now()
        assert isinstance(result, datetime)

    def test_has_utc_timezone(self):
        result = utc_now()
        assert result.tzinfo is UTC

    def test_is_recent(self):
        before = datetime.now(UTC)
        result = utc_now()
        after = datetime.now(UTC)
        assert before <= result <= after


class TestGenerateUlid:
    """Tests for generate_ulid()."""

    def test_returns_string(self):
        result = generate_ulid()
        assert isinstance(result, str)

    def test_length_is_26(self):
        result = generate_ulid()
        assert len(result) == 26

    def test_uses_crockford_base32(self):
        valid_chars = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        result = generate_ulid()
        assert all(c in valid_chars for c in result), f"Invalid chars in {result}"

    def test_uniqueness(self):
        ids = {generate_ulid() for _ in range(100)}
        assert len(ids) == 100

    def test_time_sortable(self):
        """ULIDs generated later should sort after earlier ones."""
        import time

        first = generate_ulid()
        time.sleep(0.002)
        second = generate_ulid()
        # Time prefix (first 10 chars) should be monotonically non-decreasing
        assert first[:10] <= second[:10]


class TestToIso8601:
    """Tests for to_iso8601()."""

    def test_none_returns_none(self):
        assert to_iso8601(None) is None

    def test_datetime_returns_string(self):
        dt = datetime(2025, 12, 26, 10, 30, 0, tzinfo=UTC)
        result = to_iso8601(dt)
        assert isinstance(result, str)
        assert "2025-12-26" in result

    def test_roundtrip(self):
        dt = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)
        result = from_iso8601(to_iso8601(dt))
        assert result == dt


class TestFromIso8601:
    """Tests for from_iso8601()."""

    def test_none_returns_none(self):
        assert from_iso8601(None) is None

    def test_parses_iso_string(self):
        result = from_iso8601("2025-12-26T10:30:00+00:00")
        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 26

    def test_parses_naive_string(self):
        result = from_iso8601("2025-12-26T10:30:00")
        assert isinstance(result, datetime)
        assert result.hour == 10
        assert result.minute == 30
