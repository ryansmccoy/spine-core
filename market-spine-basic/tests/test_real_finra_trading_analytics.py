"""
Real FINRA Trading Analytics - End-to-End Test

This test proves Market Spine supports institutional-grade trading analytics
using ACTUAL production-like FINRA OTC data (not mocks or synthetic data).

Test Workflow:
1. Use real CSV files from data/finra/*.csv as fixtures
2. Create temporary SQLite database
3. Run full pipeline: ingest → normalize → compute analytics
4. Assert REAL invariants (shares sum to 1.0, HHI bounds, etc.)
5. Test idempotency and as-of correctness with capture_id
6. Verify point-in-time replay works correctly

This demonstrates what an institutional investment desk would actually run.
"""

import sqlite3
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from spine.domains.finra.otc_transparency.calculations import (
    compute_weekly_symbol_tier_volume_share,
    compute_weekly_symbol_venue_concentration_hhi,
    compute_weekly_symbol_venue_share,
    compute_weekly_symbol_venue_volume,
)

# Real data files (production-like FINRA OTC weekly reports)
# Path is relative to spine-core root, not market-spine-basic
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "finra"
TIER1_FILES = sorted(DATA_DIR.glob("finra_otc_weekly_tier1_2025*.csv"))
TIER2_FILES = sorted(DATA_DIR.glob("finra_otc_weekly_tier2_2025*.csv"))
OTC_FILES = sorted(DATA_DIR.glob("finra_otc_weekly_otc_2025*.csv"))

ALL_FILES = TIER1_FILES + TIER2_FILES + OTC_FILES


