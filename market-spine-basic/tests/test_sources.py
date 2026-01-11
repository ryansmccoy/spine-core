"""
Tests for the source abstraction layer and ingestion patterns.

Tests:
1. Idempotent rerun - same params should skip (already ingested)
2. Capture replay - C1 vs C2 have distinct capture_ids
3. Offline API ingest - API source with mock content
4. Source factory validation
"""

from datetime import date
from pathlib import Path

import pytest

from market_spine.db import init_connection_provider, init_db
from spine.domains.finra.otc_transparency.connector import parse_finra_content
from spine.domains.finra.otc_transparency.sources import (
    APISource,
    FileSource,
    IngestionError,
    Payload,
    create_source,
)
from spine.framework.db import get_connection
from spine.framework.dispatcher import Dispatcher

# Initialize connection provider for tests
init_connection_provider()


@pytest.fixture(autouse=True)
def setup_db():
    """Initialize database for each test."""
    init_db()


@pytest.fixture
def fixture_path() -> Path:
    """Path to test fixture."""
    return Path(__file__).parent.parent / "data" / "fixtures" / "otc" / "week_2025-12-26.psv"


@pytest.fixture
def mock_psv_content() -> str:
    """Mock PSV content simulating API response (matches fixture format)."""
    return """WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-12-26|NMS Tier 1|AAPL|ARCA|1000000|500
2025-12-26|NMS Tier 1|MSFT|ARCA|800000|400
2025-12-26|NMS Tier 1|GOOGL|ARCA|500000|250"""


class TestSourceFactory:
    """Tests for the create_source factory."""

    def test_create_file_source_requires_file_path(self):
        """File source requires file_path parameter."""
        with pytest.raises(ValueError, match="file_path is required"):
            create_source(source_type="file")

    def test_create_api_source_requires_tier(self):
        """API source requires tier parameter."""
        with pytest.raises(ValueError, match="tier is required"):
            create_source(source_type="api", week_ending=date(2025, 12, 26))

    def test_create_api_source_requires_week_ending(self):
        """API source requires week_ending parameter."""
        with pytest.raises(ValueError, match="week_ending is required"):
            create_source(source_type="api", tier="NMS_TIER_1")

    def test_create_file_source_valid(self, fixture_path):
        """Valid file source creation."""
        source = create_source(source_type="file", file_path=fixture_path)
        assert isinstance(source, FileSource)
        assert source.source_type == "file"

    def test_create_api_source_valid(self):
        """Valid API source creation with mock content."""
        source = create_source(
            source_type="api",
            tier="NMS_TIER_1",
            week_ending=date(2025, 12, 26),
            mock_content="header\ndata",
        )
        assert isinstance(source, APISource)
        assert source.source_type == "api"


class TestFileSource:
    """Tests for FileSource."""

    def test_fetch_returns_payload(self, fixture_path):
        """FileSource.fetch() returns Payload with content and metadata."""
        source = FileSource(file_path=fixture_path)
        payload = source.fetch()

        assert isinstance(payload, Payload)
        assert isinstance(payload.content, str)
        assert len(payload.content) > 0
        assert payload.metadata.source_type == "file"
        assert str(fixture_path) in payload.metadata.source_name

    def test_fetch_parses_week_ending(self, fixture_path):
        """FileSource extracts week_ending from file date via business logic."""
        source = FileSource(file_path=fixture_path)
        payload = source.fetch()

        # file_date is extracted from filename (2025-12-26)
        assert payload.metadata.file_date == date(2025, 12, 26)
        # week_ending is derived via derive_week_ending_from_publish_date()
        # The fixture contains WeekEnding=2025-12-26 in the data itself
        assert payload.metadata.week_ending is not None

    def test_fetch_override_week_ending(self, fixture_path):
        """week_ending can be overridden."""
        override = date(2025, 1, 10)
        source = FileSource(file_path=fixture_path, week_ending_override=override)
        payload = source.fetch()

        assert payload.metadata.week_ending == override

    def test_content_is_parseable(self, fixture_path):
        """Content from FileSource can be parsed by parse_finra_content."""
        source = FileSource(file_path=fixture_path)
        payload = source.fetch()

        records = list(parse_finra_content(payload.content))
        assert len(records) > 0
        assert all(hasattr(r, "symbol") for r in records)

    def test_file_not_found_raises_ingestion_error(self, tmp_path):
        """Missing file raises IngestionError."""
        source = FileSource(file_path=tmp_path / "nonexistent.psv")
        with pytest.raises(IngestionError, match="File not found"):
            source.fetch()


