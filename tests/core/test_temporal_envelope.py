"""
Tests for spine.core.temporal_envelope module.

Tests cover:
- TemporalEnvelope creation and defaults
- Query helpers (known_as_of, effective_as_of, published_as_of)
- timestamps_dict serialisation
- now_envelope factory
- BiTemporalRecord creation and queries
- BiTemporalRecord.supersede correction workflow
"""

import pytest
from datetime import UTC, datetime, timedelta

from spine.core.temporal_envelope import BiTemporalRecord, TemporalEnvelope


# =============================================================================
# Helpers
# =============================================================================


def _ts(offset_hours: int = 0) -> datetime:
    """Create a UTC datetime offset from a fixed base time."""
    base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    return base + timedelta(hours=offset_hours)


# =============================================================================
# TemporalEnvelope
# =============================================================================


class TestTemporalEnvelopeCreation:
    """Tests for TemporalEnvelope creation and field defaults."""

    def test_basic_creation(self):
        """All four timestamps explicitly provided."""
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(1),
            ingest_time=_ts(2),
            payload={"ticker": "AAPL"},
            effective_time=_ts(3),
        )
        assert env.event_time == _ts(0)
        assert env.publish_time == _ts(1)
        assert env.ingest_time == _ts(2)
        assert env.effective_time == _ts(3)
        assert env.payload == {"ticker": "AAPL"}

    def test_effective_time_defaults_to_event_time(self):
        """effective_time should default to event_time when omitted."""
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(1),
            ingest_time=_ts(2),
            payload="data",
        )
        assert env.effective_time == env.event_time

    def test_frozen(self):
        """TemporalEnvelope should be immutable (frozen dataclass)."""
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(0),
            ingest_time=_ts(0),
            payload=None,
        )
        with pytest.raises(AttributeError):
            env.payload = "changed"  # type: ignore[misc]

    def test_envelope_id_optional(self):
        """envelope_id is optional and defaults to None."""
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(0),
            ingest_time=_ts(0),
            payload="x",
        )
        assert env.envelope_id is None

    def test_envelope_id_set(self):
        """envelope_id can be explicitly set."""
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(0),
            ingest_time=_ts(0),
            payload="x",
            envelope_id="env-001",
        )
        assert env.envelope_id == "env-001"


class TestTemporalEnvelopeQueries:
    """Tests for TemporalEnvelope query helpers."""

    def test_known_as_of_before_ingest(self):
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(1),
            ingest_time=_ts(2),
            payload="x",
        )
        assert env.known_as_of(_ts(1)) is False

    def test_known_as_of_at_ingest(self):
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(1),
            ingest_time=_ts(2),
            payload="x",
        )
        assert env.known_as_of(_ts(2)) is True

    def test_known_as_of_after_ingest(self):
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(1),
            ingest_time=_ts(2),
            payload="x",
        )
        assert env.known_as_of(_ts(3)) is True

    def test_effective_as_of(self):
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(1),
            ingest_time=_ts(2),
            payload="x",
            effective_time=_ts(5),
        )
        assert env.effective_as_of(_ts(4)) is False
        assert env.effective_as_of(_ts(5)) is True
        assert env.effective_as_of(_ts(6)) is True

    def test_published_as_of(self):
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(3),
            ingest_time=_ts(4),
            payload="x",
        )
        assert env.published_as_of(_ts(2)) is False
        assert env.published_as_of(_ts(3)) is True


class TestTemporalEnvelopeSerialization:
    """Tests for timestamps_dict and factories."""

    def test_timestamps_dict(self):
        env = TemporalEnvelope(
            event_time=_ts(0),
            publish_time=_ts(1),
            ingest_time=_ts(2),
            payload="x",
            effective_time=_ts(3),
        )
        d = env.timestamps_dict()
        assert d["event_time"] == _ts(0).isoformat()
        assert d["publish_time"] == _ts(1).isoformat()
        assert d["ingest_time"] == _ts(2).isoformat()
        assert d["effective_time"] == _ts(3).isoformat()

    def test_now_envelope(self):
        env = TemporalEnvelope.now_envelope({"msg": "hello"})
        assert env.payload == {"msg": "hello"}
        assert env.effective_time == env.event_time
        # All timestamps should be recent (within 2 seconds of now)
        now = datetime.now(UTC)
        assert (now - env.ingest_time).total_seconds() < 2
        assert (now - env.publish_time).total_seconds() < 2

    def test_now_envelope_with_event_time(self):
        past = _ts(-100)
        env = TemporalEnvelope.now_envelope(42, event_time=past)
        assert env.event_time == past
        assert env.effective_time == past
        # But ingest/publish should be "now"
        now = datetime.now(UTC)
        assert (now - env.ingest_time).total_seconds() < 2


# =============================================================================
# BiTemporalRecord
# =============================================================================


