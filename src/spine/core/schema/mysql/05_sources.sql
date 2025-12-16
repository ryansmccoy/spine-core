-- =============================================================================
-- SPINE CORE - SOURCE TRACKING TABLES (MySQL / MariaDB)
-- =============================================================================
-- Uses: AUTO_INCREMENT, DATETIME, TINYINT for booleans, JSON type, LONGBLOB.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_sources (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    source_type VARCHAR(100) NOT NULL,
    config_json JSON NOT NULL,
    domain VARCHAR(255),
    enabled TINYINT NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    updated_at DATETIME NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255),
    INDEX idx_sources_type (source_type),
    INDEX idx_sources_domain (domain),
    INDEX idx_sources_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_source_fetches (
    id VARCHAR(255) PRIMARY KEY,
    source_id VARCHAR(255),
    source_name VARCHAR(255) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    source_locator TEXT NOT NULL,
    status VARCHAR(50) NOT NULL,
    record_count INTEGER,
    byte_count INTEGER,
    content_hash VARCHAR(255),
    etag VARCHAR(255),
    last_modified VARCHAR(255),
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    duration_ms INTEGER,
    error TEXT,
    error_category VARCHAR(100),
    retry_count INTEGER NOT NULL DEFAULT 0,
    execution_id VARCHAR(255),
    run_id VARCHAR(255),
    capture_id VARCHAR(255),
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    INDEX idx_source_fetches_source (source_id),
    INDEX idx_source_fetches_status (status),
    INDEX idx_source_fetches_hash (content_hash),
    INDEX idx_source_fetches_started (started_at),
    INDEX idx_source_fetches_execution (execution_id),
    INDEX idx_source_fetches_run (run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_source_cache (
    cache_key VARCHAR(255) PRIMARY KEY,
    source_id VARCHAR(255),
    source_type VARCHAR(100) NOT NULL,
    source_locator TEXT NOT NULL,
    content_hash VARCHAR(255) NOT NULL,
    content_size INTEGER NOT NULL,
    content_path TEXT,
    content_blob LONGBLOB,
    fetched_at DATETIME NOT NULL,
    expires_at DATETIME,
    etag VARCHAR(255),
    last_modified VARCHAR(255),
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    last_accessed_at DATETIME,
    INDEX idx_source_cache_source (source_id),
    INDEX idx_source_cache_expires (expires_at),
    INDEX idx_source_cache_accessed (last_accessed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_database_connections (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    dialect VARCHAR(100) NOT NULL,
    host VARCHAR(255),
    port INTEGER,
    `database` VARCHAR(255) NOT NULL,
    username VARCHAR(255),
    password_ref VARCHAR(255),
    pool_size INTEGER NOT NULL DEFAULT 5,
    max_overflow INTEGER NOT NULL DEFAULT 10,
    pool_timeout INTEGER NOT NULL DEFAULT 30,
    enabled TINYINT NOT NULL DEFAULT 1,
    last_connected_at DATETIME,
    last_error TEXT,
    last_error_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    updated_at DATETIME NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255),
    INDEX idx_db_connections_dialect (dialect),
    INDEX idx_db_connections_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
