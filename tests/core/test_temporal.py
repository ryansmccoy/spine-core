"""
Tests for spine.core.temporal module.

Tests cover:
- WeekEnding creation and validation
- Friday validation logic
- Date range iteration
- Window calculations
- Comparison operators
"""

import pytest
from datetime import date

from spine.core.temporal import WeekEnding, _nearest_friday


class TestNearestFriday:
    """Tests for _nearest_friday helper function."""

    def test_friday_returns_same(self):
        """Test that Friday returns itself."""
        friday = date(2026, 1, 9)  # Friday
        assert _nearest_friday(friday) == friday

    def test_saturday_returns_next_friday(self):
        """Test that Saturday returns the next Friday (Friday of that week)."""
        saturday = date(2026, 1, 10)  # Saturday
        expected = date(2026, 1, 16)  # Friday of that week
        assert _nearest_friday(saturday) == expected

    def test_monday_returns_next_friday(self):
        """Test that Monday returns the next Friday."""
        monday = date(2026, 1, 5)  # Monday
        expected = date(2026, 1, 9)  # Friday
        assert _nearest_friday(monday) == expected

    def test_wednesday_returns_friday(self):
        """Test that Wednesday returns the Friday of that week."""
        wednesday = date(2026, 1, 7)  # Wednesday
        expected = date(2026, 1, 9)  # Friday
        assert _nearest_friday(wednesday) == expected


class TestWeekEndingCreation:
    """Tests for WeekEnding creation."""

    def test_create_from_string(self):
        """Test creating WeekEnding from ISO string."""
        we = WeekEnding("2026-01-09")  # Friday
        assert we.value == date(2026, 1, 9)

    def test_create_from_date(self):
        """Test creating WeekEnding from date object."""
        friday = date(2026, 1, 9)
        we = WeekEnding(friday)
        assert we.value == friday

    def test_create_from_weekending(self):
        """Test creating WeekEnding from another WeekEnding."""
        original = WeekEnding("2026-01-09")
        copy = WeekEnding(original)
        assert copy.value == original.value

    def test_invalid_type_raises_error(self):
        """Test that invalid type raises TypeError."""
        with pytest.raises(TypeError, match="Expected str, date, or WeekEnding"):
            WeekEnding(12345)

    def test_non_friday_raises_error(self):
        """Test that non-Friday date raises ValueError."""
        with pytest.raises(ValueError, match="must be Friday"):
            WeekEnding("2026-01-08")  # Thursday

    def test_error_message_includes_day_name(self):
        """Test that error message includes the actual day name."""
        with pytest.raises(ValueError, match="Thursday"):
            WeekEnding("2026-01-08")

    def test_error_message_suggests_nearest_friday(self):
        """Test that error message suggests nearest Friday."""
        with pytest.raises(ValueError, match="Nearest Friday"):
            WeekEnding("2026-01-07")  # Wednesday


class TestWeekEndingClassMethods:
    """Tests for WeekEnding class methods."""

    def test_from_any_date_monday(self):
        """Test from_any_date with Monday."""
        we = WeekEnding.from_any_date(date(2026, 1, 5))  # Monday
        assert we.value == date(2026, 1, 9)  # Friday of that week

    def test_from_any_date_sunday(self):
        """Test from_any_date with Sunday."""
        we = WeekEnding.from_any_date(date(2026, 1, 11))  # Sunday
        assert we.value == date(2026, 1, 16)  # Following Friday

    def test_last_n_returns_correct_count(self):
        """Test last_n returns correct number of weeks."""
        weeks = WeekEnding.last_n(3, as_of=date(2026, 1, 9))
        assert len(weeks) == 3

    def test_last_n_oldest_first(self):
        """Test last_n returns oldest first."""
        weeks = WeekEnding.last_n(3, as_of=date(2026, 1, 9))
        assert weeks[0].value < weeks[1].value < weeks[2].value

    def test_last_n_includes_reference_week(self):
        """Test last_n includes the reference week."""
        weeks = WeekEnding.last_n(3, as_of=date(2026, 1, 9))
        assert weeks[-1].value == date(2026, 1, 9)

    def test_last_n_correct_dates(self):
        """Test last_n returns correct dates."""
        weeks = WeekEnding.last_n(4, as_of=date(2026, 1, 9))
        expected = [
            date(2025, 12, 19),
            date(2025, 12, 26),
            date(2026, 1, 2),
            date(2026, 1, 9),
        ]
        assert [w.value for w in weeks] == expected

    def test_range_inclusive(self):
        """Test that range is inclusive of both ends."""
        start = WeekEnding("2026-01-02")
        end = WeekEnding("2026-01-16")
        weeks = list(WeekEnding.range(start, end))

        assert weeks[0].value == date(2026, 1, 2)
        assert weeks[-1].value == date(2026, 1, 16)

    def test_range_generates_weekly(self):
        """Test that range generates weekly intervals."""
        start = WeekEnding("2026-01-02")
        end = WeekEnding("2026-01-23")
        weeks = list(WeekEnding.range(start, end))

        assert len(weeks) == 4
        for i in range(1, len(weeks)):
            assert (weeks[i].value - weeks[i-1].value).days == 7


