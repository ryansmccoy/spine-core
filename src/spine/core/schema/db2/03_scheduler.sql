-- =============================================================================
-- SPINE CORE - SCHEDULER TABLES (IBM DB2)
-- =============================================================================
-- Uses: GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR.
-- DB2 does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_schedules (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    target_type VARCHAR(100) NOT NULL DEFAULT 'operation',
    target_name VARCHAR(255) NOT NULL,
    params CLOB,
    schedule_type VARCHAR(50) NOT NULL DEFAULT 'cron',
    cron_expression VARCHAR(255),
    interval_seconds INTEGER,
    run_at VARCHAR(255),
    timezone VARCHAR(100) NOT NULL DEFAULT 'UTC',
    enabled SMALLINT NOT NULL DEFAULT 1,
    max_instances INTEGER NOT NULL DEFAULT 1,
    misfire_grace_seconds INTEGER NOT NULL DEFAULT 60,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    last_run_status VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    created_by VARCHAR(255),
    version INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT uq_schedules_name UNIQUE (name)
);

CREATE INDEX idx_schedules_enabled ON core_schedules(enabled);
CREATE INDEX idx_schedules_next_run ON core_schedules(next_run_at);
CREATE INDEX idx_schedules_target ON core_schedules(target_type, target_name);
CREATE INDEX idx_schedules_name ON core_schedules(name);


CREATE TABLE core_schedule_runs (
    id VARCHAR(255) NOT NULL PRIMARY KEY,
    schedule_id VARCHAR(255) NOT NULL,
    schedule_name VARCHAR(255) NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    run_id VARCHAR(255),
    execution_id VARCHAR(255),
    error CLOB,
    skip_reason CLOB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);

CREATE INDEX idx_schedule_runs_schedule ON core_schedule_runs(schedule_id);
CREATE INDEX idx_schedule_runs_status ON core_schedule_runs(status);
CREATE INDEX idx_schedule_runs_scheduled ON core_schedule_runs(scheduled_at);
CREATE INDEX idx_schedule_runs_created ON core_schedule_runs(created_at);


CREATE TABLE core_schedule_locks (
    schedule_id VARCHAR(255) NOT NULL PRIMARY KEY,
    locked_by VARCHAR(255) NOT NULL,
    locked_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_schedule_locks_expires ON core_schedule_locks(expires_at);
