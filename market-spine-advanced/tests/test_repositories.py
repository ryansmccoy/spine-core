"""Tests for repository layer."""

import json
from datetime import date
from decimal import Decimal

import pytest

from market_spine.repositories.executions import ExecutionRepository, ExecutionEventRepository
from market_spine.repositories.otc import OTCRepository


class TestExecutionRepository:
    """Tests for ExecutionRepository."""

    def test_create_execution(self, db_conn, clean_tables):
        """Test creating an execution."""
        exec_id = ExecutionRepository.create(
            pipeline_name="test.pipeline",
            params={"key": "value"},
            logical_key="test:key",
        )

        assert exec_id is not None
        assert len(exec_id) == 26  # ULID length

    def test_get_execution(self, db_conn, clean_tables):
        """Test getting an execution."""
        exec_id = ExecutionRepository.create("test.pipeline", {"foo": "bar"})

        execution = ExecutionRepository.get(exec_id)

        assert execution is not None
        assert execution["id"] == exec_id
        assert execution["pipeline_name"] == "test.pipeline"
        assert execution["params"] == {"foo": "bar"}
        assert execution["status"] == "pending"

    def test_update_status(self, db_conn, clean_tables):
        """Test updating execution status."""
        exec_id = ExecutionRepository.create("test.pipeline")

        ExecutionRepository.update_status(exec_id, "running")
        execution = ExecutionRepository.get(exec_id)
        assert execution["status"] == "running"
        assert execution["started_at"] is not None

        ExecutionRepository.update_status(exec_id, "completed")
        execution = ExecutionRepository.get(exec_id)
        assert execution["status"] == "completed"
        assert execution["completed_at"] is not None

    def test_update_status_with_error(self, db_conn, clean_tables):
        """Test updating status with error message."""
        exec_id = ExecutionRepository.create("test.pipeline")

        ExecutionRepository.update_status(exec_id, "failed", "Something went wrong")
        execution = ExecutionRepository.get(exec_id)

        assert execution["status"] == "failed"
        assert execution["error_message"] == "Something went wrong"

    def test_list_executions(self, db_conn, clean_tables):
        """Test listing executions."""
        ExecutionRepository.create("pipeline.a")
        ExecutionRepository.create("pipeline.b")
        ExecutionRepository.create("pipeline.a")

        all_execs = ExecutionRepository.list_executions()
        assert len(all_execs) == 3

        filtered = ExecutionRepository.list_executions(pipeline_name="pipeline.a")
        assert len(filtered) == 2

    def test_logical_key_conflict(self, db_conn, clean_tables):
        """Test logical key conflict detection."""
        ExecutionRepository.create("test.pipeline", logical_key="unique:key")

        conflict = ExecutionRepository.check_logical_key_conflict("unique:key")
        assert conflict is not None

        no_conflict = ExecutionRepository.check_logical_key_conflict("other:key")
        assert no_conflict is None


class TestExecutionEventRepository:
    """Tests for ExecutionEventRepository."""

    def test_emit_event(self, db_conn, clean_tables):
        """Test emitting an event."""
        exec_id = ExecutionRepository.create("test.pipeline")

        event_id = ExecutionEventRepository.emit(
            exec_id,
            "test.event",
            {"data": "value"},
        )

        assert event_id is not None

    def test_get_events(self, db_conn, clean_tables):
        """Test getting events for execution."""
        exec_id = ExecutionRepository.create("test.pipeline")

        ExecutionEventRepository.emit(exec_id, "event.a", {"step": 1})
        ExecutionEventRepository.emit(exec_id, "event.b", {"step": 2})

        events = ExecutionEventRepository.get_events(exec_id)

        assert len(events) == 2
        assert events[0]["event_type"] == "event.a"
        assert events[1]["event_type"] == "event.b"

    def test_event_deduplication(self, db_conn, clean_tables):
        """Test event idempotency key deduplication."""
        exec_id = ExecutionRepository.create("test.pipeline")

        event1 = ExecutionEventRepository.emit(exec_id, "test.event", idempotency_key="unique-key")
        event2 = ExecutionEventRepository.emit(exec_id, "test.event", idempotency_key="unique-key")

        assert event1 is not None
        assert event2 is None  # Deduplicated

        events = ExecutionEventRepository.get_events(exec_id)
        assert len(events) == 1


