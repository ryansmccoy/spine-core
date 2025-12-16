"""
Tests for spine.core.watermarks module.

Tests cover:
- Watermark dataclass creation
- WatermarkStore in-memory backend (advance, get, list_all, list_gaps, delete)
- Forward-only semantics (advance is monotonic)
- Metadata merging
- WatermarkStore SQLite backend
"""

import sqlite3

import pytest
from datetime import UTC, datetime

from spine.core.watermarks import Watermark, WatermarkGap, WatermarkStore


# =============================================================================
# Watermark dataclass
# =============================================================================


class TestWatermark:
    """Tests for the Watermark frozen dataclass."""

    def test_basic_creation(self):
        wm = Watermark(
            domain="equity",
            source="polygon",
            partition_key="AAPL",
            high_water="2026-02-15T00:00:00Z",
        )
        assert wm.domain == "equity"
        assert wm.high_water == "2026-02-15T00:00:00Z"
        assert wm.low_water is None
        assert wm.metadata == {}

    def test_frozen(self):
        wm = Watermark(
            domain="d", source="s", partition_key="pk", high_water="100",
        )
        with pytest.raises(AttributeError):
            wm.high_water = "200"  # type: ignore[misc]


# =============================================================================
# WatermarkStore — in-memory backend
# =============================================================================


class TestWatermarkStoreInMemory:
    """Tests for the in-memory WatermarkStore."""

    def setup_method(self):
        self.store = WatermarkStore()

    def test_get_returns_none_when_empty(self):
        assert self.store.get("d", "s", "pk") is None

    def test_advance_creates_new(self):
        wm = self.store.advance("equity", "polygon", "AAPL", "100")
        assert wm.high_water == "100"
        assert wm.domain == "equity"

    def test_advance_moves_forward(self):
        self.store.advance("d", "s", "pk", "100")
        wm = self.store.advance("d", "s", "pk", "200")
        assert wm.high_water == "200"

    def test_advance_rejects_backward(self):
        """Forward-only: lower high_water is ignored."""
        self.store.advance("d", "s", "pk", "200")
        wm = self.store.advance("d", "s", "pk", "100")
        assert wm.high_water == "200"

    def test_advance_rejects_equal(self):
        """Equal high_water is a no-op."""
        self.store.advance("d", "s", "pk", "100")
        wm = self.store.advance("d", "s", "pk", "100")
        assert wm.high_water == "100"

    def test_get_after_advance(self):
        self.store.advance("d", "s", "pk", "100")
        wm = self.store.get("d", "s", "pk")
        assert wm is not None
        assert wm.high_water == "100"

    def test_advance_merges_metadata(self):
        self.store.advance("d", "s", "pk", "100", metadata={"a": 1})
        wm = self.store.advance("d", "s", "pk", "200", metadata={"b": 2})
        assert wm.metadata == {"a": 1, "b": 2}

    def test_advance_preserves_low_water(self):
        self.store.advance("d", "s", "pk", "100", low_water="50")
        wm = self.store.advance("d", "s", "pk", "200")
        assert wm.low_water == "50"

    def test_advance_overrides_low_water(self):
        self.store.advance("d", "s", "pk", "100", low_water="50")
        wm = self.store.advance("d", "s", "pk", "200", low_water="75")
        assert wm.low_water == "75"

    def test_list_all_empty(self):
        assert self.store.list_all() == []

    def test_list_all(self):
        self.store.advance("d1", "s", "pk1", "100")
        self.store.advance("d2", "s", "pk2", "200")
        result = self.store.list_all()
        assert len(result) == 2

    def test_list_all_filtered_by_domain(self):
        self.store.advance("d1", "s", "pk1", "100")
        self.store.advance("d2", "s", "pk2", "200")
        result = self.store.list_all(domain="d1")
        assert len(result) == 1
        assert result[0].domain == "d1"

    def test_list_gaps(self):
        self.store.advance("d", "s", "pk1", "100")
        # pk2 is missing
        gaps = self.store.list_gaps("d", "s", ["pk1", "pk2", "pk3"])
        assert len(gaps) == 2
        keys = {g.partition_key for g in gaps}
        assert keys == {"pk2", "pk3"}

    def test_list_gaps_no_missing(self):
        self.store.advance("d", "s", "pk1", "100")
        gaps = self.store.list_gaps("d", "s", ["pk1"])
        assert len(gaps) == 0

    def test_delete_existing(self):
        self.store.advance("d", "s", "pk", "100")
        assert self.store.delete("d", "s", "pk") is True
        assert self.store.get("d", "s", "pk") is None

    def test_delete_nonexistent(self):
        assert self.store.delete("d", "s", "pk") is False

    def test_updated_at_is_set(self):
        wm = self.store.advance("d", "s", "pk", "100")
        assert wm.updated_at is not None
        now = datetime.now(UTC)
        assert (now - wm.updated_at).total_seconds() < 2

    def test_different_partition_keys_are_independent(self):
        self.store.advance("d", "s", "pk1", "AAA")
        self.store.advance("d", "s", "pk2", "BBB")
        wm1 = self.store.get("d", "s", "pk1")
        wm2 = self.store.get("d", "s", "pk2")
        assert wm1.high_water == "AAA"
        assert wm2.high_water == "BBB"


