"""Quality gates and validation helpers for FINRA OTC transparency pipelines."""

from datetime import date
from typing import Any

import structlog

logger = structlog.get_logger()


def require_history_window(
    conn: Any,
    table: str,
    week_ending: date,
    window_weeks: int,
    tier: str | None = None,
    symbol: str | None = None,
    check_readiness: bool = False,
) -> tuple[bool, list[str]]:
    """
    Validate that CONSECUTIVE historical weeks exist for rolling calculations.
    
    INSTITUTIONAL-GRADE CONTRACT:
    - Computes exact expected week_endings using WeekEnding.window()
    - Validates ALL expected weeks are present (no gaps allowed)
    - Returns missing weeks as exact ISO date strings in chronological order
    - Ensures rolling windows are mathematically sound (no partial data)
    
    Args:
        conn: Database connection
        table: Source table name (e.g., "finra_otc_transparency_symbol_summary")
        week_ending: Target week ending date (must be Friday)
        window_weeks: Required number of consecutive weeks (e.g., 6 for rolling-6w)
        tier: Optional tier filter (e.g., "NMS_TIER_1")
        symbol: Optional symbol filter (e.g., "AAPL")
        check_readiness: If True, also check core_data_readiness for each week
    
    Returns:
        (ok: bool, missing_weeks: list[str])
        - ok=True only if ALL expected consecutive weeks exist
        - missing_weeks contains ISO dates of missing weeks in chronological order
    
    Examples:
        # Enforce consecutive 6-week window for AAPL
        ok, missing = require_history_window(
            conn, "finra_otc_transparency_symbol_summary",
            date(2026, 1, 3), window_weeks=6,
            tier="NMS_TIER_1", symbol="AAPL"
        )
        # Returns (False, ["2025-11-29", "2025-12-06"]) if those weeks missing
        
        # Check tier-level completeness with readiness validation
        ok, missing = require_history_window(
            conn, "finra_otc_transparency_symbol_summary",
            date(2026, 1, 3), window_weeks=6,
            tier="NMS_TIER_1", check_readiness=True
        )
    """
    # Compute exact expected consecutive weeks (oldest to newest)
    from spine.core import WeekEnding
    
    target = WeekEnding(week_ending)
    expected_weeks = target.window(window_weeks)
    
    # Create ordered list of expected week strings for comparison
    expected_week_list = [str(w.value) for w in expected_weeks]
    expected_week_set = set(expected_week_list)
    
    # Build query to find existing weeks in table
    filters = ["week_ending IN ({})".format(",".join(["?"] * len(expected_weeks)))]
    params = expected_week_list.copy()
    
    if tier:
        filters.append("tier = ?")
        params.append(tier)
    
    if symbol:
        filters.append("symbol = ?")
        params.append(symbol)
    
    where_clause = " AND ".join(filters)
    
    # Query distinct weeks present in table
    query = f"""
        SELECT DISTINCT week_ending 
        FROM {table}
        WHERE {where_clause}
        ORDER BY week_ending
    """
    
    rows = conn.execute(query, params).fetchall()
    found_weeks = {row["week_ending"] if isinstance(row["week_ending"], str) else str(row["week_ending"]) for row in rows}
    
    # STRICT CHECK: Must have ALL expected consecutive weeks (no gaps)
    missing_weeks = sorted(expected_week_set - found_weeks)
    has_complete_consecutive_window = len(missing_weeks) == 0
    
    if not has_complete_consecutive_window:
        logger.warning(
            "history_window_incomplete",
            table=table,
            week_ending=str(week_ending),
            window_weeks=window_weeks,
            expected_weeks=expected_week_list,
            found_weeks=sorted(found_weeks),
            missing_weeks=missing_weeks,
            tier=tier,
            symbol=symbol,
        )
        return False, missing_weeks
    
    # Optional: Check readiness for ALL expected weeks (strict validation)
    if check_readiness:
        unready_weeks = []
        for week in expected_week_list:
            ready_query = """
                SELECT is_ready 
                FROM core_data_readiness
                WHERE domain = 'finra.otc_transparency'
                  AND partition_key = ?
                  AND ready_for = 'ANALYTICS'
            """
            partition_key = f"{week}|{tier}" if tier else week
            result = conn.execute(ready_query, (partition_key,)).fetchone()
            
            if not result or not result["is_ready"]:
                unready_weeks.append(week)
        
        if unready_weeks:
            logger.warning(
                "history_window_not_ready",
                table=table,
                week_ending=str(week_ending),
                expected_weeks=expected_week_list,
                unready_weeks=sorted(unready_weeks),
                tier=tier,
            )
            return False, sorted(unready_weeks)
    
    logger.debug(
        "history_window_validated",
        table=table,
        week_ending=str(week_ending),
        window_weeks=window_weeks,
        consecutive_weeks_confirmed=len(expected_week_list),
        tier=tier,
        symbol=symbol,
    )
    
    return True, []


def get_symbols_with_sufficient_history(
    conn: Any,
    table: str,
    week_ending: date,
    window_weeks: int,
    tier: str,
) -> set[str]:
    """
    Get set of symbols that have sufficient history for rolling calculations.
    
    Args:
        conn: Database connection
        table: Source table name
        week_ending: Target week ending date
        window_weeks: Required number of historical weeks
        tier: Tier filter (required)
    
    Returns:
        Set of symbol strings that meet the history requirement
    
    Example:
        valid_symbols = get_symbols_with_sufficient_history(
            conn, "finra_otc_transparency_symbol_summary",
            date(2026, 1, 2), window_weeks=6, tier="NMS_TIER_1"
        )
        # Returns: {"AAPL", "MSFT", "GOOGL"} - only symbols with 6+ weeks
    """
    from spine.core import WeekEnding
    
    target = WeekEnding(week_ending)
    expected_weeks = target.window(window_weeks)
    week_strs = [str(w.value) for w in expected_weeks]
    
    # Get symbols with week counts
    placeholders = ",".join(["?"] * len(week_strs))
    query = f"""
        SELECT 
            symbol,
            COUNT(DISTINCT week_ending) as week_count
        FROM {table}
        WHERE tier = ?
          AND week_ending IN ({placeholders})
        GROUP BY symbol
        HAVING week_count >= ?
    """
    
    params = [tier] + week_strs + [window_weeks]
    rows = conn.execute(query, params).fetchall()
    
    valid_symbols = {row["symbol"] for row in rows}
    
    logger.debug(
        "symbols_with_history_computed",
        table=table,
        week_ending=str(week_ending),
        window_weeks=window_weeks,
        tier=tier,
        valid_symbols=len(valid_symbols),
    )
    
    return valid_symbols
