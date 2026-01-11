"""
Record validation and normalization (bronze -> silver).

This module validates RawOTCRecords and transforms them into clean,
analysis-ready records. Invalid records are rejected with clear reasons.

The normalizer enforces:
- Valid tier values (NMS_TIER_1, NMS_TIER_2, OTC)
- Non-empty symbols and MPIDs
- Non-negative share/trade counts
- Proper symbol cleaning
"""

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date

from spine.domains.finra.otc_transparency.connector import RawOTCRecord
from spine.domains.finra.otc_transparency.schema import Tier


@dataclass
class NormalizedRecord:
    """
    A validated, normalized OTC record (silver layer).

    All fields are guaranteed to be valid:
    - Tier is a valid Tier enum value
    - Symbol is uppercase and cleaned
    - MPID is uppercase and non-empty
    - Counts are non-negative

    Clock 1: week_ending - Business time (when trading occurred)
    Clock 2: source_last_update_date - When FINRA updated the row
    Clock 3: captured_at - Set by pipeline when ingested (not stored here)
    """

    week_ending: date
    tier: Tier
    symbol: str
    mpid: str
    total_shares: int
    total_trades: int
    source_last_update_date: date | None = None  # Clock 2
    issue_name: str = ""
    venue_name: str = ""
    record_hash: str = ""
    source_line: int = 0


