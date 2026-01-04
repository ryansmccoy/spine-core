-- =============================================================================
-- MARKET SPINE SCHEMA - COMBINED OPERATIONAL ARTIFACT
-- =============================================================================
-- 
-- ⚠️  THIS FILE IS GENERATED - DO NOT EDIT DIRECTLY ⚠️
--
-- To modify the schema:
--   1. Edit the source module files in:
--      - packages/spine-core/src/spine/core/schema/
--      - packages/spine-domains/src/spine/domains/{domain}/schema/
--   2. Run: python scripts/build_schema.py
--   3. Commit both module files AND this generated file
--
-- Generated: 2026-01-04T02:22:58.005671
-- Build script: scripts/build_schema.py
--
-- OWNERSHIP MODEL:
-- - Core framework tables: spine-core package
-- - Domain-specific tables: spine-domains package (by domain)
--
-- MODULES INCLUDED (in order):
--   - Core Framework
--   - FINRA OTC Transparency - Tables
--   - FINRA OTC Transparency - Indexes
--   - FINRA OTC Transparency - Views
--   - Reference: Exchange Calendar - Tables
--   - Reference: Exchange Calendar - Indexes
--
-- =============================================================================



-- ===========================================================================
-- MODULE: Core Framework
-- Source: packages\spine-core\src\spine\core\schema\00_core.sql
-- ===========================================================================

-- =============================================================================
-- SPINE CORE - FRAMEWORK TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Core framework tables for execution tracking, manifest, quality,
--              work scheduling, anomalies, and operational metadata.
--
-- This module must NOT contain domain-specific tables (finra_*, reference_*, etc.)
-- =============================================================================


-- =============================================================================
-- MIGRATIONS TRACKING
-- =============================================================================

CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);


-- =============================================================================
-- EXECUTION & MANIFEST
-- =============================================================================

