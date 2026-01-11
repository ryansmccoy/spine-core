# tests/domains/otc/test_otc.py

"""Tests for OTC domain - parser, normalizer, calculations, and quality checks."""

import pytest
from pathlib import Path
from datetime import date

from market_spine.domains.otc.models import RawRecord, Tier, VenueVolume
from market_spine.domains.otc.parser import parse_finra_file, parse_finra_content
from market_spine.domains.otc.normalizer import normalize_records
from market_spine.domains.otc.calculations import compute_symbol_summaries, compute_venue_shares
from market_spine.domains.otc.quality import OTCQualityChecker, Severity, QualityResult


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample FINRA CSV file."""
    content = """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-12
NMS Tier 1|AAPL|Apple Inc.|VENUE B|VENB|500000|2500|2025-12-12
NMS Tier 1|MSFT|Microsoft|VENUE A|VENA|800000|4000|2025-12-12"""
    file = tmp_path / "test.csv"
    file.write_text(content)
    return file


@pytest.fixture
def sample_content():
    """Sample FINRA content as string."""
    return """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-12
NMS Tier 2|GOOG|Alphabet Inc.|VENUE C|VENC|200000|1000|2025-12-12"""


class TestParser:
    """Tests for FINRA file parser."""

    def test_parse_file(self, sample_csv):
        """Test parsing a FINRA file from disk."""
        records = list(parse_finra_file(sample_csv))

        assert len(records) == 3
        assert records[0].symbol == "AAPL"
        assert records[0].share_volume == 1000000
        assert records[0].trade_count == 5000
        assert records[0].tier == "NMS Tier 1"
        assert records[0].week_ending == date(2025, 12, 12)

    def test_parse_file_generates_hash(self, sample_csv):
        """Test that parsing generates record hashes."""
        records = list(parse_finra_file(sample_csv))

        for record in records:
            assert record.record_hash != ""
            assert len(record.record_hash) == 32

    def test_parse_content(self, sample_content):
        """Test parsing FINRA data from string content."""
        records = list(parse_finra_content(sample_content))

        assert len(records) == 2
        assert records[0].symbol == "AAPL"
        assert records[1].symbol == "GOOG"
        assert records[1].tier == "NMS Tier 2"

    def test_parse_skips_malformed_rows(self, tmp_path):
        """Test that malformed rows are skipped."""
        content = """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-12
