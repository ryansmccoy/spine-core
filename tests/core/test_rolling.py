"""
Tests for spine.core.rolling module.

Tests cover:
- RollingWindow creation
- Window period generation
- Rolling computation with fetch/aggregate
- RollingResult dataclass
- Trend computation
"""

import pytest
from datetime import date

from spine.core.rolling import (
    RollingWindow,
    RollingResult,
    compute_trend,
)
from spine.core.temporal import WeekEnding


class TestRollingResult:
    """Tests for RollingResult dataclass."""

    def test_result_creation(self):
        """Test creating a RollingResult."""
        result = RollingResult(
            aggregates={"avg": 100, "sum": 500},
            periods_present=5,
            periods_total=6,
            is_complete=False,
        )

        assert result.aggregates["avg"] == 100
        assert result.aggregates["sum"] == 500
        assert result.periods_present == 5
        assert result.periods_total == 6
        assert result.is_complete is False

    def test_complete_result(self):
        """Test a complete RollingResult."""
        result = RollingResult(
            aggregates={"value": 42},
            periods_present=6,
            periods_total=6,
            is_complete=True,
        )

        assert result.is_complete is True

    def test_empty_result(self):
        """Test a result with no data."""
        result = RollingResult(
            aggregates={},
            periods_present=0,
            periods_total=6,
            is_complete=False,
        )

        assert result.aggregates == {}
        assert result.periods_present == 0


class TestRollingWindow:
    """Tests for RollingWindow class."""

    @pytest.fixture
    def week_window(self):
        """6-week rolling window for WeekEnding."""
        return RollingWindow(
            size=6,
            step_back=lambda w: w.previous()
        )

    def test_window_creation(self, week_window):
        """Test creating a RollingWindow."""
        assert week_window.size == 6

    def test_get_window_returns_correct_size(self, week_window):
        """Test get_window returns correct number of periods."""
        as_of = WeekEnding("2026-01-09")
        periods = week_window.get_window(as_of)

        assert len(periods) == 6

    def test_get_window_oldest_first(self, week_window):
        """Test get_window returns periods oldest first."""
        as_of = WeekEnding("2026-01-09")
        periods = week_window.get_window(as_of)

        # First should be oldest
        assert periods[0].value < periods[-1].value

        # Last should be the as_of week
        assert periods[-1].value == as_of.value

    def test_get_window_correct_dates(self, week_window):
        """Test get_window returns correct dates."""
        as_of = WeekEnding("2026-01-09")
        periods = week_window.get_window(as_of)

        # Recalculate: 2026-01-09 is the 6th (newest)
        # -1 week: 2026-01-02
        # -2 weeks: 2025-12-26
        # -3 weeks: 2025-12-19
        # -4 weeks: 2025-12-12
        # -5 weeks: 2025-12-05
        expected_dates = [
            date(2025, 12, 5),
            date(2025, 12, 12),
            date(2025, 12, 19),
            date(2025, 12, 26),
            date(2026, 1, 2),
            date(2026, 1, 9),
        ]

        actual_dates = [p.value for p in periods]
        assert actual_dates == expected_dates


class TestRollingCompute:
    """Tests for RollingWindow.compute method."""

    @pytest.fixture
    def week_window(self):
        """4-week rolling window for simpler testing."""
        return RollingWindow(
            size=4,
            step_back=lambda w: w.previous()
        )

    def test_compute_all_data_present(self, week_window):
        """Test compute when all periods have data."""
        as_of = WeekEnding("2026-01-09")

        # Mock data: every week has 100 volume
        data = {
            date(2025, 12, 19): 100,
            date(2025, 12, 26): 150,
            date(2026, 1, 2): 200,
            date(2026, 1, 9): 250,
        }

        result = week_window.compute(
            as_of=as_of,
            fetch_fn=lambda w: data.get(w.value),
            aggregate_fn=lambda pairs: {
                "sum": sum(v for _, v in pairs),
                "avg": sum(v for _, v in pairs) / len(pairs),
            }
        )

        assert result.is_complete is True
        assert result.periods_present == 4
        assert result.periods_total == 4
        assert result.aggregates["sum"] == 700
        assert result.aggregates["avg"] == 175.0

    def test_compute_partial_data(self, week_window):
        """Test compute when some periods have no data."""
        as_of = WeekEnding("2026-01-09")

        # Only 2 weeks have data
        data = {
            date(2025, 12, 26): 150,
            date(2026, 1, 9): 250,
        }

        result = week_window.compute(
            as_of=as_of,
            fetch_fn=lambda w: data.get(w.value),
            aggregate_fn=lambda pairs: {
                "sum": sum(v for _, v in pairs),
                "count": len(pairs),
            }
        )

        assert result.is_complete is False
        assert result.periods_present == 2
        assert result.periods_total == 4
        assert result.aggregates["sum"] == 400
        assert result.aggregates["count"] == 2

    def test_compute_no_data(self, week_window):
        """Test compute when no periods have data."""
        as_of = WeekEnding("2026-01-09")

        result = week_window.compute(
            as_of=as_of,
            fetch_fn=lambda w: None,  # No data
            aggregate_fn=lambda pairs: {"sum": sum(v for _, v in pairs)}
        )

        assert result.is_complete is False
        assert result.periods_present == 0
        assert result.aggregates == {}


class TestComputeTrend:
    """Tests for compute_trend function."""

    def test_trend_up(self):
        """Test upward trend detection."""
        first_values = [100, 100, 100]
        last_values = [120, 120, 120]

        direction, pct = compute_trend(first_values, last_values, threshold_pct=5.0)

        assert direction == "UP"
        assert pct == 20.0

    def test_trend_down(self):
        """Test downward trend detection."""
        first_values = [100, 100, 100]
        last_values = [80, 80, 80]

        direction, pct = compute_trend(first_values, last_values, threshold_pct=5.0)

        assert direction == "DOWN"
        assert pct == -20.0

    def test_trend_flat_within_threshold(self):
        """Test flat trend when change is within threshold."""
        first_values = [100, 100, 100]
        last_values = [102, 102, 102]  # 2% change, below 5% threshold

        direction, pct = compute_trend(first_values, last_values, threshold_pct=5.0)

        assert direction == "FLAT"
        assert pct == 2.0

    def test_trend_custom_threshold(self):
        """Test trend with custom threshold."""
        first_values = [100]
        last_values = [108]  # 8% increase

        # With 10% threshold, this should be FLAT
        direction, pct = compute_trend(first_values, last_values, threshold_pct=10.0)
        assert direction == "FLAT"

        # With 5% threshold, this should be UP
        direction, pct = compute_trend(first_values, last_values, threshold_pct=5.0)
        assert direction == "UP"

    def test_trend_empty_first_values(self):
        """Test trend with empty first values."""
        direction, pct = compute_trend([], [100, 200])

        assert direction == "FLAT"
        assert pct == 0.0

    def test_trend_empty_last_values(self):
        """Test trend with empty last values."""
        direction, pct = compute_trend([100, 200], [])

        assert direction == "FLAT"
        assert pct == 0.0

    def test_trend_zero_first_average(self):
        """Test trend when first average is zero (avoid division by zero)."""
        direction, pct = compute_trend([0, 0], [100, 200])

        assert direction == "FLAT"
        assert pct == 0.0

    def test_trend_rounds_percentage(self):
        """Test that percentage is rounded to 2 decimal places."""
        first_values = [100]
        last_values = [133]  # 33% increase

        direction, pct = compute_trend(first_values, last_values)

        assert pct == 33.0  # Rounded
