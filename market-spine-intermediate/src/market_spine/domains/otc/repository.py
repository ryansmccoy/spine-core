# src/market_spine/domains/otc/repository.py

"""Repository for PostgreSQL - Intermediate tier adds this."""

from datetime import date
from decimal import Decimal
from typing import Any

from market_spine.db import get_connection
from market_spine.domains.otc.models import RawRecord, VenueVolume, Tier


class OTCRepository:
    """
    Data access for OTC tables.

    Basic tier uses direct SQL.
    Intermediate adds repository pattern for cleaner code.
    """

    def insert_raw_batch(self, records: list[dict], batch_id: str) -> tuple[int, int]:
        """Insert raw records, return (inserted, duplicates)."""
        with get_connection() as conn:
            result = conn.execute("SELECT record_hash FROM otc.raw")
            existing_hashes = {r["record_hash"] for r in result.fetchall()}

            new_records = [r for r in records if r["record_hash"] not in existing_hashes]

            for r in new_records:
                conn.execute(
                    """
                    INSERT INTO otc.raw (
                        batch_id, record_hash, week_ending, tier,
                        symbol, issue_name, venue_name, mpid,
                        share_volume, trade_count, source_file
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        batch_id,
                        r["record_hash"],
                        r["week_ending"],
                        r["tier"],
                        r["symbol"],
                        r["issue_name"],
                        r["venue_name"],
                        r["mpid"],
                        r["share_volume"],
                        r["trade_count"],
                        r.get("source_file"),
                    ),
                )

            conn.commit()
            return len(new_records), len(records) - len(new_records)

    def get_unnormalized_raw_records(self) -> list[RawRecord]:
        """Get raw records that haven't been normalized yet."""
        with get_connection() as conn:
            result = conn.execute("""
                SELECT * FROM otc.raw 
                WHERE record_hash NOT IN (SELECT record_hash FROM otc.venue_volume)
            """)
            rows = result.fetchall()

            return [
                RawRecord(
                    tier=r["tier"],
                    symbol=r["symbol"],
                    issue_name=r["issue_name"],
                    venue_name=r["venue_name"],
                    mpid=r["mpid"],
                    share_volume=r["share_volume"],
                    trade_count=r["trade_count"],
                    week_ending=r["week_ending"],
                    record_hash=r["record_hash"],
                )
                for r in rows
            ]

    def get_week_stats(self, week_ending: date) -> dict[str, Any]:
        """Get summary stats for a week."""
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT 
                    COUNT(DISTINCT mpid) as venue_count,
                    COUNT(DISTINCT symbol) as symbol_count,
                    COALESCE(SUM(share_volume), 0) as total_volume
                FROM otc.venue_volume
                WHERE week_ending = %s
            """,
                (week_ending,),
            )
            row = result.fetchone()

            return {
                "venue_count": row["venue_count"] or 0,
                "symbol_count": row["symbol_count"] or 0,
                "total_volume": row["total_volume"] or 0,
            }

    def upsert_venue_volume(self, records: list[VenueVolume]) -> int:
        """Insert or update venue volume records."""
        with get_connection() as conn:
            for r in records:
                conn.execute(
                    """
                    INSERT INTO otc.venue_volume (
                        week_ending, tier, symbol, mpid,
                        share_volume, trade_count, avg_trade_size, record_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (week_ending, tier, symbol, mpid) 
                    DO UPDATE SET
                        share_volume = EXCLUDED.share_volume,
                        trade_count = EXCLUDED.trade_count,
                        avg_trade_size = EXCLUDED.avg_trade_size
                """,
                    (
                        r.week_ending,
                        r.tier.value,
                        r.symbol,
                        r.mpid,
                        r.share_volume,
                        r.trade_count,
                        str(r.avg_trade_size) if r.avg_trade_size else None,
                        r.record_hash,
                    ),
                )
            conn.commit()
            return len(records)

    def get_all_venue_volume(self) -> list[VenueVolume]:
        """Get all venue volume records."""
        with get_connection() as conn:
            result = conn.execute("SELECT * FROM otc.venue_volume")
            rows = result.fetchall()

            return [
                VenueVolume(
                    week_ending=r["week_ending"],
                    tier=Tier(r["tier"]),
                    symbol=r["symbol"],
                    mpid=r["mpid"],
                    share_volume=r["share_volume"],
                    trade_count=r["trade_count"],
                    avg_trade_size=Decimal(str(r["avg_trade_size"]))
                    if r["avg_trade_size"]
                    else None,
                    record_hash=r["record_hash"],
                )
                for r in rows
            ]

    def upsert_symbol_summaries(self, summaries: list) -> int:
        """Insert or update symbol summaries."""
        with get_connection() as conn:
            for s in summaries:
                conn.execute(
                    """
                    INSERT INTO otc.symbol_summary (
                        week_ending, tier, symbol, total_volume,
                        total_trades, venue_count, avg_trade_size
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (week_ending, tier, symbol) 
                    DO UPDATE SET
                        total_volume = EXCLUDED.total_volume,
                        total_trades = EXCLUDED.total_trades,
                        venue_count = EXCLUDED.venue_count,
                        avg_trade_size = EXCLUDED.avg_trade_size
                """,
                    (
                        s.week_ending,
                        s.tier.value,
                        s.symbol,
                        s.total_volume,
                        s.total_trades,
                        s.venue_count,
                        str(s.avg_trade_size) if s.avg_trade_size else None,
                    ),
                )
            conn.commit()
            return len(summaries)

    def upsert_venue_shares(self, venues: list) -> int:
        """Insert or update venue shares."""
        with get_connection() as conn:
            for v in venues:
                conn.execute(
                    """
                    INSERT INTO otc.venue_share (
                        week_ending, mpid, total_volume, total_trades,
                        symbol_count, market_share_pct, rank
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (week_ending, mpid) 
                    DO UPDATE SET
                        total_volume = EXCLUDED.total_volume,
                        total_trades = EXCLUDED.total_trades,
                        symbol_count = EXCLUDED.symbol_count,
                        market_share_pct = EXCLUDED.market_share_pct,
                        rank = EXCLUDED.rank
                """,
                    (
                        v.week_ending,
                        v.mpid,
                        v.total_volume,
                        v.total_trades,
                        v.symbol_count,
                        str(v.market_share_pct),
                        v.rank,
                    ),
                )
            conn.commit()
            return len(venues)
