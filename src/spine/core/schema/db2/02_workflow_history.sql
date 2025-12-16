-- =============================================================================
-- SPINE CORE - WORKFLOW HISTORY TABLES (IBM DB2)
-- =============================================================================
-- Uses: GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR.
-- DB2 does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_workflow_runs (
    run_id VARCHAR(255) NOT NULL PRIMARY KEY,
    workflow_name VARCHAR(255) NOT NULL,
    workflow_version INTEGER NOT NULL DEFAULT 1,
    domain VARCHAR(255),
    partition_key CLOB,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    params CLOB,
    outputs CLOB,
    error CLOB,
    error_category VARCHAR(100),
    error_retryable SMALLINT,
    total_steps INTEGER NOT NULL DEFAULT 0,
    completed_steps INTEGER NOT NULL DEFAULT 0,
    failed_steps INTEGER NOT NULL DEFAULT 0,
    skipped_steps INTEGER NOT NULL DEFAULT 0,
    triggered_by VARCHAR(100) NOT NULL DEFAULT 'manual',
    parent_run_id VARCHAR(255),
    schedule_id VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    created_by VARCHAR(255),
    capture_id VARCHAR(255)
);

CREATE INDEX idx_workflow_runs_status ON core_workflow_runs(status);
CREATE INDEX idx_workflow_runs_name ON core_workflow_runs(workflow_name);
CREATE INDEX idx_workflow_runs_domain ON core_workflow_runs(domain);
CREATE INDEX idx_workflow_runs_started ON core_workflow_runs(started_at);
CREATE INDEX idx_workflow_runs_created ON core_workflow_runs(created_at);


CREATE TABLE core_workflow_steps (
    step_id VARCHAR(255) NOT NULL PRIMARY KEY,
    run_id VARCHAR(255) NOT NULL,
    step_name VARCHAR(255) NOT NULL,
    step_type VARCHAR(100) NOT NULL,
    step_order INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    params CLOB,
    outputs CLOB,
    error CLOB,
    error_category VARCHAR(100),
    row_count INTEGER,
    metrics CLOB,
    attempt INTEGER NOT NULL DEFAULT 1,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    execution_id VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    CONSTRAINT uq_step_run_attempt UNIQUE (run_id, step_name, attempt)
);

CREATE INDEX idx_workflow_steps_run ON core_workflow_steps(run_id);
CREATE INDEX idx_workflow_steps_status ON core_workflow_steps(status);
CREATE INDEX idx_workflow_steps_execution ON core_workflow_steps(execution_id);


CREATE TABLE core_workflow_events (
    id INTEGER NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id VARCHAR(255) NOT NULL,
    step_id VARCHAR(255),
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    payload CLOB,
    idempotency_key VARCHAR(255),
    CONSTRAINT uq_workflow_events_idemp UNIQUE (idempotency_key)
);

CREATE INDEX idx_workflow_events_run ON core_workflow_events(run_id, timestamp);
CREATE INDEX idx_workflow_events_step ON core_workflow_events(step_id);
CREATE INDEX idx_workflow_events_type ON core_workflow_events(event_type);
