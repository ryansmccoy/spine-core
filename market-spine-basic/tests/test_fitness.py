"""
Fitness tests for institutional-grade calculation lifecycle and DB hardening.

These tests verify:
1. Uniqueness constraints work correctly with capture_id
2. Replay idempotency (DELETE + INSERT pattern)
3. Calc version selection is policy-driven (not MAX)
4. Determinism (ignoring audit fields)
5. Venue share invariants (shares sum to 1.0)

See docs/fitness/ for detailed documentation.
"""

from datetime import date, datetime
from pathlib import Path
from sqlite3 import IntegrityError

import pytest

from market_spine.db import init_connection_provider, init_db
from spine.domains.finra.otc_transparency.calculations import (
    AUDIT_FIELDS,
    VenueShareRow,
    VenueVolumeRow,
    compute_venue_share_v1,
    rows_equal_deterministic,
    strip_audit_fields,
    validate_venue_share_invariants,
)
from spine.domains.finra.otc_transparency.schema import (
    CALCS,
    TABLES,
    Tier,
    check_deprecation_warning,
    get_calc_metadata,
    get_current_version,
    get_version_rank,
    is_deprecated,
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


# =============================================================================
# UNIQUENESS CONSTRAINT TESTS
# =============================================================================


class TestUniquenessConstraints:
    """Tests for uniqueness constraints using capture_id."""

    def test_duplicate_insert_same_capture_fails(self):
        """Same business key + capture_id should fail on second insert."""
        import uuid
        conn = get_connection()
        
        # Use unique values to avoid collision with other tests
        test_id = uuid.uuid4().hex[:8]
        capture_id = f"cap-test-dup-{test_id}"
        symbol = f"TEST{test_id[:4]}"
        
        # First insert succeeds
        conn.execute(
            f"""
            INSERT INTO {TABLES["symbol_summary"]} (
                execution_id, batch_id, week_ending, tier, symbol,
                total_volume, total_trades, venue_count,
                captured_at, capture_id, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("exec-1", "batch-1", "2025-12-26", "OTC", symbol,
             1000, 10, 3, "2025-01-01T00:00:00", capture_id, "2025-01-01T00:00:00"),
        )
        conn.commit()
        
        # Second insert with same capture_id should fail
        with pytest.raises(IntegrityError):
            conn.execute(
                f"""
                INSERT INTO {TABLES["symbol_summary"]} (
                    execution_id, batch_id, week_ending, tier, symbol,
                    total_volume, total_trades, venue_count,
                    captured_at, capture_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("exec-2", "batch-2", "2025-12-26", "OTC", symbol,
                 2000, 20, 5, "2025-01-01T00:00:00", capture_id, "2025-01-01T00:00:00"),
            )

    def test_different_capture_succeeds(self):
        """Same business key with different capture_id should succeed."""
        import uuid
        conn = get_connection()
        
        # Use unique values to avoid collision with other tests
        test_id = uuid.uuid4().hex[:8]
        symbol = f"DIFF{test_id[:4]}"
        
        # First insert
        conn.execute(
            f"""
            INSERT INTO {TABLES["symbol_summary"]} (
                execution_id, batch_id, week_ending, tier, symbol,
                total_volume, total_trades, venue_count,
                captured_at, capture_id, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("exec-1", "batch-1", "2025-12-26", "OTC", symbol,
             1000, 10, 3, "2025-01-01T00:00:00", f"cap-diff-1-{test_id}", "2025-01-01T00:00:00"),
        )
        
        # Second insert with different capture_id should succeed
        conn.execute(
            f"""
            INSERT INTO {TABLES["symbol_summary"]} (
                execution_id, batch_id, week_ending, tier, symbol,
                total_volume, total_trades, venue_count,
                captured_at, capture_id, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("exec-2", "batch-2", "2025-12-26", "OTC", symbol,
             2000, 20, 5, "2025-01-02T00:00:00", f"cap-diff-2-{test_id}", "2025-01-02T00:00:00"),
        )
        conn.commit()
        
        # Both should exist
        count = conn.execute(
            f"SELECT COUNT(*) FROM {TABLES['symbol_summary']} WHERE symbol = ?",
            (symbol,)
        ).fetchone()[0]
        assert count == 2


class TestReplayIdempotency:
    """Tests for replay using DELETE + INSERT pattern."""

    def test_replay_with_delete_insert_is_idempotent(self, fixture_path):
        """DELETE + INSERT pattern produces identical results."""
        dispatcher = Dispatcher()
        
        # First run
        exec1 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "OTC", "force": True},
        )
        assert exec1.status.value == "completed"
        capture1 = exec1.result.metrics.get("capture_id")
        
        conn = get_connection()
        count1 = conn.execute(
            f"SELECT COUNT(*) FROM {TABLES['raw']} WHERE capture_id = ?",
            (capture1,)
        ).fetchone()[0]
        
        # Replay with same capture (force=True triggers DELETE + INSERT)
        # This will create a new capture_id, but we can verify row counts match
        exec2 = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "OTC", "force": True},
        )
        assert exec2.status.value == "completed"
        capture2 = exec2.result.metrics.get("capture_id")
        
        count2 = conn.execute(
            f"SELECT COUNT(*) FROM {TABLES['raw']} WHERE capture_id = ?",
            (capture2,)
        ).fetchone()[0]
        
        # Same row count (same source data)
        assert count1 == count2


