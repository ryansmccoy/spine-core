"""
Tests for Exchange Calendar domain — Architecture Stress Test.

These tests prove:
1. New domain does not affect FINRA pipelines
2. New datasource works via registry only (no branching)
3. New calculation follows calc lifecycle rules
4. Replay and determinism semantics still hold

The test that would FAIL if architecture were poorly modular:
- test_finra_pipelines_unaffected_by_calendar_import
"""

import json
import tempfile
from datetime import date, datetime, UTC
from pathlib import Path

import pytest

from spine.domains.reference.exchange_calendar.calculations import (
    Holiday,
    MonthlyTradingDays,
    TradingDayResult,
    compute_monthly_trading_days,
    holidays_to_set,
    is_trading_day,
    is_weekend,
    next_trading_day,
    parse_holidays,
    previous_trading_day,
    strip_audit_fields,
    trading_days_between,
)
from spine.domains.reference.exchange_calendar.schema import (
    DOMAIN,
    Exchange,
    Stage,
    TABLES,
    partition_key,
)
from spine.domains.reference.exchange_calendar.sources import (
    AnnualPeriod,
    IngestionError,
    IngestionMetadata,
    JsonSource,
    PERIOD_REGISTRY,
    Payload,
    SOURCE_REGISTRY,
    create_source,
    resolve_period,
    resolve_source,
)


# =============================================================================
# TEST DATA
# =============================================================================

SAMPLE_HOLIDAYS_JSON = {
    "year": 2025,
    "exchange_code": "XNYS",
    "holidays": [
        {"date": "2025-01-01", "name": "New Year's Day"},
        {"date": "2025-01-20", "name": "MLK Day"},
        {"date": "2025-07-04", "name": "Independence Day"},
        {"date": "2025-12-25", "name": "Christmas Day"},
    ],
}


@pytest.fixture
def holidays_file(tmp_path: Path) -> Path:
    """Create a temporary JSON file with holiday data."""
    file_path = tmp_path / "holidays.json"
    file_path.write_text(json.dumps(SAMPLE_HOLIDAYS_JSON))
    return file_path


@pytest.fixture
def sample_holidays() -> set[date]:
    """Sample holiday set for testing."""
    return {
        date(2025, 1, 1),   # New Year's Day (Wednesday)
        date(2025, 1, 20),  # MLK Day (Monday)
        date(2025, 7, 4),   # Independence Day (Friday)
        date(2025, 12, 25), # Christmas (Thursday)
    }


# =============================================================================
# DOMAIN ISOLATION TESTS
# =============================================================================


class TestDomainIsolation:
    """Prove new domain does not affect FINRA domain."""

    def test_finra_pipelines_unaffected_by_calendar_import(self):
        """
        CRITICAL TEST: Importing exchange_calendar should not modify FINRA registry.
        
        This would FAIL if:
        - Exchange calendar polluted global registries
        - Source/Period registries were shared incorrectly
        - Pipeline registration had side effects
        """
        # Import FINRA first
        from spine.domains.finra.otc_transparency import sources as finra_sources
        
        finra_source_count = len(finra_sources.SOURCE_REGISTRY)
        finra_period_count = len(finra_sources.PERIOD_REGISTRY)
        
        # Now import exchange calendar
        from spine.domains.reference.exchange_calendar import sources as calendar_sources
        
        # FINRA registries should be unchanged
        assert len(finra_sources.SOURCE_REGISTRY) == finra_source_count
        assert len(finra_sources.PERIOD_REGISTRY) == finra_period_count
        
        # Calendar has its own separate registries
        assert calendar_sources.SOURCE_REGISTRY is not finra_sources.SOURCE_REGISTRY
        assert calendar_sources.PERIOD_REGISTRY is not finra_sources.PERIOD_REGISTRY

    def test_exchange_calendar_schema_independent(self):
        """Exchange calendar domain has its own schema constants."""
        from spine.domains.finra.otc_transparency.schema import DOMAIN as FINRA_DOMAIN
        
        assert DOMAIN != FINRA_DOMAIN
        assert DOMAIN == "reference.exchange_calendar"
        assert "holidays" in TABLES
        assert "trading_days" in TABLES

    def test_pipeline_registry_contains_both_domains(self):
        """Both domains register pipelines without conflict."""
        from spine.framework.registry import list_pipelines
        
        pipelines = list_pipelines()
        
        # FINRA pipelines present
        assert "finra.otc_transparency.ingest_week" in pipelines
        assert "finra.otc_transparency.normalize_week" in pipelines
        
        # Exchange calendar pipelines present
        assert "reference.exchange_calendar.ingest_year" in pipelines
        assert "reference.exchange_calendar.compute_trading_days" in pipelines


