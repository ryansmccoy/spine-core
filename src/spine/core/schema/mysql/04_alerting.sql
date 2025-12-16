-- =============================================================================
-- SPINE CORE - ALERTING TABLES (MySQL / MariaDB)
-- =============================================================================
-- Uses: AUTO_INCREMENT, DATETIME, TINYINT for booleans, JSON type.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_alert_channels (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    channel_type VARCHAR(100) NOT NULL,
    config_json JSON NOT NULL,
    min_severity VARCHAR(50) NOT NULL DEFAULT 'ERROR',
    domains JSON,
    enabled TINYINT NOT NULL DEFAULT 1,
    throttle_minutes INTEGER NOT NULL DEFAULT 5,
    last_success_at DATETIME,
    last_failure_at DATETIME,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    updated_at DATETIME NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255),
    INDEX idx_alert_channels_type (channel_type),
    INDEX idx_alert_channels_enabled (enabled),
    INDEX idx_alert_channels_severity (min_severity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_alerts (
    id VARCHAR(255) PRIMARY KEY,
    severity VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    message TEXT NOT NULL,
    source VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    execution_id VARCHAR(255),
    run_id VARCHAR(255),
    metadata_json JSON,
    error_category VARCHAR(100),
    created_at DATETIME NOT NULL DEFAULT NOW(),
    dedup_key VARCHAR(255),
    capture_id VARCHAR(255),
    INDEX idx_alerts_severity (severity),
    INDEX idx_alerts_source (source),
    INDEX idx_alerts_domain (domain),
    INDEX idx_alerts_created (created_at),
    INDEX idx_alerts_dedup (dedup_key, created_at),
    INDEX idx_alerts_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_alert_deliveries (
    id VARCHAR(255) PRIMARY KEY,
    alert_id VARCHAR(255) NOT NULL,
    channel_id VARCHAR(255) NOT NULL,
    channel_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    attempted_at DATETIME,
    delivered_at DATETIME,
    response_json JSON,
    error TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    next_retry_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    UNIQUE KEY uq_delivery_attempt (alert_id, channel_id, attempt),
    INDEX idx_alert_deliveries_alert (alert_id),
    INDEX idx_alert_deliveries_channel (channel_id),
    INDEX idx_alert_deliveries_status (status),
    INDEX idx_alert_deliveries_retry (next_retry_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_alert_throttle (
    dedup_key VARCHAR(255) PRIMARY KEY,
    last_sent_at DATETIME NOT NULL,
    send_count INTEGER NOT NULL DEFAULT 1,
    expires_at DATETIME NOT NULL,
    INDEX idx_alert_throttle_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