class TestAPISource:
    """Tests for APISource with mock content."""

    def test_fetch_with_mock_returns_payload(self, mock_psv_content):
        """APISource with mock_content returns Payload."""
        source = APISource(
            tier="NMS_TIER_1", week_ending=date(2025, 12, 26), mock_content=mock_psv_content
        )
        payload = source.fetch()

        assert isinstance(payload, Payload)
        assert payload.content == mock_psv_content
        assert payload.metadata.source_type == "api"
        assert "mock://" in payload.metadata.source_name

    def test_fetch_without_mock_raises_error(self):
        """APISource without mock_content raises IngestionError (not implemented)."""
        source = APISource(tier="NMS_TIER_1", week_ending=date(2025, 12, 26))
        with pytest.raises(IngestionError, match="Live API fetch not implemented"):
            source.fetch()

    def test_mock_content_is_parseable(self, mock_psv_content):
        """Mock API content can be parsed by parse_finra_content."""
        source = APISource(
            tier="NMS_TIER_1", week_ending=date(2025, 12, 26), mock_content=mock_psv_content
        )
        payload = source.fetch()

        records = list(parse_finra_content(payload.content))
        assert len(records) == 3
        symbols = {r.symbol for r in records}
        assert symbols == {"AAPL", "MSFT", "GOOGL"}


class TestIdempotentRerun:
    """Tests for idempotency - same capture should be skipped."""

    def test_second_run_skips_already_ingested(self, fixture_path):
        """Running same params twice should skip the second run."""
        dispatcher = Dispatcher()

        # First run with force=True to ensure we start fresh
        exec1 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "OTC", "force": True},
        )
        assert exec1.status.value == "completed"
        assert exec1.result is not None
        # First run should not be skipped
        assert exec1.result.metrics.get("skipped") is not True

        # Second run with same params (no force) - should be skipped
        exec2 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "OTC"},
        )
        assert exec2.status.value == "completed"
        # Should be skipped
        assert exec2.result is not None
        assert exec2.result.metrics.get("skipped") is True

    def test_force_reingests(self, fixture_path):
        """force=True allows reingesting same data."""
        dispatcher = Dispatcher()

        # Use NMS_TIER_2 for this test to avoid conflict with other tests
        # First run
        exec1 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "NMS_TIER_2", "force": True},
        )
        assert exec1.status.value == "completed"
        assert exec1.result is not None
        capture1 = exec1.result.metrics.get("capture_id")

        # Force reingest
        exec2 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "NMS_TIER_2", "force": True},
        )
        assert exec2.status.value == "completed"
        assert exec2.result is not None
        capture2 = exec2.result.metrics.get("capture_id")

        # Should have different capture_ids
        assert capture1 is not None
        assert capture2 is not None
        assert capture1 != capture2


class TestCaptureReplay:
    """Tests for capture semantics - C1 vs C2 have distinct capture_ids."""

    def test_distinct_runs_get_distinct_capture_ids(self, fixture_path):
        """Each capture (forced run) gets a unique capture_id."""
        dispatcher = Dispatcher()

        # First capture (force to ensure fresh start for NMS_TIER_1)
        exec1 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "NMS_TIER_1", "force": True},
        )
        assert exec1.result is not None
        capture1 = exec1.result.metrics.get("capture_id")

        # Second capture (forced)
        exec2 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "NMS_TIER_1", "force": True},
        )
        assert exec2.result is not None
        capture2 = exec2.result.metrics.get("capture_id")

        assert capture1 is not None
        assert capture2 is not None
        assert capture1 != capture2

        # Both should contain identifying info
        assert "NMS_TIER_1" in capture1

    def test_captures_are_queryable_separately(self, fixture_path):
        """Data from different captures should be queryable by capture_id."""
        dispatcher = Dispatcher()

        # Use a unique tier to avoid conflicts - but NMS_TIER_1 should work if forced
        # Two captures with force to ensure they both insert
        exec1 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "NMS_TIER_1", "force": True},
        )
        assert exec1.result is not None
        capture1 = exec1.result.metrics.get("capture_id")

        exec2 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "NMS_TIER_1", "force": True},
        )
        assert exec2.result is not None
        capture2 = exec2.result.metrics.get("capture_id")

        # Query by capture_id (use correct table name)
        conn = get_connection()
        c1_count = conn.execute(
            "SELECT COUNT(*) FROM finra_otc_transparency_raw WHERE capture_id = ?", (capture1,)
        ).fetchone()[0]
        c2_count = conn.execute(
            "SELECT COUNT(*) FROM finra_otc_transparency_raw WHERE capture_id = ?", (capture2,)
        ).fetchone()[0]

        # Both should have records
        assert c1_count > 0
        assert c2_count > 0


