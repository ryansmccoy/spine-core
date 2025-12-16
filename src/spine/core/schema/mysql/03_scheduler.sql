-- =============================================================================
-- SPINE CORE - SCHEDULER TABLES (MySQL / MariaDB)
-- =============================================================================
-- Uses: AUTO_INCREMENT, DATETIME, TINYINT for booleans, JSON type.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_schedules (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    target_type VARCHAR(100) NOT NULL DEFAULT 'pipeline',
    target_name VARCHAR(255) NOT NULL,
    params JSON,
    schedule_type VARCHAR(50) NOT NULL DEFAULT 'cron',
    cron_expression VARCHAR(255),
    interval_seconds INTEGER,
    run_at VARCHAR(255),
    timezone VARCHAR(100) NOT NULL DEFAULT 'UTC',
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
    INDEX idx_schedules_next_run (next_run_at),
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
    INDEX idx_schedule_runs_schedule (schedule_id),
    INDEX idx_schedule_runs_status (status),
    INDEX idx_schedule_runs_scheduled (scheduled_at),
    INDEX idx_schedule_runs_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS core_schedule_locks (
    schedule_id VARCHAR(255) PRIMARY KEY,
    locked_by VARCHAR(255) NOT NULL,
    locked_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    INDEX idx_schedule_locks_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
