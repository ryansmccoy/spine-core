"""
FINRA OTC file connector - parsing PSV files.

This module handles reading and parsing FINRA OTC transparency files.
It produces raw records that can then be validated and normalized.

FINRA OTC Weekly Data Semantics:
- FINRA publishes OTC weekly data on Mondays
- The data reflects trading activity from the prior Mon-Fri week
- lastUpdateDate in the file = publication date (Monday)
- week_ending = derived business time (previous Friday)

Example:
    File Date (Monday) | Derived Week Ending (Friday)
    2025-12-15         | 2025-12-12
    2025-12-22         | 2025-12-19
    2025-12-29         | 2025-12-26
"""

import csv
import hashlib
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path


@dataclass
class FileMetadata:
    """
    Metadata extracted from a FINRA OTC file for date inference.

    The pipeline uses this to determine the three clocks:
    - file_date: When the file was published (Monday)
    - week_ending: Business time (derived Friday)
    - captured_at: When we ingested it (set by pipeline)
    """

    file_date: date  # Publication date (from filename or content)
    week_ending: date  # Derived business time (Friday)
    source: str  # Where file_date came from: "filename", "content", "override"
    tier_hint: str | None = None  # Tier detected from filename (e.g., "tier1", "otc")


@dataclass
class RawOTCRecord:
    """
    A record as parsed from FINRA source file (bronze layer).

    Minimal processing - just convert strings to typed values.

    Clock 1: week_ending - Business time (the week the trading occurred)
    Clock 2: source_last_update_date - When FINRA last updated this row in their system
    """

    week_ending: date
    tier: str  # Raw tier string from file
    symbol: str  # Raw symbol (may need normalization)
    mpid: str  # Market participant ID
    total_shares: int
    total_trades: int
    source_last_update_date: date | None = None  # FINRA lastUpdateDate (Clock 2)
    issue_name: str = ""  # Company name (optional)
    venue_name: str = ""  # Full venue name (optional)
    source_line: int = 0  # Line number in source file
    record_hash: str = field(default="")

    def __post_init__(self):
        if not self.record_hash:
            self.record_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute deterministic hash for deduplication."""
        content = f"{self.week_ending.isoformat()}|{self.tier}|{self.symbol}|{self.mpid}|{self.total_shares}|{self.total_trades}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]


def parse_finra_file(path: str | Path) -> Iterator[RawOTCRecord]:
    """
    Parse a FINRA OTC weekly transparency PSV file.

    FINRA files are pipe-delimited with headers like:
    - tierDescription
    - issueSymbolIdentifier
    - issueName
    - marketParticipantName
    - MPID
    - totalWeeklyShareQuantity
    - totalWeeklyTradeCount
    - lastUpdateDate

    Args:
        path: Path to PSV file

    Yields:
        RawOTCRecord for each valid row
    """
    path = Path(path)

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")

        for i, row in enumerate(reader, start=2):  # Line 1 is header
            record = _parse_row(row, i)
            if record:
                yield record


def parse_finra_content(content: str) -> Iterator[RawOTCRecord]:
    """
    Parse FINRA data from string content.

    Useful for HTTP downloads or testing.
    """
    reader = csv.DictReader(io.StringIO(content), delimiter="|")

    for i, row in enumerate(reader, start=2):
        record = _parse_row(row, i)
        if record:
            yield record


def parse_simple_psv(path: str | Path) -> Iterator[RawOTCRecord]:
    """
    Parse simplified PSV format (for testing).

    Expected columns:
    WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades

    Header is auto-detected (starts with "WeekEnding").
    """
    path = Path(path)

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # Detect header
    start = 1 if lines and lines[0].strip().lower().startswith("weekending") else 0

    for i, line in enumerate(lines[start:], start=start + 1):
        parts = line.strip().split("|")
        if len(parts) < 6:
            continue

        try:
            yield RawOTCRecord(
                week_ending=date.fromisoformat(parts[0].strip()),
                tier=parts[1].strip(),
                symbol=parts[2].strip().upper(),
                mpid=parts[3].strip().upper(),
                total_shares=int(parts[4].strip()),
                total_trades=int(parts[5].strip()),
                source_line=i,
            )
        except (ValueError, IndexError):
            continue


def _parse_row(row: dict, line_num: int) -> RawOTCRecord | None:
    """Parse a single row from FINRA format."""
    try:
        # Extract week_ending (business time - Clock 1)
        # Look for weekEnding first, otherwise derive from lastUpdateDate
        week_str = row.get("weekEnding") or row.get("WeekEnding", "")

        if week_str:
            week_ending = _parse_date(week_str)
        else:
            # FINRA files have lastUpdateDate (Monday publication date)
            # Derive week_ending (previous Friday) from it
            last_update_str = row.get("lastUpdateDate", "")
            publish_date = _parse_date(last_update_str)
            if publish_date:
                week_ending = derive_week_ending_from_publish_date(publish_date)
            else:
                week_ending = None

        if week_ending is None:
            return None

        # Extract source_last_update_date (FINRA source time - Clock 2)
        source_last_update = _parse_date(row.get("lastUpdateDate", ""))

        return RawOTCRecord(
            week_ending=week_ending,
            tier=row.get("tierDescription", row.get("Tier", "")),
            symbol=(row.get("issueSymbolIdentifier") or row.get("Symbol", "")).upper().strip(),
            mpid=(row.get("MPID") or row.get("mpid", "")).upper().strip(),
            total_shares=int(row.get("totalWeeklyShareQuantity") or row.get("TotalShares", 0)),
            total_trades=int(row.get("totalWeeklyTradeCount") or row.get("TotalTrades", 0)),
            source_last_update_date=source_last_update,  # Clock 2
            issue_name=row.get("issueName", ""),
            venue_name=row.get("marketParticipantName", ""),
            source_line=line_num,
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _parse_date(value: str) -> date | None:
    """Parse date from various formats."""
    if not value:
        return None

    value = value.strip()

    # Try ISO format first
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass

    # Try YYYY-MM-DD with time
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        pass

    return None


def derive_week_ending_from_publish_date(publish_date: date) -> date:
    """
    Derive the week_ending (Friday) from FINRA's publication date.

    FINRA publishes OTC weekly data on Mondays. The data reflects
    trading activity from the previous Mon-Fri week.

    Rule: week_ending = file_date - 3 days (for Monday publication)

    Example:
        2025-12-22 (Mon) -> 2025-12-19 (Fri)
        2025-12-29 (Mon) -> 2025-12-26 (Fri)

    Note: For period-agnostic code, use:
        from sources import resolve_period
        period = resolve_period("weekly")
        week_ending = period.derive_period_end(publish_date)
    """
    # Monday is weekday 0, Friday is weekday 4
    # If it's Monday (0), previous Friday is 3 days back
    days_since_friday = (publish_date.weekday() - 4) % 7
    if days_since_friday == 0:
        days_since_friday = 7  # If it's Friday, go back a week
    return publish_date - timedelta(days=days_since_friday)


def extract_file_date_from_filename(path: str | Path) -> date | None:
    """
    Extract the publication date from a FINRA filename.

    Supports patterns:
        finra_otc_weekly_tier1_20251222.csv -> 2025-12-22
        finra_otc_weekly_otc_20251215.csv   -> 2025-12-15
        nms_tier1_2025-12-26.psv            -> 2025-12-26

    Returns None if no date pattern found.
    """
    filename = Path(path).stem  # Remove extension

    # Pattern 1: YYYYMMDD (e.g., 20251222)
    match = re.search(r"(\d{4})(\d{2})(\d{2})$", filename)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    # Pattern 2: YYYY-MM-DD anywhere in filename
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    return None


def extract_tier_from_filename(path: str | Path) -> str | None:
    """
    Extract tier hint from FINRA filename.

    Supports patterns:
        finra_otc_weekly_tier1_... -> NMS_TIER_1
        finra_otc_weekly_tier2_... -> NMS_TIER_2
        finra_otc_weekly_otc_...   -> OTC

    Returns None if no tier pattern found.
    """
    filename = Path(path).stem.lower()

    if "tier1" in filename or "tier_1" in filename:
        return "NMS_TIER_1"
    elif "tier2" in filename or "tier_2" in filename:
        return "NMS_TIER_2"
    elif "_otc_" in filename:
        return "OTC"

    return None


def extract_file_date_from_content(path: str | Path) -> date | None:
    """
    Extract publication date from file content (lastUpdateDate column).

    Reads the first data row to get the date.
    Returns None if file cannot be parsed or date not found.
    """
    path = Path(path)
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="|")
            for row in reader:
                last_update = row.get("lastUpdateDate", "")
                return _parse_date(last_update)
    except Exception:
        pass
    return None


def get_file_metadata(
    path: str | Path,
    week_ending_override: date | None = None,
    file_date_override: date | None = None,
) -> FileMetadata:
    """
    Extract complete metadata from a FINRA file for pipeline use.

    Determines file_date using this precedence:
    1. file_date_override (if provided)
    2. Date from filename
    3. lastUpdateDate from file content
    4. Raises ValueError if none found

    Determines week_ending:
    1. week_ending_override (if provided)
    2. Derived from file_date using FINRA rule (file_date - 3 days)

    Args:
        path: Path to FINRA file
        week_ending_override: Explicit week_ending (for dev/backfill)
        file_date_override: Explicit file_date (for dev/backfill)

    Returns:
        FileMetadata with file_date, week_ending, source, and tier_hint

    Raises:
        ValueError: If file_date cannot be determined
    """
    path = Path(path)

    # Determine file_date with precedence
    if file_date_override:
        file_date = file_date_override
        source = "override"
    else:
        # Try filename first
        file_date = extract_file_date_from_filename(path)
        if file_date:
            source = "filename"
        else:
            # Fall back to content
            file_date = extract_file_date_from_content(path)
            if file_date:
                source = "content"
            else:
                raise ValueError(f"Could not determine file_date from filename or content: {path}")

    # Determine week_ending
    if week_ending_override:
        week_ending = week_ending_override
        source = "override"  # Override takes precedence for source label
    else:
        week_ending = derive_week_ending_from_publish_date(file_date)

    # Extract tier hint from filename
    tier_hint = extract_tier_from_filename(path)

    return FileMetadata(
        file_date=file_date,
        week_ending=week_ending,
        source=source,
        tier_hint=tier_hint,
    )


def detect_week_ending_from_file(path: str | Path) -> date | None:
    """
    Read first data row of a FINRA file and derive week_ending from lastUpdateDate.

    Returns the Friday (week_ending) for the data in this file.
    Returns None if file cannot be parsed or date not found.

    DEPRECATED: Use get_file_metadata() instead for full context.
    """
    path = Path(path)
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="|")
            for row in reader:
                last_update = row.get("lastUpdateDate", "")
                publish_date = _parse_date(last_update)
                if publish_date:
                    return derive_week_ending_from_publish_date(publish_date)
                break  # Only check first row
    except Exception:
        pass
    return None