# =============================================================================
# CALC VERSION REGISTRY TESTS
# =============================================================================


class TestCalcVersionRegistry:
    """Tests for policy-driven version selection."""

    def test_get_current_version_returns_policy_version(self):
        """get_current_version returns the policy-defined current."""
        version = get_current_version("venue_share")
        assert version == "v1"  # As defined in CALCS registry

    def test_get_current_version_unknown_raises(self):
        """Unknown calc name raises KeyError."""
        with pytest.raises(KeyError, match="Unknown calc"):
            get_current_version("nonexistent_calc")

    def test_version_rank_handles_v10_vs_v2(self):
        """v10 should have higher rank than v2 (numeric comparison)."""
        # v10 = 10, v2 = 2
        assert get_version_rank("venue_share", "v10") > get_version_rank("venue_share", "v2")
        assert get_version_rank("venue_share", "v2") > get_version_rank("venue_share", "v1")

    def test_is_deprecated_false_for_current(self):
        """Current version is not deprecated."""
        assert not is_deprecated("venue_share", "v1")

    def test_calcs_registry_structure(self):
        """CALCS registry has required fields."""
        for calc_name, config in CALCS.items():
            assert "versions" in config
            assert "current" in config
            assert "deprecated" in config
            assert "table" in config
            assert "business_keys" in config
            
            # Current must be in versions
            assert config["current"] in config["versions"]

    # =========================================================================
    # REGISTRY CONTRACT INVARIANTS (must never be violated)
    # =========================================================================

    def test_current_version_never_deprecated(self):
        """INVARIANT: Current version cannot be in deprecated list."""
        for calc_name, config in CALCS.items():
            current = config["current"]
            deprecated = config.get("deprecated", [])
            assert current not in deprecated, (
                f"REGISTRY VIOLATION: {calc_name}.current='{current}' is also in deprecated list! "
                f"A calc's current version cannot be deprecated. "
                f"Either update 'current' to a newer version or remove from deprecated."
            )

    def test_deprecated_versions_exist_in_versions(self):
        """INVARIANT: Deprecated versions must still exist in versions list."""
        for calc_name, config in CALCS.items():
            versions = config["versions"]
            deprecated = config.get("deprecated", [])
            for dep in deprecated:
                assert dep in versions, (
                    f"REGISTRY VIOLATION: {calc_name} has deprecated='{dep}' "
                    f"but it's not in versions={versions}. "
                    f"Never remove a version from the registry without a migration plan."
                )

    def test_versions_list_non_empty(self):
        """INVARIANT: Every calc must have at least one version."""
        for calc_name, config in CALCS.items():
            versions = config["versions"]
            assert len(versions) > 0, (
                f"REGISTRY VIOLATION: {calc_name} has empty versions list. "
                f"Every calc must have at least one version."
            )

    def test_versions_sorted_chronologically(self):
        """CONVENTION: Versions should be in chronological order (oldest first)."""
        for calc_name, config in CALCS.items():
            versions = config["versions"]
            if len(versions) > 1:
                # Extract version numbers
                nums = [int(v.lstrip("v")) for v in versions if v.startswith("v")]
                assert nums == sorted(nums), (
                    f"REGISTRY CONVENTION: {calc_name}.versions should be sorted "
                    f"chronologically (oldest first). Got: {versions}"
                )

    def test_business_keys_non_empty(self):
        """INVARIANT: Every calc must define business keys."""
        for calc_name, config in CALCS.items():
            keys = config.get("business_keys", [])
            assert len(keys) > 0, (
                f"REGISTRY VIOLATION: {calc_name} has no business_keys. "
                f"Every calc must define its natural key."
            )

    def test_table_name_follows_convention(self):
        """CONVENTION: Table names should be snake_case with domain prefix."""
        for calc_name, config in CALCS.items():
            table = config["table"]
            assert table.startswith("finra_otc_"), (
                f"REGISTRY CONVENTION: {calc_name}.table='{table}' should start "
                f"with 'finra_otc_' domain prefix."
            )
            assert table == table.lower(), (
                f"REGISTRY CONVENTION: {calc_name}.table='{table}' should be lowercase."
            )

    # =========================================================================
    # DEPRECATION SURFACING TESTS
    # =========================================================================

    def test_check_deprecation_warning_none_for_current(self):
        """Current version returns no deprecation warning."""
        warning = check_deprecation_warning("venue_share", "v1")
        assert warning is None

    def test_get_calc_metadata_returns_required_fields(self):
        """get_calc_metadata returns all required fields."""
        meta = get_calc_metadata("venue_share")
        
        assert "calc_name" in meta
        assert "calc_version" in meta
        assert "is_current" in meta
        assert "deprecated" in meta
        assert "deprecation_warning" in meta
        assert "table" in meta
        assert "business_keys" in meta
        
        # Current version should be marked correctly
        assert meta["is_current"] is True
        assert meta["deprecated"] is False
        assert meta["deprecation_warning"] is None

    def test_get_calc_metadata_unknown_calc_raises(self):
        """Unknown calc name raises KeyError."""
        with pytest.raises(KeyError, match="Unknown calc"):
            get_calc_metadata("nonexistent_calc")

    def test_get_calc_metadata_unknown_version_raises(self):
        """Unknown version raises ValueError."""
        with pytest.raises(ValueError, match="Unknown version"):
            get_calc_metadata("venue_share", "v999")


