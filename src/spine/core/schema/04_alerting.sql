-- =============================================================================
-- SPINE CORE - ALERTING TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Tables for alert channel configuration and delivery tracking.
--              Supports Slack, Email, ServiceNow, and extensible channels.
--
-- Tier Usage:
--   Basic: Not used
--   Intermediate: Required (Slack, Email)
--   Advanced/Full: Required (+ ServiceNow, PagerDuty)
--
-- Design Principles Applied:
--   #3 Registry-Driven: Channels registered by name
--   #13 Observable: All alerts tracked with delivery status
--
-- Dependencies: None
-- =============================================================================


-- =============================================================================
-- ALERT CHANNELS (Channel Configuration)
-- =============================================================================

-- Stores alert channel configurations
-- Each channel type (slack, email, servicenow) has type-specific config in config_json
CREATE TABLE IF NOT EXISTS core_alert_channels (
    -- Identity
    id TEXT PRIMARY KEY,                    -- ULID
    name TEXT NOT NULL UNIQUE,              -- e.g., "slack-prod", "email-ops"
    channel_type TEXT NOT NULL,             -- slack, email, servicenow, pagerduty, webhook
    
    -- Configuration (type-specific)
    config_json TEXT NOT NULL,              -- JSON: Type-specific config
    -- Slack: {"webhook_url": "...", "channel": "#alerts"}
    -- Email: {"smtp_host": "...", "recipients": ["..."], "from": "..."}
    -- ServiceNow: {"instance": "...", "username": "...", "assignment_group": "..."}
    
    -- Routing
    min_severity TEXT NOT NULL DEFAULT 'ERROR',  -- INFO, WARNING, ERROR, CRITICAL
    domains TEXT,                           -- JSON array: ["finra.*", "market_data.*"] (NULL = all)
    
    -- State
    enabled INTEGER NOT NULL DEFAULT 1,     -- 1=enabled, 0=disabled
    
    -- Throttling
    throttle_minutes INTEGER NOT NULL DEFAULT 5,  -- Min interval between same alerts
    
    -- Health
    last_success_at TEXT,                   -- Last successful delivery
    last_failure_at TEXT,                   -- Last failed delivery
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_alert_channels_type ON core_alert_channels(channel_type);
CREATE INDEX IF NOT EXISTS idx_alert_channels_enabled ON core_alert_channels(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_channels_severity ON core_alert_channels(min_severity);


-- =============================================================================
-- ALERTS (Alert Delivery Log)
-- =============================================================================

-- Tracks all alerts sent (or attempted)
-- Provides audit trail and debugging for notification issues
CREATE TABLE IF NOT EXISTS core_alerts (
    -- Identity
    id TEXT PRIMARY KEY,                    -- ULID
    
    -- Alert content
    severity TEXT NOT NULL,                 -- INFO, WARNING, ERROR, CRITICAL
    title TEXT NOT NULL,                    -- Short summary
    message TEXT NOT NULL,                  -- Detailed message
    
    -- Source
    source TEXT NOT NULL,                   -- Pipeline/workflow that triggered
    domain TEXT,                            -- Domain context
    execution_id TEXT,                      -- FK to execution (if applicable)
    run_id TEXT,                            -- FK to workflow run (if applicable)
    
    -- Context
    metadata_json TEXT,                     -- JSON: Additional context
    error_category TEXT,                    -- Error classification
    
    -- Timing
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- Deduplication
    dedup_key TEXT,                         -- For throttling (hash of source+title+severity)
    
    -- Capture linkage
    capture_id TEXT                         -- Related capture ID
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON core_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_source ON core_alerts(source);
CREATE INDEX IF NOT EXISTS idx_alerts_domain ON core_alerts(domain);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON core_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_dedup ON core_alerts(dedup_key, created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_run ON core_alerts(run_id) WHERE run_id IS NOT NULL;


-- =============================================================================
-- ALERT DELIVERIES (Delivery Status Per Channel)
-- =============================================================================

-- Tracks delivery attempts for each alert to each channel
-- Enables retry and debugging
CREATE TABLE IF NOT EXISTS core_alert_deliveries (
    -- Identity
    id TEXT PRIMARY KEY,                    -- ULID
    alert_id TEXT NOT NULL,                 -- FK to core_alerts
    channel_id TEXT NOT NULL,               -- FK to core_alert_channels
    channel_name TEXT NOT NULL,             -- Denormalized for query efficiency
    
    -- Status
    status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, SENT, FAILED, THROTTLED
    
    -- Timing
    attempted_at TEXT,                      -- When delivery was attempted
    delivered_at TEXT,                      -- When confirmed delivered
    
    -- Result
    response_json TEXT,                     -- JSON: Channel response
    error TEXT,                             -- Error message if failed
    
    -- Retry
    attempt INTEGER NOT NULL DEFAULT 1,     -- Attempt number
    next_retry_at TEXT,                     -- When to retry (if failed)
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    UNIQUE(alert_id, channel_id, attempt)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_alert ON core_alert_deliveries(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_channel ON core_alert_deliveries(channel_id);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_status ON core_alert_deliveries(status);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_retry ON core_alert_deliveries(next_retry_at) WHERE status = 'FAILED';


-- =============================================================================
-- ALERT THROTTLE STATE (Deduplication Tracking)
-- =============================================================================

-- Tracks recent alerts to prevent spam
-- Records are cleaned up based on throttle window
CREATE TABLE IF NOT EXISTS core_alert_throttle (
    dedup_key TEXT PRIMARY KEY,             -- Hash of source+title+severity
    last_sent_at TEXT NOT NULL,             -- When last sent
    send_count INTEGER NOT NULL DEFAULT 1,  -- Times sent in window
    expires_at TEXT NOT NULL                -- When this entry can be removed
);

CREATE INDEX IF NOT EXISTS idx_alert_throttle_expires ON core_alert_throttle(expires_at);