class TestOfflineAPIIngest:
    """Tests for API ingestion using mock/offline content."""

    def test_api_ingest_with_mock_content(self, mock_psv_content):
        """API source with mock_response works end-to-end."""
        dispatcher = Dispatcher()

        # Use force=True and unique week to ensure fresh ingest
        exec_result = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={
                "source_type": "api",
                "tier": "NMS_TIER_1",
                "week_ending": "2026-01-02",  # Different Friday
                "mock_response": mock_psv_content,
                "force": True,
            },
        )

        assert exec_result.status.value == "completed"
        assert exec_result.result is not None
        assert exec_result.result.metrics.get("records") == 3

    def test_api_and_file_produce_same_schema(self, fixture_path, mock_psv_content):
        """Data from file and API sources have the same schema in raw table."""
        dispatcher = Dispatcher()

        # File ingest (use tier OTC to differentiate)
        dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "OTC", "force": True},
        )

        # API ingest (NMS_TIER_2 to differentiate, use Friday date)
        dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={
                "source_type": "api",
                "tier": "NMS_TIER_2",
                "week_ending": "2025-12-19",  # Friday
                "mock_response": mock_psv_content,
                "force": True,
            },
        )

        # Query both (use correct table name)
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT tier, source_file 
            FROM finra_otc_transparency_raw 
            GROUP BY tier
            ORDER BY tier
            """
        ).fetchall()

        tiers = {r["tier"] for r in rows}
        assert "OTC" in tiers
        assert "NMS_TIER_2" in tiers

        # source_file column should contain file path for file, mock URL for API
        for row in rows:
            assert row["source_file"] is not None
            assert len(row["source_file"]) > 0


# =============================================================================
# EXTENSIBILITY GUARANTEE TESTS
# =============================================================================


class TestSourceRegistryExtensibility:
    """
    Tests proving sources can be added without modifying pipeline code.

    These tests document the extensibility contract:
    - Adding a new source is decorator + class only
    - resolve_source() handles lookup automatically
    - Pipeline never branches on source type
    """

    def test_source_registry_contains_file_and_api(self):
        """Registry contains built-in sources."""
        from spine.domains.finra.otc_transparency.sources import (
            list_sources,
        )

        sources = list_sources()
        assert "file" in sources
        assert "api" in sources

    def test_resolve_source_uses_registry(self):
        """resolve_source looks up from registry, not if/else."""
        from spine.domains.finra.otc_transparency.sources import (
            SOURCE_REGISTRY,
            resolve_source,
        )

        # Verify file source is resolved from registry
        file_source = resolve_source("file", file_path=Path(__file__))
        assert file_source.__class__ is SOURCE_REGISTRY["file"]
        assert file_source.source_type == "file"

    def test_resolve_source_unknown_raises_helpful_error(self):
        """Unknown source type raises clear error with known sources."""
        from spine.domains.finra.otc_transparency.sources import resolve_source

        with pytest.raises(ValueError) as exc_info:
            resolve_source("nonexistent_source", file_path="test.psv")

        error = str(exc_info.value)
        assert "Unknown source: nonexistent_source" in error
        assert "file" in error  # Lists known sources
        assert "api" in error

    def test_adding_source_requires_no_factory_edit(self):
        """
        Adding a new source only requires @register_source decorator.

        This test simulates adding an S3 source and verifies:
        1. Registration works via decorator
        2. resolve_source can look it up
        3. No changes to resolve_source code needed
        """
        from spine.domains.finra.otc_transparency.sources import (
            SOURCE_REGISTRY,
            IngestionMetadata,
            IngestionSource,
            Payload,
            register_source,
            resolve_source,
        )

        # Simulate adding a new S3 source
        @register_source("test_s3")
        class TestS3Source(IngestionSource):
            def __init__(self, bucket: str = "test", **kwargs):
                self.bucket = bucket

            @property
            def source_type(self) -> str:
                return "test_s3"

            def fetch(self) -> Payload:
                return Payload(
                    content="test content",
                    metadata=IngestionMetadata(
                        week_ending=date(2025, 12, 26),
                        file_date=date(2025, 12, 29),
                        source_type="test_s3",
                        source_name="s3://test/data.csv",
                    ),
                )

        try:
            # Should be in registry now
            assert "test_s3" in SOURCE_REGISTRY

            # Should be resolvable without any code changes
            source = resolve_source("test_s3", bucket="my-bucket")
            assert source.source_type == "test_s3"
            assert source.bucket == "my-bucket"

            # Should fetch successfully
            payload = source.fetch()
            assert payload.content == "test content"

        finally:
            # Cleanup: remove test source from registry
            del SOURCE_REGISTRY["test_s3"]


class TestPeriodRegistryExtensibility:
    """
    Tests proving periods can be added without modifying pipeline code.

    These tests document the extensibility contract:
    - Adding a new period is decorator + class only
    - resolve_period() handles lookup automatically
    - WeeklyPeriod is default, backward compatible
    """

    def test_period_registry_contains_weekly_and_monthly(self):
        """Registry contains built-in periods."""
        from spine.domains.finra.otc_transparency.sources import (
            list_periods,
        )

        periods = list_periods()
        assert "weekly" in periods
        assert "monthly" in periods

    def test_resolve_period_defaults_to_weekly(self):
        """Default period is weekly for backward compatibility."""
        from spine.domains.finra.otc_transparency.sources import resolve_period

        period = resolve_period()  # No arg = weekly
        assert period.period_type == "weekly"

    def test_weekly_period_derives_friday_from_monday(self):
        """WeeklyPeriod.derive_period_end gives Friday from Monday."""
        from spine.domains.finra.otc_transparency.sources import WeeklyPeriod

        period = WeeklyPeriod()

        # Monday 2025-12-22 → Friday 2025-12-19
        result = period.derive_period_end(date(2025, 12, 22))
        assert result == date(2025, 12, 19)
        assert result.weekday() == 4  # Friday

    def test_monthly_period_derives_month_end(self):
        """MonthlyPeriod.derive_period_end gives last day of prev month."""
        from spine.domains.finra.otc_transparency.sources import MonthlyPeriod

        period = MonthlyPeriod()

        # Jan 2, 2026 → Dec 31, 2025
        result = period.derive_period_end(date(2026, 1, 2))
        assert result == date(2025, 12, 31)
        assert period.validate_date(result)  # Is month end

    def test_adding_period_requires_no_factory_edit(self):
        """
        Adding a new period only requires @register_period decorator.
        """
        from spine.domains.finra.otc_transparency.sources import (
            PERIOD_REGISTRY,
            PeriodStrategy,
            register_period,
            resolve_period,
        )

        # Simulate adding a quarterly period
        @register_period("test_quarterly")
        class TestQuarterlyPeriod(PeriodStrategy):
            @property
            def period_type(self) -> str:
                return "test_quarterly"

            def derive_period_end(self, publish_date: date) -> date:
                # Quarter end logic (simplified)
                month = ((publish_date.month - 1) // 3) * 3 + 3
                if month > 12:
                    month = 12
                return date(publish_date.year, month, 30)

            def validate_date(self, period_end: date) -> bool:
                return period_end.month in (3, 6, 9, 12) and period_end.day >= 28

            def format_for_filename(self, period_end: date) -> str:
                return f"Q{(period_end.month - 1) // 3 + 1}-{period_end.year}"

            def format_for_display(self, period_end: date) -> str:
                return f"Q{(period_end.month - 1) // 3 + 1} {period_end.year}"

        try:
            # Should be in registry
            assert "test_quarterly" in PERIOD_REGISTRY

            # Should be resolvable
            period = resolve_period("test_quarterly")
            assert period.period_type == "test_quarterly"

            # Should format correctly
            assert "Q4" in period.format_for_filename(date(2025, 12, 31))

        finally:
            # Cleanup
            del PERIOD_REGISTRY["test_quarterly"]


class TestBackwardCompatibility:
    """Tests ensuring existing code continues to work."""

    def test_create_source_still_works(self, fixture_path):
        """create_source() backward-compat function still works."""
        from spine.domains.finra.otc_transparency.sources import create_source

        source = create_source(source_type="file", file_path=fixture_path)
        assert source.source_type == "file"

        payload = source.fetch()
        assert payload.metadata.week_ending is not None

    def test_derive_week_ending_from_publish_date_still_works(self):
        """Backward-compat function in sources.py still works."""
        from spine.domains.finra.otc_transparency.sources import (
            derive_week_ending_from_publish_date,
        )

        result = derive_week_ending_from_publish_date(date(2025, 12, 22))
        assert result == date(2025, 12, 19)

    def test_connector_derive_week_ending_still_works(self):
        """Original connector function still works."""
        from spine.domains.finra.otc_transparency.connector import (
            derive_week_ending_from_publish_date,
        )

        result = derive_week_ending_from_publish_date(date(2025, 12, 22))
        assert result == date(2025, 12, 19)

    def test_metadata_has_period_end_alias(self, fixture_path):
        """IngestionMetadata.period_end aliases week_ending."""
        from spine.domains.finra.otc_transparency.sources import FileSource

        source = FileSource(file_path=fixture_path)
        payload = source.fetch()

        # Both should return same value
        assert payload.metadata.period_end == payload.metadata.week_ending
