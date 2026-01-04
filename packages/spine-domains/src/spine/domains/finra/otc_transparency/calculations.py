"""
Pure aggregation functions (silver -> gold).

These functions aggregate normalized OTC records into venue-level
and symbol-level summaries. They're pure functions operating on
in-memory data structures - no database dependencies.

Aggregation Layers:
1. Venue Volume: Group by (week, tier, symbol, mpid) - already in raw data
2. Symbol Aggregate: Group by (week, tier, symbol) - sum across venues
3. Venue Share: Group by (week, tier, mpid) - market share per venue
4. Rolling: Time-series across weeks

All functions preserve the 3-clock model:
- week_ending: Business time (aggregation key)
- source_last_update_date: Max of source dates in group
- captured_at: Passed through (set by pipeline)

FIELD CLASSIFICATION (for determinism tests):
- Deterministic: All business keys, calc outputs, calc_name, calc_version, capture_id
- Audit-only: calculated_at, ingested_at, normalized_at (vary by wall-clock)
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields
from datetime import date, timedelta
from typing import Any

from spine.domains.finra.otc_transparency.schema import Tier


# =============================================================================
# DETERMINISM HELPERS
# =============================================================================

# Fields that are audit-only and should be excluded from determinism assertions
AUDIT_FIELDS = frozenset({
    "calculated_at",
    "ingested_at", 
    "normalized_at",
    "computed_at",
    "id",  # Auto-increment IDs
    "rn",  # Row numbers from window functions
})


def strip_audit_fields(row: dict | Any) -> dict:
    """
    Strip audit-only fields from a row for deterministic comparison.
    
    Use this when comparing calc outputs across runs.
    """
    if hasattr(row, "__dataclass_fields__"):
        row = asdict(row)
    elif not isinstance(row, dict):
        row = dict(row)
    
    return {k: v for k, v in row.items() if k not in AUDIT_FIELDS}


def rows_equal_deterministic(rows1: Sequence, rows2: Sequence) -> bool:
    """
    Compare two sequences of rows, ignoring audit fields.
    
    Returns True if all deterministic fields match.
    """
    if len(rows1) != len(rows2):
        return False
    
    stripped1 = [strip_audit_fields(r) for r in rows1]
    stripped2 = [strip_audit_fields(r) for r in rows2]
    
    # Sort by all keys for consistent comparison
    def sort_key(d: dict) -> tuple:
        return tuple(sorted(d.items()))
    
    return sorted(stripped1, key=sort_key) == sorted(stripped2, key=sort_key)


@dataclass
class VenueVolumeRow:
    """
    Venue-level volume (one row per symbol+mpid per week).

    This is essentially the normalized data reshaped for the database.
    Clock 1 (week_ending) and Clock 2 (source_last_update_date) preserved.
    """

    week_ending: date
    tier: Tier
    symbol: str
    mpid: str
    total_shares: int
    total_trades: int
    source_last_update_date: date | None = None  # Clock 2


@dataclass
class SymbolAggregateRow:
    """
    Symbol-level aggregate (sum across all venues for a symbol).

    Derived from venue-level data:
    - total_shares = sum of shares across all MPIDs
    - total_trades = sum of trades across all MPIDs
    - venue_count = number of distinct MPIDs

    Clock 2 = max(source_last_update_date) across contributing rows.
    """

    week_ending: date
    tier: Tier
    symbol: str
    total_shares: int
    total_trades: int
    venue_count: int
    source_last_update_date: date | None = None  # Max of Clock 2

    @property
    def total_volume(self) -> int:
        """Alias for total_shares (backward compatibility)."""
        return self.total_shares


@dataclass
class RollingRow:
    """
    Rolling statistics for a symbol (time-series view).

    Contains point-in-time data plus rolling calculations:
    - shares_4wk: Sum of shares over trailing 4 weeks
    - shares_13wk: Sum of shares over trailing 13 weeks
    - trades_4wk, trades_13wk: Similar for trades
    """

    week_ending: date
    tier: Tier
    symbol: str
    total_shares: int
    total_trades: int
    venue_count: int
    shares_4wk: int | None = None
    shares_13wk: int | None = None
    trades_4wk: int | None = None
    trades_13wk: int | None = None
    source_last_update_date: date | None = None  # Max Clock 2


def aggregate_to_symbol_level(
    venue_rows: Sequence[VenueVolumeRow],
) -> list[SymbolAggregateRow]:
    """
    Aggregate venue-level data to symbol-level.

    Groups by (week_ending, tier, symbol) and computes:
    - total_shares: Sum across venues
    - total_trades: Sum across venues
    - venue_count: Count of distinct MPIDs
    - source_last_update_date: Max of source dates

    Args:
        venue_rows: Venue-level records (from normalized data)

    Returns:
        List of symbol-level aggregates
    """
    # Group by (week, tier, symbol)
    groups: dict[tuple[date, Tier, str], list[VenueVolumeRow]] = defaultdict(list)

    for row in venue_rows:
        key = (row.week_ending, row.tier, row.symbol)
        groups[key].append(row)

    # Compute aggregates
    results: list[SymbolAggregateRow] = []

    for (week, tier, symbol), rows in sorted(groups.items()):
        total_shares = sum(r.total_shares for r in rows)
        total_trades = sum(r.total_trades for r in rows)
        venue_count = len(set(r.mpid for r in rows))

        # Max source_last_update_date (Clock 2)
        source_dates = [r.source_last_update_date for r in rows if r.source_last_update_date]
        max_source_date = max(source_dates) if source_dates else None

        results.append(
            SymbolAggregateRow(
                week_ending=week,
                tier=tier,
                symbol=symbol,
                total_shares=total_shares,
                total_trades=total_trades,
                venue_count=venue_count,
                source_last_update_date=max_source_date,
            )
        )

    return results


def compute_rolling_stats(
    symbol_rows: Sequence[SymbolAggregateRow],
    target_week: date,
    tier: Tier,
    symbol: str,
) -> RollingRow | None:
    """
    Compute rolling statistics for a single symbol at a point in time.

    Requires historical data for the symbol to compute trailing sums.
    Returns None if no data exists for the target week.

    Rolling windows:
    - 4wk: Current week + 3 prior weeks
    - 13wk: Current week + 12 prior weeks
    """
    # Filter to just this symbol/tier
    symbol_data = [r for r in symbol_rows if r.tier == tier and r.symbol == symbol]

    if not symbol_data:
        return None

    # Build week -> row lookup
    by_week: dict[date, SymbolAggregateRow] = {r.week_ending: r for r in symbol_data}

    # Check if we have data for target week
    if target_week not in by_week:
        return None

    current = by_week[target_week]

    # Compute trailing weeks
    weeks_4 = [target_week - timedelta(weeks=i) for i in range(4)]
    weeks_13 = [target_week - timedelta(weeks=i) for i in range(13)]

    def sum_weeks(weeks: list[date], field: str) -> int | None:
        """Sum a field over a list of weeks, None if insufficient data."""
        values = []
        for w in weeks:
            if w in by_week:
                values.append(getattr(by_week[w], field))
        # Require at least 50% of weeks to have data
        if len(values) >= len(weeks) // 2:
            return sum(values)
        return None

    return RollingRow(
        week_ending=target_week,
        tier=tier,
        symbol=symbol,
        total_shares=current.total_shares,
        total_trades=current.total_trades,
        venue_count=current.venue_count,
        shares_4wk=sum_weeks(weeks_4, "total_shares"),
        shares_13wk=sum_weeks(weeks_13, "total_shares"),
        trades_4wk=sum_weeks(weeks_4, "total_trades"),
        trades_13wk=sum_weeks(weeks_13, "total_trades"),
        source_last_update_date=current.source_last_update_date,
    )


def compute_rolling_for_week(
    symbol_rows: Sequence[SymbolAggregateRow],
    target_week: date,
) -> list[RollingRow]:
    """
    Compute rolling statistics for ALL symbols for a given week.

    Filters to rows from target_week, then computes rolling stats for each.
    """
    # Find all (tier, symbol) pairs present in target week
    pairs_in_week = set((r.tier, r.symbol) for r in symbol_rows if r.week_ending == target_week)

    results: list[RollingRow] = []

    for tier, symbol in sorted(pairs_in_week):
        rolling = compute_rolling_stats(symbol_rows, target_week, tier, symbol)
        if rolling:
            results.append(rolling)

    return results


def dedupe_venue_rows(rows: Sequence[VenueVolumeRow]) -> list[VenueVolumeRow]:
    """
    Deduplicate venue rows by (week, tier, symbol, mpid).

    If duplicates exist, keeps the one with highest total_shares.
    This handles FINRA restatements where a corrected row may appear.
    """
    seen: dict[tuple[date, Tier, str, str], VenueVolumeRow] = {}

    for row in rows:
        key = (row.week_ending, row.tier, row.symbol, row.mpid)
        existing = seen.get(key)

        if existing is None:
            seen[key] = row
        elif row.total_shares > existing.total_shares:
            # Keep the row with more shares (likely the corrected one)
            seen[key] = row

    return list(seen.values())


def filter_by_tier(
    rows: Sequence[VenueVolumeRow],
    tier: Tier,
) -> list[VenueVolumeRow]:
    """Filter venue rows to a specific tier."""
    return [r for r in rows if r.tier == tier]


def filter_by_week_range(
    rows: Sequence[VenueVolumeRow],
    start_week: date,
    end_week: date,
) -> list[VenueVolumeRow]:
    """Filter venue rows to a date range (inclusive)."""
    return [r for r in rows if start_week <= r.week_ending <= end_week]


# =============================================================================
# BACKWARD COMPATIBILITY ALIASES
# =============================================================================

# Type alias for backward compatibility
SymbolSummary = SymbolAggregateRow


def _get_volume(record) -> int:
    """Extract volume from record (handles different attribute names)."""
    if hasattr(record, "total_shares"):
        return record.total_shares
    if hasattr(record, "share_volume"):
        return record.share_volume
    if hasattr(record, "total_volume"):
        return record.total_volume
    return 0


def _get_trades(record) -> int:
    """Extract trade count from record (handles different attribute names)."""
    if hasattr(record, "total_trades"):
        return record.total_trades
    if hasattr(record, "trade_count"):
        return record.trade_count
    return 0


def compute_symbol_summaries(records) -> list[SymbolAggregateRow]:
    """
    Aggregate venue records to symbol summaries.

    Groups by (week, tier, symbol) and sums volumes.
    This is a backward-compatible wrapper around aggregate_to_symbol_level.

    Args:
        records: Iterable of records with week_ending, tier, symbol,
                 total_shares, total_trades

    Returns:
        List of SymbolAggregateRow (aliased as SymbolSummary)
    """
    groups: dict[tuple, list] = defaultdict(list)

    for r in records:
        # Handle tier as string or enum
        tier = r.tier if isinstance(r.tier, Tier) else Tier(r.tier)
        key = (r.week_ending, tier, r.symbol)
        groups[key].append(r)

    summaries = []
    for (week, tier, symbol), venues in sorted(groups.items()):
        total_vol = sum(_get_volume(v) for v in venues)
        total_trades = sum(_get_trades(v) for v in venues)
        venue_count = len(set(getattr(v, "mpid", "") for v in venues))

        summaries.append(
            SymbolAggregateRow(
                week_ending=week,
                tier=tier,
                symbol=symbol,
                total_shares=total_vol,
                total_trades=total_trades,
                venue_count=venue_count,
            )
        )

    return summaries


# =============================================================================
# VENUE SHARE CALCULATION (v1)
# =============================================================================


@dataclass
class VenueShareRow:
    """
    Venue market share for a tier (aggregated across all symbols).
    
    Business keys: (week_ending, tier, mpid)
    Invariant: SUM(market_share_pct) = 1.0 per (week_ending, tier)
    """
    week_ending: date
    tier: Tier
    mpid: str
    total_volume: int
    total_trades: int
    symbol_count: int
    market_share_pct: float  # 0.0 to 1.0
    rank: int  # 1 = largest venue
    
    # Calc identity
    calc_name: str = "venue_share"
    calc_version: str = "v1"
    
    # Capture identity (set by pipeline)
    capture_id: str = ""
    captured_at: str = ""


def compute_venue_share_v1(
    venue_rows: Sequence[VenueVolumeRow],
) -> list[VenueShareRow]:
    """
    Compute venue market share (v1) for each MPID within a tier.
    
    Groups by (week, tier, mpid), computes:
    - total_volume: Sum of shares across all symbols for this venue
    - total_trades: Sum of trades
    - symbol_count: Number of distinct symbols traded at this venue
    - market_share_pct: venue_volume / tier_total_volume
    - rank: 1 = largest venue by volume
    
    Invariant: For each (week, tier), SUM(market_share_pct) = 1.0
    
    Args:
        venue_rows: Venue-level records (from normalized data)
    
    Returns:
        List of VenueShareRow ordered by (week, tier, rank)
    """
    # Group by (week, tier)
    by_week_tier: dict[tuple[date, Tier], list[VenueVolumeRow]] = defaultdict(list)
    for row in venue_rows:
        by_week_tier[(row.week_ending, row.tier)].append(row)
    
    results: list[VenueShareRow] = []
    
    for (week, tier), rows in sorted(by_week_tier.items()):
        # Aggregate per MPID
        by_mpid: dict[str, list[VenueVolumeRow]] = defaultdict(list)
        for r in rows:
            by_mpid[r.mpid].append(r)
        
        # Compute venue totals
        venue_totals: list[dict[str, Any]] = []
        for mpid, mpid_rows in by_mpid.items():
            venue_totals.append({
                "mpid": mpid,
                "volume": sum(r.total_shares for r in mpid_rows),
                "trades": sum(r.total_trades for r in mpid_rows),
                "symbols": len(set(r.symbol for r in mpid_rows)),
            })
        
        # Compute tier total for share calculation
        tier_volume = sum(v["volume"] for v in venue_totals)
        
        # Sort by volume descending for ranking
        venue_totals.sort(key=lambda x: x["volume"], reverse=True)
        
        # Build output rows with rank and share
        for rank, v in enumerate(venue_totals, 1):
            share = v["volume"] / tier_volume if tier_volume > 0 else 0.0
            results.append(VenueShareRow(
                week_ending=week,
                tier=tier,
                mpid=v["mpid"],
                total_volume=v["volume"],
                total_trades=v["trades"],
                symbol_count=v["symbols"],
                market_share_pct=share,
                rank=rank,
            ))
    
    return results


def validate_venue_share_invariants(rows: Sequence[VenueShareRow]) -> list[str]:
    """
    Validate venue share invariants.
    
    Returns list of error messages (empty if valid).
    """
    errors: list[str] = []
    
    # Group by (week, tier)
    by_group: dict[tuple[date, Tier], list[VenueShareRow]] = defaultdict(list)
    for r in rows:
        by_group[(r.week_ending, r.tier)].append(r)
    
    for (week, tier), group in by_group.items():
        # Invariant 1: Shares sum to 1.0
        total_share = sum(r.market_share_pct for r in group)
        if abs(total_share - 1.0) > 0.0001:
            errors.append(
                f"Share invariant failed: {week}/{tier.value} sums to {total_share:.6f}"
            )
        
        # Invariant 2: Ranks are consecutive 1..N
        ranks = sorted(r.rank for r in group)
        expected = list(range(1, len(ranks) + 1))
        if ranks != expected:
            errors.append(
                f"Rank invariant failed: {week}/{tier.value} ranks={ranks}"
            )
        
        # Invariant 3: Non-negative values
        for r in group:
            if r.total_volume < 0:
                errors.append(f"Negative volume: {week}/{tier.value}/{r.mpid}")
            if r.market_share_pct < 0:
                errors.append(f"Negative share: {week}/{tier.value}/{r.mpid}")
    
    return errors


# =============================================================================
# CROSS-DOMAIN CALCULATION: Volume Per Trading Day
# =============================================================================
# 
# This calculation demonstrates cross-domain dependencies:
# - Depends on: reference.exchange_calendar (holidays)
# - Produces: Volume normalized by trading days in the week
#
# DEPENDENCY CONTRACT:
# - Upstream: reference_exchange_calendar_holidays table
# - Join key: week_ending.year → calendar year
# - Exchange: XNYS (NYSE) for all FINRA OTC data
# - Failure mode: Clear error if calendar not loaded


class DependencyMissingError(Exception):
    """
    Raised when a cross-domain dependency is not satisfied.
    
    Provides actionable error message with remediation steps.
    """
    
    def __init__(self, domain: str, year: int, hint: str = ""):
        self.domain = domain
        self.year = year
        self.hint = hint
        message = f"Missing dependency: {domain} data for year {year}. {hint}"
        super().__init__(message)


@dataclass
class DomainDependency:
    """
    Declares a dependency on another domain's data.
    
    Used by calculations to explicitly declare what they need.
    
    Example:
        DomainDependency(
            domain="reference.exchange_calendar",
            table="reference_exchange_calendar_holidays",
            key_description="year",
            required=True,
            error_hint="Run: spine run reference.exchange_calendar.ingest_year --year {year}",
        )
    """
    domain: str
    table: str
    key_description: str
    required: bool = True
    error_hint: str = ""


@dataclass
class DependencyCheckResult:
    """Result of checking domain dependencies."""
    
    satisfied: bool
    errors: list[str]
    warnings: list[str]
    
    @classmethod
    def success(cls) -> "DependencyCheckResult":
        """Create a success result."""
        return cls(satisfied=True, errors=[], warnings=[])
    
    @classmethod
    def failure(cls, errors: list[str], warnings: list[str] | None = None) -> "DependencyCheckResult":
        """Create a failure result."""
        return cls(satisfied=False, errors=errors, warnings=warnings or [])


def check_dependencies(
    conn,
    dependencies: list[DomainDependency],
    context: dict[str, Any],
) -> DependencyCheckResult:
    """
    Check if all dependencies are satisfied.
    
    This is a standardized dependency checker that:
    - Validates each dependency is present in the database
    - Returns structured errors with remediation hints
    - Supports context-based error message formatting
    
    Args:
        conn: Database connection
        dependencies: List of DomainDependency to check
        context: Context dict for error message formatting (e.g., {"year": 2025})
        
    Returns:
        DependencyCheckResult with satisfied flag and error/warning lists
    """
    errors = []
    warnings = []
    
    for dep in dependencies:
        # Check if table has any rows matching the context
        # For now, simple count check - can be extended for specific key checks
        try:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {dep.table} LIMIT 1"
            ).fetchone()[0]
            
            if count == 0:
                if dep.required:
                    hint = dep.error_hint.format(**context) if dep.error_hint else ""
                    errors.append(
                        f"Dependency not satisfied: {dep.domain} ({dep.table}). {hint}"
                    )
                else:
                    warnings.append(f"Optional dependency {dep.domain} not available")
        except Exception as e:
            # Table doesn't exist or query failed
            if dep.required:
                hint = dep.error_hint.format(**context) if dep.error_hint else ""
                errors.append(
                    f"Dependency table not found: {dep.table}. {hint}"
                )
    
    if errors:
        return DependencyCheckResult.failure(errors, warnings)
    return DependencyCheckResult.success()


@dataclass
class VolumePerTradingDayRow:
    """
    Symbol volume normalized by trading days in the week.
    
    This is a cross-domain calculation:
    - FINRA data: total_shares, total_trades from symbol_summary
    - Calendar data: trading_days from exchange_calendar
    
    Normalization:
    - volume_per_day = total_shares / trading_days
    - trades_per_day = total_trades / trading_days
    
    Year-Boundary Handling:
    - For weeks spanning year boundaries (e.g., Dec 29 - Jan 2),
      holidays are loaded for ALL years in the date range.
    - Trading days are counted across the full range.
    """
    
    week_ending: date
    tier: Tier
    symbol: str
    total_shares: int
    total_trades: int
    trading_days: int
    volume_per_day: float
    trades_per_day: float
    exchange_code: str = "XNYS"
    
    # Week date range
    week_start: date | None = None
    week_end: date | None = None
    
    # Calc metadata
    calc_name: str = "volume_per_trading_day"
    calc_version: str = "1.1.0"  # Bumped for year-boundary + as-of support
    
    # Dependency tracking (for audit and replay)
    calendar_years_used: list[int] | None = None  # All years touched by the week
    calendar_capture_id_used: str | None = None   # Which calendar capture was used


def get_week_date_range(week_ending: date, days_in_week: int = 5) -> tuple[date, date]:
    """
    Derive the week date range from week_ending.
    
    FINRA OTC data uses Friday as week_ending, with weeks running Mon-Fri.
    
    Args:
        week_ending: The week ending date (typically Friday)
        days_in_week: Number of trading days in a week (default: 5 for Mon-Fri)
        
    Returns:
        Tuple of (week_start, week_end)
    """
    week_start = week_ending - timedelta(days=days_in_week - 1)
    return (week_start, week_ending)


def get_years_in_range(start_date: date, end_date: date) -> list[int]:
    """
    Get all calendar years touched by a date range.
    
    For year-boundary weeks, this returns multiple years.
    Example: Dec 29, 2025 - Jan 2, 2026 returns [2025, 2026]
    
    Args:
        start_date: Start of range
        end_date: End of range
        
    Returns:
        Sorted list of years
    """
    years = set()
    current = start_date
    while current <= end_date:
        years.add(current.year)
        current += timedelta(days=1)
    return sorted(years)


def compute_volume_per_trading_day(
    symbol_rows: Sequence[SymbolAggregateRow],
    holidays: set[date],
    exchange_code: str = "XNYS",
    calendar_capture_id: str | None = None,
) -> list[VolumePerTradingDayRow]:
    """
    Compute volume per trading day for symbol aggregates.
    
    This is a PURE FUNCTION with explicit dependencies:
    - symbol_rows: FINRA symbol aggregates (from finra.otc_transparency)
    - holidays: Set of holiday dates (from reference.exchange_calendar)
    
    The function does NOT query the database. The caller is responsible
    for loading dependencies and passing them in.
    
    Year-Boundary Semantics:
    - For each week, derives the date range (Mon-Fri)
    - Counts trading days across the full range
    - Handles weeks spanning year boundaries (e.g., Dec 29 - Jan 2)
    - Caller must provide holidays for ALL years in the range
    
    Args:
        symbol_rows: Symbol-level aggregates from FINRA
        holidays: Set of holiday dates for ALL relevant years
        exchange_code: Exchange calendar used (default: XNYS)
        calendar_capture_id: Which calendar capture was used (for audit)
        
    Returns:
        List of VolumePerTradingDayRow with normalized metrics
    """
    from spine.domains.reference.exchange_calendar.calculations import (
        trading_days_between,
    )
    
    results: list[VolumePerTradingDayRow] = []
    
    for row in symbol_rows:
        # Derive week date range
        week_start, week_end = get_week_date_range(row.week_ending)
        
        # Get all years touched by this week
        years_in_range = get_years_in_range(week_start, week_end)
        
        # Count trading days across the full range
        td_result = trading_days_between(week_start, week_end, holidays, exchange_code)
        trading_days = td_result.trading_days
        
        # Avoid division by zero (shouldn't happen for valid weeks)
        if trading_days == 0:
            volume_per_day = 0.0
            trades_per_day = 0.0
        else:
            volume_per_day = row.total_shares / trading_days
            trades_per_day = row.total_trades / trading_days
        
        results.append(VolumePerTradingDayRow(
            week_ending=row.week_ending,
            tier=row.tier,
            symbol=row.symbol,
            total_shares=row.total_shares,
            total_trades=row.total_trades,
            trading_days=trading_days,
            volume_per_day=round(volume_per_day, 2),
            trades_per_day=round(trades_per_day, 2),
            exchange_code=exchange_code,
            week_start=week_start,
            week_end=week_end,
            calendar_years_used=years_in_range,
            calendar_capture_id_used=calendar_capture_id,
        ))
    
    return results


def load_holidays_for_years(
    conn,
    years: list[int],
    exchange_code: str = "XNYS",
    capture_id: str | None = None,
) -> tuple[set[date], str | None]:
    """
    Load holidays from exchange calendar for multiple years.
    
    Supports year-boundary weeks by loading holidays for all relevant years.
    
    As-Of Mode:
    - If capture_id is None: Load latest data for each year
    - If capture_id is provided: Load data from that specific capture
    
    Args:
        conn: Database connection
        years: List of years to load
        exchange_code: Exchange MIC code
        capture_id: Optional specific capture_id to load (for as-of queries)
        
    Returns:
        Tuple of (holiday set, capture_id_used)
        
    Raises:
        DependencyMissingError: If calendar not loaded for any year
    """
    all_holidays: set[date] = set()
    capture_id_used: str | None = None
    
    for year in years:
        if capture_id:
            # As-of mode: Load specific capture
            rows = conn.execute(
                """
                SELECT holiday_date, capture_id FROM reference_exchange_calendar_holidays
                WHERE year = ? AND exchange_code = ? AND capture_id = ?
                """,
                (year, exchange_code, capture_id),
            ).fetchall()
        else:
            # Latest mode: Load most recent capture
            rows = conn.execute(
                """
                SELECT holiday_date, capture_id FROM reference_exchange_calendar_holidays
                WHERE year = ? AND exchange_code = ?
                ORDER BY captured_at DESC
                """,
                (year, exchange_code),
            ).fetchall()
        
        if not rows:
            raise DependencyMissingError(
                domain="reference.exchange_calendar",
                year=year,
                hint=f"Run: spine run reference.exchange_calendar.ingest_year "
                     f"--file path/to/holidays_{exchange_code.lower()}_{year}.json",
            )
        
        # Deduplicate by holiday_date (in case of multiple captures)
        seen_dates: set[date] = set()
        for r in rows:
            holiday_date = date.fromisoformat(r[0])
            if holiday_date not in seen_dates:
                all_holidays.add(holiday_date)
                seen_dates.add(holiday_date)
                if capture_id_used is None:
                    capture_id_used = r[1]  # Capture the capture_id
    
    return all_holidays, capture_id_used


def load_holidays_for_year(conn, year: int, exchange_code: str = "XNYS") -> set[date]:
    """
    Load holidays from exchange calendar for a specific year.
    
    DEPRECATED: Use load_holidays_for_years() for better year-boundary support.
    
    This is a DATABASE ACCESSOR function (not pure).
    
    Args:
        conn: Database connection
        year: Calendar year to load
        exchange_code: Exchange MIC code
        
    Returns:
        Set of holiday dates
        
    Raises:
        DependencyMissingError: If calendar not loaded for year
    """
    holidays, _ = load_holidays_for_years(conn, [year], exchange_code)
    return holidays


def check_calendar_dependency(conn, year: int, exchange_code: str = "XNYS") -> list[str]:
    """
    Check if exchange calendar is loaded for a year.
    
    Returns:
        List of error messages (empty if satisfied)
    """
    count = conn.execute(
        """
        SELECT COUNT(*) FROM reference_exchange_calendar_holidays
        WHERE year = ? AND exchange_code = ?
        """,
        (year, exchange_code),
    ).fetchone()[0]
    
    if count == 0:
        return [
            f"Exchange calendar for {exchange_code} {year} not loaded. "
            f"Run: spine run reference.exchange_calendar.ingest_year --year {year}"
        ]
    
    return []


# =============================================================================
# REAL TRADING ANALYTICS CALCULATIONS
# =============================================================================
# These calculations provide institutional-grade trading analytics:
# - Venue-level volume tracking (base gold layer)
# - Venue market share analysis
# - Market concentration metrics (HHI)
# - Tier split analytics
#
# Design principles:
# - Capture_id ensures point-in-time consistency
# - Pure functions for testability
# - Explicit invariants (e.g., shares sum to 1.0)
# - No database dependencies in calculation logic


@dataclass
class WeeklySymbolVenueVolumeRow:
    """
    Venue-level volume for a symbol (base gold layer).
    
    Grain: (symbol, week_ending, tier, mpid, capture_id)
    
    This is the foundation for all venue-level analytics. It tracks:
    - Which venues trade each symbol
    - Volume and trade count per venue
    - Audit trail via capture_id
    
    Invariants:
    - total_volume >= 0
    - trade_count >= 0
    - If total_volume > 0, then trade_count > 0 (at least one trade)
    """
    week_ending: date
    tier: Tier | str
    symbol: str
    mpid: str
    venue_name: str
    total_volume: int
    trade_count: int
    calc_name: str = "weekly_symbol_venue_volume"
    calc_version: str = "v1"
    captured_at: str | None = None
    capture_id: str | None = None


@dataclass
class WeeklySymbolVenueShareRow:
    """
    Venue market share for a symbol.
    
    Grain: (symbol, week_ending, tier, mpid, capture_id)
    
    Derived from WeeklySymbolVenueVolumeRow by computing:
        venue_share = venue_volume / sum(all_venue_volumes)
    
    Invariants:
    - 0 <= venue_share <= 1.0
    - sum(venue_share) == 1.0 per (symbol, week_ending, tier, capture_id)
    - If total_symbol_volume == 0, all venue_shares == 0 (explicitly handled)
    """
    week_ending: date
    tier: Tier | str
    symbol: str
    mpid: str
    venue_name: str
    venue_volume: int
    total_symbol_volume: int
    venue_share: float
    calc_name: str = "weekly_symbol_venue_share"
    calc_version: str = "v1"
    captured_at: str | None = None
    capture_id: str | None = None


@dataclass
class WeeklySymbolVenueConcentrationHHIRow:
    """
    Herfindahl-Hirschman Index (HHI) for venue concentration.
    
    Grain: (symbol, week_ending, tier, capture_id)
    
    HHI = sum(venue_share²) measures market concentration:
    - HHI = 1.0: One venue has 100% market share (monopoly)
    - HHI → 0: Perfect competition (many venues with equal share)
    - HHI > 0.25: Highly concentrated
    - HHI < 0.15: Competitive
    
    Invariants:
    - 0 <= HHI <= 1.0
    - venue_count > 0
    - total_symbol_volume >= 0
    """
    week_ending: date
    tier: Tier | str
    symbol: str
    hhi: float
    venue_count: int
    total_symbol_volume: int
    calc_name: str = "weekly_symbol_venue_concentration_hhi"
    calc_version: str = "v1"
    captured_at: str | None = None
    capture_id: str | None = None


@dataclass
class WeeklySymbolTierVolumeShareRow:
    """
    Tier volume split for a symbol.
    
    Grain: (symbol, week_ending, tier, capture_id)
    
    Shows how a symbol's volume is distributed across tiers:
    - NMS_TIER_1: Most liquid symbols
    - NMS_TIER_2: Less liquid
    - OTC: Over-the-counter
    
    Invariants:
    - 0 <= tier_volume_share <= 1.0
    - sum(tier_volume_share) == 1.0 per (symbol, week_ending, capture_id)
    - tier_volume >= 0
    """
    week_ending: date
    tier: Tier | str
    symbol: str
    tier_volume: int
    total_symbol_volume_all_tiers: int
    tier_volume_share: float
    calc_name: str = "weekly_symbol_tier_volume_share"
    calc_version: str = "v1"
    captured_at: str | None = None
    capture_id: str | None = None


def compute_weekly_symbol_venue_volume(
    normalized_rows: Sequence[dict],
) -> list[WeeklySymbolVenueVolumeRow]:
    """
    Compute venue-level volume from normalized FINRA data.
    
    This is the base gold layer that all other venue analytics depend on.
    It simply reshapes the normalized data into the calculation grain.
    
    Args:
        normalized_rows: Normalized FINRA OTC data (from finra_otc_transparency_normalized table)
    
    Returns:
        List of venue volume rows
    
    Example:
        >>> from datetime import date
        >>> rows = [
        ...     {'week_ending': date(2025, 12, 26), 'tier': 'NMS_TIER_1', 'symbol': 'AAPL',
        ...      'mpid': 'ETMM', 'market_participant_name': 'E*TRADE',
        ...      'total_weekly_share_quantity': 1000000, 'total_weekly_trade_count': 100,
        ...      'captured_at': '2025-12-27T10:00:00Z', 'capture_id': 'cap_123'},
        ...     {'week_ending': date(2025, 12, 26), 'tier': 'NMS_TIER_1', 'symbol': 'AAPL',
        ...      'mpid': 'UBSS', 'market_participant_name': 'UBS',
        ...      'total_weekly_share_quantity': 500000, 'total_weekly_trade_count': 50,
        ...      'captured_at': '2025-12-27T10:00:00Z', 'capture_id': 'cap_123'},
        ... ]
        >>> result = compute_weekly_symbol_venue_volume(rows)
        >>> len(result)
        2
        >>> result[0].symbol
        'AAPL'
        >>> result[0].total_volume
        1000000
    """
    results: list[WeeklySymbolVenueVolumeRow] = []
    
    for row in normalized_rows:
        results.append(WeeklySymbolVenueVolumeRow(
            week_ending=row["week_ending"] if isinstance(row["week_ending"], date) else date.fromisoformat(row["week_ending"]),
            tier=row["tier"],
            symbol=row["symbol"],
            mpid=row["mpid"],
            venue_name=row.get("venue_name", row["mpid"]),
            total_volume=row["total_shares"],
            trade_count=row["total_trades"],
            captured_at=row.get("captured_at"),
            capture_id=row.get("capture_id"),
        ))
    
    return results


def compute_weekly_symbol_venue_share(
    venue_volume_rows: Sequence[WeeklySymbolVenueVolumeRow],
) -> list[WeeklySymbolVenueShareRow]:
    """
    Compute venue market share from venue volume data.
    
    For each (symbol, week, tier, capture_id) group:
        venue_share = venue_volume / sum(all_venue_volumes)
    
    Args:
        venue_volume_rows: Venue volume data from compute_weekly_symbol_venue_volume
    
    Returns:
        List of venue share rows with invariant: sum(venue_share) == 1.0 per group
    
    Edge cases:
        - If total_symbol_volume == 0, all venue_shares == 0.0
        - Precision: Uses float division, venue_share may not sum to exactly 1.0 due to rounding
    
    Example:
        >>> from datetime import date
        >>> venue_vols = [
        ...     WeeklySymbolVenueVolumeRow(
        ...         week_ending=date(2025, 12, 26), tier='NMS_TIER_1', symbol='AAPL',
        ...         mpid='ETMM', venue_name='E*TRADE', total_volume=600000, trade_count=60,
        ...         capture_id='cap_123'),
        ...     WeeklySymbolVenueVolumeRow(
        ...         week_ending=date(2025, 12, 26), tier='NMS_TIER_1', symbol='AAPL',
        ...         mpid='UBSS', venue_name='UBS', total_volume=400000, trade_count=40,
        ...         capture_id='cap_123'),
        ... ]
        >>> result = compute_weekly_symbol_venue_share(venue_vols)
        >>> result[0].venue_share
        0.6
        >>> result[1].venue_share
        0.4
        >>> sum(r.venue_share for r in result)
        1.0
    """
    # Group by (week, tier, symbol, capture_id)
    groups: dict[tuple, list[WeeklySymbolVenueVolumeRow]] = defaultdict(list)
    
    for row in venue_volume_rows:
        key = (row.week_ending, row.tier, row.symbol, row.capture_id)
        groups[key].append(row)
    
    results: list[WeeklySymbolVenueShareRow] = []
    
    for (week, tier, symbol, capture_id), rows in sorted(groups.items()):
        total_symbol_volume = sum(r.total_volume for r in rows)
        
        for row in rows:
            if total_symbol_volume == 0:
                venue_share = 0.0
            else:
                venue_share = row.total_volume / total_symbol_volume
            
            results.append(WeeklySymbolVenueShareRow(
                week_ending=week,
                tier=tier,
                symbol=symbol,
                mpid=row.mpid,
                venue_name=row.venue_name,
                venue_volume=row.total_volume,
                total_symbol_volume=total_symbol_volume,
                venue_share=venue_share,
                captured_at=row.captured_at,
                capture_id=capture_id,
            ))
    
    return results


def compute_weekly_symbol_venue_concentration_hhi(
    venue_share_rows: Sequence[WeeklySymbolVenueShareRow],
) -> list[WeeklySymbolVenueConcentrationHHIRow]:
    """
    Compute Herfindahl-Hirschman Index (HHI) from venue share data.
    
    HHI = sum(venue_share²) for each (symbol, week, tier, capture_id)
    
    Interpretation:
        - HHI = 1.0: One venue has 100% (complete monopoly)
        - HHI = 0.25: Four equal-sized venues
        - HHI = 0.1: Ten equal-sized venues
        - HHI → 0: Perfect competition
    
    Args:
        venue_share_rows: Venue share data from compute_weekly_symbol_venue_share
    
    Returns:
        List of HHI rows with invariant: 0 <= HHI <= 1.0
    
    Example:
        >>> from datetime import date
        >>> shares = [
        ...     WeeklySymbolVenueShareRow(
        ...         week_ending=date(2025, 12, 26), tier='NMS_TIER_1', symbol='AAPL',
        ...         mpid='ETMM', venue_name='E*TRADE', venue_volume=1000, total_symbol_volume=1000,
        ...         venue_share=1.0, capture_id='cap_123'),
        ... ]
        >>> result = compute_weekly_symbol_venue_concentration_hhi(shares)
        >>> result[0].hhi
        1.0
        >>> result[0].venue_count
        1
    """
    # Group by (week, tier, symbol, capture_id)
    groups: dict[tuple, list[WeeklySymbolVenueShareRow]] = defaultdict(list)
    
    for row in venue_share_rows:
        key = (row.week_ending, row.tier, row.symbol, row.capture_id)
        groups[key].append(row)
    
    results: list[WeeklySymbolVenueConcentrationHHIRow] = []
    
    for (week, tier, symbol, capture_id), rows in sorted(groups.items()):
        # HHI = sum of squared market shares
        hhi = sum(r.venue_share ** 2 for r in rows)
        venue_count = len(rows)
        total_volume = rows[0].total_symbol_volume if rows else 0
        captured_at = rows[0].captured_at if rows else None
        
        results.append(WeeklySymbolVenueConcentrationHHIRow(
            week_ending=week,
            tier=tier,
            symbol=symbol,
            hhi=hhi,
            venue_count=venue_count,
            total_symbol_volume=total_volume,
            captured_at=captured_at,
            capture_id=capture_id,
        ))
    
    return results


def compute_weekly_symbol_tier_volume_share(
    venue_volume_rows: Sequence[WeeklySymbolVenueVolumeRow],
) -> list[WeeklySymbolTierVolumeShareRow]:
    """
    Compute tier volume split from venue volume data.
    
    For each (symbol, week, capture_id):
        1. Sum volume by tier
        2. Compute tier_volume_share = tier_volume / sum(all_tier_volumes)
    
    This shows how a symbol's trading is distributed across NMS_TIER_1, NMS_TIER_2, OTC.
    
    Args:
        venue_volume_rows: Venue volume data from compute_weekly_symbol_venue_volume
    
    Returns:
        List of tier volume share rows with invariant: sum(tier_volume_share) == 1.0 per (symbol, week, capture_id)
    
    Example:
        >>> from datetime import date
        >>> venue_vols = [
        ...     WeeklySymbolVenueVolumeRow(
        ...         week_ending=date(2025, 12, 26), tier='NMS_TIER_1', symbol='AAPL',
        ...         mpid='ETMM', venue_name='E*TRADE', total_volume=800000, trade_count=80,
        ...         capture_id='cap_123'),
        ...     WeeklySymbolVenueVolumeRow(
        ...         week_ending=date(2025, 12, 26), tier='OTC', symbol='AAPL',
        ...         mpid='OTCM', venue_name='OTC Markets', total_volume=200000, trade_count=20,
        ...         capture_id='cap_123'),
        ... ]
        >>> result = compute_weekly_symbol_tier_volume_share(venue_vols)
        >>> [r.tier for r in result]
        ['NMS_TIER_1', 'OTC']
        >>> [r.tier_volume_share for r in result]
        [0.8, 0.2]
    """
    # First, group by (symbol, week, tier, capture_id) to sum venues within tier
    tier_groups: dict[tuple, int] = defaultdict(int)
    metadata: dict[tuple, tuple] = {}  # Store captured_at
    
    for row in venue_volume_rows:
        key = (row.week_ending, row.tier, row.symbol, row.capture_id)
        tier_groups[key] += row.total_volume
        if key not in metadata:
            metadata[key] = (row.captured_at,)
    
    # Then group by (symbol, week, capture_id) to compute cross-tier totals
    symbol_totals: dict[tuple, int] = defaultdict(int)
    
    for (week, tier, symbol, capture_id), tier_volume in tier_groups.items():
        symbol_key = (week, symbol, capture_id)
        symbol_totals[symbol_key] += tier_volume
    
    # Compute tier shares
    results: list[WeeklySymbolTierVolumeShareRow] = []
    
    for (week, tier, symbol, capture_id), tier_volume in sorted(tier_groups.items()):
        symbol_key = (week, symbol, capture_id)
        total_symbol_volume = symbol_totals[symbol_key]
        
        if total_symbol_volume == 0:
            tier_share = 0.0
        else:
            tier_share = tier_volume / total_symbol_volume
        
        captured_at = metadata[(week, tier, symbol, capture_id)][0]
        
        results.append(WeeklySymbolTierVolumeShareRow(
            week_ending=week,
            tier=tier,
            symbol=symbol,
            tier_volume=tier_volume,
            total_symbol_volume_all_tiers=total_symbol_volume,
            tier_volume_share=tier_share,
            captured_at=captured_at,
            capture_id=capture_id,
        ))
    
    return results
