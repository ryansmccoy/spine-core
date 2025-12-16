-- =============================================================================
-- SPINE CORE - ALERTING TABLES (PostgreSQL)
-- =============================================================================
-- Uses: SERIAL, TIMESTAMP, BOOLEAN, JSONB, partial indexes.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_alert_channels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    channel_type TEXT NOT NULL,
    config_json JSONB NOT NULL,
    min_severity TEXT NOT NULL DEFAULT 'ERROR',
    domains JSONB,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    throttle_minutes INTEGER NOT NULL DEFAULT 5,
    last_success_at TIMESTAMP,
    last_failure_at TIMESTAMP,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_channels_type ON core_alert_channels(channel_type);
CREATE INDEX IF NOT EXISTS idx_alert_channels_enabled ON core_alert_channels(enabled);
CREATE INDEX IF NOT EXISTS idx_alert_channels_severity ON core_alert_channels(min_severity);


CREATE TABLE IF NOT EXISTS core_alerts (
    id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    source TEXT NOT NULL,
    domain TEXT,
    execution_id TEXT,
    run_id TEXT,
    metadata_json JSONB,
    error_category TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    dedup_key TEXT,
    capture_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_severity ON core_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_source ON core_alerts(source);
CREATE INDEX IF NOT EXISTS idx_alerts_domain ON core_alerts(domain);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON core_alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_dedup ON core_alerts(dedup_key, created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_run ON core_alerts(run_id) WHERE run_id IS NOT NULL;


CREATE TABLE IF NOT EXISTS core_alert_deliveries (
    id TEXT PRIMARY KEY,
    alert_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempted_at TIMESTAMP,
    delivered_at TIMESTAMP,
    response_json JSONB,
    error TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    next_retry_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(alert_id, channel_id, attempt)
);

CREATE INDEX IF NOT EXISTS idx_alert_deliveries_alert ON core_alert_deliveries(alert_id);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_channel ON core_alert_deliveries(channel_id);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_status ON core_alert_deliveries(status);
CREATE INDEX IF NOT EXISTS idx_alert_deliveries_retry ON core_alert_deliveries(next_retry_at) WHERE status = 'FAILED';


CREATE TABLE IF NOT EXISTS core_alert_throttle (
    dedup_key TEXT PRIMARY KEY,
    last_sent_at TIMESTAMP NOT NULL,
    send_count INTEGER NOT NULL DEFAULT 1,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alert_throttle_expires ON core_alert_throttle(expires_at);