class TestBiTemporalRecordCreation:
    """Tests for BiTemporalRecord creation and properties."""

    def test_basic_creation(self):
        rec = BiTemporalRecord(
            record_id="r1",
            entity_key="AAPL",
            valid_from=_ts(0),
            valid_to=None,
            system_from=_ts(0),
            system_to=None,
        )
        assert rec.is_current is True
        assert rec.payload == {}
        assert rec.provenance == ""

    def test_is_current_false_when_system_closed(self):
        rec = BiTemporalRecord(
            record_id="r1",
            entity_key="AAPL",
            valid_from=_ts(0),
            valid_to=None,
            system_from=_ts(0),
            system_to=_ts(5),
        )
        assert rec.is_current is False

    def test_is_current_false_when_valid_closed(self):
        rec = BiTemporalRecord(
            record_id="r1",
            entity_key="AAPL",
            valid_from=_ts(0),
            valid_to=_ts(10),
            system_from=_ts(0),
            system_to=None,
        )
        assert rec.is_current is False


class TestBiTemporalRecordQueries:
    """Tests for valid_at, known_at, and as_of queries."""

    def setup_method(self):
        self.rec = BiTemporalRecord(
            record_id="r1",
            entity_key="AAPL",
            valid_from=_ts(0),
            valid_to=_ts(10),
            system_from=_ts(2),
            system_to=_ts(8),
            payload={"price": 195.0},
        )

    def test_valid_at_before_range(self):
        assert self.rec.valid_at(_ts(-1)) is False

    def test_valid_at_in_range(self):
        assert self.rec.valid_at(_ts(5)) is True

    def test_valid_at_at_start(self):
        assert self.rec.valid_at(_ts(0)) is True

    def test_valid_at_at_end(self):
        """valid_to is exclusive."""
        assert self.rec.valid_at(_ts(10)) is False

    def test_known_at_before_system(self):
        assert self.rec.known_at(_ts(1)) is False

    def test_known_at_in_system(self):
        assert self.rec.known_at(_ts(5)) is True

    def test_known_at_after_superseded(self):
        assert self.rec.known_at(_ts(8)) is False

    def test_as_of_both_in_range(self):
        assert self.rec.as_of(valid_when=_ts(5), system_when=_ts(5)) is True

    def test_as_of_valid_out_of_range(self):
        assert self.rec.as_of(valid_when=_ts(11), system_when=_ts(5)) is False

    def test_as_of_system_out_of_range(self):
        assert self.rec.as_of(valid_when=_ts(5), system_when=_ts(9)) is False

    def test_valid_at_open_ended(self):
        """Record with valid_to=None is valid indefinitely."""
        rec = BiTemporalRecord(
            record_id="r2",
            entity_key="AAPL",
            valid_from=_ts(0),
            valid_to=None,
            system_from=_ts(0),
            system_to=None,
        )
        assert rec.valid_at(_ts(1000)) is True


class TestBiTemporalRecordSupersede:
    """Tests for the supersede correction workflow."""

    def test_supersede_closes_old_and_creates_new(self):
        original = BiTemporalRecord(
            record_id="r1",
            entity_key="AAPL",
            valid_from=_ts(0),
            valid_to=None,
            system_from=_ts(0),
            system_to=None,
            payload={"price": 195.0},
            provenance="polygon",
        )
        fix_time = _ts(10)
        closed, new = original.supersede(
            new_record_id="r2",
            new_payload={"price": 196.0},
            correction_time=fix_time,
            provenance="manual_correction",
        )
        # Old record should be closed
        assert closed.record_id == "r1"
        assert closed.system_to == fix_time
        assert closed.payload == {"price": 195.0}
        assert closed.provenance == "polygon"

        # New record should be current
        assert new.record_id == "r2"
        assert new.entity_key == "AAPL"
        assert new.system_from == fix_time
        assert new.system_to is None
        assert new.valid_from == _ts(0)  # inherited
        assert new.valid_to is None
        assert new.payload == {"price": 196.0}
        assert new.provenance == "manual_correction"

    def test_supersede_preserves_valid_range(self):
        """By default, valid_from/valid_to are inherited."""
        original = BiTemporalRecord(
            record_id="r1",
            entity_key="X",
            valid_from=_ts(0),
            valid_to=_ts(5),
            system_from=_ts(0),
            system_to=None,
            payload={"v": 1},
        )
        _, new = original.supersede(
            new_record_id="r2",
            new_payload={"v": 2},
        )
        assert new.valid_from == _ts(0)
        assert new.valid_to == _ts(5)

    def test_supersede_can_override_valid_range(self):
        original = BiTemporalRecord(
            record_id="r1",
            entity_key="X",
            valid_from=_ts(0),
            valid_to=_ts(5),
            system_from=_ts(0),
            system_to=None,
            payload={"v": 1},
        )
        _, new = original.supersede(
            new_record_id="r3",
            new_payload={"v": 3},
            new_valid_from=_ts(1),
            new_valid_to=_ts(6),
        )
        assert new.valid_from == _ts(1)
        assert new.valid_to == _ts(6)
