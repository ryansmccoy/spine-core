-- =============================================================================
-- SPINE CORE - FRAMEWORK TABLES (MySQL / MariaDB)
-- =============================================================================
-- Uses: AUTO_INCREMENT, DATETIME, TINYINT for booleans, JSON type.
-- =============================================================================


CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    filename VARCHAR(255) NOT NULL UNIQUE,
    applied_at DATETIME NOT NULL DEFAULT NOW()
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_executions (
    id VARCHAR(255) PRIMARY KEY,
    pipeline VARCHAR(255) NOT NULL,
    params JSON DEFAULT (JSON_OBJECT()),
    lane VARCHAR(50) NOT NULL DEFAULT 'normal',
    trigger_source VARCHAR(100) NOT NULL DEFAULT 'api',
    logical_key VARCHAR(255),
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    parent_execution_id VARCHAR(255),
    created_at DATETIME NOT NULL,
    started_at DATETIME,
    completed_at DATETIME,
    result TEXT,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    idempotency_key VARCHAR(255),
    INDEX idx_core_executions_status (status),
    INDEX idx_core_executions_pipeline (pipeline),
    INDEX idx_core_executions_created_at (created_at),
    CONSTRAINT fk_exec_parent FOREIGN KEY (parent_execution_id) REFERENCES core_executions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_manifest (
    domain VARCHAR(255) NOT NULL,
    partition_key TEXT NOT NULL,
    stage VARCHAR(255) NOT NULL,
    stage_rank INTEGER,
    row_count INTEGER,
    metrics_json JSON,
    execution_id VARCHAR(255),
    batch_id VARCHAR(255),
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uq_manifest (domain, partition_key(255), stage),
    INDEX idx_core_manifest_domain_partition (domain, partition_key(255)),
    INDEX idx_core_manifest_domain_stage (domain, stage),
    INDEX idx_core_manifest_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_rejects (
    domain VARCHAR(255) NOT NULL,
    partition_key TEXT NOT NULL,
    stage VARCHAR(255) NOT NULL,
    reason_code VARCHAR(255) NOT NULL,
    reason_detail TEXT,
    raw_json JSON,
    record_key VARCHAR(255),
    source_locator VARCHAR(500),
    line_number INTEGER,
    execution_id VARCHAR(255) NOT NULL,
    batch_id VARCHAR(255),
    created_at DATETIME NOT NULL,
    INDEX idx_core_rejects_domain_partition (domain, partition_key(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_quality (
    domain VARCHAR(255) NOT NULL,
    partition_key TEXT NOT NULL,
    check_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    message TEXT,
    actual_value TEXT,
    expected_value TEXT,
    details_json JSON,
    execution_id VARCHAR(255) NOT NULL,
    batch_id VARCHAR(255),
    created_at DATETIME NOT NULL,
    INDEX idx_core_quality_domain_partition (domain, partition_key(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_anomalies (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    domain VARCHAR(255) NOT NULL,
    pipeline VARCHAR(255),
    partition_key TEXT,
    stage VARCHAR(255),
    severity VARCHAR(50) NOT NULL,
    category VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    details_json JSON,
    affected_records INTEGER,
    sample_records JSON,
    execution_id VARCHAR(255),
    batch_id VARCHAR(255),
    capture_id VARCHAR(255),
    detected_at DATETIME NOT NULL,
    resolved_at DATETIME,
    resolution_note TEXT,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    INDEX idx_core_anomalies_domain_partition (domain, partition_key(255)),
    INDEX idx_core_anomalies_severity (severity),
    INDEX idx_core_anomalies_category (category),
    INDEX idx_core_anomalies_detected_at (detected_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_work_items (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    domain VARCHAR(255) NOT NULL,
    pipeline VARCHAR(255) NOT NULL,
    partition_key TEXT NOT NULL,
    params_json JSON,
    desired_at DATETIME NOT NULL,
    priority INTEGER DEFAULT 100,
    state VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    last_error TEXT,
    last_error_at DATETIME,
    next_attempt_at DATETIME,
    current_execution_id VARCHAR(255),
    latest_execution_id VARCHAR(255),
    locked_by VARCHAR(255),
    locked_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    updated_at DATETIME NOT NULL DEFAULT NOW(),
    completed_at DATETIME,
    UNIQUE KEY uq_work_items (domain, pipeline, partition_key(255)),
    INDEX idx_core_work_items_state (state),
    INDEX idx_core_work_items_desired_at (desired_at),
    INDEX idx_core_work_items_next_attempt (state, next_attempt_at),
    INDEX idx_core_work_items_domain_pipeline (domain, pipeline),
    INDEX idx_core_work_items_partition (domain, partition_key(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_execution_events (
    id VARCHAR(255) PRIMARY KEY,
    execution_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    timestamp DATETIME NOT NULL,
    data JSON DEFAULT (JSON_OBJECT()),
    INDEX idx_core_execution_events_execution_id (execution_id),
    INDEX idx_core_execution_events_timestamp (timestamp),
    CONSTRAINT fk_execution FOREIGN KEY (execution_id) REFERENCES core_executions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_dead_letters (
    id VARCHAR(255) PRIMARY KEY,
    execution_id VARCHAR(255) NOT NULL,
    pipeline VARCHAR(255) NOT NULL,
    params JSON DEFAULT (JSON_OBJECT()),
    error TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at DATETIME NOT NULL,
    last_retry_at DATETIME,
    resolved_at DATETIME,
    resolved_by VARCHAR(255),
    INDEX idx_core_dead_letters_resolved (resolved_at),
    INDEX idx_core_dead_letters_pipeline (pipeline)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_concurrency_locks (
    lock_key VARCHAR(255) PRIMARY KEY,
    execution_id VARCHAR(255) NOT NULL,
    acquired_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    INDEX idx_core_concurrency_locks_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_schedules (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    target_type VARCHAR(50) NOT NULL DEFAULT 'pipeline',
    target_name VARCHAR(255) NOT NULL,
    params JSON,
    schedule_type VARCHAR(50) NOT NULL DEFAULT 'cron',
    cron_expression VARCHAR(100),
    interval_seconds INTEGER,
    run_at VARCHAR(50),
    timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    enabled TINYINT NOT NULL DEFAULT 1,
    max_instances INTEGER NOT NULL DEFAULT 1,
    misfire_grace_seconds INTEGER NOT NULL DEFAULT 60,
    last_run_at DATETIME,
    next_run_at DATETIME,
    last_run_status VARCHAR(50),
    created_at DATETIME NOT NULL DEFAULT NOW(),
    updated_at DATETIME NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255),
    version INTEGER NOT NULL DEFAULT 1,
    INDEX idx_schedules_enabled (enabled),
    INDEX idx_schedules_target (target_type, target_name),
    INDEX idx_schedules_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_schedule_runs (
    id VARCHAR(255) PRIMARY KEY,
    schedule_id VARCHAR(255) NOT NULL,
    schedule_name VARCHAR(255) NOT NULL,
    scheduled_at DATETIME NOT NULL,
    started_at DATETIME,
    completed_at DATETIME,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    run_id VARCHAR(255),
    execution_id VARCHAR(255),
    error TEXT,
    skip_reason TEXT,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    INDEX idx_schedule_runs_schedule_id (schedule_id),
    INDEX idx_schedule_runs_status (status),
    INDEX idx_schedule_runs_scheduled_at (scheduled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_schedule_locks (
    schedule_id VARCHAR(255) PRIMARY KEY,
    locked_by VARCHAR(255) NOT NULL,
    locked_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    INDEX idx_schedule_locks_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- =============================================================================
-- CALC DEPENDENCIES, EXPECTED SCHEDULES, DATA READINESS
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_calc_dependencies (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    calc_domain VARCHAR(255) NOT NULL,
    calc_pipeline VARCHAR(255) NOT NULL,
    calc_table VARCHAR(255),
    depends_on_domain VARCHAR(255) NOT NULL,
    depends_on_table VARCHAR(255) NOT NULL,
    dependency_type VARCHAR(50) NOT NULL,
    description TEXT,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    INDEX idx_core_calc_dependencies_calc (calc_domain, calc_pipeline),
    INDEX idx_core_calc_dependencies_upstream (depends_on_domain, depends_on_table)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_expected_schedules (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    domain VARCHAR(255) NOT NULL,
    pipeline VARCHAR(255) NOT NULL,
    schedule_type VARCHAR(50) NOT NULL,
    cron_expression VARCHAR(100),
    partition_template TEXT NOT NULL,
    partition_values TEXT,
    expected_delay_hours INTEGER,
    preliminary_hours INTEGER,
    description TEXT,
    is_active TINYINT DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT NOW(),
    updated_at DATETIME NOT NULL DEFAULT NOW(),
    INDEX idx_core_expected_schedules_domain (domain, pipeline),
    INDEX idx_core_expected_schedules_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_data_readiness (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    domain VARCHAR(255) NOT NULL,
    partition_key TEXT NOT NULL,
    is_ready TINYINT DEFAULT 0,
    ready_for VARCHAR(100),
    all_partitions_present TINYINT DEFAULT 0,
    all_stages_complete TINYINT DEFAULT 0,
    no_critical_anomalies TINYINT DEFAULT 0,
    dependencies_current TINYINT DEFAULT 0,
    age_exceeds_preliminary TINYINT DEFAULT 0,
    blocking_issues JSON,
    certified_at DATETIME,
    certified_by VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT NOW(),
    updated_at DATETIME NOT NULL DEFAULT NOW(),
    UNIQUE KEY uq_data_readiness (domain, partition_key(255), ready_for),
    INDEX idx_core_data_readiness_domain (domain, partition_key(255)),
    INDEX idx_core_data_readiness_status (is_ready, ready_for)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