# =============================================================================
# SOURCE REGISTRY TESTS
# =============================================================================


class TestSourceRegistry:
    """Prove new source works via registry only."""

    def test_json_source_registered(self):
        """JsonSource is registered in domain-local registry."""
        assert "json" in SOURCE_REGISTRY
        assert SOURCE_REGISTRY["json"] is JsonSource

    def test_resolve_source_returns_json_source(self, holidays_file: Path):
        """resolve_source() creates JsonSource without branching."""
        source = resolve_source(
            source_type="json",
            file_path=holidays_file,
            year=2025,
            exchange_code="XNYS",
        )
        
        assert isinstance(source, JsonSource)
        assert source.source_type == "json"

    def test_create_source_delegates_to_registry(self, holidays_file: Path):
        """create_source() delegates to resolve_source()."""
        source = create_source(
            source_type="json",
            file_path=holidays_file,
        )
        
        assert isinstance(source, JsonSource)

    def test_unknown_source_raises_helpful_error(self):
        """Unknown source type raises with available sources."""
        with pytest.raises(ValueError) as exc:
            resolve_source(source_type="unknown")
        
        assert "unknown" in str(exc.value).lower()
        assert "json" in str(exc.value).lower()

    def test_json_source_fetch_returns_payload(self, holidays_file: Path):
        """JsonSource.fetch() returns proper Payload."""
        source = JsonSource(file_path=holidays_file)
        payload = source.fetch()
        
        assert isinstance(payload, Payload)
        assert isinstance(payload.content, dict)
        assert payload.metadata.year == 2025
        assert payload.metadata.exchange_code == "XNYS"
        assert payload.metadata.source_type == "json"


# =============================================================================
# PERIOD REGISTRY TESTS
# =============================================================================


class TestPeriodRegistry:
    """Prove annual period works via registry."""

    def test_annual_period_registered(self):
        """AnnualPeriod is registered in domain-local registry."""
        assert "annual" in PERIOD_REGISTRY
        assert PERIOD_REGISTRY["annual"] is AnnualPeriod

    def test_resolve_period_returns_annual(self):
        """resolve_period() creates AnnualPeriod by default."""
        period = resolve_period()
        
        assert isinstance(period, AnnualPeriod)
        assert period.period_type == "annual"

    def test_annual_period_derives_year_end(self):
        """AnnualPeriod.derive_period_end() returns Dec 31."""
        period = AnnualPeriod()
        
        # Any date in 2025 should derive to Dec 31, 2025
        assert period.derive_period_end(date(2025, 1, 15)) == date(2025, 12, 31)
        assert period.derive_period_end(date(2025, 6, 15)) == date(2025, 12, 31)
        assert period.derive_period_end(date(2025, 12, 31)) == date(2025, 12, 31)

    def test_annual_period_validates_year_end_only(self):
        """AnnualPeriod.validate_date() only accepts Dec 31."""
        period = AnnualPeriod()
        
        assert period.validate_date(date(2025, 12, 31)) is True
        assert period.validate_date(date(2025, 6, 30)) is False
        assert period.validate_date(date(2025, 1, 1)) is False

    def test_annual_period_format_display(self):
        """AnnualPeriod.format_for_display() returns year string."""
        period = AnnualPeriod()
        
        assert period.format_for_display(date(2025, 12, 31)) == "2025"


# =============================================================================
# CALCULATION LIFECYCLE TESTS
# =============================================================================