class TestWeekEndingInstanceMethods:
    """Tests for WeekEnding instance methods."""

    def test_previous_one_week(self):
        """Test previous() returns one week earlier."""
        we = WeekEnding("2026-01-09")
        prev = we.previous()
        assert prev.value == date(2026, 1, 2)

    def test_previous_multiple_weeks(self):
        """Test previous(n) returns n weeks earlier."""
        we = WeekEnding("2026-01-09")
        prev = we.previous(3)
        assert prev.value == date(2025, 12, 19)

    def test_next_one_week(self):
        """Test next() returns one week later."""
        we = WeekEnding("2026-01-09")
        nxt = we.next()
        assert nxt.value == date(2026, 1, 16)

    def test_next_multiple_weeks(self):
        """Test next(n) returns n weeks later."""
        we = WeekEnding("2026-01-09")
        nxt = we.next(2)
        assert nxt.value == date(2026, 1, 23)

    def test_window_returns_correct_size(self):
        """Test window returns correct number of weeks."""
        we = WeekEnding("2026-01-09")
        window = we.window(4)
        assert len(window) == 4

    def test_window_ends_with_current(self):
        """Test window ends with the current week."""
        we = WeekEnding("2026-01-09")
        window = we.window(4)
        assert window[-1].value == we.value

    def test_window_oldest_first(self):
        """Test window is ordered oldest first."""
        we = WeekEnding("2026-01-09")
        window = we.window(4)
        for i in range(1, len(window)):
            assert window[i-1].value < window[i].value


class TestWeekEndingStringRepresentation:
    """Tests for WeekEnding string representations."""

    def test_str_returns_iso_format(self):
        """Test __str__ returns ISO format."""
        we = WeekEnding("2026-01-09")
        assert str(we) == "2026-01-09"

    def test_repr_format(self):
        """Test __repr__ format."""
        we = WeekEnding("2026-01-09")
        assert repr(we) == "WeekEnding('2026-01-09')"


class TestWeekEndingComparison:
    """Tests for WeekEnding comparison operators."""

    def test_less_than(self):
        """Test < operator."""
        earlier = WeekEnding("2026-01-02")
        later = WeekEnding("2026-01-09")
        assert earlier < later
        assert not later < earlier

    def test_less_than_or_equal(self):
        """Test <= operator."""
        we1 = WeekEnding("2026-01-09")
        we2 = WeekEnding("2026-01-09")
        we3 = WeekEnding("2026-01-16")
        assert we1 <= we2
        assert we1 <= we3
        assert not we3 <= we1

    def test_greater_than(self):
        """Test > operator."""
        earlier = WeekEnding("2026-01-02")
        later = WeekEnding("2026-01-09")
        assert later > earlier
        assert not earlier > later

    def test_greater_than_or_equal(self):
        """Test >= operator."""
        we1 = WeekEnding("2026-01-09")
        we2 = WeekEnding("2026-01-09")
        we3 = WeekEnding("2026-01-02")
        assert we1 >= we2
        assert we1 >= we3
        assert not we3 >= we1

    def test_comparison_with_non_weekending_returns_not_implemented(self):
        """Test comparison with non-WeekEnding."""
        we = WeekEnding("2026-01-09")
        # These should return NotImplemented, which Python converts to TypeError
        with pytest.raises(TypeError):
            we < "2026-01-02"
        with pytest.raises(TypeError):
            we > date(2026, 1, 2)
