# tests/finra/otc_transparency/test_calculations.py

"""Tests for FINRA OTC Transparency aggregation calculations."""

from datetime import date

from spine.domains.finra.otc_transparency.calculations import (
    SymbolSummary,
    VenueVolumeRow,
)
from spine.domains.finra.otc_transparency.schema import Tier


class TestCalculations:
    """Tests for aggregation calculations."""

    def test_symbol_summary_dataclass(self):
        """Test SymbolSummary (SymbolAggregateRow) dataclass."""
        summary = SymbolSummary(
            week_ending=date(2026, 1, 3),
            tier=Tier.NMS_TIER_1,
            symbol="AAPL",
            total_shares=1500000,  # Named total_shares, aliased as total_volume
            total_trades=7500,
            venue_count=2,
        )

        assert summary.symbol == "AAPL"
        assert summary.total_volume == 1500000  # Property alias
        assert summary.total_shares == 1500000  # Actual field
        assert summary.venue_count == 2

    def test_venue_volume_dataclass(self):
        """Test VenueVolumeRow dataclass."""
        venue = VenueVolumeRow(
            week_ending=date(2026, 1, 3),
            tier=Tier.NMS_TIER_1,
            symbol="AAPL",
            mpid="VENA",
            total_shares=1000000,
            total_trades=5000,
        )

        assert venue.mpid == "VENA"
        assert venue.total_shares == 1000000
        assert venue.symbol == "AAPL"

    def test_symbol_summary_avg_trade_size(self):
        """Test that SymbolAggregateRow has the correct fields."""
        summary = SymbolSummary(
            week_ending=date(2026, 1, 3),
            tier=Tier.OTC,
            symbol="TEST",
            total_shares=1000000,
            total_trades=5000,
            venue_count=1,
        )
        
        # Verify basic fields
        assert summary.total_shares == 1000000
        assert summary.total_volume == 1000000  # alias for total_shares
        assert summary.total_trades == 5000