# =============================================================================
# DETERMINISM TESTS
# =============================================================================


class TestDeterminism:
    """Tests for deterministic output comparison."""

    def test_audit_fields_defined(self):
        """AUDIT_FIELDS contains expected fields."""
        assert "calculated_at" in AUDIT_FIELDS
        assert "ingested_at" in AUDIT_FIELDS
        assert "id" in AUDIT_FIELDS

    def test_strip_audit_fields_removes_audit(self):
        """strip_audit_fields removes audit-only fields."""
        row = {
            "week_ending": "2025-12-26",
            "tier": "OTC",
            "symbol": "AAPL",
            "calculated_at": "2025-01-01T00:00:00",
            "id": 123,
        }
        stripped = strip_audit_fields(row)
        
        assert "calculated_at" not in stripped
        assert "id" not in stripped
        assert stripped["week_ending"] == "2025-12-26"
        assert stripped["symbol"] == "AAPL"

    def test_rows_equal_deterministic_ignores_audit(self):
        """rows_equal_deterministic ignores audit field differences."""
        rows1 = [
            {"week_ending": "2025-12-26", "symbol": "AAPL", "calculated_at": "2025-01-01"},
            {"week_ending": "2025-12-26", "symbol": "MSFT", "calculated_at": "2025-01-01"},
        ]
        rows2 = [
            {"week_ending": "2025-12-26", "symbol": "AAPL", "calculated_at": "2025-01-02"},
            {"week_ending": "2025-12-26", "symbol": "MSFT", "calculated_at": "2025-01-02"},
        ]
        
        # Different calculated_at, but deterministically equal
        assert rows_equal_deterministic(rows1, rows2)

    def test_rows_equal_deterministic_detects_real_diff(self):
        """rows_equal_deterministic detects actual data differences."""
        rows1 = [{"week_ending": "2025-12-26", "symbol": "AAPL"}]
        rows2 = [{"week_ending": "2025-12-26", "symbol": "MSFT"}]
        
        assert not rows_equal_deterministic(rows1, rows2)


# =============================================================================
# VENUE SHARE CALC TESTS
# =============================================================================


