"""SQL views for FINRA OTC Transparency domain.

INSTITUTIONAL-GRADE PATTERN:
- Views defined in schema/02_views.sql (not created at runtime)
- Applied via migrations/build_schema.py
- This module retained for backward compatibility and documentation
"""

# View: Latest rolling 6-week averages with quality gate
VIEW_ROLLING_6W_LATEST = """
-- See schema/02_views.sql for authoritative definition
-- This is retained for documentation/testing purposes only
CREATE VIEW IF NOT EXISTS finra_otc_transparency_rolling_6w_avg_symbol_volume_latest AS
SELECT 
    week_ending,
    tier,
    symbol,
    avg_volume,
    avg_trades,
    min_volume,
    max_volume,
    trend_direction,
    trend_pct,
    weeks_in_window,
    is_complete,
    input_min_capture_id,
    input_max_capture_id,
    input_min_captured_at,
    input_max_captured_at,
    capture_id,
    captured_at,
    execution_id,
    batch_id,
    calculated_at
FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY week_ending, tier, symbol 
               ORDER BY captured_at DESC
           ) as rn
    FROM finra_otc_transparency_symbol_rolling_6w
    WHERE is_complete = 1  -- QUALITY GATE: Only complete consecutive windows
) r
WHERE r.rn = 1
"""

# View: Latest rolling with anomaly filtering
VIEW_ROLLING_6W_CLEAN = """
-- See schema/02_views.sql for authoritative definition
CREATE VIEW IF NOT EXISTS finra_otc_transparency_rolling_6w_clean AS
SELECT 
    r.*
FROM finra_otc_transparency_rolling_6w_avg_symbol_volume_latest r
WHERE NOT EXISTS (
    SELECT 1 
    FROM core_anomalies a
    WHERE a.domain = 'finra.otc_transparency'
      AND a.stage = 'ROLLING'
      AND a.partition_key = r.week_ending || '|' || r.tier  -- Exact partition match
      AND a.severity IN ('ERROR', 'CRITICAL')
      AND a.resolved_at IS NULL
)
"""

# View: Rolling stats with completeness metrics
VIEW_ROLLING_6W_STATS = """
-- See schema/02_views.sql for authoritative definition
CREATE VIEW IF NOT EXISTS finra_otc_transparency_rolling_6w_stats AS
SELECT 
    week_ending,
    tier,
    COUNT(DISTINCT symbol) as total_symbols,
    SUM(CASE WHEN is_complete = 1 THEN 1 ELSE 0 END) as complete_symbols,
    SUM(CASE WHEN is_complete = 0 THEN 1 ELSE 0 END) as incomplete_symbols,
    ROUND(100.0 * SUM(CASE WHEN is_complete = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) as completeness_pct,
    AVG(weeks_in_window) as avg_weeks_available,
    MIN(weeks_in_window) as min_weeks_available,
    MAX(weeks_in_window) as max_weeks_available,
    MAX(calculated_at) as last_updated,
    COUNT(DISTINCT capture_id) as distinct_captures
FROM finra_otc_transparency_symbol_rolling_6w
GROUP BY week_ending, tier
"""


def create_views(conn) -> None:
    """
    DEPRECATED: Views now created via schema/02_views.sql migrations.
    
    This function is retained for backward compatibility with existing tests
    but should not be used in production code. Use build_schema.py instead.
    
    Args:
        conn: Database connection
    """
    import warnings
    warnings.warn(
        "create_views() is deprecated. Views are now defined in schema/02_views.sql "
        "and applied via migrations. This function will be removed in a future version.",
        DeprecationWarning,
        stacklevel=2,
    )
    
    conn.execute(VIEW_ROLLING_6W_LATEST)
    conn.execute(VIEW_ROLLING_6W_CLEAN)
    conn.execute(VIEW_ROLLING_6W_STATS)
    conn.commit()


def drop_views(conn) -> None:
    """Drop all FINRA OTC transparency views (for testing/cleanup)."""
    conn.execute("DROP VIEW IF EXISTS finra_otc_transparency_rolling_6w_stats")
    conn.execute("DROP VIEW IF EXISTS finra_otc_transparency_rolling_6w_clean")
    conn.execute("DROP VIEW IF EXISTS finra_otc_transparency_rolling_6w_avg_symbol_volume_latest")
    conn.commit()