-- Core executions (placeholder for Intermediate tier)
-- NOTE: NOT USED in Basic tier. Basic keeps executions in memory.
CREATE TABLE IF NOT EXISTS core_executions (
    id TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    params TEXT,                    -- JSON
    lane TEXT NOT NULL DEFAULT 'normal',
    trigger_source TEXT NOT NULL,
    logical_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_core_executions_status ON core_executions(status);
CREATE INDEX IF NOT EXISTS idx_core_executions_pipeline ON core_executions(pipeline);


-- Core manifest (tracks pipeline execution state per domain/partition/stage)
CREATE TABLE IF NOT EXISTS core_manifest (
    domain TEXT NOT NULL,           -- e.g., "finra.otc_transparency"
    partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-26", "tier": "OTC"}
    stage TEXT NOT NULL,
    stage_rank INTEGER,
    row_count INTEGER,
    metrics_json TEXT,
    execution_id TEXT,
    batch_id TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (domain, partition_key, stage)
);

CREATE INDEX IF NOT EXISTS idx_core_manifest_domain_partition ON core_manifest(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_manifest_domain_stage ON core_manifest(domain, stage);
CREATE INDEX IF NOT EXISTS idx_core_manifest_updated_at ON core_manifest(updated_at);


-- =============================================================================
-- QUALITY & REJECTS
-- =============================================================================

-- Core rejects (tracks rejected records during pipeline processing)
CREATE TABLE IF NOT EXISTS core_rejects (
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    stage TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    reason_detail TEXT,
    raw_json TEXT,
    record_key TEXT,
    source_locator TEXT,
    line_number INTEGER,
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_rejects_domain_partition ON core_rejects(domain, partition_key);


-- Core quality (tracks quality check results)
CREATE TABLE IF NOT EXISTS core_quality (
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,
    check_name TEXT NOT NULL,
    category TEXT NOT NULL,         -- INTEGRITY, COMPLETENESS, BUSINESS_RULE
    status TEXT NOT NULL,           -- PASS, WARN, FAIL
    message TEXT,
    actual_value TEXT,
    expected_value TEXT,
    details_json TEXT,
    execution_id TEXT NOT NULL,
    batch_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_quality_domain_partition ON core_quality(domain, partition_key);


-- Core anomalies (tracks data quality issues, business rule violations, and operational warnings)
-- Lightweight persistence for failures and warnings without blocking pipeline execution
CREATE TABLE IF NOT EXISTS core_anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Scope
    domain TEXT NOT NULL,
    pipeline TEXT,                  -- Pipeline that detected anomaly (NULL for system-level)
    partition_key TEXT,             -- Affected partition (JSON)
    stage TEXT,                     -- Pipeline stage where detected
    
    -- Classification
    severity TEXT NOT NULL,         -- INFO, WARN, ERROR, CRITICAL
    category TEXT NOT NULL,         -- INCOMPLETE_INPUT, BUSINESS_RULE, COMPLETENESS, CONSISTENCY, FRESHNESS, DEPENDENCY
    
    -- Details
    message TEXT NOT NULL,          -- Human-readable description
    details_json TEXT,              -- Additional context (expected vs actual, sample records, etc.)
    
    -- Affected data
    affected_records INTEGER,       -- Count of records impacted
    sample_records TEXT,            -- JSON: Sample of affected records for investigation
    
    -- Context
    execution_id TEXT,              -- Execution that detected this anomaly
    batch_id TEXT,
    capture_id TEXT,                -- Capture this anomaly applies to (if applicable)
    
    -- Lifecycle
    detected_at TEXT NOT NULL,
    resolved_at TEXT,               -- When anomaly was addressed (NULL if unresolved)
    resolution_note TEXT,           -- How it was resolved
    
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_core_anomalies_domain_partition ON core_anomalies(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_severity ON core_anomalies(severity);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_category ON core_anomalies(category);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_detected_at ON core_anomalies(detected_at);
CREATE INDEX IF NOT EXISTS idx_core_anomalies_unresolved ON core_anomalies(resolved_at) WHERE resolved_at IS NULL;


-- =============================================================================
-- WORK SCHEDULING & OPERATIONS
-- =============================================================================

-- Core work items (tracks scheduled/expected pipeline runs for operational automation)
-- Used by cron jobs, Kubernetes CronJobs, and schedulers to manage work queues
CREATE TABLE IF NOT EXISTS core_work_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Work definition
    domain TEXT NOT NULL,           -- e.g., "finra.otc_transparency"
    pipeline TEXT NOT NULL,         -- e.g., "ingest_week", "normalize_week"
    partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-26", "tier": "OTC"}
    params_json TEXT,               -- Additional pipeline parameters (JSON)
    
    -- Scheduling
    desired_at TEXT NOT NULL,       -- When this work should be done (ISO 8601)
    priority INTEGER DEFAULT 100,   -- Higher = more urgent (for queuing)
    
    -- State machine: PENDING → RUNNING → COMPLETE (or FAILED → RETRY_WAIT → PENDING)
    state TEXT NOT NULL DEFAULT 'PENDING',
    -- States: PENDING, RUNNING, COMPLETE, FAILED, RETRY_WAIT, CANCELLED
    
    -- Retry and failure handling
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,                -- Error message from most recent attempt
    last_error_at TEXT,             -- When error occurred
    next_attempt_at TEXT,           -- For exponential backoff (NULL if not retrying)
    
    -- Execution tracking
    current_execution_id TEXT,      -- execution_id of RUNNING attempt
    latest_execution_id TEXT,       -- execution_id of last COMPLETE attempt
    locked_by TEXT,                 -- Worker ID that claimed this work (optional)
    locked_at TEXT,                 -- When work was claimed
    
    -- Audit trail
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,              -- When state became COMPLETE
    
    UNIQUE(domain, pipeline, partition_key)
);

CREATE INDEX IF NOT EXISTS idx_core_work_items_state ON core_work_items(state);
CREATE INDEX IF NOT EXISTS idx_core_work_items_desired_at ON core_work_items(desired_at);
CREATE INDEX IF NOT EXISTS idx_core_work_items_next_attempt ON core_work_items(state, next_attempt_at);
CREATE INDEX IF NOT EXISTS idx_core_work_items_domain_pipeline ON core_work_items(domain, pipeline);
CREATE INDEX IF NOT EXISTS idx_core_work_items_partition ON core_work_items(domain, partition_key);


-- Core calculation dependencies (tracks lineage between calculations and their data sources)
-- Enables automatic invalidation when upstream data is revised
CREATE TABLE IF NOT EXISTS core_calc_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Downstream calculation
    calc_domain TEXT NOT NULL,
    calc_pipeline TEXT NOT NULL,
    calc_table TEXT,                -- Specific table (if applicable)
    
    -- Upstream dependency
    depends_on_domain TEXT NOT NULL,
    depends_on_table TEXT NOT NULL,
    
    -- Dependency metadata
    dependency_type TEXT NOT NULL,  -- REQUIRED, OPTIONAL, REFERENCE
    description TEXT,               -- Why this dependency exists
    
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_core_calc_dependencies_calc ON core_calc_dependencies(calc_domain, calc_pipeline);
CREATE INDEX IF NOT EXISTS idx_core_calc_dependencies_upstream ON core_calc_dependencies(depends_on_domain, depends_on_table);


-- Core expected schedules (declarative specification of pipeline execution cadence)
-- Used for detecting missed runs, late data, and validating completeness
CREATE TABLE IF NOT EXISTS core_expected_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Pipeline identification
    domain TEXT NOT NULL,
    pipeline TEXT NOT NULL,
    
    -- Schedule specification
    schedule_type TEXT NOT NULL,    -- WEEKLY, DAILY, MONTHLY, ANNUAL, TRIGGERED
    cron_expression TEXT,           -- Optional: Cron format for complex schedules
    
    -- Partition template
    partition_template TEXT NOT NULL, -- JSON: {"week_ending": "${MONDAY}", "tier": "${TIER}"}
    partition_values TEXT,          -- JSON: Expected values for template variables
    
    -- SLA and expectations
    expected_delay_hours INTEGER,   -- How long after business date should data arrive
    preliminary_hours INTEGER,      -- Hours before data is considered stable/final
    
    -- Metadata
    description TEXT,
    is_active INTEGER DEFAULT 1,    -- 0 to temporarily disable schedule
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_core_expected_schedules_domain ON core_expected_schedules(domain, pipeline);
CREATE INDEX IF NOT EXISTS idx_core_expected_schedules_active ON core_expected_schedules(is_active);


-- Core data readiness (tracks certification status for data products)
-- Indicates when data is "ready for trading" or "ready for compliance reporting"
CREATE TABLE IF NOT EXISTS core_data_readiness (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Data product identification
    domain TEXT NOT NULL,
    partition_key TEXT NOT NULL,    -- JSON: {"week_ending": "2025-12-22", "tier": "NMS_TIER_1"}
    
    -- Readiness status
    is_ready INTEGER DEFAULT 0,     -- 1 when all criteria satisfied
    ready_for TEXT,                 -- USE_CASE: "trading", "compliance", "research"
    
    -- Certification criteria results
    all_partitions_present INTEGER DEFAULT 0,
    all_stages_complete INTEGER DEFAULT 0,
    no_critical_anomalies INTEGER DEFAULT 0,
    dependencies_current INTEGER DEFAULT 0,
    age_exceeds_preliminary INTEGER DEFAULT 0,
    
    -- Details
    blocking_issues TEXT,           -- JSON: List of issues preventing readiness
    certified_at TEXT,              -- When readiness criteria were met
    certified_by TEXT,              -- System or user who certified
    
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(domain, partition_key, ready_for)
);

CREATE INDEX IF NOT EXISTS idx_core_data_readiness_domain ON core_data_readiness(domain, partition_key);
CREATE INDEX IF NOT EXISTS idx_core_data_readiness_status ON core_data_readiness(is_ready, ready_for);



-- ===========================================================================
-- MODULE: FINRA OTC Transparency - Tables
-- Source: packages\spine-domains\src\spine\domains\finra\otc_transparency\schema\00_tables.sql
-- ===========================================================================

-- =============================================================================
-- FINRA OTC TRANSPARENCY DOMAIN - TABLES
-- =============================================================================
-- Owner: spine-domains/finra/otc_transparency
-- Description: FINRA OTC Transparency weekly trading data
--
-- 3-CLOCK TEMPORAL MODEL:
--   Clock 1: week_ending (business time - when trading occurred)
--   Clock 2: source_last_update_date (FINRA system time - when FINRA updated)
--   Clock 3: captured_at + capture_id (platform time - when we ingested)
--
-- UNIQUE constraints include capture_id to allow multiple captures of same week.
-- This enables point-in-time queries and correction tracking.
-- =============================================================================


-- =============================================================================
-- RAW & NORMALIZED LAYERS
-- =============================================================================

-- Raw data from FINRA files (source of truth for all 3 clocks)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_raw (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    
    -- Clock 1: Business time
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    issue_name TEXT,
    venue_name TEXT,
    mpid TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    
    -- Clock 2: Source system time (from FINRA lastUpdateDate)
    source_last_update_date TEXT,
    
    -- Clock 3: Platform capture time
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    source_file TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);


-- Normalized table (cleaned, standardized data from raw)
-- This is the "source of truth" for downstream calculations
CREATE TABLE IF NOT EXISTS finra_otc_transparency_normalized (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    -- Business keys
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    
    -- Metrics
    total_shares INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    
    -- Additional attributes
    issue_name TEXT,
    venue_name TEXT,
    source_last_update_date TEXT,
    
    -- Capture identity (Clock 3)
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    -- Lineage
    source_raw_id INTEGER,
    normalized_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);


-- =============================================================================
-- SILVER LAYER - AGGREGATIONS & SUMMARIES
-- =============================================================================

-- Normalized venue volumes (propagates capture identity from raw)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_venue_volume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    total_shares INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    avg_trade_size TEXT,
    record_hash TEXT NOT NULL,
    
    -- Clock 3: Propagated from raw
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    normalized_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);


-- Symbol weekly summaries (propagates capture identity)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_symbol_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size TEXT,
    
    -- Clock 3: Propagated from normalized
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id)
);


-- Venue market share (propagates capture identity)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_venue_share (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    mpid TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    symbol_count INTEGER NOT NULL,
    market_share_pct TEXT NOT NULL,
    rank INTEGER NOT NULL,
    
    -- Clock 3: Propagated from normalized
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, mpid, capture_id)
);


