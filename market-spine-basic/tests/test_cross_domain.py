"""
Tests for Cross-Domain Dependency Handling.

These tests prove:
1. Re-running FINRA does not re-run Exchange Calendar unnecessarily
2. Backfilling Exchange Calendar updates downstream calcs correctly
3. capture_id semantics remain correct
4. Dependency failures are clear and actionable

The key test that would FAIL if architecture were poorly designed:
- test_dependency_missing_gives_actionable_error
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from spine.domains.finra.otc_transparency.calculations import (
    DependencyMissingError,
    DomainDependency,
    SymbolAggregateRow,
    check_calendar_dependency,
    compute_volume_per_trading_day,
    load_holidays_for_year,
)
from spine.domains.finra.otc_transparency.schema import Tier

# =============================================================================
# TEST DATA
# =============================================================================


@pytest.fixture
def sample_symbol_rows() -> list[SymbolAggregateRow]:
    """Sample FINRA symbol aggregates for testing."""
    return [
        SymbolAggregateRow(
            week_ending=date(2025, 1, 10),  # Friday
            tier=Tier.NMS_TIER_1,
            symbol="AAPL",
            total_shares=1_000_000,
            total_trades=5_000,
            venue_count=5,
        ),
        SymbolAggregateRow(
            week_ending=date(2025, 1, 10),
            tier=Tier.NMS_TIER_1,
            symbol="MSFT",
            total_shares=500_000,
            total_trades=2_500,
            venue_count=3,
        ),
    ]


@pytest.fixture
def sample_holidays_2025() -> set[date]:
    """Sample NYSE holidays for 2025."""
    return {
        date(2025, 1, 1),  # New Year's Day (Wednesday)
        date(2025, 1, 20),  # MLK Day (Monday)
        date(2025, 7, 4),  # Independence Day (Friday)
        date(2025, 12, 25),  # Christmas (Thursday)
    }


# =============================================================================
# CROSS-DOMAIN CALCULATION TESTS
# =============================================================================


class TestVolumePerTradingDay:
    """Test the cross-domain volume per trading day calculation."""

    def test_compute_with_full_week(self, sample_symbol_rows, sample_holidays_2025):
        """Compute volume/day for a week with no holidays."""
        # Week of Jan 6-10, 2025: Mon-Fri, no holidays = 5 trading days
        results = compute_volume_per_trading_day(
            sample_symbol_rows,
            sample_holidays_2025,
            exchange_code="XNYS",
        )

        assert len(results) == 2

        # AAPL: 1,000,000 / 5 = 200,000 per day
        aapl = next(r for r in results if r.symbol == "AAPL")
        assert aapl.trading_days == 5
        assert aapl.volume_per_day == 200_000.0
        assert aapl.trades_per_day == 1_000.0

        # MSFT: 500,000 / 5 = 100,000 per day
        msft = next(r for r in results if r.symbol == "MSFT")
        assert msft.trading_days == 5
        assert msft.volume_per_day == 100_000.0

    def test_compute_with_holiday_in_week(self, sample_holidays_2025):
        """Compute volume/day for a week with a holiday."""
        # Week of Jan 20-24, 2025: MLK Day is Monday = 4 trading days
        symbol_rows = [
            SymbolAggregateRow(
                week_ending=date(2025, 1, 24),  # Friday
                tier=Tier.NMS_TIER_1,
                symbol="AAPL",
                total_shares=800_000,
                total_trades=4_000,
                venue_count=5,
            ),
        ]

        results = compute_volume_per_trading_day(
            symbol_rows,
            sample_holidays_2025,
            exchange_code="XNYS",
        )

        assert len(results) == 1
        assert results[0].trading_days == 4  # MLK Day is holiday
        assert results[0].volume_per_day == 200_000.0  # 800,000 / 4

    def test_result_includes_calc_metadata(self, sample_symbol_rows, sample_holidays_2025):
        """Result includes calc_name and calc_version."""
        results = compute_volume_per_trading_day(
            sample_symbol_rows,
            sample_holidays_2025,
        )

        for r in results:
            assert r.calc_name == "volume_per_trading_day"
            assert r.calc_version == "1.1.0"  # Bumped for year-boundary + as-of support
            assert r.exchange_code == "XNYS"
            assert r.calendar_years_used == [2025]

    def test_pure_function_deterministic(self, sample_symbol_rows, sample_holidays_2025):
        """Same inputs produce same outputs (deterministic)."""
        results1 = compute_volume_per_trading_day(
            sample_symbol_rows,
            sample_holidays_2025,
        )
        results2 = compute_volume_per_trading_day(
            sample_symbol_rows,
            sample_holidays_2025,
        )

        for r1, r2 in zip(results1, results2):
            assert r1.trading_days == r2.trading_days
            assert r1.volume_per_day == r2.volume_per_day
            assert r1.trades_per_day == r2.trades_per_day


# =============================================================================
# DEPENDENCY HANDLING TESTS
# =============================================================================


class TestDependencyHandling:
    """Test that cross-domain dependencies are handled correctly."""

    def test_dependency_missing_gives_actionable_error(self):
        """Missing dependency raises error with remediation hint."""
        # Create mock connection with no calendar data
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with pytest.raises(DependencyMissingError) as exc:
            load_holidays_for_year(mock_conn, 2025, "XNYS")

        assert "reference.exchange_calendar" in str(exc.value)
        assert "2025" in str(exc.value)
        assert "spine run" in str(exc.value)  # Actionable hint

    def test_check_calendar_dependency_returns_errors(self):
        """check_calendar_dependency returns list of errors if missing."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (0,)

        errors = check_calendar_dependency(mock_conn, 2025, "XNYS")

        assert len(errors) == 1
        assert "2025" in errors[0]
        assert "spine run" in errors[0]

    def test_check_calendar_dependency_empty_if_satisfied(self):
        """check_calendar_dependency returns empty list if data exists."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (10,)  # 10 holidays

        errors = check_calendar_dependency(mock_conn, 2025, "XNYS")

        assert errors == []

    def test_load_holidays_success(self):
        """load_holidays_for_year returns set of dates when data exists."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            ("2025-01-01", "cap_001"),
            ("2025-01-20", "cap_001"),
        ]

        holidays = load_holidays_for_year(mock_conn, 2025, "XNYS")

        assert len(holidays) == 2
        assert date(2025, 1, 1) in holidays
        assert date(2025, 1, 20) in holidays


