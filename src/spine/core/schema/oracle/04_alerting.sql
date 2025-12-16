-- =============================================================================
-- SPINE CORE - ALERTING TABLES (Oracle)
-- =============================================================================
-- Uses: NUMBER GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR2, NUMBER(1).
-- Oracle does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_alert_channels (
    id VARCHAR2(255) PRIMARY KEY,
    name VARCHAR2(255) NOT NULL UNIQUE,
    channel_type VARCHAR2(100) NOT NULL,
    config_json CLOB NOT NULL,
    min_severity VARCHAR2(50) DEFAULT 'ERROR' NOT NULL,
    domains CLOB,
    enabled NUMBER(1) DEFAULT 1 NOT NULL,
    throttle_minutes NUMBER DEFAULT 5 NOT NULL,
    last_success_at TIMESTAMP,
    last_failure_at TIMESTAMP,
    consecutive_failures NUMBER DEFAULT 0 NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    created_by VARCHAR2(255)
);

CREATE INDEX idx_alert_channels_type ON core_alert_channels(channel_type);
CREATE INDEX idx_alert_channels_enabled ON core_alert_channels(enabled);
CREATE INDEX idx_alert_channels_severity ON core_alert_channels(min_severity);


CREATE TABLE core_alerts (
    id VARCHAR2(255) PRIMARY KEY,
    severity VARCHAR2(50) NOT NULL,
    title VARCHAR2(500) NOT NULL,
    message CLOB NOT NULL,
    source VARCHAR2(255) NOT NULL,
    domain VARCHAR2(255),
    execution_id VARCHAR2(255),
    run_id VARCHAR2(255),
    metadata_json CLOB,
    error_category VARCHAR2(100),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    dedup_key VARCHAR2(255),
    capture_id VARCHAR2(255)
);

CREATE INDEX idx_alerts_severity ON core_alerts(severity);
CREATE INDEX idx_alerts_source ON core_alerts(source);
CREATE INDEX idx_alerts_domain ON core_alerts(domain);
CREATE INDEX idx_alerts_created ON core_alerts(created_at);
CREATE INDEX idx_alerts_dedup ON core_alerts(dedup_key, created_at);
CREATE INDEX idx_alerts_run ON core_alerts(run_id);


CREATE TABLE core_alert_deliveries (
    id VARCHAR2(255) PRIMARY KEY,
    alert_id VARCHAR2(255) NOT NULL,
    channel_id VARCHAR2(255) NOT NULL,
    channel_name VARCHAR2(255) NOT NULL,
    status VARCHAR2(50) DEFAULT 'PENDING' NOT NULL,
    attempted_at TIMESTAMP,
    delivered_at TIMESTAMP,
    response_json CLOB,
    error CLOB,
    attempt NUMBER DEFAULT 1 NOT NULL,
    next_retry_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_delivery_attempt UNIQUE (alert_id, channel_id, attempt)
);

CREATE INDEX idx_alert_deliveries_alert ON core_alert_deliveries(alert_id);
CREATE INDEX idx_alert_deliveries_channel ON core_alert_deliveries(channel_id);
CREATE INDEX idx_alert_deliveries_status ON core_alert_deliveries(status);
CREATE INDEX idx_alert_deliveries_retry ON core_alert_deliveries(next_retry_at);


CREATE TABLE core_alert_throttle (
    dedup_key VARCHAR2(255) PRIMARY KEY,
    last_sent_at TIMESTAMP NOT NULL,
    send_count NUMBER DEFAULT 1 NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_alert_throttle_expires ON core_alert_throttle(expires_at);