class TestOTCRepository:
    """Tests for OTCRepository."""

    def test_upsert_raw_trade(self, db_conn, clean_tables):
        """Test upserting raw trade."""
        payload = {"symbol": "AAPL", "price": 185.50}

        record_hash = OTCRepository.upsert_raw_trade(payload, source="test")

        assert record_hash is not None
        assert len(record_hash) == 64  # SHA256 hex

    def test_bulk_upsert_raw_trades(self, db_conn, clean_tables, sample_raw_trades):
        """Test bulk upserting raw trades."""
        count = OTCRepository.bulk_upsert_raw_trades(sample_raw_trades, source="test")

        assert count == 2

        unprocessed = OTCRepository.get_unprocessed_raw_trades()
        assert len(unprocessed) == 2

    def test_mark_raw_trades_processed(self, db_conn, clean_tables, sample_raw_trades):
        """Test marking raw trades as processed."""
        OTCRepository.bulk_upsert_raw_trades(sample_raw_trades, source="test")

        unprocessed = OTCRepository.get_unprocessed_raw_trades()
        hashes = [r["record_hash"] for r in unprocessed]

        OTCRepository.mark_raw_trades_processed(hashes)

        still_unprocessed = OTCRepository.get_unprocessed_raw_trades()
        assert len(still_unprocessed) == 0

    def test_bulk_upsert_trades(self, db_conn, clean_tables, sample_trades):
        """Test bulk upserting normalized trades."""
        inserted, updated = OTCRepository.bulk_upsert_trades(sample_trades)

        assert inserted == 3
        assert updated == 0

        # Upsert again should update
        inserted2, updated2 = OTCRepository.bulk_upsert_trades(sample_trades)
        assert inserted2 == 0
        assert updated2 == 3

    def test_get_trades(self, db_conn, clean_tables, sample_trades):
        """Test getting trades with filters."""
        OTCRepository.bulk_upsert_trades(sample_trades)

        all_trades = OTCRepository.get_trades()
        assert len(all_trades) == 3

        aapl_trades = OTCRepository.get_trades(symbol="AAPL")
        assert len(aapl_trades) == 2

        date_trades = OTCRepository.get_trades(start_date=date(2024, 1, 15))
        assert len(date_trades) == 3

    def test_get_symbols(self, db_conn, clean_tables, sample_trades):
        """Test getting unique symbols."""
        OTCRepository.bulk_upsert_trades(sample_trades)

        symbols = OTCRepository.get_symbols()

        assert set(symbols) == {"AAPL", "GOOGL"}

    def test_upsert_daily_metrics(self, db_conn, clean_tables):
        """Test upserting daily metrics."""
        inserted = OTCRepository.upsert_daily_metrics(
            symbol="AAPL",
            metric_date=date(2024, 1, 15),
            vwap=Decimal("185.75"),
            total_volume=Decimal("1500"),
            total_notional=Decimal("278625"),
            trade_count=2,
            high_price=Decimal("186.00"),
            low_price=Decimal("185.50"),
        )

        assert inserted is True

        # Update same day
        updated = OTCRepository.upsert_daily_metrics(
            symbol="AAPL",
            metric_date=date(2024, 1, 15),
            vwap=Decimal("185.80"),
            total_volume=Decimal("1600"),
            total_notional=Decimal("297280"),
            trade_count=3,
            high_price=Decimal("186.50"),
            low_price=Decimal("185.00"),
        )

        assert updated is False  # Was update, not insert

    def test_get_daily_metrics(self, db_conn, clean_tables):
        """Test getting daily metrics."""
        OTCRepository.upsert_daily_metrics(
            symbol="AAPL",
            metric_date=date(2024, 1, 15),
            vwap=Decimal("185.75"),
            total_volume=Decimal("1500"),
            total_notional=Decimal("278625"),
            trade_count=2,
            high_price=Decimal("186.00"),
            low_price=Decimal("185.50"),
        )

        metrics = OTCRepository.get_daily_metrics(symbol="AAPL")

        assert len(metrics) == 1
        assert metrics[0]["symbol"] == "AAPL"
        assert metrics[0]["vwap"] == Decimal("185.75")
