-- =============================================================================
-- FINRA OTC TRANSPARENCY DOMAIN - VIEWS
-- =============================================================================
-- Owner: spine-domains/finra/otc_transparency
-- Description: Convenience views for "latest only" queries
-- =============================================================================


-- =============================================================================
-- SILVER LAYER VIEWS - LATEST ONLY
-- =============================================================================

-- Latest symbol summary per (week, tier, symbol)
CREATE VIEW IF NOT EXISTS finra_otc_transparency_symbol_summary_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol 
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_symbol_summary
) WHERE rn = 1;

-- Latest venue share per (week, tier, mpid)
CREATE VIEW IF NOT EXISTS finra_otc_transparency_venue_share_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, mpid 
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_venue_share
) WHERE rn = 1;

-- Latest rolling metrics per (week, tier, symbol)
-- INSTITUTIONAL-GRADE: Quality gate + capture provenance + anomaly filtering
CREATE VIEW IF NOT EXISTS finra_otc_transparency_symbol_rolling_6w_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol 
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_symbol_rolling_6w
    WHERE is_complete = 1  -- QUALITY GATE: Only complete consecutive windows
) WHERE rn = 1;

-- Latest rolling 6-week averages (alias for clarity)
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
FROM finra_otc_transparency_symbol_rolling_6w_latest;

-- Clean rolling data (anomaly-filtered for production analytics)
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
);

-- Rolling completeness statistics (data quality monitoring)
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
GROUP BY week_ending, tier;


-- =============================================================================
-- GOLD LAYER VIEWS - LATEST ONLY
-- =============================================================================

CREATE VIEW IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_volume_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol, mpid
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_weekly_symbol_venue_volume
) WHERE rn = 1;

CREATE VIEW IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_share_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol, mpid
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_weekly_symbol_venue_share
) WHERE rn = 1;

CREATE VIEW IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_concentration_hhi_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_weekly_symbol_venue_concentration_hhi
) WHERE rn = 1;

CREATE VIEW IF NOT EXISTS finra_otc_transparency_weekly_symbol_tier_volume_share_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_weekly_symbol_tier_volume_share
) WHERE rn = 1;
