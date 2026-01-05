"""
Deterministic hashing utilities for record deduplication.

Hash functions produce stable, reproducible hashes for records
to enable idempotent ingestion and lineage tracking.
"""

import hashlib
from typing import Any


def compute_hash(*values: Any, length: int = 32) -> str:
    """
    Compute deterministic hash from values.

    Args:
        *values: Values to hash (converted to strings)
        length: Hex digest length (default 32 = 128 bits)

    Returns:
        Hex string of specified length

    Example:
        >>> compute_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
        'a1b2c3d4e5f6...'
    """
    content = "|".join(str(v) for v in values)
    return hashlib.sha256(content.encode()).hexdigest()[:length]


def compute_record_hash(
    week_ending: str,
    tier: str,
    symbol: str,
    mpid: str,
    total_shares: int = None,
    total_trades: int = None,
) -> str:
    """
    Compute hash for an OTC-style record.

    Uses natural key by default. If volume/trades provided,
    includes them (for content-based dedup).

    Args:
        week_ending: ISO date string
        tier: Tier value
        symbol: Stock symbol
        mpid: Market participant ID
        total_shares: Optional share volume (for content hash)
        total_trades: Optional trade count (for content hash)

    Returns:
        32-char hex hash
    """
    if total_shares is not None and total_trades is not None:
        return compute_hash(week_ending, tier, symbol, mpid, total_shares, total_trades)
    return compute_hash(week_ending, tier, symbol, mpid)
