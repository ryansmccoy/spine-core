# src/market_spine/domains/otc/normalizer.py

"""
Normalization logic - shared across all tiers.

Copy this file directly to each project.
"""

from decimal import Decimal

from market_spine.domains.otc.models import (
    RawRecord,
    VenueVolume,
    NormalizeResult,
    Tier,
)


def normalize_records(records: list[RawRecord]) -> NormalizeResult:
    """
    Normalize raw FINRA records into VenueVolume records.

    Transformations:
    - Parse tier string to enum
    - Calculate avg trade size
    - Skip records with negative values
    """
    accepted = []
    rejected = 0

    for raw in records:
        # Validate
        if raw.share_volume < 0 or raw.trade_count < 0:
            rejected += 1
            continue

        # Parse tier
        try:
            tier = Tier.from_finra(raw.tier)
        except ValueError:
            rejected += 1
            continue

        # Calculate avg trade size
        avg_size = None
        if raw.trade_count > 0:
            avg_size = Decimal(raw.share_volume) / Decimal(raw.trade_count)

        accepted.append(
            VenueVolume(
                week_ending=raw.week_ending,
                tier=tier,
                symbol=raw.symbol,
                mpid=raw.mpid,
                share_volume=raw.share_volume,
                trade_count=raw.trade_count,
                avg_trade_size=avg_size,
                record_hash=raw.record_hash,
            )
        )

    return NormalizeResult(
        processed=len(records),
        accepted=len(accepted),
        rejected=rejected,
        records=accepted,
    )
