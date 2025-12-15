"""
Deterministic hashing utilities for record deduplication and lineage.

Provides stable, reproducible hash functions that enable idempotent ingestion
and content-based change detection. Hash values are used throughout spine-core
for L2 idempotency (same input → same output) and record tracking.

Manifesto:
    Data pipelines need stable identifiers that survive re-processing:
    - **Natural key hash:** Identify records by business key
    - **Content hash:** Detect when record data has changed
    - **Deterministic:** Same inputs always produce same hash
    - **Collision-resistant:** Different inputs produce different hashes

    compute_hash() provides the foundation - a simple, deterministic SHA-256
    based hash that works with any combination of values.

Architecture:
    ::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Hashing Patterns                          │
        └─────────────────────────────────────────────────────────────┘

        Natural Key Hash (L2_INPUT dedup):
        ┌────────────────────────────────────────────────────────────┐
        │ hash = compute_hash(week, tier, symbol, mpid)              │
        │                                                            │
        │ Same (week, tier, symbol, mpid) → Same hash               │
        │ Different values → Different hash                         │
        └────────────────────────────────────────────────────────────┘

        Content Hash (change detection):
        ┌────────────────────────────────────────────────────────────┐
        │ hash = compute_hash(week, tier, symbol, mpid, shares)     │
        │                                                            │
        │ Same record + same data → Same hash                       │
        │ Same record + different data → Different hash (UPDATE!)   │
        └────────────────────────────────────────────────────────────┘

Features:
    - **compute_hash():** Generic hash from any values
    - **compute_record_hash():** OTC-specific record hash
    - **Configurable length:** Default 32 chars (128 bits)
    - **SHA-256 based:** Cryptographically sound

Examples:
    Basic usage:

    >>> compute_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
    'a1b2c3d4...'  # 32-char hex string

    Content-based dedup:

    >>> h1 = compute_hash("2025-12-26", "AAPL", 1000)
    >>> h2 = compute_hash("2025-12-26", "AAPL", 1000)
    >>> h1 == h2
    True
    >>> h3 = compute_hash("2025-12-26", "AAPL", 2000)  # Different volume
    >>> h1 == h3
    False

Tags:
    hashing, deduplication, idempotency, lineage, spine-core

Doc-Types:
    - API Reference
    - Idempotency Patterns Guide
"""

import hashlib
from typing import Any


def compute_hash(*values: Any, length: int = 32) -> str:
    """
    Compute deterministic hash from values.

    Creates a stable, reproducible hash by concatenating string representations
    of all values with '|' delimiter, then computing SHA-256. This is the
    foundational hash function for spine-core's deduplication patterns.

    Manifesto:
        Hashing must be:
        - **Deterministic:** Same inputs → same output, always
        - **Order-dependent:** (a, b) ≠ (b, a)
        - **Type-agnostic:** Converts everything to strings
        - **Collision-resistant:** SHA-256 provides strong guarantees

    Examples:
        Basic hashing:

        >>> compute_hash("2025-12-26", "NMS_TIER_1")
        'a1b2c3d4e5f6...'  # 32-char hex

        Hash depends on order:

        >>> compute_hash("a", "b") != compute_hash("b", "a")
        True

        Shorter hash:

        >>> len(compute_hash("test", length=16))
        16

    Args:
        *values: Values to hash (converted to strings)
        length: Hex digest length (default 32 = 128 bits)

    Returns:
        Hex string of specified length

    Tags:
        hashing, utility, spine-core
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
    Compute hash for an OTC-style record with optional content.

    Produces either a natural key hash (for dedup by identity) or a content
    hash (for change detection). When total_shares/total_trades are provided,
    the hash changes if the data changes - enabling update detection.

    Manifesto:
        OTC transparency records have a natural key: (week_ending, tier, symbol, mpid).
        Two hashing modes:
        - **Natural key only:** Identifies the record (same record = same hash)
        - **With content:** Detects updates (same record + new data = new hash)

    Architecture:
        ```
        Natural Key Hash (identity):
        ┌─────────────────────────────────────┐
        │ compute_record_hash(week, tier,     │
        │                     symbol, mpid)   │
        │                                     │
        │ Same record → Same hash             │
        │ (Used for L2 dedup)                 │
        └─────────────────────────────────────┘

        Content Hash (change detection):
        ┌─────────────────────────────────────┐
        │ compute_record_hash(week, tier,     │
        │     symbol, mpid, shares, trades)   │
        │                                     │
        │ Same record + same data → Same hash │
        │ Same record + new data → New hash   │
        │ (Used for UPDATE detection)         │
        └─────────────────────────────────────┘
        ```

    Examples:
        Natural key hash (dedup by identity):

        >>> h1 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
        >>> h2 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE")
        >>> h1 == h2
        True

        Content hash (detect updates):

        >>> h1 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 1000, 50)
        >>> h2 = compute_record_hash("2025-12-26", "NMS_TIER_1", "AAPL", "NITE", 2000, 75)
        >>> h1 == h2
        False  # Data changed!

    Args:
        week_ending: ISO date string (Friday)
        tier: Tier value (e.g., "NMS_TIER_1")
        symbol: Stock symbol
        mpid: Market participant ID
        total_shares: Optional share volume (for content hash)
        total_trades: Optional trade count (for content hash)

    Returns:
        32-char hex hash

    Tags:
        hashing, otc, record-hash, deduplication, spine-core
    """
    if total_shares is not None and total_trades is not None:
        return compute_hash(week_ending, tier, symbol, mpid, total_shares, total_trades)
    return compute_hash(week_ending, tier, symbol, mpid)
