-- =============================================================================
-- SPINE CORE - ALERTING TABLES (IBM DB2)
-- =============================================================================
-- Uses: GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR, SMALLINT.
-- DB2 does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_alert_channels (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    channel_type VARCHAR(100) NOT NULL,
    config_json CLOB NOT NULL,
    min_severity VARCHAR(50) NOT NULL DEFAULT 'ERROR',
    domains CLOB,
    enabled SMALLINT NOT NULL DEFAULT 1,
    throttle_minutes INTEGER NOT NULL DEFAULT 5,
    last_success_at TIMESTAMP,
    last_failure_at TIMESTAMP,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    created_by VARCHAR(255),
    CONSTRAINT uq_alert_channels_name UNIQUE (name)
);

CREATE INDEX idx_alert_channels_type ON core_alert_channels(channel_type);
CREATE INDEX idx_alert_channels_enabled ON core_alert_channels(enabled);
CREATE INDEX idx_alert_channels_severity ON core_alert_channels(min_severity);


CREATE TABLE core_alerts (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    severity VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    message CLOB NOT NULL,
    source VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    execution_id VARCHAR(255),
    run_id VARCHAR(255),
    metadata_json CLOB,
    error_category VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    dedup_key VARCHAR(255),
    capture_id VARCHAR(255)
);

CREATE INDEX idx_alerts_severity ON core_alerts(severity);
CREATE INDEX idx_alerts_source ON core_alerts(source);
CREATE INDEX idx_alerts_domain ON core_alerts(domain);
CREATE INDEX idx_alerts_created ON core_alerts(created_at);
CREATE INDEX idx_alerts_dedup ON core_alerts(dedup_key, created_at);
CREATE INDEX idx_alerts_run ON core_alerts(run_id);


CREATE TABLE core_alert_deliveries (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    alert_id VARCHAR(255) NOT NULL,
    channel_id VARCHAR(255) NOT NULL,
    channel_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    attempted_at TIMESTAMP,
    delivered_at TIMESTAMP,
    response_json CLOB,
    error CLOB,
    attempt INTEGER NOT NULL DEFAULT 1,
    next_retry_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    CONSTRAINT uq_delivery_attempt UNIQUE (alert_id, channel_id, attempt)
);

CREATE INDEX idx_alert_deliveries_alert ON core_alert_deliveries(alert_id);
CREATE INDEX idx_alert_deliveries_channel ON core_alert_deliveries(channel_id);
CREATE INDEX idx_alert_deliveries_status ON core_alert_deliveries(status);
CREATE INDEX idx_alert_deliveries_retry ON core_alert_deliveries(next_retry_at);


CREATE TABLE core_alert_throttle (
    dedup_key VARCHAR(255) NOT NULL PRIMARY KEY,
    last_sent_at TIMESTAMP NOT NULL,
    send_count INTEGER NOT NULL DEFAULT 1,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_alert_throttle_expires ON core_alert_throttle(expires_at);
