# src/market_spine/domains/otc/calculations.py

"""
Aggregation calculations - shared across all tiers.

Copy this file directly to each project.
"""

from collections import defaultdict
from decimal import Decimal

from market_spine.domains.otc.models import (
    VenueVolume,
    SymbolSummary,
    VenueShare,
)


def compute_symbol_summaries(venue_data: list[VenueVolume]) -> list[SymbolSummary]:
    """
    Aggregate venue data to symbol summaries.

    Groups by (week, tier, symbol) and sums volumes.
    """
    groups: dict[tuple, list[VenueVolume]] = defaultdict(list)

    for v in venue_data:
        key = (v.week_ending, v.tier, v.symbol)
        groups[key].append(v)

    summaries = []
    for (week, tier, symbol), venues in groups.items():
        total_vol = sum(v.share_volume for v in venues)
        total_trades = sum(v.trade_count for v in venues)

        avg_size = None
        if total_trades > 0:
            avg_size = Decimal(total_vol) / Decimal(total_trades)

        summaries.append(
            SymbolSummary(
                week_ending=week,
                tier=tier,
                symbol=symbol,
                total_volume=total_vol,
                total_trades=total_trades,
                venue_count=len(venues),
                avg_trade_size=avg_size,
            )
        )

    return summaries


def compute_venue_shares(venue_data: list[VenueVolume]) -> list[VenueShare]:
    """
    Compute venue market share across all symbols.

    Groups by (week, mpid) and calculates % of total.
    """
    # Calculate weekly totals
    week_totals: dict = defaultdict(int)
    for v in venue_data:
        week_totals[v.week_ending] += v.share_volume

    # Group by (week, mpid)
    groups: dict[tuple, list[VenueVolume]] = defaultdict(list)
    for v in venue_data:
        groups[(v.week_ending, v.mpid)].append(v)

    results = []
    for (week, mpid), venues in groups.items():
        total_vol = sum(v.share_volume for v in venues)
        total_trades = sum(v.trade_count for v in venues)
        symbols = {v.symbol for v in venues}

        week_total = week_totals[week]
        share_pct = Decimal(0)
        if week_total > 0:
            share_pct = (Decimal(total_vol) / Decimal(week_total) * 100).quantize(Decimal("0.01"))

        results.append(
            VenueShare(
                week_ending=week,
                mpid=mpid,
                total_volume=total_vol,
                total_trades=total_trades,
                symbol_count=len(symbols),
                market_share_pct=share_pct,
            )
        )

    # Rank by volume per week
    by_week: dict = defaultdict(list)
    for r in results:
        by_week[r.week_ending].append(r)

    for week, venues in by_week.items():
        venues.sort(key=lambda v: v.total_volume, reverse=True)
        for i, v in enumerate(venues, 1):
            v.rank = i

    return results