class TestVenueShareCalc:
    """Tests for venue share calculation and invariants."""

    def test_compute_venue_share_basic(self):
        """Basic venue share computation."""
        venue_rows = [
            VenueVolumeRow(
                week_ending=date(2025, 12, 26),
                tier=Tier.OTC,
                symbol="AAPL",
                mpid="ETRD",
                total_shares=1000,
                total_trades=10,
            ),
            VenueVolumeRow(
                week_ending=date(2025, 12, 26),
                tier=Tier.OTC,
                symbol="AAPL",
                mpid="SCHW",
                total_shares=500,
                total_trades=5,
            ),
            VenueVolumeRow(
                week_ending=date(2025, 12, 26),
                tier=Tier.OTC,
                symbol="MSFT",
                mpid="ETRD",
                total_shares=500,
                total_trades=5,
            ),
        ]
        
        shares = compute_venue_share_v1(venue_rows)
        
        # Should have 2 venues (ETRD, SCHW)
        assert len(shares) == 2
        
        # ETRD has 1500 (1000+500), SCHW has 500 => total 2000
        etrd = next(s for s in shares if s.mpid == "ETRD")
        schw = next(s for s in shares if s.mpid == "SCHW")
        
        assert etrd.total_volume == 1500
        assert schw.total_volume == 500
        assert etrd.market_share_pct == 0.75  # 1500/2000
        assert schw.market_share_pct == 0.25  # 500/2000
        assert etrd.rank == 1
        assert schw.rank == 2

    def test_shares_sum_to_one_invariant(self):
        """Venue shares must sum to 1.0 per (week, tier)."""
        venue_rows = [
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "AAPL", "V1", 100, 10),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "MSFT", "V2", 200, 20),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "GOOGL", "V3", 300, 30),
        ]
        
        shares = compute_venue_share_v1(venue_rows)
        total_share = sum(s.market_share_pct for s in shares)
        
        assert abs(total_share - 1.0) < 0.0001

    def test_validate_invariants_passes_for_valid(self):
        """validate_venue_share_invariants returns empty for valid data."""
        venue_rows = [
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "AAPL", "V1", 100, 10),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "MSFT", "V2", 200, 20),
        ]
        
        shares = compute_venue_share_v1(venue_rows)
        errors = validate_venue_share_invariants(shares)
        
        assert errors == []

    def test_ranks_are_consecutive(self):
        """Ranks must be 1, 2, 3... with no gaps."""
        venue_rows = [
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "A", "V1", 100, 1),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "B", "V2", 200, 2),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "C", "V3", 300, 3),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "D", "V4", 400, 4),
        ]
        
        shares = compute_venue_share_v1(venue_rows)
        ranks = sorted(s.rank for s in shares)
        
        assert ranks == [1, 2, 3, 4]

    def test_symbol_count_correct(self):
        """symbol_count reflects distinct symbols per venue."""
        venue_rows = [
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "AAPL", "V1", 100, 1),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "MSFT", "V1", 200, 2),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "GOOGL", "V1", 300, 3),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "AAPL", "V2", 50, 1),
        ]
        
        shares = compute_venue_share_v1(venue_rows)
        
        v1 = next(s for s in shares if s.mpid == "V1")
        v2 = next(s for s in shares if s.mpid == "V2")
        
        assert v1.symbol_count == 3  # AAPL, MSFT, GOOGL
        assert v2.symbol_count == 1  # AAPL only


class TestVenueSharePipeline:
    """Integration tests for venue share pipeline."""

    def test_pipeline_registered(self):
        """Venue share pipeline is registered."""
        from spine.framework.registry import list_pipelines
        
        pipelines = list_pipelines()
        assert "finra.otc_transparency.compute_venue_share" in pipelines

    def test_pipeline_runs_successfully(self, fixture_path):
        """Venue share pipeline runs end-to-end."""
        dispatcher = Dispatcher()
        
        # First ingest data (week_ending is auto-detected from file)
        ingest_result = dispatcher.submit(
            "finra.otc_transparency.ingest_week",
            params={"file_path": str(fixture_path), "tier": "OTC", "force": True},
        )
        assert ingest_result.status.value == "completed"
        
        # Get the week_ending from the ingest result (auto-detected from file)
        # The fixture file date derives to a specific week_ending
        conn = get_connection()
        week_row = conn.execute(
            f"SELECT DISTINCT week_ending FROM {TABLES['raw']} WHERE tier = 'OTC' ORDER BY week_ending DESC LIMIT 1"
        ).fetchone()
        assert week_row is not None
        week_ending = week_row[0]
        
        # Now normalize with the actual week_ending
        dispatcher.submit(
            "finra.otc_transparency.normalize_week",
            params={"week_ending": week_ending, "tier": "OTC", "force": True},
        )
        
        # Run venue share
        result = dispatcher.submit(
            "finra.otc_transparency.compute_venue_share",
            params={"week_ending": week_ending, "tier": "OTC", "force": True},
        )
        
        assert result.status.value == "completed"
        assert result.result.metrics.get("venues", 0) > 0
        
        # Get the capture_id from the result to query the correct data
        capture_id = result.result.metrics.get("capture_id")
        assert capture_id is not None
        
        # Verify invariant (shares sum to 1.0) for THIS capture only
        shares_sum = conn.execute(
            f"""
            SELECT SUM(CAST(market_share_pct AS REAL)) 
            FROM {TABLES['venue_share']}
            WHERE week_ending = ? AND tier = 'OTC' AND capture_id = ?
            """,
            (week_ending, capture_id)
        ).fetchone()[0]
        
        assert shares_sum is not None
        assert abs(shares_sum - 1.0) < 0.0001, f"Shares sum to {shares_sum}, expected 1.0"