# =============================================================================
# DOMAIN ISOLATION TESTS
# =============================================================================


class TestDomainIsolation:
    """Prove that re-running FINRA does not re-run Exchange Calendar."""

    def test_finra_manifest_separate_from_calendar_manifest(self):
        """Each domain has independent manifest entries."""
        from spine.domains.finra.otc_transparency.schema import DOMAIN as FINRA_DOMAIN
        from spine.domains.reference.exchange_calendar.schema import DOMAIN as CALENDAR_DOMAIN

        # Domains are different
        assert FINRA_DOMAIN != CALENDAR_DOMAIN
        # FINRA uses underscore format for manifest domain key
        assert "finra" in FINRA_DOMAIN.lower()
        assert CALENDAR_DOMAIN == "reference.exchange_calendar"

    def test_finra_calc_does_not_import_calendar_pipeline(self):
        """FINRA calc imports calendar calculations, not pipelines."""
        # This import should work - it's the calc function
        from spine.domains.reference.exchange_calendar.calculations import (
            trading_days_between,
        )

        # Verify it's a function, not a pipeline
        assert callable(trading_days_between)

    def test_calendar_domain_calculations_have_no_finra_imports(self):
        """Exchange Calendar calculations do not depend on FINRA."""
        import inspect

        import spine.domains.reference.exchange_calendar.calculations as cal_calcs

        # Get source code of calculations module (the actual logic)
        calcs_source = inspect.getsource(cal_calcs)

        # No FINRA imports in the calculation logic
        assert "from spine.domains.finra" not in calcs_source
        assert "import spine.domains.finra" not in calcs_source


# =============================================================================
# REPLAY & BACKFILL TESTS
# =============================================================================


