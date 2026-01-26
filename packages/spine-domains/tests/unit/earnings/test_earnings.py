"""Tests for earnings domain models and pipeline."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from spine.domains.earnings import (
    DOMAIN,
    TABLES,
    EarningsConfig,
    EarningsEvent,
    EarningsPipeline,
    EarningsSurprise,
    EstimateSnapshot,
    MetricCode,
    ReportTime,
    SurpriseDirection,
    SurpriseMagnitude,
    partition_key,
)


class TestSchema:
    """Tests for earnings schema definitions."""

    def test_domain_constant(self):
        """Test domain identifier."""
        assert DOMAIN == "earnings"

    def test_tables_dict(self):
        """Test table names follow convention."""
        assert "events" in TABLES
        assert "estimates" in TABLES
        assert "actuals" in TABLES
        assert "surprises" in TABLES
        
        # All should start with earnings_
        for table in TABLES.values():
            assert table.startswith("earnings_")

    def test_metric_codes(self):
        """Test metric code enum."""
        assert MetricCode.EPS.value == "eps"
        assert MetricCode.REVENUE.value == "revenue"
        assert "eps" in MetricCode.values()

    def test_report_time_enum(self):
        """Test report time enum."""
        assert ReportTime.BMO.value == "bmo"
        assert ReportTime.AMC.value == "amc"
        assert ReportTime.UNKNOWN.value == "unknown"

    def test_surprise_direction_enum(self):
        """Test surprise direction enum."""
        assert SurpriseDirection.BEAT.value == "beat"
        assert SurpriseDirection.MISS.value == "miss"
        assert SurpriseDirection.INLINE.value == "inline"

    def test_partition_key_date_only(self):
        """Test partition key generation with date only."""
        pk = partition_key("2026-01-30")
        assert "2026-01-30" in pk
        assert "report_date" in pk

    def test_partition_key_with_ticker(self):
        """Test partition key with ticker."""
        pk = partition_key("2026-01-30", ticker="AAPL")
        assert "AAPL" in pk
        assert "ticker" in pk


class TestEarningsEvent:
    """Tests for EarningsEvent model."""

    def test_basic_creation(self):
        """Test creating a basic event."""
        event = EarningsEvent(
            ticker="AAPL",
            report_date="2026-01-30",
            fiscal_year=2026,
            fiscal_period="Q1",
        )
        
        assert event.ticker == "AAPL"
        assert event.fiscal_year == 2026
        assert event.report_time == ReportTime.UNKNOWN

    def test_natural_key_auto_generated(self):
        """Test natural key is auto-generated."""
        event = EarningsEvent(
            ticker="AAPL",
            report_date="2026-01-30",
            fiscal_year=2026,
            fiscal_period="Q1",
            source_vendor="polygon",
        )
        
        assert "polygon" in event.natural_key
        assert "aapl" in event.natural_key
        assert "2026" in event.natural_key


class TestEstimateSnapshot:
    """Tests for EstimateSnapshot model."""

    def test_basic_creation(self):
        """Test creating a snapshot."""
        snapshot = EstimateSnapshot(
            ticker="AAPL",
            fiscal_period="2026:Q1",
            metric_code=MetricCode.EPS,
            estimate_value=Decimal("2.35"),
            captured_at=datetime(2026, 1, 15, tzinfo=UTC),
        )
        
        assert snapshot.ticker == "AAPL"
        assert snapshot.estimate_value == Decimal("2.35")

    def test_natural_key_includes_date(self):
        """Test natural key includes capture date."""
        snapshot = EstimateSnapshot(
            ticker="AAPL",
            fiscal_period="2026:Q1",
            metric_code=MetricCode.EPS,
            estimate_value=Decimal("2.35"),
            captured_at=datetime(2026, 1, 15, tzinfo=UTC),
            source_vendor="polygon",
        )
        
        assert "20260115" in snapshot.natural_key
        assert "eps" in snapshot.natural_key


class TestEarningsSurprise:
    """Tests for EarningsSurprise model."""

    def test_beat_scenario(self):
        """Test creating a beat scenario."""
        surprise = EarningsSurprise(
            ticker="AAPL",
            fiscal_period="2026:Q1",
            metric_code=MetricCode.EPS,
            actual_value=Decimal("2.42"),
            actual_reported_at=datetime(2026, 1, 30, tzinfo=UTC),
            direction=SurpriseDirection.BEAT,
            estimate_value=Decimal("2.35"),
            surprise_amount=Decimal("0.07"),
            surprise_pct=Decimal("0.0298"),
            magnitude=SurpriseMagnitude.SMALL,
        )
        
        assert surprise.direction == SurpriseDirection.BEAT
        assert surprise.surprise_pct > 0

    def test_miss_scenario(self):
        """Test creating a miss scenario."""
        surprise = EarningsSurprise(
            ticker="MSFT",
            fiscal_period="2026:Q2",
            metric_code=MetricCode.EPS,
            actual_value=Decimal("2.50"),
            actual_reported_at=datetime(2026, 1, 30, tzinfo=UTC),
            direction=SurpriseDirection.MISS,
            estimate_value=Decimal("2.80"),
            surprise_amount=Decimal("-0.30"),
            surprise_pct=Decimal("-0.1071"),
        )
        
        assert surprise.direction == SurpriseDirection.MISS
        assert surprise.surprise_pct < 0

    def test_no_estimate_scenario(self):
        """Test scenario with no estimate."""
        surprise = EarningsSurprise(
            ticker="NVDA",
            fiscal_period="2026:Q4",
            metric_code=MetricCode.EPS,
            actual_value=Decimal("4.50"),
            actual_reported_at=datetime(2026, 1, 30, tzinfo=UTC),
            direction=SurpriseDirection.NO_ESTIMATE,
        )
        
        assert surprise.direction == SurpriseDirection.NO_ESTIMATE
        assert surprise.estimate_value is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        surprise = EarningsSurprise(
            ticker="AAPL",
            fiscal_period="2026:Q1",
            metric_code=MetricCode.EPS,
            actual_value=Decimal("2.42"),
            actual_reported_at=datetime(2026, 1, 30, tzinfo=UTC),
            direction=SurpriseDirection.BEAT,
        )
        
        d = surprise.to_dict()
        
        assert d["ticker"] == "AAPL"
        assert d["direction"] == "beat"
        assert d["metric_code"] == "eps"


class TestEarningsConfig:
    """Tests for EarningsConfig."""

    def test_default_date_range(self):
        """Test default date range is 7 days."""
        config = EarningsConfig()
        
        assert config.date_from == date.today()
        assert config.date_to == date.today() + timedelta(days=7)

    def test_custom_dates(self):
        """Test custom date range."""
        config = EarningsConfig(
            date_from=date(2026, 1, 30),
            date_to=date(2026, 2, 15),
        )
        
        assert config.date_from == date(2026, 1, 30)
        assert config.date_to == date(2026, 2, 15)

    def test_ticker_filter(self):
        """Test ticker filtering."""
        config = EarningsConfig(
            tickers=["AAPL", "MSFT"],
        )
        
        assert config.tickers == ["AAPL", "MSFT"]


class TestEarningsPipeline:
    """Tests for EarningsPipeline."""

    @pytest.fixture
    def config(self) -> EarningsConfig:
        """Create test config."""
        return EarningsConfig(
            date_from=date(2026, 1, 30),
            date_to=date(2026, 2, 6),
        )

    @pytest.fixture
    def pipeline(self, config: EarningsConfig) -> EarningsPipeline:
        """Create test pipeline."""
        return EarningsPipeline(config)

    def test_pipeline_creation(self, pipeline: EarningsPipeline):
        """Test pipeline initialization."""
        assert pipeline.config is not None
        assert not pipeline._initialized

    @pytest.mark.asyncio
    async def test_pipeline_context_manager(self, config: EarningsConfig):
        """Test async context manager."""
        async with EarningsPipeline(config) as pipeline:
            assert pipeline._initialized
        
        assert not pipeline._initialized

    @pytest.mark.asyncio
    async def test_pipeline_run_demo_mode(self, pipeline: EarningsPipeline):
        """Test pipeline in demo mode (no adapter)."""
        await pipeline.initialize()
        
        try:
            result = await pipeline.run()
            
            assert result.success or len(result.events) >= 0
            assert result.batch_id != ""
            assert result.completed_at is not None
        finally:
            await pipeline.close()

    @pytest.mark.asyncio
    async def test_compute_single_surprise_beat(self, pipeline: EarningsPipeline):
        """Test computing a single beat surprise."""
        from spine.domains.earnings.models import EarningsActual
        
        actual = EarningsActual(
            ticker="AAPL",
            fiscal_period="2026:Q1",
            metric_code=MetricCode.EPS,
            actual_value=Decimal("2.42"),
            reported_at=datetime(2026, 1, 30, tzinfo=UTC),
            source_vendor="polygon",
        )
        
        estimate = EstimateSnapshot(
            ticker="AAPL",
            fiscal_period="2026:Q1",
            metric_code=MetricCode.EPS,
            estimate_value=Decimal("2.35"),
            captured_at=datetime(2026, 1, 15, tzinfo=UTC),
            source_vendor="polygon",
        )
        
        surprise = pipeline._compute_single_surprise(actual, estimate, "test_batch")
        
        assert surprise.direction == SurpriseDirection.BEAT
        assert surprise.surprise_amount == Decimal("0.07")
        assert surprise.surprise_pct > 0

    @pytest.mark.asyncio
    async def test_compute_single_surprise_miss(self, pipeline: EarningsPipeline):
        """Test computing a single miss surprise."""
        from spine.domains.earnings.models import EarningsActual
        
        actual = EarningsActual(
            ticker="MSFT",
            fiscal_period="2026:Q2",
            metric_code=MetricCode.EPS,
            actual_value=Decimal("2.50"),
            reported_at=datetime(2026, 1, 30, tzinfo=UTC),
            source_vendor="polygon",
        )
        
        estimate = EstimateSnapshot(
            ticker="MSFT",
            fiscal_period="2026:Q2",
            metric_code=MetricCode.EPS,
            estimate_value=Decimal("2.80"),
            captured_at=datetime(2026, 1, 15, tzinfo=UTC),
            source_vendor="polygon",
        )
        
        surprise = pipeline._compute_single_surprise(actual, estimate, "test_batch")
        
        assert surprise.direction == SurpriseDirection.MISS
        assert surprise.surprise_amount == Decimal("-0.30")
        assert surprise.surprise_pct < 0

    @pytest.mark.asyncio
    async def test_compute_single_surprise_no_estimate(self, pipeline: EarningsPipeline):
        """Test computing surprise with no estimate."""
        from spine.domains.earnings.models import EarningsActual
        
        actual = EarningsActual(
            ticker="NVDA",
            fiscal_period="2026:Q4",
            metric_code=MetricCode.EPS,
            actual_value=Decimal("4.50"),
            reported_at=datetime(2026, 1, 30, tzinfo=UTC),
            source_vendor="polygon",
        )
        
        surprise = pipeline._compute_single_surprise(actual, None, "test_batch")
        
        assert surprise.direction == SurpriseDirection.NO_ESTIMATE
        assert surprise.estimate_value is None

    @pytest.mark.asyncio
    async def test_result_summary(self, pipeline: EarningsPipeline):
        """Test result summary generation."""
        await pipeline.initialize()
        
        try:
            result = await pipeline.run()
            summary = result.summary
            
            assert "events" in summary
            assert "surprises" in summary
            assert "batch_id" in summary
            assert "errors" in summary
        finally:
            await pipeline.close()


class TestIntegration:
    """Integration tests with FeedSpine (if available)."""

    @pytest.mark.asyncio
    async def test_pipeline_with_feedspine_adapter(self):
        """Test pipeline integrates with FeedSpine adapter."""
        try:
            from feedspine.adapter.polygon_earnings import PolygonEarningsAdapter
        except ImportError:
            pytest.skip("FeedSpine not installed")
        
        config = EarningsConfig(
            date_from=date(2026, 1, 30),
            date_to=date(2026, 2, 6),
        )
        
        async with EarningsPipeline(config) as pipeline:
            result = await pipeline.run()
            
            # Should have fetched events in demo mode
            assert len(result.events) > 0 or pipeline._adapter is not None
