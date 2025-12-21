-- =============================================================================
-- SPINE CORE - SCHEDULER TABLES (Oracle)
-- =============================================================================
-- Uses: NUMBER GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR2.
-- Oracle does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_schedules (
    id VARCHAR2(255) PRIMARY KEY,
    name VARCHAR2(255) NOT NULL UNIQUE,
    target_type VARCHAR2(100) DEFAULT 'operation' NOT NULL,
    target_name VARCHAR2(255) NOT NULL,
    params CLOB,
    schedule_type VARCHAR2(50) DEFAULT 'cron' NOT NULL,
    cron_expression VARCHAR2(255),
    interval_seconds NUMBER,
    run_at VARCHAR2(255),
    timezone VARCHAR2(100) DEFAULT 'UTC' NOT NULL,
    enabled NUMBER(1) DEFAULT 1 NOT NULL,
    max_instances NUMBER DEFAULT 1 NOT NULL,
    misfire_grace_seconds NUMBER DEFAULT 60 NOT NULL,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    last_run_status VARCHAR2(50),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    created_by VARCHAR2(255),
    version NUMBER DEFAULT 1 NOT NULL
);

CREATE INDEX idx_schedules_enabled ON core_schedules(enabled);
CREATE INDEX idx_schedules_next_run ON core_schedules(next_run_at);
CREATE INDEX idx_schedules_target ON core_schedules(target_type, target_name);
CREATE INDEX idx_schedules_name ON core_schedules(name);


CREATE TABLE core_schedule_runs (
    id VARCHAR2(255) PRIMARY KEY,
    schedule_id VARCHAR2(255) NOT NULL,
    schedule_name VARCHAR2(255) NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR2(50) DEFAULT 'PENDING' NOT NULL,
    run_id VARCHAR2(255),
    execution_id VARCHAR2(255),
    error CLOB,
    skip_reason CLOB,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

CREATE INDEX idx_schedule_runs_schedule ON core_schedule_runs(schedule_id);
CREATE INDEX idx_schedule_runs_status ON core_schedule_runs(status);
CREATE INDEX idx_schedule_runs_scheduled ON core_schedule_runs(scheduled_at);
CREATE INDEX idx_schedule_runs_created ON core_schedule_runs(created_at);


CREATE TABLE core_schedule_locks (
    schedule_id VARCHAR2(255) PRIMARY KEY,
    locked_by VARCHAR2(255) NOT NULL,
    locked_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_schedule_locks_expires ON core_schedule_locks(expires_at);
