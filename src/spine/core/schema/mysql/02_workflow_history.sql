-- =============================================================================
-- SPINE CORE - WORKFLOW HISTORY TABLES (MySQL / MariaDB)
-- =============================================================================
-- Uses: AUTO_INCREMENT, DATETIME, TINYINT for booleans, JSON type.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_workflow_runs (
    run_id VARCHAR(255) PRIMARY KEY,
    workflow_name VARCHAR(255) NOT NULL,
    workflow_version INTEGER NOT NULL DEFAULT 1,
    domain VARCHAR(255),
    partition_key TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    started_at DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER,
    params JSON,
    outputs JSON,
    error TEXT,
    error_category VARCHAR(100),
    error_retryable TINYINT,
    total_steps INTEGER NOT NULL DEFAULT 0,
    completed_steps INTEGER NOT NULL DEFAULT 0,
    failed_steps INTEGER NOT NULL DEFAULT 0,
    skipped_steps INTEGER NOT NULL DEFAULT 0,
    triggered_by VARCHAR(100) NOT NULL DEFAULT 'manual',
    parent_run_id VARCHAR(255),
    schedule_id VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255),
    capture_id VARCHAR(255),
    INDEX idx_workflow_runs_status (status),
    INDEX idx_workflow_runs_name (workflow_name),
    INDEX idx_workflow_runs_domain (domain),
    INDEX idx_workflow_runs_started (started_at),
    INDEX idx_workflow_runs_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_workflow_steps (
    step_id VARCHAR(255) PRIMARY KEY,
    run_id VARCHAR(255) NOT NULL,
    step_name VARCHAR(255) NOT NULL,
    step_type VARCHAR(100) NOT NULL,
    step_order INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    started_at DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER,
    params JSON,
    outputs JSON,
    error TEXT,
    error_category VARCHAR(100),
    row_count INTEGER,
    metrics JSON,
    attempt INTEGER NOT NULL DEFAULT 1,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    execution_id VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT NOW(),
    UNIQUE KEY uq_step_run_attempt (run_id, step_name, attempt),
    INDEX idx_workflow_steps_run (run_id),
    INDEX idx_workflow_steps_status (status),
    INDEX idx_workflow_steps_execution (execution_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_workflow_events (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    run_id VARCHAR(255) NOT NULL,
    step_id VARCHAR(255),
    event_type VARCHAR(100) NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT NOW(),
    payload JSON,
    idempotency_key VARCHAR(255) UNIQUE,
    INDEX idx_workflow_events_run (run_id, timestamp),
    INDEX idx_workflow_events_step (step_id),
    INDEX idx_workflow_events_type (event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