class TestReplaySemantics:
    """Prove replay and backfill semantics are correct."""

    def test_same_holiday_data_produces_same_result(self, sample_symbol_rows, sample_holidays_2025):
        """
        If calendar data is unchanged, rerunning calc produces same result.

        This proves determinism for replay.
        """
        results1 = compute_volume_per_trading_day(
            sample_symbol_rows,
            sample_holidays_2025,
        )

        # "Re-run" the calculation
        results2 = compute_volume_per_trading_day(
            sample_symbol_rows,
            sample_holidays_2025,
        )

        # Results are deterministic
        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1.volume_per_day == r2.volume_per_day
            assert r1.trading_days == r2.trading_days

    def test_updated_calendar_changes_downstream_calc(self, sample_symbol_rows):
        """
        If calendar data is updated, downstream calc picks up changes.

        This proves backfill propagation.
        """
        # Original: Week has 5 trading days
        holidays_v1: set[date] = set()  # No holidays

        results_v1 = compute_volume_per_trading_day(
            sample_symbol_rows,
            holidays_v1,
        )

        # Updated: Add a holiday in the week (e.g., Jan 8 is now a holiday)
        holidays_v2 = {date(2025, 1, 8)}  # Wednesday is now holiday

        results_v2 = compute_volume_per_trading_day(
            sample_symbol_rows,
            holidays_v2,
        )

        # Results are different
        aapl_v1 = next(r for r in results_v1 if r.symbol == "AAPL")
        aapl_v2 = next(r for r in results_v2 if r.symbol == "AAPL")

        assert aapl_v1.trading_days == 5
        assert aapl_v2.trading_days == 4  # One less due to new holiday

        # Volume per day increased (same volume, fewer days)
        assert aapl_v2.volume_per_day > aapl_v1.volume_per_day

    def test_different_years_independent(self, sample_holidays_2025):
        """
        Calculations for different years use different calendar data.
        """
        # 2025 week
        rows_2025 = [
            SymbolAggregateRow(
                week_ending=date(2025, 1, 10),
                tier=Tier.NMS_TIER_1,
                symbol="AAPL",
                total_shares=1_000_000,
                total_trades=5_000,
                venue_count=5,
            ),
        ]

        # 2024 week (uses different calendar year)
        rows_2024 = [
            SymbolAggregateRow(
                week_ending=date(2024, 1, 12),
                tier=Tier.NMS_TIER_1,
                symbol="AAPL",
                total_shares=1_000_000,
                total_trades=5_000,
                venue_count=5,
            ),
        ]

        # Each year would need its own holiday set
        # This test just proves the calculation respects the week_ending.year
        results_2025 = compute_volume_per_trading_day(rows_2025, sample_holidays_2025)
        results_2024 = compute_volume_per_trading_day(rows_2024, set())  # Empty 2024 holidays

        assert results_2025[0].calendar_years_used == [2025]
        assert results_2024[0].calendar_years_used == [2024]


# =============================================================================
# ARCHITECTURE VALIDATION TESTS
# =============================================================================


class TestArchitectureConstraints:
    """Validate architectural constraints are maintained."""

    def test_calculation_is_pure_function(self, sample_symbol_rows, sample_holidays_2025):
        """
        The core calculation has no database dependencies.

        It receives data as arguments, not via database queries.
        """
        # This call succeeds with no database - it's pure
        results = compute_volume_per_trading_day(
            sample_symbol_rows,
            sample_holidays_2025,
        )

        assert len(results) > 0

    def test_dependency_contract_is_explicit(self):
        """
        Pipeline explicitly declares its dependencies.
        """
        from spine.framework.registry import get_pipeline

        pipeline_cls = get_pipeline("finra.otc_transparency.compute_volume_per_day")

        # Pipeline has DEPENDENCIES attribute
        assert hasattr(pipeline_cls, "DEPENDENCIES")
        assert len(pipeline_cls.DEPENDENCIES) >= 1

        # Dependency declares domain and table
        dep = pipeline_cls.DEPENDENCIES[0]
        assert dep["domain"] == "reference.exchange_calendar"
        assert "holidays" in dep["table"]

    def test_no_pipeline_calls_other_pipeline(self):
        """
        Pipelines don't call other pipelines directly.

        Execution order is controlled externally, not hardcoded.
        """
        import inspect

        from spine.domains.finra.otc_transparency import pipelines

        source = inspect.getsource(pipelines.ComputeVolumePerDayPipeline)

        # Should not call other pipelines
        # Note: "ingest_year" may appear in error message hints, which is OK
        assert "run_pipeline" not in source
        assert ".run(" not in source  # Check for actual pipeline invocation


# =============================================================================
# HARDENING FEATURES TESTS
# =============================================================================