class TestCalculationLifecycle:
    """Prove calculations follow calc lifecycle rules."""

    def test_is_trading_day_pure_function(self, sample_holidays: set[date]):
        """is_trading_day is a pure function with no side effects."""
        # Same inputs always produce same outputs
        result1 = is_trading_day(date(2025, 1, 2), sample_holidays)
        result2 = is_trading_day(date(2025, 1, 2), sample_holidays)
        
        assert result1 == result2

    def test_trading_days_between_deterministic(self, sample_holidays: set[date]):
        """trading_days_between produces deterministic results."""
        result1 = trading_days_between(
            date(2025, 1, 1),
            date(2025, 1, 31),
            sample_holidays,
        )
        result2 = trading_days_between(
            date(2025, 1, 1),
            date(2025, 1, 31),
            sample_holidays,
        )
        
        # Deterministic fields must match
        assert result1.trading_days == result2.trading_days
        assert result1.calendar_days == result2.calendar_days
        assert result1.holidays_in_range == result2.holidays_in_range
        assert result1.weekends_in_range == result2.weekends_in_range

    def test_calc_result_has_calc_metadata(self, sample_holidays: set[date]):
        """Calculation results include calc_name and calc_version."""
        result = trading_days_between(
            date(2025, 1, 1),
            date(2025, 1, 31),
            sample_holidays,
        )
        
        assert result.calc_name == "trading_days_between"
        assert result.calc_version == "1.0.0"

    def test_monthly_trading_days_has_calc_metadata(self, sample_holidays: set[date]):
        """MonthlyTradingDays includes calc metadata."""
        results = compute_monthly_trading_days(2025, "XNYS", sample_holidays)
        
        for month_result in results:
            assert month_result.calc_name == "monthly_trading_days"
            assert month_result.calc_version == "1.0.0"

    def test_strip_audit_fields_removes_calculated_at(self):
        """strip_audit_fields removes audit-only fields."""
        row = {
            "year": 2025,
            "exchange_code": "XNYS",
            "trading_days": 21,
            "calculated_at": "2025-01-01T00:00:00",
            "id": 123,
        }
        
        stripped = strip_audit_fields(row)
        
        assert "calculated_at" not in stripped
        assert "id" not in stripped
        assert stripped["year"] == 2025
        assert stripped["trading_days"] == 21


# =============================================================================
# DETERMINISM & REPLAY TESTS
# =============================================================================


class TestDeterminismAndReplay:
    """Prove replay and determinism semantics hold."""

    def test_same_input_produces_same_output(self, sample_holidays: set[date]):
        """Pure calculations produce identical results for identical inputs."""
        # Run calculation twice
        result1 = compute_monthly_trading_days(2025, "XNYS", sample_holidays)
        result2 = compute_monthly_trading_days(2025, "XNYS", sample_holidays)
        
        # All deterministic fields must match
        for r1, r2 in zip(result1, result2):
            assert r1.year == r2.year
            assert r1.month == r2.month
            assert r1.trading_days == r2.trading_days
            assert r1.calendar_days == r2.calendar_days
            assert r1.holidays == r2.holidays

    def test_next_trading_day_deterministic(self, sample_holidays: set[date]):
        """next_trading_day is deterministic."""
        result1 = next_trading_day(date(2025, 1, 1), sample_holidays)
        result2 = next_trading_day(date(2025, 1, 1), sample_holidays)
        
        assert result1 == result2
        assert result1 == date(2025, 1, 2)  # Jan 1 is holiday, Jan 2 is Thursday

    def test_previous_trading_day_deterministic(self, sample_holidays: set[date]):
        """previous_trading_day is deterministic."""
        result1 = previous_trading_day(date(2025, 1, 2), sample_holidays)
        result2 = previous_trading_day(date(2025, 1, 2), sample_holidays)
        
        assert result1 == result2
        assert result1 == date(2024, 12, 31)  # Jan 1 is holiday, go back to Dec 31


# =============================================================================
# CORRECTNESS TESTS
# =============================================================================