# =============================================================================
# WatermarkStore — SQLite backend
# =============================================================================


@pytest.fixture
def sqlite_conn():
    """Create an in-memory SQLite connection with the watermarks table."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE core_watermarks (
            domain TEXT NOT NULL,
            source TEXT NOT NULL,
            partition_key TEXT NOT NULL,
            high_water TEXT NOT NULL,
            low_water TEXT,
            metadata_json TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE (domain, source, partition_key)
        )
    """)
    conn.commit()
    return conn


class TestWatermarkStoreSQLite:
    """Tests for WatermarkStore with a real SQLite connection."""

    def test_advance_and_get(self, sqlite_conn):
        store = WatermarkStore(conn=sqlite_conn)
        store.advance("equity", "polygon", "AAPL", "2026-02-15")
        wm = store.get("equity", "polygon", "AAPL")
        assert wm is not None
        assert wm.high_water == "2026-02-15"
        assert wm.domain == "equity"

    def test_advance_forward_only(self, sqlite_conn):
        store = WatermarkStore(conn=sqlite_conn)
        store.advance("d", "s", "pk", "200")
        wm = store.advance("d", "s", "pk", "100")
        assert wm.high_water == "200"

    def test_advance_upserts(self, sqlite_conn):
        store = WatermarkStore(conn=sqlite_conn)
        store.advance("d", "s", "pk", "100")
        store.advance("d", "s", "pk", "200")
        # Should have exactly one row
        count = sqlite_conn.execute(
            "SELECT COUNT(*) FROM core_watermarks"
        ).fetchone()[0]
        assert count == 1

    def test_list_all_from_db(self, sqlite_conn):
        store = WatermarkStore(conn=sqlite_conn)
        store.advance("d1", "s", "pk1", "A")
        store.advance("d2", "s", "pk2", "B")
        all_wm = store.list_all()
        assert len(all_wm) == 2

    def test_list_all_filtered_from_db(self, sqlite_conn):
        store = WatermarkStore(conn=sqlite_conn)
        store.advance("d1", "s", "pk1", "A")
        store.advance("d2", "s", "pk2", "B")
        result = store.list_all(domain="d1")
        assert len(result) == 1

    def test_delete_from_db(self, sqlite_conn):
        store = WatermarkStore(conn=sqlite_conn)
        store.advance("d", "s", "pk", "100")
        assert store.delete("d", "s", "pk") is True
        assert store.get("d", "s", "pk") is None
        count = sqlite_conn.execute(
            "SELECT COUNT(*) FROM core_watermarks"
        ).fetchone()[0]
        assert count == 0

    def test_metadata_persisted(self, sqlite_conn):
        store = WatermarkStore(conn=sqlite_conn)
        store.advance("d", "s", "pk", "100", metadata={"batch": 42})
        wm = store.get("d", "s", "pk")
        assert wm.metadata == {"batch": 42}

    def test_get_nonexistent_from_db(self, sqlite_conn):
        store = WatermarkStore(conn=sqlite_conn)
        assert store.get("d", "s", "pk") is None