-- Rolling 6-week symbol statistics
CREATE TABLE IF NOT EXISTS finra_otc_transparency_symbol_rolling_6w (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    avg_volume TEXT NOT NULL,
    avg_trades TEXT NOT NULL,
    min_volume INTEGER NOT NULL,
    max_volume INTEGER NOT NULL,
    trend_direction TEXT,
    trend_pct TEXT,
    weeks_in_window INTEGER NOT NULL,
    is_complete INTEGER NOT NULL,
    
    -- Clock 3: From current week's capture
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id)
);


-- Liquidity scores
CREATE TABLE IF NOT EXISTS finra_otc_transparency_liquidity_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,

    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    liquidity_score TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size TEXT NOT NULL,

    -- Clock 3: Propagated from summary
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,

    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(week_ending, tier, symbol, capture_id)
);


-- Research snapshot (wide denormalized table for analysts)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_research_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    
    -- Current week stats
    total_volume INTEGER NOT NULL,
    total_trades INTEGER NOT NULL,
    venue_count INTEGER NOT NULL,
    avg_trade_size TEXT,
    
    -- Rolling stats
    rolling_avg_volume TEXT,
    rolling_avg_trades TEXT,
    rolling_min_volume INTEGER,
    rolling_max_volume INTEGER,
    trend_direction TEXT,
    trend_pct TEXT,
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id)
);