@dataclass
class RejectedRecord:
    """Record that failed validation with reason."""

    raw: RawOTCRecord
    reasons: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Container for normalized records and rejections."""

    valid: list[NormalizedRecord]
    rejected: list[RejectedRecord]

    @property
    def total(self) -> int:
        return len(self.valid) + len(self.rejected)

    @property
    def rejection_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return len(self.rejected) / self.total

    # Backward compatibility aliases
    @property
    def accepted(self) -> list[NormalizedRecord]:
        """Alias for valid (backward compatibility)."""
        return self.valid

    @property
    def accepted_count(self) -> int:
        """Count of valid records (backward compatibility)."""
        return len(self.valid)

    @property
    def rejected_count(self) -> int:
        """Count of rejected records."""
        return len(self.rejected)


# Tier mappings for normalization
TIER_ALIASES: dict[str, Tier] = {
    # Standard names
    "NMS_TIER_1": Tier.NMS_TIER_1,
    "NMS_TIER_2": Tier.NMS_TIER_2,
    "OTC": Tier.OTC,
    # Common variations
    "NMS Tier 1": Tier.NMS_TIER_1,
    "NMS Tier 2": Tier.NMS_TIER_2,
    "NMS TIER 1": Tier.NMS_TIER_1,
    "NMS TIER 2": Tier.NMS_TIER_2,
    "tier1": Tier.NMS_TIER_1,
    "tier2": Tier.NMS_TIER_2,
    "TIER1": Tier.NMS_TIER_1,
    "TIER2": Tier.NMS_TIER_2,
    "Tier 1": Tier.NMS_TIER_1,
    "Tier 2": Tier.NMS_TIER_2,
    "OTC Other": Tier.OTC,
    "otc": Tier.OTC,
}


def normalize_tier(tier_str: str) -> Tier | None:
    """
    Normalize a tier string to a Tier enum.

    Handles variations like:
        "NMS Tier 1" -> Tier.NMS_TIER_1
        "tier1" -> Tier.NMS_TIER_1
        "OTC Other" -> Tier.OTC

    Returns None if tier cannot be normalized.
    """
    tier_clean = tier_str.strip()

    # Direct match
    if tier_clean in TIER_ALIASES:
        return TIER_ALIASES[tier_clean]

    # Case-insensitive try
    tier_lower = tier_clean.lower()
    for key, value in TIER_ALIASES.items():
        if key.lower() == tier_lower:
            return value

    # Pattern matching
    if "tier" in tier_lower and "1" in tier_lower:
        return Tier.NMS_TIER_1
    if "tier" in tier_lower and "2" in tier_lower:
        return Tier.NMS_TIER_2
    if "otc" in tier_lower:
        return Tier.OTC

    return None


def clean_symbol(symbol: str) -> str:
    """
    Clean and normalize a stock symbol.

    - Uppercase
    - Remove leading/trailing whitespace
    - Remove special characters except common ones (., -, /)
    """
    cleaned = symbol.strip().upper()
    # Allow letters, numbers, dots, hyphens
    cleaned = re.sub(r"[^A-Z0-9.\-/]", "", cleaned)
    return cleaned


def validate_record(raw: RawOTCRecord) -> tuple[NormalizedRecord | None, list[str]]:
    """
    Validate and normalize a single raw record.

    Returns:
        (NormalizedRecord, []) if valid
        (None, [reasons]) if invalid
    """
    reasons: list[str] = []

    # Validate tier
    tier = normalize_tier(raw.tier)
    if tier is None:
        reasons.append(f"Invalid tier: '{raw.tier}'")

    # Validate symbol
    symbol = clean_symbol(raw.symbol)
    if not symbol:
        reasons.append(f"Empty symbol after cleaning: '{raw.symbol}'")
    elif len(symbol) > 20:  # Sanity check
        reasons.append(f"Symbol too long: '{symbol}' ({len(symbol)} chars)")

    # Validate MPID
    mpid = raw.mpid.strip().upper()
    if not mpid:
        reasons.append("Empty MPID")
    elif len(mpid) > 20:  # Sanity check
        reasons.append(f"MPID too long: '{mpid}' ({len(mpid)} chars)")

    # Validate counts
    if raw.total_shares < 0:
        reasons.append(f"Negative share count: {raw.total_shares}")
    if raw.total_trades < 0:
        reasons.append(f"Negative trade count: {raw.total_trades}")

    # Skip zero-volume records (they're noise)
    if raw.total_shares == 0 and raw.total_trades == 0:
        reasons.append("Zero volume record (0 shares, 0 trades)")

    # If any validation failed, return None
    if reasons:
        return None, reasons

    # Create normalized record
    return NormalizedRecord(
        week_ending=raw.week_ending,
        tier=tier,  # type: ignore  # We checked above
        symbol=symbol,
        mpid=mpid,
        total_shares=raw.total_shares,
        total_trades=raw.total_trades,
        source_last_update_date=raw.source_last_update_date,
        issue_name=raw.issue_name.strip(),
        venue_name=raw.venue_name.strip(),
        record_hash=raw.record_hash,
        source_line=raw.source_line,
    ), []


def normalize_records(
    records: Sequence[RawOTCRecord],
    reject_zero_volume: bool = True,
) -> ValidationResult:
    """
    Validate and normalize a batch of raw records.

    Args:
        records: Raw records to normalize
        reject_zero_volume: If True, reject records with 0 shares and 0 trades

    Returns:
        ValidationResult with valid and rejected records
    """
    valid: list[NormalizedRecord] = []
    rejected: list[RejectedRecord] = []

    for raw in records:
        normalized, reasons = validate_record(raw)

        # If not rejecting zero volume, remove that reason and retry
        if not reject_zero_volume and reasons == ["Zero volume record (0 shares, 0 trades)"]:
            # Still need the tier/symbol validation
            tier = normalize_tier(raw.tier)
            symbol = clean_symbol(raw.symbol)
            mpid = raw.mpid.strip().upper()

            if tier and symbol and mpid:
                normalized = NormalizedRecord(
                    week_ending=raw.week_ending,
                    tier=tier,
                    symbol=symbol,
                    mpid=mpid,
                    total_shares=0,
                    total_trades=0,
                    source_last_update_date=raw.source_last_update_date,
                    issue_name=raw.issue_name.strip(),
                    venue_name=raw.venue_name.strip(),
                    record_hash=raw.record_hash,
                    source_line=raw.source_line,
                )
                reasons = []

        if normalized:
            valid.append(normalized)
        else:
            rejected.append(RejectedRecord(raw=raw, reasons=reasons))

    return ValidationResult(valid=valid, rejected=rejected)


def normalize_stream(
    records: Iterator[RawOTCRecord],
    reject_zero_volume: bool = True,
) -> Iterator[NormalizedRecord]:
    """
    Stream-friendly normalization - yields only valid records.

    Silently drops invalid records. Use normalize_records() if you
    need to track rejections.
    """
    for raw in records:
        normalized, reasons = validate_record(raw)

        # Handle zero volume special case
        if not reject_zero_volume and reasons == ["Zero volume record (0 shares, 0 trades)"]:
            tier = normalize_tier(raw.tier)
            symbol = clean_symbol(raw.symbol)
            mpid = raw.mpid.strip().upper()

            if tier and symbol and mpid:
                yield NormalizedRecord(
                    week_ending=raw.week_ending,
                    tier=tier,
                    symbol=symbol,
                    mpid=mpid,
                    total_shares=0,
                    total_trades=0,
                    source_last_update_date=raw.source_last_update_date,
                    issue_name=raw.issue_name.strip(),
                    venue_name=raw.venue_name.strip(),
                    record_hash=raw.record_hash,
                    source_line=raw.source_line,
                )
            continue

        if normalized:
            yield normalized