BAD|ROW|MISSING|COLUMNS
NMS Tier 1|MSFT|Microsoft|VENUE A|VENA|800000|4000|2025-12-12"""
        file = tmp_path / "bad.csv"
        file.write_text(content)

        records = list(parse_finra_file(file))
        assert len(records) == 2  # Bad row skipped


class TestNormalizer:
    """Tests for record normalization."""

    def test_normalize(self, sample_csv):
        """Test normalizing raw records."""
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)

        assert result.accepted == 3
        assert result.rejected == 0
        assert result.processed == 3
        assert len(result.records) == 3

    def test_normalize_parses_tier(self, sample_csv):
        """Test that tier strings are converted to enums."""
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)

        assert result.records[0].tier == Tier.NMS_TIER_1

    def test_normalize_calculates_avg_trade_size(self, sample_csv):
        """Test that average trade size is calculated."""
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)

        # AAPL at VENA: 1,000,000 shares / 5,000 trades = 200
        aapl = result.records[0]
        assert aapl.avg_trade_size == 200

    def test_normalize_rejects_negative_values(self):
        """Test that records with negative values are rejected."""
        records = [
            RawRecord(
                tier="NMS Tier 1",
                symbol="BAD",
                issue_name="Bad Stock",
                venue_name="Venue",
                mpid="VENX",
                share_volume=-1000,  # Negative
                trade_count=100,
                week_ending=date(2025, 12, 12),
            )
        ]

        result = normalize_records(records)

        assert result.accepted == 0
        assert result.rejected == 1

    def test_normalize_rejects_invalid_tier(self):
        """Test that records with invalid tier are rejected."""
        records = [
            RawRecord(
                tier="Invalid Tier",  # Not a valid tier
                symbol="BAD",
                issue_name="Bad Stock",
                venue_name="Venue",
                mpid="VENX",
                share_volume=1000,
                trade_count=100,
                week_ending=date(2025, 12, 12),
            )
        ]

        result = normalize_records(records)

        assert result.accepted == 0
        assert result.rejected == 1


class TestCalculations:
    """Tests for summary calculations."""

    def test_symbol_summary(self, sample_csv):
        """Test computing symbol summaries."""
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)

        summaries = compute_symbol_summaries(result.records)

        # Should have 2 symbols: AAPL and MSFT
        assert len(summaries) == 2

        aapl = next(s for s in summaries if s.symbol == "AAPL")
        assert aapl.total_volume == 1500000  # 1M + 500K
        assert aapl.total_trades == 7500  # 5000 + 2500
        assert aapl.venue_count == 2

        msft = next(s for s in summaries if s.symbol == "MSFT")
        assert msft.total_volume == 800000
        assert msft.venue_count == 1

    def test_symbol_summary_calculates_avg_size(self, sample_csv):
        """Test that symbol summary calculates average trade size."""
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)

        summaries = compute_symbol_summaries(result.records)

        aapl = next(s for s in summaries if s.symbol == "AAPL")
        # 1,500,000 / 7,500 = 200
        assert aapl.avg_trade_size == 200

    def test_venue_shares(self, sample_csv):
        """Test computing venue market shares."""
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)

        venues = compute_venue_shares(result.records)

        # Should have 2 venues: VENA and VENB
        assert len(venues) == 2

        vena = next(v for v in venues if v.mpid == "VENA")
        assert vena.total_volume == 1800000  # 1M + 800K
        assert vena.symbol_count == 2  # AAPL and MSFT

        venb = next(v for v in venues if v.mpid == "VENB")
        assert venb.total_volume == 500000
        assert venb.symbol_count == 1  # AAPL only

    def test_venue_shares_calculates_percentage(self, sample_csv):
        """Test that market share percentage is calculated."""
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)

        venues = compute_venue_shares(result.records)

        # Total: 2,300,000
        # VENA: 1,800,000 = 78.26%
        # VENB: 500,000 = 21.74%
        vena = next(v for v in venues if v.mpid == "VENA")
        venb = next(v for v in venues if v.mpid == "VENB")

        assert float(vena.market_share_pct) == pytest.approx(78.26, rel=0.01)
        assert float(venb.market_share_pct) == pytest.approx(21.74, rel=0.01)

    def test_venue_shares_assigns_rank(self, sample_csv):
        """Test that venues are ranked by volume."""
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)

        venues = compute_venue_shares(result.records)

        vena = next(v for v in venues if v.mpid == "VENA")
        venb = next(v for v in venues if v.mpid == "VENB")

        assert vena.rank == 1  # Higher volume
        assert venb.rank == 2


class TestRawRecord:
    """Tests for RawRecord model."""

    def test_hash_is_deterministic(self):
        """Test that the same inputs produce the same hash."""
        record1 = RawRecord(
            tier="NMS Tier 1",
            symbol="AAPL",
            issue_name="Apple Inc.",
            venue_name="Venue A",
            mpid="VENA",
            share_volume=1000,
            trade_count=100,
            week_ending=date(2025, 12, 12),
        )
        record2 = RawRecord(
            tier="NMS Tier 1",
            symbol="AAPL",
            issue_name="Apple Inc.",
            venue_name="Venue A",
            mpid="VENA",
            share_volume=1000,
            trade_count=100,
            week_ending=date(2025, 12, 12),
        )

        assert record1.record_hash == record2.record_hash

    def test_hash_differs_for_different_records(self):
        """Test that different records produce different hashes."""
        record1 = RawRecord(
            tier="NMS Tier 1",
            symbol="AAPL",
            issue_name="Apple Inc.",
            venue_name="Venue A",
            mpid="VENA",
            share_volume=1000,
            trade_count=100,
            week_ending=date(2025, 12, 12),
        )
        record2 = RawRecord(
            tier="NMS Tier 1",
            symbol="MSFT",  # Different symbol
            issue_name="Microsoft",
            venue_name="Venue A",
            mpid="VENA",
            share_volume=1000,
            trade_count=100,
            week_ending=date(2025, 12, 12),
        )

        assert record1.record_hash != record2.record_hash


class TestTierEnum:
    """Tests for Tier enum."""

    def test_from_finra_nms_tier_1(self):
        """Test parsing NMS Tier 1."""
        tier = Tier.from_finra("NMS Tier 1")
        assert tier == Tier.NMS_TIER_1

    def test_from_finra_nms_tier_2(self):
        """Test parsing NMS Tier 2."""
        tier = Tier.from_finra("NMS Tier 2")
        assert tier == Tier.NMS_TIER_2

    def test_from_finra_otc(self):
        """Test parsing OTC tier."""
        tier = Tier.from_finra("OTC")
        assert tier == Tier.OTC

    def test_from_finra_invalid(self):
        """Test that invalid tier raises ValueError."""
        with pytest.raises(ValueError):
            Tier.from_finra("Invalid Tier")


class TestQualityChecker:
    """Tests for OTC quality checker."""

    @pytest.fixture
    def mock_repo(self):
        """Mock repository for testing."""

        class MockRepo:
            def __init__(self):
                self.stats = {"venue_count": 10, "symbol_count": 100, "total_volume": 1000000}

            def get_week_stats(self, week):
                return self.stats

        return MockRepo()

    def test_good_week(self, mock_repo):
        """Test quality check for a week with good data."""
        checker = OTCQualityChecker(mock_repo)
        result = checker.check_week(date(2025, 12, 12))

        assert result.grade == "A"
        assert result.score == 100.0
        assert len(result.issues) == 0

    def test_no_data_week(self):
        """Test quality check for a week with no data."""

        class EmptyRepo:
            def get_week_stats(self, week):
                return {"venue_count": 0, "symbol_count": 0, "total_volume": 0}

        checker = OTCQualityChecker(EmptyRepo())
        result = checker.check_week(date(2025, 12, 12))

        assert result.grade == "F"
        assert result.score == 0.0
        assert len(result.issues) == 1
        assert result.issues[0].code == "NO_DATA"
        assert result.issues[0].severity == Severity.ERROR

    def test_venue_drop_warning(self):
        """Test quality check detects venue count drop."""
        from datetime import timedelta

        class DroppingRepo:
            def get_week_stats(self, week):
                if week == date(2025, 12, 12):
                    return {"venue_count": 5, "symbol_count": 100, "total_volume": 1000000}
                else:
                    # Prior week had 10 venues
                    return {"venue_count": 10, "symbol_count": 100, "total_volume": 1000000}

        checker = OTCQualityChecker(DroppingRepo())
        result = checker.check_week(date(2025, 12, 12))

        # Should have warning for 50% venue drop
        venue_issue = next((i for i in result.issues if i.code == "VENUE_DROP"), None)
        assert venue_issue is not None
        assert venue_issue.severity == Severity.WARNING

    def test_volume_swing_warning(self):
        """Test quality check detects large volume swing."""

        class SwingingRepo:
            def get_week_stats(self, week):
                if week == date(2025, 12, 12):
                    return {"venue_count": 10, "symbol_count": 100, "total_volume": 400000}
                else:
                    # Prior week had much higher volume (60% drop)
                    return {"venue_count": 10, "symbol_count": 100, "total_volume": 1000000}

        checker = OTCQualityChecker(SwingingRepo())
        result = checker.check_week(date(2025, 12, 12))

        # Should have warning for 60% volume swing
        volume_issue = next((i for i in result.issues if i.code == "VOLUME_SWING"), None)
        assert volume_issue is not None
        assert volume_issue.severity == Severity.WARNING