-- =============================================================================
-- GOLD LAYER - REAL TRADING ANALYTICS CALCULATIONS
-- =============================================================================
-- These tables support institutional-grade trading analytics:
-- - Venue-level volume tracking
-- - Venue market share analysis
-- - Market concentration metrics (HHI)
-- - Tier split analytics

-- Base venue volume (gold layer foundation)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_volume (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    venue_name TEXT NOT NULL,
    total_volume INTEGER NOT NULL,
    trade_count INTEGER NOT NULL,
    
    calc_name TEXT NOT NULL DEFAULT 'weekly_symbol_venue_volume',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id)
);


-- Venue market share
CREATE TABLE IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_share (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mpid TEXT NOT NULL,
    venue_name TEXT NOT NULL,
    venue_volume INTEGER NOT NULL,
    total_symbol_volume INTEGER NOT NULL,
    venue_share REAL NOT NULL,  -- 0.0 to 1.0
    
    calc_name TEXT NOT NULL DEFAULT 'weekly_symbol_venue_share',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, mpid, capture_id),
    CHECK(venue_share >= 0.0 AND venue_share <= 1.0)
);


-- Venue concentration (HHI)
CREATE TABLE IF NOT EXISTS finra_otc_transparency_weekly_symbol_venue_concentration_hhi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    hhi REAL NOT NULL,  -- 0.0 to 1.0
    venue_count INTEGER NOT NULL,
    total_symbol_volume INTEGER NOT NULL,
    
    calc_name TEXT NOT NULL DEFAULT 'weekly_symbol_venue_concentration_hhi',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id),
    CHECK(hhi >= 0.0 AND hhi <= 1.0),
    CHECK(venue_count > 0)
);