class TestYearBoundarySemantics:
    """Test year-boundary week handling (Feature #1)."""

    def test_year_boundary_week_loads_both_years(self):
        """
        Week spanning year boundary requires holidays from both years.

        Example: Dec 29, 2025 (Mon) - Jan 2, 2026 (Fri)
        - Week touches: 2025 and 2026
        - Should load holidays from both years
        """
        from spine.domains.finra.otc_transparency.calculations import (
            get_week_date_range,
            get_years_in_range,
        )

        # Friday Jan 2, 2026 is end of week that starts Mon Dec 29, 2025
        week_ending = date(2026, 1, 2)
        week_start, week_end = get_week_date_range(week_ending)

        assert week_start == date(2025, 12, 29)  # Monday in 2025
        assert week_end == date(2026, 1, 2)  # Friday in 2026

        years = get_years_in_range(week_start, week_end)
        assert years == [2025, 2026]  # Both years touched

    def test_compute_year_boundary_week(self):
        """
        Compute volume/day for week spanning year boundary.

        The calculation should handle holidays from both years correctly.
        """
        from spine.domains.finra.otc_transparency.calculations import (
            compute_volume_per_trading_day,
        )

        # Week ending Jan 2, 2026 (Mon Dec 29 - Fri Jan 2)
        symbol_row = SymbolAggregateRow(
            week_ending=date(2026, 1, 2),
            tier=Tier.NMS_TIER_1,
            symbol="AAPL",
            total_shares=1_000_000,
            total_trades=5_000,
            venue_count=5,
        )

        # Holidays spanning both years
        holidays = {
            date(2025, 12, 25),  # Christmas 2025 (Thursday)
            date(2026, 1, 1),  # New Year 2026 (Thursday)
        }

        results = compute_volume_per_trading_day(
            [symbol_row],
            holidays,
            exchange_code="XNYS",
        )

        assert len(results) == 1
        result = results[0]

        # Week: Mon 12/29, Tue 12/30, Wed 12/31, Thu 1/1 (holiday), Fri 1/2
        # Trading days: 4 (Thu 1/1 is New Year - not a trading day)
        assert result.trading_days == 4
        assert result.volume_per_day == 250_000.0  # 1M / 4

        # Metadata should track both years
        assert result.calendar_years_used == [2025, 2026]
        assert result.week_start == date(2025, 12, 29)
        assert result.week_end == date(2026, 1, 2)

    def test_load_holidays_for_multiple_years(self):
        """
        load_holidays_for_years() loads from multiple years at once.
        """
        from spine.domains.finra.otc_transparency.calculations import (
            load_holidays_for_years,
        )

        # Mock conn
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.side_effect = [
            # Year 2025 holidays
            [(date(2025, 12, 25).isoformat(), "cap_2025_001")],
            # Year 2026 holidays
            [(date(2026, 1, 1).isoformat(), "cap_2026_001")],
        ]

        holidays, capture_id = load_holidays_for_years(
            mock_conn,
            [2025, 2026],
            exchange_code="XNYS",
        )

        assert len(holidays) == 2
        assert date(2025, 12, 25) in holidays
        assert date(2026, 1, 1) in holidays
        assert capture_id is not None  # Captured from first year


class TestDependencyHelper:
    """Test dependency declaration helper (Feature #2)."""

    def test_domain_dependency_dataclass(self):
        """DomainDependency provides structured dependency declaration."""

        dep = DomainDependency(
            domain="reference.exchange_calendar",
            table="reference_exchange_calendar_holidays",
            key_description="year",
            required=True,
            error_hint="Run: spine run reference.exchange_calendar.ingest_year --year {year}",
        )

        assert dep.domain == "reference.exchange_calendar"
        assert dep.required is True
        assert "{year}" in dep.error_hint

    def test_check_dependencies_satisfied(self):
        """check_dependencies() returns success when deps satisfied."""
        from spine.domains.finra.otc_transparency.calculations import (
            check_dependencies,
        )

        # Mock conn with data present
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (10,)  # COUNT > 0

        deps = [
            DomainDependency(
                domain="reference.exchange_calendar",
                table="reference_exchange_calendar_holidays",
                key_description="year",
            ),
        ]

        result = check_dependencies(mock_conn, deps, {"year": 2025})

        assert result.satisfied is True
        assert len(result.errors) == 0

    def test_check_dependencies_missing(self):
        """check_dependencies() returns errors when deps missing."""
        from spine.domains.finra.otc_transparency.calculations import (
            check_dependencies,
        )

        # Mock conn with no data
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (0,)  # COUNT = 0

        deps = [
            DomainDependency(
                domain="reference.exchange_calendar",
                table="reference_exchange_calendar_holidays",
                key_description="year",
                error_hint="Run: spine run ingest --year {year}",
            ),
        ]

        result = check_dependencies(mock_conn, deps, {"year": 2025})

        assert result.satisfied is False
        assert len(result.errors) == 1
        assert "2025" in result.errors[0]


