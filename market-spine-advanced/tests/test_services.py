"""Tests for services layer."""

from datetime import date
from decimal import Decimal

import pytest

from market_spine.services.otc_normalizer import OTCNormalizerService
from market_spine.services.otc_metrics import OTCMetricsService
from market_spine.repositories.otc import OTCRepository


class TestOTCNormalizerService:
    """Tests for OTCNormalizerService."""

    def test_normalize_trade_standard(self):
        """Test normalizing a standard trade."""
        raw = {
            "trade_id": "T001",
            "symbol": "aapl",
            "trade_date": "2024-01-15",
            "price": "185.50",
            "size": "1000",
            "side": "buy",
            "venue": "DARK",
        }

        result = OTCNormalizerService.normalize_trade(raw, source="test")

        assert result is not None
        assert result["trade_id"] == "T001"
        assert result["symbol"] == "AAPL"  # Uppercased
        assert result["trade_date"] == date(2024, 1, 15)
        assert result["price"] == Decimal("185.50")
        assert result["size"] == Decimal("1000")
        assert result["side"] == "buy"
        assert result["notional"] == Decimal("185500")

    def test_normalize_trade_alternate_fields(self):
        """Test normalizing with alternate field names."""
        raw = {
            "tradeId": "T002",
            "ticker": "GOOGL",
            "Date": "2024-01-15",
            "Price": 142.25,
            "quantity": 200,
            "direction": "sell",
            "ATS": "VENUE1",
        }

        result = OTCNormalizerService.normalize_trade(raw, source="test")

        assert result is not None
        assert result["symbol"] == "GOOGL"
        assert result["price"] == Decimal("142.25")
        assert result["size"] == Decimal("200")
        assert result["side"] == "sell"

    def test_normalize_trade_missing_required(self):
        """Test normalization fails with missing required fields."""
        raw = {
            "trade_id": "T003",
            # Missing symbol
            "trade_date": "2024-01-15",
            "price": "100.00",
            "size": "50",
        }

        result = OTCNormalizerService.normalize_trade(raw, source="test")

        assert result is None

    def test_normalize_trade_invalid_price(self):
        """Test normalization fails with invalid price."""
        raw = {
            "symbol": "MSFT",
            "trade_date": "2024-01-15",
            "price": "not_a_number",
            "size": "100",
        }

        result = OTCNormalizerService.normalize_trade(raw, source="test")

        assert result is None

    def test_normalize_trade_generates_id(self):
        """Test trade_id is generated if not provided."""
        raw = {
            "symbol": "TSLA",
            "trade_date": "2024-01-15",
            "price": "225.00",
            "size": "100",
        }

        result = OTCNormalizerService.normalize_trade(raw, source="test")

        assert result is not None
        assert result["trade_id"] is not None
        assert len(result["trade_id"]) == 16  # MD5 hex truncated

    def test_normalize_batch(self):
        """Test batch normalization."""
        raw_trades = [
            {"symbol": "A", "trade_date": "2024-01-15", "price": "10", "size": "100"},
            {"symbol": "B", "trade_date": "invalid", "price": "20", "size": "200"},  # Invalid
            {"symbol": "C", "trade_date": "2024-01-15", "price": "30", "size": "300"},
        ]

        normalized, failed = OTCNormalizerService.normalize_batch(raw_trades)

        assert len(normalized) == 2
        assert len(failed) == 1
        assert failed[0]["symbol"] == "B"

    def test_parse_date_formats(self):
        """Test various date format parsing."""
        service = OTCNormalizerService

        assert service._parse_date("2024-01-15") == date(2024, 1, 15)
        assert service._parse_date("01/15/2024") == date(2024, 1, 15)
        assert service._parse_date("20240115") == date(2024, 1, 15)
        assert service._parse_date("2024-01-15T10:30:00Z") == date(2024, 1, 15)
        assert service._parse_date(None) is None
        assert service._parse_date("garbage") is None

    def test_process_unprocessed(self, db_conn, clean_tables, sample_raw_trades):
        """Test processing unprocessed raw trades."""
        OTCRepository.bulk_upsert_raw_trades(sample_raw_trades, source="test")

        inserted, updated = OTCNormalizerService.process_unprocessed()

        assert inserted == 2

        # Verify raw trades marked as processed
        unprocessed = OTCRepository.get_unprocessed_raw_trades()
        assert len(unprocessed) == 0

        # Verify normalized trades exist
        trades = OTCRepository.get_trades()
        assert len(trades) == 2


class TestOTCMetricsService:
    """Tests for OTCMetricsService."""

    def test_compute_daily_vwap(self, db_conn, clean_tables, sample_trades):
        """Test computing daily VWAP."""
        OTCRepository.bulk_upsert_trades(sample_trades)

        metrics = OTCMetricsService.compute_daily_vwap("AAPL", date(2024, 1, 15))

        assert metrics is not None
        assert metrics["symbol"] == "AAPL"
        assert metrics["trade_count"] == 2
        assert metrics["total_volume"] == Decimal("1500")

        # VWAP = (185.50 * 1000 + 186.00 * 500) / 1500 = 278500 / 1500 = 185.666...
        expected_vwap = Decimal("278500") / Decimal("1500")
        assert abs(metrics["vwap"] - expected_vwap) < Decimal("0.01")

    def test_compute_daily_vwap_no_trades(self, db_conn, clean_tables):
        """Test VWAP returns None when no trades."""
        metrics = OTCMetricsService.compute_daily_vwap("AAPL", date(2024, 1, 15))

        assert metrics is None

    def test_compute_and_persist(self, db_conn, clean_tables, sample_trades):
        """Test computing and persisting daily metrics."""
        OTCRepository.bulk_upsert_trades(sample_trades)

        success = OTCMetricsService.compute_and_persist_daily_metrics("AAPL", date(2024, 1, 15))

        assert success is True

        metrics = OTCRepository.get_daily_metrics(symbol="AAPL")
        assert len(metrics) == 1
        assert metrics[0]["trade_count"] == 2

    def test_compute_all_daily_metrics(self, db_conn, clean_tables, sample_trades):
        """Test computing metrics for all symbols."""
        OTCRepository.bulk_upsert_trades(sample_trades)

        count = OTCMetricsService.compute_all_daily_metrics(date(2024, 1, 15))

        assert count == 2  # AAPL and GOOGL

        metrics = OTCRepository.get_daily_metrics()
        assert len(metrics) == 2

    def test_compute_range_metrics(self, db_conn, clean_tables, sample_trades):
        """Test computing range metrics."""
        OTCRepository.bulk_upsert_trades(sample_trades)

        metrics = OTCMetricsService.compute_range_metrics(
            "AAPL",
            date(2024, 1, 1),
            date(2024, 1, 31),
        )

        assert metrics is not None
        assert metrics["trading_days"] == 1
        assert metrics["trade_count"] == 2