# =============================================================================
# MISSING DATA STRESS TESTS
# =============================================================================


class TestMissingDataBehavior:
    """
    Tests that calcs fail loudly or degrade gracefully on missing/invalid data.
    
    Principle: Calcs should NEVER silently produce incorrect results.
    They should either:
    1. Raise an exception with clear message
    2. Return empty results (for empty input)
    3. Produce valid output with warnings logged
    """

    def test_venue_share_empty_input_returns_empty(self):
        """Empty input produces empty output (not an error)."""
        result = compute_venue_share_v1([])
        assert result == []

    def test_venue_share_zero_volume_handled_gracefully(self):
        """Zero total volume doesn't cause division by zero."""
        # All venues with zero volume
        venue_rows = [
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "AAPL", "V1", 0, 0),
            VenueVolumeRow(date(2025, 12, 26), Tier.OTC, "MSFT", "V2", 0, 0),
        ]
        
        # Should not raise - returns 0% shares
        result = compute_venue_share_v1(venue_rows)
        assert len(result) == 2
        
        # All shares should be 0 (tier_volume is 0)
        for r in result:
            assert r.market_share_pct == 0.0

    def test_venue_share_negative_volume_detected_by_invariant(self):
        """Negative volume is caught by invariant validation."""
        # Manually create row with negative volume (shouldn't happen in practice)
        bad_row = VenueShareRow(
            week_ending=date(2025, 12, 26),
            tier=Tier.OTC,
            mpid="BAD",
            total_volume=-100,
            total_trades=10,
            symbol_count=1,
            market_share_pct=-0.5,
            rank=1,
        )
        
        errors = validate_venue_share_invariants([bad_row])
        
        # Should detect negative volume and share
        assert len(errors) > 0
        assert any("Negative" in e for e in errors)

    def test_get_current_version_fails_on_unknown_calc(self):
        """Unknown calc name fails loudly with helpful message."""
        with pytest.raises(KeyError) as exc_info:
            get_current_version("nonexistent_calc_xyz")
        
        # Error message should be helpful
        assert "Unknown calc" in str(exc_info.value)
        assert "nonexistent_calc_xyz" in str(exc_info.value)

    def test_get_calc_metadata_fails_on_bad_version(self):
        """Invalid version fails loudly with helpful message."""
        with pytest.raises(ValueError) as exc_info:
            get_calc_metadata("venue_share", "v999")
        
        # Error message should be helpful
        assert "Unknown version" in str(exc_info.value)
        assert "v999" in str(exc_info.value)

    def test_invariant_validation_catches_share_sum_error(self):
        """Shares not summing to 1.0 is detected."""
        # Manually create rows that don't sum to 1.0
        bad_rows = [
            VenueShareRow(
                week_ending=date(2025, 12, 26),
                tier=Tier.OTC,
                mpid="V1",
                total_volume=100,
                total_trades=10,
                symbol_count=1,
                market_share_pct=0.3,  # Should be higher
                rank=1,
            ),
            VenueShareRow(
                week_ending=date(2025, 12, 26),
                tier=Tier.OTC,
                mpid="V2",
                total_volume=50,
                total_trades=5,
                symbol_count=1,
                market_share_pct=0.2,  # Should be higher
                rank=2,
            ),
        ]
        
        errors = validate_venue_share_invariants(bad_rows)
        
        # Should detect share sum error (0.3 + 0.2 = 0.5 != 1.0)
        assert len(errors) > 0
        assert any("Share invariant" in e for e in errors)

    def test_invariant_validation_catches_rank_gaps(self):
        """Non-consecutive ranks are detected."""
        bad_rows = [
            VenueShareRow(
                week_ending=date(2025, 12, 26),
                tier=Tier.OTC,
                mpid="V1",
                total_volume=100,
                total_trades=10,
                symbol_count=1,
                market_share_pct=0.7,
                rank=1,
            ),
            VenueShareRow(
                week_ending=date(2025, 12, 26),
                tier=Tier.OTC,
                mpid="V2",
                total_volume=50,
                total_trades=5,
                symbol_count=1,
                market_share_pct=0.3,
                rank=3,  # Gap! Should be 2
            ),
        ]
        
        errors = validate_venue_share_invariants(bad_rows)
        
        # Should detect rank gap
        assert len(errors) > 0
        assert any("Rank invariant" in e for e in errors)