class TestCalculationCorrectness:
    """Verify calculation logic is correct."""

    def test_is_weekend(self):
        """is_weekend correctly identifies weekends."""
        # 2025-01-04 is Saturday, 2025-01-05 is Sunday
        assert is_weekend(date(2025, 1, 4)) is True
        assert is_weekend(date(2025, 1, 5)) is True
        
        # Weekdays
        assert is_weekend(date(2025, 1, 6)) is False  # Monday
        assert is_weekend(date(2025, 1, 3)) is False  # Friday

    def test_is_trading_day_excludes_weekends(self):
        """is_trading_day returns False for weekends."""
        holidays: set[date] = set()
        
        assert is_trading_day(date(2025, 1, 4), holidays) is False  # Saturday
        assert is_trading_day(date(2025, 1, 5), holidays) is False  # Sunday
        assert is_trading_day(date(2025, 1, 6), holidays) is True   # Monday

    def test_is_trading_day_excludes_holidays(self, sample_holidays: set[date]):
        """is_trading_day returns False for holidays."""
        assert is_trading_day(date(2025, 1, 1), sample_holidays) is False  # Holiday
        assert is_trading_day(date(2025, 1, 2), sample_holidays) is True   # Not holiday

    def test_trading_days_between_simple_week(self, sample_holidays: set[date]):
        """Count trading days in a simple week."""
        # Week of Jan 6-10, 2025 (Mon-Fri, no holidays)
        result = trading_days_between(
            date(2025, 1, 6),
            date(2025, 1, 10),
            sample_holidays,
        )
        
        assert result.trading_days == 5
        assert result.calendar_days == 5
        assert result.holidays_in_range == 0
        assert result.weekends_in_range == 0

    def test_trading_days_between_with_weekend(self, sample_holidays: set[date]):
        """Count trading days across a weekend."""
        # Jan 3-7, 2025: Fri, Sat, Sun, Mon, Tue
        result = trading_days_between(
            date(2025, 1, 3),
            date(2025, 1, 7),
            sample_holidays,
        )
        
        assert result.trading_days == 3  # Fri, Mon, Tue
        assert result.weekends_in_range == 2  # Sat, Sun

    def test_trading_days_between_with_holiday(self, sample_holidays: set[date]):
        """Count trading days with a holiday."""
        # Jan 1-3, 2025: Wed (holiday), Thu, Fri
        result = trading_days_between(
            date(2025, 1, 1),
            date(2025, 1, 3),
            sample_holidays,
        )
        
        assert result.trading_days == 2  # Thu, Fri
        assert result.holidays_in_range == 1  # Jan 1

    def test_monthly_trading_days_january_2025(self, sample_holidays: set[date]):
        """Compute trading days for January 2025."""
        results = compute_monthly_trading_days(2025, "XNYS", sample_holidays)
        
        jan = results[0]  # Month 1
        assert jan.month == 1
        assert jan.calendar_days == 31
        # Jan 2025: 31 days - 8 weekend days - 2 holidays = 21 trading days
        assert jan.holidays == 2  # Jan 1, Jan 20


# =============================================================================
# PARSE HOLIDAYS TESTS
# =============================================================================


class TestParseHolidays:
    """Test holiday parsing from JSON."""

    def test_parse_holidays_from_json(self):
        """parse_holidays extracts Holiday objects from JSON."""
        holidays = parse_holidays(SAMPLE_HOLIDAYS_JSON)
        
        assert len(holidays) == 4
        assert all(isinstance(h, Holiday) for h in holidays)
        
        # Check first holiday
        assert holidays[0].date == date(2025, 1, 1)
        assert holidays[0].name == "New Year's Day"
        assert holidays[0].exchange_code == "XNYS"
        assert holidays[0].year == 2025

    def test_holidays_to_set(self):
        """holidays_to_set creates date set for fast lookup."""
        holidays = parse_holidays(SAMPLE_HOLIDAYS_JSON)
        holiday_set = holidays_to_set(holidays)
        
        assert len(holiday_set) == 4
        assert date(2025, 1, 1) in holiday_set
        assert date(2025, 7, 4) in holiday_set
        assert date(2025, 6, 15) not in holiday_set


# =============================================================================
# SCHEMA TESTS
# =============================================================================


class TestSchema:
    """Test schema definitions."""

    def test_exchange_enum_values(self):
        """Exchange enum has expected MIC codes."""
        assert Exchange.XNYS.value == "XNYS"
        assert Exchange.XNAS.value == "XNAS"
        assert "XNYS" in Exchange.values()
        assert "XNAS" in Exchange.values()

    def test_partition_key_format(self):
        """partition_key generates valid JSON."""
        pk = partition_key(2025, "XNYS")
        
        # Should be valid JSON
        parsed = json.loads(pk)
        assert parsed["year"] == 2025
        assert parsed["exchange_code"] == "XNYS"

    def test_table_names_follow_convention(self):
        """Table names follow domain_entity convention."""
        for table_name in TABLES.values():
            assert table_name.startswith("reference_exchange_calendar_")