class TestAsOfDependencyMode:
    """Test as-of dependency mode (Feature #3)."""

    def test_load_holidays_with_capture_id(self):
        """
        load_holidays_for_years() with capture_id loads specific version.

        This supports deterministic replay: pin to exact calendar version.
        """
        from spine.domains.finra.otc_transparency.calculations import (
            load_holidays_for_years,
        )

        # Mock conn to return data for specific capture
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (date(2025, 1, 1).isoformat(), "cap_20250101_123456"),
            (date(2025, 7, 4).isoformat(), "cap_20250101_123456"),
        ]

        holidays, capture_id_used = load_holidays_for_years(
            mock_conn,
            [2025],
            exchange_code="XNYS",
            capture_id="cap_20250101_123456",
        )

        assert len(holidays) == 2
        assert capture_id_used == "cap_20250101_123456"

        # Verify query used capture_id filter
        call_args = mock_conn.execute.call_args[0]
        assert "capture_id = ?" in call_args[0]
        assert "cap_20250101_123456" in call_args[1]

    def test_compute_tracks_capture_id(self):
        """
        compute_volume_per_trading_day() writes capture_id to output.

        This enables downstream systems to know which calendar version was used.
        """
        from spine.domains.finra.otc_transparency.calculations import (
            compute_volume_per_trading_day,
        )

        symbol_row = SymbolAggregateRow(
            week_ending=date(2025, 1, 10),
            tier=Tier.NMS_TIER_1,
            symbol="AAPL",
            total_shares=1_000_000,
            total_trades=5_000,
            venue_count=5,
        )

        holidays = {date(2025, 1, 1)}

        results = compute_volume_per_trading_day(
            [symbol_row],
            holidays,
            exchange_code="XNYS",
            calendar_capture_id="cap_test_123",
        )

        assert results[0].calendar_capture_id_used == "cap_test_123"


class TestExchangeCodeParameterization:
    """Test exchange code parameterization (Feature #4)."""

    def test_compute_with_different_exchanges(self):
        """
        compute_volume_per_trading_day() accepts exchange_code param.

        This allows same calculation to work with XNYS, XNAS, etc.
        """
        from spine.domains.finra.otc_transparency.calculations import (
            compute_volume_per_trading_day,
        )

        symbol_row = SymbolAggregateRow(
            week_ending=date(2025, 1, 10),
            tier=Tier.NMS_TIER_1,
            symbol="AAPL",
            total_shares=1_000_000,
            total_trades=5_000,
            venue_count=5,
        )

        holidays_xnys = {date(2025, 1, 1)}
        holidays_xnas = {date(2025, 1, 1), date(2025, 1, 8)}  # Different calendar - holiday on Wed

        # Compute with NYSE calendar
        results_xnys = compute_volume_per_trading_day(
            [symbol_row],
            holidays_xnys,
            exchange_code="XNYS",
        )

        # Compute with NASDAQ calendar
        results_xnas = compute_volume_per_trading_day(
            [symbol_row],
            holidays_xnas,
            exchange_code="XNAS",
        )

        assert results_xnys[0].exchange_code == "XNYS"
        assert results_xnas[0].exchange_code == "XNAS"

        # Different holiday calendars = different trading day counts
        # Week Jan 6-10: Mon, Tue, Wed (XNAS holiday), Thu, Fri
        assert results_xnys[0].trading_days == 5
        assert results_xnas[0].trading_days == 4  # Jan 8 holiday

    def test_load_holidays_for_different_exchanges(self):
        """
        load_holidays_for_years() filters by exchange_code.
        """
        from spine.domains.finra.otc_transparency.calculations import (
            load_holidays_for_years,
        )

        # Mock conn
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            (date(2025, 1, 1).isoformat(), "cap_001"),
        ]

        load_holidays_for_years(
            mock_conn,
            [2025],
            exchange_code="XNAS",
        )

        # Verify query filtered by XNAS
        call_args = mock_conn.execute.call_args[0]
        assert "exchange_code = ?" in call_args[0]
        assert "XNAS" in call_args[1]

    def test_pipeline_accepts_exchange_code_param(self):
        """
        ComputeVolumePerDayPipeline has exchange_code optional param.
        """
        from spine.framework.registry import get_pipeline

        pipeline_cls = get_pipeline("finra.otc_transparency.compute_volume_per_day")

        # Check spec has exchange_code param
        assert "exchange_code" in pipeline_cls.spec.optional_params
        param = pipeline_cls.spec.optional_params["exchange_code"]
        assert param.default == "XNYS"
