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
CREATE VIEW IF NOT EXISTS finra_otc_transparency_symbol_rolling_6w_latest AS
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol 
        ORDER BY captured_at DESC
    ) as rn
    FROM finra_otc_transparency_symbol_rolling_6w
) WHERE rn = 1;


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