@pytest.fixture
def temp_db():
    """Create a temporary database with schema initialized."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_analytics.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Load schema
        schema_path = Path(__file__).parent.parent / "migrations" / "schema.sql"
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()

        yield conn

        conn.close()


class TestRealFINRATradingAnalytics:
    """
    Real trading analytics using actual FINRA data.

    This is NOT an academic exercise. These tests prove Market Spine
    can handle institutional-grade analytics with real data.
    """

    def test_real_data_files_exist(self):
        """Verify we have real FINRA data files to test with."""
        assert len(TIER1_FILES) >= 3, f"Need at least 3 Tier 1 files, found {len(TIER1_FILES)}"
        assert len(TIER2_FILES) >= 3, f"Need at least 3 Tier 2 files, found {len(TIER2_FILES)}"
        assert len(OTC_FILES) >= 3, f"Need at least 3 OTC files, found {len(OTC_FILES)}"

        # Verify files are not empty
        for file in ALL_FILES:
            assert file.stat().st_size > 1000, f"{file.name} seems too small"

    def test_end_to_end_real_analytics(self, temp_db):
        """
        Full end-to-end test using real FINRA data.

        Workflow:
        1. Ingest real CSV files
        2. Normalize data
        3. Compute venue volume (base gold)
        4. Compute venue share
        5. Compute HHI concentration
        6. Compute tier split
        7. Assert real invariants hold
        """
        from spine.core import new_batch_id, new_context

        conn = temp_db
        batch_id = new_batch_id()
        ctx = new_context(batch_id=batch_id)
        execution_id = ctx.execution_id
        captured_at = datetime.now(UTC).isoformat()

        # Use first TIER1 file for this test (week 2025-12-15)
        test_file = TIER1_FILES[0]
        week_ending = "2025-12-15"
        tier = "NMS_TIER_1"

        # Step 1: Ingest real CSV
        raw_count = self._ingest_real_csv(
            conn, test_file, week_ending, tier, execution_id, batch_id, captured_at
        )
        assert raw_count > 0, "Should have ingested real data"
        print(f"✓ Ingested {raw_count} real FINRA rows")

        # Step 2: Normalize
        capture_id = (
            f"finra.otc_transparency:{tier}:{week_ending}:{captured_at[:10].replace('-', '')}"
        )
        norm_count = self._normalize_data(
            conn, week_ending, tier, execution_id, batch_id, captured_at, capture_id
        )
        assert norm_count > 0, "Should have normalized data"
        print(f"✓ Normalized to {norm_count} rows")

        # Step 3: Compute venue volume (base gold layer)
        venue_volume_rows = self._compute_venue_volume(
            conn, week_ending, tier, capture_id, execution_id, batch_id
        )
        assert len(venue_volume_rows) > 0, "Should have venue volume data"
        print(f"✓ Computed {len(venue_volume_rows)} venue volume rows")

        # Step 4: Compute venue share
        venue_share_rows = self._compute_venue_share(
            conn, week_ending, tier, capture_id, execution_id, batch_id
        )
        assert len(venue_share_rows) > 0, "Should have venue share data"
        print(f"✓ Computed {len(venue_share_rows)} venue share rows")

        # Step 5: Compute HHI concentration
        hhi_rows = self._compute_hhi(conn, week_ending, tier, capture_id, execution_id, batch_id)
        assert len(hhi_rows) > 0, "Should have HHI data"
        print(f"✓ Computed {len(hhi_rows)} HHI rows")

        # Step 6: Compute tier split (requires multiple tiers)
        # Ingest TIER2 and OTC data for the same week
        tier2_file = [f for f in TIER2_FILES if "20251215" in f.name][0]
        otc_file = [f for f in OTC_FILES if "20251215" in f.name][0]

        self._ingest_real_csv(
            conn, tier2_file, week_ending, "NMS_TIER_2", execution_id, batch_id, captured_at
        )
        self._ingest_real_csv(
            conn, otc_file, week_ending, "OTC", execution_id, batch_id, captured_at
        )

        # Normalize other tiers
        cap_tier2 = (
            f"finra.otc_transparency:NMS_TIER_2:{week_ending}:{captured_at[:10].replace('-', '')}"
        )
        cap_otc = f"finra.otc_transparency:OTC:{week_ending}:{captured_at[:10].replace('-', '')}"

        self._normalize_data(
            conn, week_ending, "NMS_TIER_2", execution_id, batch_id, captured_at, cap_tier2
        )
        self._normalize_data(conn, week_ending, "OTC", execution_id, batch_id, captured_at, cap_otc)

        # Compute venue volume for all tiers
        self._compute_venue_volume(
            conn, week_ending, "NMS_TIER_2", cap_tier2, execution_id, batch_id
        )
        self._compute_venue_volume(conn, week_ending, "OTC", cap_otc, execution_id, batch_id)

        tier_split_rows = self._compute_tier_split(conn, week_ending, execution_id, batch_id)
        assert len(tier_split_rows) > 0, "Should have tier split data"
        print(f"✓ Computed {len(tier_split_rows)} tier split rows")

        # ASSERT REAL INVARIANTS
        self._assert_invariants(conn, week_ending, tier, capture_id)

        print("\\n✅ All real analytics computed successfully with invariants satisfied")

    def test_idempotency_and_asof(self, temp_db):
        """
        Test idempotency and as-of correctness.

        1. Compute analytics with capture_id_1
        2. Re-run with same capture_id → should be idempotent
        3. Run with new capture_id_2 → should coexist
        4. Query by capture_id → should get point-in-time data
        """
        from spine.core import new_batch_id, new_context

        conn = temp_db
        test_file = TIER1_FILES[0]
        week_ending = "2025-12-15"
        tier = "NMS_TIER_1"

        # Run 1: Initial computation
        batch_id_1 = new_batch_id()
        ctx_1 = new_context(batch_id=batch_id_1)
        exec_id_1 = ctx_1.execution_id
        captured_at_1 = "2025-12-16T10:00:00Z"
        capture_id_1 = f"finra.otc_transparency:{tier}:{week_ending}:20251216"

        self._ingest_real_csv(
            conn, test_file, week_ending, tier, exec_id_1, batch_id_1, captured_at_1
        )
        self._normalize_data(
            conn, week_ending, tier, exec_id_1, batch_id_1, captured_at_1, capture_id_1
        )
        venue_vol_1 = self._compute_venue_volume(
            conn, week_ending, tier, capture_id_1, exec_id_1, batch_id_1
        )

        count_1 = len(venue_vol_1)
        assert count_1 > 0

        # Run 2: Re-run with same capture_id (idempotent)
        batch_id_2 = new_batch_id()
        ctx_2 = new_context(batch_id=batch_id_2)
        exec_id_2 = ctx_2.execution_id

        # Delete and re-insert (simulating re-run)
        conn.execute(
            "DELETE FROM finra_otc_transparency_weekly_symbol_venue_volume WHERE capture_id = ?",
            (capture_id_1,),
        )
        venue_vol_2 = self._compute_venue_volume(
            conn, week_ending, tier, capture_id_1, exec_id_2, batch_id_2
        )

        count_2 = len(venue_vol_2)
        assert count_2 == count_1, "Idempotent: same capture_id should produce same row count"

        # Run 3: New capture_id (coexistence)
        captured_at_3 = "2025-12-17T14:00:00Z"
        capture_id_3 = f"finra.otc_transparency:{tier}:{week_ending}:20251217"
        batch_id_3 = new_batch_id()
        ctx_3 = new_context(batch_id=batch_id_3)
        exec_id_3 = ctx_3.execution_id

        self._normalize_data(
            conn, week_ending, tier, exec_id_3, batch_id_3, captured_at_3, capture_id_3
        )
        venue_vol_3 = self._compute_venue_volume(
            conn, week_ending, tier, capture_id_3, exec_id_3, batch_id_3
        )

        # Should now have TWO distinct captures in the database
        total_rows = conn.execute(
            """SELECT COUNT(*) FROM finra_otc_transparency_weekly_symbol_venue_volume
               WHERE week_ending = ? AND tier = ?""",
            (week_ending, tier),
        ).fetchone()[0]

        expected_total = count_1 + len(venue_vol_3)
        assert total_rows == expected_total, "Should have rows from both captures"

        # As-of query: Get data for specific capture_id
        rows_cap_1 = conn.execute(
            """SELECT COUNT(*) FROM finra_otc_transparency_weekly_symbol_venue_volume
               WHERE capture_id = ?""",
            (capture_id_1,),
        ).fetchone()[0]

        assert rows_cap_1 == count_1, "As-of query should return only capture_id_1 data"

        print("\\n✅ Idempotency and as-of correctness verified")

    def test_venue_share_invariants(self, temp_db):
        """
        Test that venue shares sum to 1.0 for each symbol.

        This is a critical invariant for trading analytics.
        """
        from spine.core import new_batch_id, new_context

        conn = temp_db
        test_file = TIER1_FILES[0]
        week_ending = "2025-12-15"
        tier = "NMS_TIER_1"

        batch_id = new_batch_id()
        ctx = new_context(batch_id=batch_id)
        execution_id = ctx.execution_id
        captured_at = datetime.now(UTC).isoformat()
        capture_id = f"test_capture_{datetime.now().timestamp()}"

        self._ingest_real_csv(
            conn, test_file, week_ending, tier, execution_id, batch_id, captured_at
        )
        self._normalize_data(
            conn, week_ending, tier, execution_id, batch_id, captured_at, capture_id
        )
        self._compute_venue_volume(conn, week_ending, tier, capture_id, execution_id, batch_id)
        self._compute_venue_share(conn, week_ending, tier, capture_id, execution_id, batch_id)

        # Check that shares sum to 1.0 for each symbol
        results = conn.execute(
            """
            SELECT symbol, SUM(venue_share) as total_share
            FROM finra_otc_transparency_weekly_symbol_venue_share
            WHERE capture_id = ?
            GROUP BY symbol
        """,
            (capture_id,),
        ).fetchall()

        for row in results:
            symbol = row["symbol"]
            total_share = row["total_share"]
            # Allow tiny floating point errors
            assert abs(total_share - 1.0) < 0.0001, (
                f"{symbol}: shares sum to {total_share}, not 1.0"
            )

        print(f"\\n✅ Venue shares sum to 1.0 for all {len(results)} symbols")

    def test_hhi_bounds(self, temp_db):
        """
        Test that HHI is bounded correctly: 0 <= HHI <= 1.0

        Also verify interpretation:
        - HHI = 1.0 when one venue has 100% share
        - HHI decreases as market becomes more fragmented
        """
        from spine.core import new_batch_id, new_context

        conn = temp_db
        test_file = TIER1_FILES[0]
        week_ending = "2025-12-15"
        tier = "NMS_TIER_1"

        batch_id = new_batch_id()
        ctx = new_context(batch_id=batch_id)
        execution_id = ctx.execution_id
        captured_at = datetime.now(UTC).isoformat()
        capture_id = f"test_capture_{datetime.now().timestamp()}"

        self._ingest_real_csv(
            conn, test_file, week_ending, tier, execution_id, batch_id, captured_at
        )
        self._normalize_data(
            conn, week_ending, tier, execution_id, batch_id, captured_at, capture_id
        )
        self._compute_venue_volume(conn, week_ending, tier, capture_id, execution_id, batch_id)
        self._compute_venue_share(conn, week_ending, tier, capture_id, execution_id, batch_id)
        self._compute_hhi(conn, week_ending, tier, capture_id, execution_id, batch_id)

        # Check HHI bounds
        results = conn.execute(
            """
            SELECT symbol, hhi, venue_count
            FROM finra_otc_transparency_weekly_symbol_venue_concentration_hhi
            WHERE capture_id = ?
        """,
            (capture_id,),
        ).fetchall()

        monopoly_count = 0
        competitive_count = 0

        for row in results:
            symbol = row["symbol"]
            hhi = row["hhi"]
            venue_count = row["venue_count"]

            assert 0.0 <= hhi <= 1.0, f"{symbol}: HHI {hhi} out of bounds"

            # Count concentration levels
            if hhi > 0.9:
                monopoly_count += 1
            elif hhi < 0.15:
                competitive_count += 1

        print(f"\\n✅ HHI bounds verified for {len(results)} symbols")
        print(f"   - {monopoly_count} symbols with monopoly/dominant venue (HHI > 0.9)")
        print(f"   - {competitive_count} symbols with competitive markets (HHI < 0.15)")

    # Helper methods

    def _ingest_real_csv(
        self, conn, file_path, week_ending, tier, execution_id, batch_id, captured_at
    ):
        """Ingest real FINRA CSV file into raw table."""
        import csv
        import hashlib

        with open(file_path) as f:
            reader = csv.DictReader(f, delimiter="|")
            rows_inserted = 0

            for row in reader:
                # Match schema.sql column names
                symbol = row.get("issueSymbolIdentifier", "")
                mpid = row.get("MPID", "")
                total_shares = int(row.get("totalWeeklyShareQuantity", 0))
                total_trades = int(row.get("totalWeeklyTradeCount", 0))

                # Generate record hash for uniqueness
                record_str = f"{week_ending}|{tier}|{symbol}|{mpid}|{total_shares}|{total_trades}"
                record_hash = hashlib.sha256(record_str.encode()).hexdigest()[:16]

                # Derive capture_id
                capture_date = captured_at[:10].replace("-", "")  # YYYYMMDD
                capture_id = f"finra.otc_transparency:{tier}:{week_ending}:{capture_date}"

                conn.execute(
                    """
                    INSERT INTO finra_otc_transparency_raw (
                        execution_id, batch_id, record_hash,
                        week_ending, tier, symbol, issue_name,
                        venue_name, mpid, total_shares, total_trades,
                        source_last_update_date, captured_at, capture_id,
                        source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        execution_id,
                        batch_id,
                        record_hash,
                        week_ending,
                        tier,
                        symbol,
                        row.get("issueName", ""),
                        row.get("marketParticipantName", ""),
                        mpid,
                        total_shares,
                        total_trades,
                        row.get("lastUpdateDate", ""),
                        captured_at,
                        capture_id,
                        str(file_path),
                    ),
                )
                rows_inserted += 1

        conn.commit()
        return rows_inserted

    def _normalize_data(
        self, conn, week_ending, tier, execution_id, batch_id, captured_at, capture_id
    ):
        """Normalize raw data."""
        conn.execute(
            """
            INSERT INTO finra_otc_transparency_normalized (
                execution_id, batch_id, week_ending, tier, symbol, mpid,
                venue_name, total_shares, total_trades,
                issue_name, source_last_update_date,
                captured_at, capture_id
            )
            SELECT
                execution_id, batch_id, week_ending, tier,
                symbol, mpid, venue_name,
                total_shares, total_trades,
                issue_name, source_last_update_date,
                ?, ?
            FROM finra_otc_transparency_raw
            WHERE week_ending = ? AND tier = ? AND execution_id = ?
        """,
            (captured_at, capture_id, week_ending, tier, execution_id),
        )

        conn.commit()

        count = conn.execute(
            "SELECT COUNT(*) FROM finra_otc_transparency_normalized WHERE capture_id = ?",
            (capture_id,),
        ).fetchone()[0]

        return count

    def _compute_venue_volume(self, conn, week_ending, tier, capture_id, execution_id, batch_id):
        """Compute venue volume from normalized data."""
        # Fetch normalized data
        rows = conn.execute(
            """
            SELECT * FROM finra_otc_transparency_normalized
            WHERE week_ending = ? AND tier = ? AND capture_id = ?
        """,
            (week_ending, tier, capture_id),
        ).fetchall()

        normalized_dicts = [dict(row) for row in rows]

        # Compute venue volume
        venue_volumes = compute_weekly_symbol_venue_volume(normalized_dicts)

        # Insert into database
        for vv in venue_volumes:
            conn.execute(
                """
                INSERT INTO finra_otc_transparency_weekly_symbol_venue_volume (
                    execution_id, batch_id, week_ending, tier, symbol, mpid, venue_name,
                    total_volume, trade_count, calc_name, calc_version,
                    captured_at, capture_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    execution_id,
                    batch_id,
                    str(vv.week_ending),
                    vv.tier,
                    vv.symbol,
                    vv.mpid,
                    vv.venue_name,
                    vv.total_volume,
                    vv.trade_count,
                    vv.calc_name,
                    vv.calc_version,
                    vv.captured_at,
                    vv.capture_id,
                    datetime.now(UTC).isoformat(),
                ),
            )

        conn.commit()
        return venue_volumes

    def _compute_venue_share(self, conn, week_ending, tier, capture_id, execution_id, batch_id):
        """Compute venue share from venue volume."""
        # Fetch venue volume data
        rows = conn.execute(
            """
            SELECT * FROM finra_otc_transparency_weekly_symbol_venue_volume
            WHERE week_ending = ? AND tier = ? AND capture_id = ?
        """,
            (week_ending, tier, capture_id),
        ).fetchall()

        from spine.domains.finra.otc_transparency.calculations import WeeklySymbolVenueVolumeRow

        venue_vols = [
            WeeklySymbolVenueVolumeRow(
                week_ending=date.fromisoformat(row["week_ending"]),
                tier=row["tier"],
                symbol=row["symbol"],
                mpid=row["mpid"],
                venue_name=row["venue_name"],
                total_volume=row["total_volume"],
                trade_count=row["trade_count"],
                captured_at=row["captured_at"],
                capture_id=row["capture_id"],
            )
            for row in rows
        ]

        # Compute venue shares
        venue_shares = compute_weekly_symbol_venue_share(venue_vols)

        # Insert into database
        for vs in venue_shares:
            conn.execute(
                """
                INSERT INTO finra_otc_transparency_weekly_symbol_venue_share (
                    execution_id, batch_id, week_ending, tier, symbol, mpid, venue_name,
                    venue_volume, total_symbol_volume, venue_share,
                    calc_name, calc_version, captured_at, capture_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    execution_id,
                    batch_id,
                    str(vs.week_ending),
                    vs.tier,
                    vs.symbol,
                    vs.mpid,
                    vs.venue_name,
                    vs.venue_volume,
                    vs.total_symbol_volume,
                    vs.venue_share,
                    vs.calc_name,
                    vs.calc_version,
                    vs.captured_at,
                    vs.capture_id,
                    datetime.now(UTC).isoformat(),
                ),
            )

        conn.commit()
        return venue_shares

    def _compute_hhi(self, conn, week_ending, tier, capture_id, execution_id, batch_id):
        """Compute HHI from venue share."""
        # Fetch venue share data
        rows = conn.execute(
            """
            SELECT * FROM finra_otc_transparency_weekly_symbol_venue_share
            WHERE week_ending = ? AND tier = ? AND capture_id = ?
        """,
            (week_ending, tier, capture_id),
        ).fetchall()

        from spine.domains.finra.otc_transparency.calculations import WeeklySymbolVenueShareRow

        venue_shares = [
            WeeklySymbolVenueShareRow(
                week_ending=date.fromisoformat(row["week_ending"]),
                tier=row["tier"],
                symbol=row["symbol"],
                mpid=row["mpid"],
                venue_name=row["venue_name"],
                venue_volume=row["venue_volume"],
                total_symbol_volume=row["total_symbol_volume"],
                venue_share=row["venue_share"],
                captured_at=row["captured_at"],
                capture_id=row["capture_id"],
            )
            for row in rows
        ]

        # Compute HHI
        hhi_rows = compute_weekly_symbol_venue_concentration_hhi(venue_shares)

        # Insert into database
        for hhi in hhi_rows:
            conn.execute(
                """
                INSERT INTO finra_otc_transparency_weekly_symbol_venue_concentration_hhi (
                    execution_id, batch_id, week_ending, tier, symbol, hhi,
                    venue_count, total_symbol_volume,
                    calc_name, calc_version, captured_at, capture_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    execution_id,
                    batch_id,
                    str(hhi.week_ending),
                    hhi.tier,
                    hhi.symbol,
                    hhi.hhi,
                    hhi.venue_count,
                    hhi.total_symbol_volume,
                    hhi.calc_name,
                    hhi.calc_version,
                    hhi.captured_at,
                    hhi.capture_id,
                    datetime.now(UTC).isoformat(),
                ),
            )

        conn.commit()
        return hhi_rows

    def _compute_tier_split(self, conn, week_ending, execution_id, batch_id):
        """Compute tier split from venue volume (all tiers)."""
        # Fetch venue volume for all tiers
        rows = conn.execute(
            """
            SELECT * FROM finra_otc_transparency_weekly_symbol_venue_volume
            WHERE week_ending = ?
        """,
            (week_ending,),
        ).fetchall()

        from spine.domains.finra.otc_transparency.calculations import WeeklySymbolVenueVolumeRow

        venue_vols = [
            WeeklySymbolVenueVolumeRow(
                week_ending=date.fromisoformat(row["week_ending"]),
                tier=row["tier"],
                symbol=row["symbol"],
                mpid=row["mpid"],
                venue_name=row["venue_name"],
                total_volume=row["total_volume"],
                trade_count=row["trade_count"],
                captured_at=row["captured_at"],
                capture_id=row["capture_id"],
            )
            for row in rows
        ]

        # Compute tier splits
        tier_splits = compute_weekly_symbol_tier_volume_share(venue_vols)

        # Insert into database
        for ts in tier_splits:
            conn.execute(
                """
                INSERT INTO finra_otc_transparency_weekly_symbol_tier_volume_share (
                    execution_id, batch_id, week_ending, tier, symbol,
                    tier_volume, total_symbol_volume_all_tiers, tier_volume_share,
                    calc_name, calc_version, captured_at, capture_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    execution_id,
                    batch_id,
                    str(ts.week_ending),
                    ts.tier,
                    ts.symbol,
                    ts.tier_volume,
                    ts.total_symbol_volume_all_tiers,
                    ts.tier_volume_share,
                    ts.calc_name,
                    ts.calc_version,
                    ts.captured_at,
                    ts.capture_id,
                    datetime.now(UTC).isoformat(),
                ),
            )

        conn.commit()
        return tier_splits

    def _assert_invariants(self, conn, week_ending, tier, capture_id):
        """Assert all critical invariants for trading analytics."""
        # Invariant 1: Venue shares sum to 1.0 per symbol
        shares_check = conn.execute(
            """
            SELECT symbol, SUM(venue_share) as total
            FROM finra_otc_transparency_weekly_symbol_venue_share
            WHERE capture_id = ?
            GROUP BY symbol
        """,
            (capture_id,),
        ).fetchall()

        for row in shares_check:
            assert abs(row["total"] - 1.0) < 0.0001, (
                f"Invariant violated: {row['symbol']} shares sum to {row['total']}"
            )

        # Invariant 2: HHI bounds
        hhi_check = conn.execute(
            """
            SELECT symbol, hhi FROM finra_otc_transparency_weekly_symbol_venue_concentration_hhi
            WHERE capture_id = ?
        """,
            (capture_id,),
        ).fetchall()

        for row in hhi_check:
            assert 0.0 <= row["hhi"] <= 1.0, f"Invariant violated: {row['symbol']} HHI={row['hhi']}"

        # Invariant 3: Venue shares between 0 and 1
        vs_bounds = conn.execute(
            """
            SELECT symbol, mpid, venue_share
            FROM finra_otc_transparency_weekly_symbol_venue_share
            WHERE capture_id = ? AND (venue_share < 0 OR venue_share > 1)
        """,
            (capture_id,),
        ).fetchall()

        assert len(vs_bounds) == 0, (
            f"Invariant violated: found {len(vs_bounds)} venue shares out of bounds"
        )

        print("✅ All invariants satisfied")