-- Tier volume share
CREATE TABLE IF NOT EXISTS finra_otc_transparency_weekly_symbol_tier_volume_share (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL,
    tier_volume INTEGER NOT NULL,
    total_symbol_volume_all_tiers INTEGER NOT NULL,
    tier_volume_share REAL NOT NULL,  -- 0.0 to 1.0
    
    calc_name TEXT NOT NULL DEFAULT 'weekly_symbol_tier_volume_share',
    calc_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Clock 3: Capture identity
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(week_ending, tier, symbol, capture_id),
    CHECK(tier_volume_share >= 0.0 AND tier_volume_share <= 1.0)
);



-- ===========================================================================
-- MODULE: FINRA OTC Transparency - Indexes
-- Source: packages\spine-domains\src\spine\domains\finra\otc_transparency\schema\01_indexes.sql
-- ===========================================================================

-- =============================================================================
-- FINRA OTC TRANSPARENCY DOMAIN - INDEXES
-- =============================================================================
-- Owner: spine-domains/finra/otc_transparency
-- Description: Performance indexes for FINRA OTC Transparency tables
-- =============================================================================


-- =============================================================================
-- RAW & NORMALIZED INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_raw_week ON finra_otc_transparency_raw(week_ending);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_raw_symbol ON finra_otc_transparency_raw(symbol);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_raw_capture ON finra_otc_transparency_raw(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_raw_pit ON finra_otc_transparency_raw(week_ending, tier, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_normalized_week ON finra_otc_transparency_normalized(week_ending);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_normalized_symbol ON finra_otc_transparency_normalized(symbol);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_normalized_capture ON finra_otc_transparency_normalized(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_normalized_latest ON finra_otc_transparency_normalized(week_ending, tier, symbol, captured_at DESC);


-- =============================================================================
-- SILVER LAYER INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_venue_volume_week ON finra_otc_transparency_venue_volume(week_ending);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_venue_volume_symbol ON finra_otc_transparency_venue_volume(symbol);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_venue_volume_capture ON finra_otc_transparency_venue_volume(week_ending, tier, capture_id);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_symbol_summary_capture ON finra_otc_transparency_symbol_summary(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_symbol_summary_pit ON finra_otc_transparency_symbol_summary(week_ending, tier, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_venue_share_capture ON finra_otc_transparency_venue_share(week_ending, tier, capture_id);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_symbol_rolling_6w_capture ON finra_otc_transparency_symbol_rolling_6w(week_ending, tier, capture_id);

CREATE INDEX IF NOT EXISTS idx_finra_otc_transparency_liquidity_score_capture ON finra_otc_transparency_liquidity_score(week_ending, tier, capture_id);


-- =============================================================================
-- GOLD LAYER INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_volume_capture 
    ON finra_otc_transparency_weekly_symbol_venue_volume(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_volume_symbol 
    ON finra_otc_transparency_weekly_symbol_venue_volume(symbol, week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_volume_latest 
    ON finra_otc_transparency_weekly_symbol_venue_volume(week_ending, tier, symbol, mpid, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_share_capture 
    ON finra_otc_transparency_weekly_symbol_venue_share(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_share_symbol 
    ON finra_otc_transparency_weekly_symbol_venue_share(symbol, week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_share_latest 
    ON finra_otc_transparency_weekly_symbol_venue_share(week_ending, tier, symbol, mpid, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_concentration_hhi_capture 
    ON finra_otc_transparency_weekly_symbol_venue_concentration_hhi(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_concentration_hhi_symbol 
    ON finra_otc_transparency_weekly_symbol_venue_concentration_hhi(symbol, week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_venue_concentration_hhi_latest 
    ON finra_otc_transparency_weekly_symbol_venue_concentration_hhi(week_ending, tier, symbol, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_tier_volume_share_capture 
    ON finra_otc_transparency_weekly_symbol_tier_volume_share(week_ending, tier, capture_id);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_tier_volume_share_symbol 
    ON finra_otc_transparency_weekly_symbol_tier_volume_share(symbol, week_ending, tier);
CREATE INDEX IF NOT EXISTS idx_finra_otc_weekly_symbol_tier_volume_share_latest 
    ON finra_otc_transparency_weekly_symbol_tier_volume_share(week_ending, tier, symbol, captured_at DESC);



-- ===========================================================================
-- MODULE: FINRA OTC Transparency - Views
-- Source: packages\spine-domains\src\spine\domains\finra\otc_transparency\schema\02_views.sql
-- ===========================================================================

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



-- ===========================================================================
-- MODULE: Reference: Exchange Calendar - Tables
-- Source: packages\spine-domains\src\spine\domains\reference\exchange_calendar\schema\00_tables.sql
-- ===========================================================================

-- =============================================================================
-- REFERENCE DATA: EXCHANGE CALENDAR DOMAIN - TABLES
-- =============================================================================
-- Owner: spine-domains/reference/exchange_calendar
-- Description: Exchange holiday calendars and computed trading day data
--
-- Ingestion cadence: Annual (updated once per year)
-- Partition key: {"year": 2025, "exchange_code": "XNYS"}
-- =============================================================================


-- Holiday calendar data (raw from JSON files)
CREATE TABLE IF NOT EXISTS reference_exchange_calendar_holidays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    exchange_code TEXT NOT NULL,
    holiday_date TEXT NOT NULL,
    holiday_name TEXT NOT NULL,
    
    -- Capture metadata
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(year, exchange_code, holiday_date)
);


-- Computed trading days by month
CREATE TABLE IF NOT EXISTS reference_exchange_calendar_trading_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    exchange_code TEXT NOT NULL,
    month INTEGER NOT NULL,
    trading_days INTEGER NOT NULL,
    calendar_days INTEGER NOT NULL,
    holidays INTEGER NOT NULL,
    
    -- Calc metadata
    calc_name TEXT NOT NULL,
    calc_version TEXT NOT NULL,
    
    -- Capture metadata
    execution_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    calculated_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(year, exchange_code, month)
);



-- ===========================================================================
-- MODULE: Reference: Exchange Calendar - Indexes
-- Source: packages\spine-domains\src\spine\domains\reference\exchange_calendar\schema\01_indexes.sql
-- ===========================================================================

-- =============================================================================
-- REFERENCE DATA: EXCHANGE CALENDAR DOMAIN - INDEXES
-- =============================================================================
-- Owner: spine-domains/reference/exchange_calendar
-- Description: Performance indexes for exchange calendar tables
-- =============================================================================


CREATE INDEX IF NOT EXISTS idx_reference_exchange_calendar_holidays_year 
    ON reference_exchange_calendar_holidays(year, exchange_code);

CREATE INDEX IF NOT EXISTS idx_reference_exchange_calendar_trading_days_year
    ON reference_exchange_calendar_trading_days(year, exchange_code);



-- =============================================================================
-- RECORD SCHEMA VERSION
-- =============================================================================

INSERT OR IGNORE INTO _migrations (filename) VALUES ('001_schema.sql');
