-- =============================================================================
-- SPINE CORE - WORKFLOW HISTORY TABLES (Oracle)
-- =============================================================================
-- Uses: NUMBER GENERATED ALWAYS AS IDENTITY, TIMESTAMP, CLOB, VARCHAR2.
-- Oracle does not support IF NOT EXISTS on CREATE TABLE.
-- =============================================================================


CREATE TABLE core_workflow_runs (
    run_id VARCHAR2(255) PRIMARY KEY,
    workflow_name VARCHAR2(255) NOT NULL,
    workflow_version NUMBER DEFAULT 1 NOT NULL,
    domain VARCHAR2(255),
    partition_key CLOB,
    status VARCHAR2(50) DEFAULT 'PENDING' NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms NUMBER,
    params CLOB,
    outputs CLOB,
    error CLOB,
    error_category VARCHAR2(100),
    error_retryable NUMBER(1),
    total_steps NUMBER DEFAULT 0 NOT NULL,
    completed_steps NUMBER DEFAULT 0 NOT NULL,
    failed_steps NUMBER DEFAULT 0 NOT NULL,
    skipped_steps NUMBER DEFAULT 0 NOT NULL,
    triggered_by VARCHAR2(100) DEFAULT 'manual' NOT NULL,
    parent_run_id VARCHAR2(255),
    schedule_id VARCHAR2(255),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    created_by VARCHAR2(255),
    capture_id VARCHAR2(255)
);

CREATE INDEX idx_workflow_runs_status ON core_workflow_runs(status);
CREATE INDEX idx_workflow_runs_name ON core_workflow_runs(workflow_name);
CREATE INDEX idx_workflow_runs_domain ON core_workflow_runs(domain);
CREATE INDEX idx_workflow_runs_started ON core_workflow_runs(started_at);
CREATE INDEX idx_workflow_runs_created ON core_workflow_runs(created_at);


CREATE TABLE core_workflow_steps (
    step_id VARCHAR2(255) PRIMARY KEY,
    run_id VARCHAR2(255) NOT NULL,
    step_name VARCHAR2(255) NOT NULL,
    step_type VARCHAR2(100) NOT NULL,
    step_order NUMBER NOT NULL,
    status VARCHAR2(50) DEFAULT 'PENDING' NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms NUMBER,
    params CLOB,
    outputs CLOB,
    error CLOB,
    error_category VARCHAR2(100),
    row_count NUMBER,
    metrics CLOB,
    attempt NUMBER DEFAULT 1 NOT NULL,
    max_attempts NUMBER DEFAULT 1 NOT NULL,
    execution_id VARCHAR2(255),
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_step_run_attempt UNIQUE (run_id, step_name, attempt)
);

CREATE INDEX idx_workflow_steps_run ON core_workflow_steps(run_id);
CREATE INDEX idx_workflow_steps_status ON core_workflow_steps(status);
CREATE INDEX idx_workflow_steps_execution ON core_workflow_steps(execution_id);


CREATE TABLE core_workflow_events (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id VARCHAR2(255) NOT NULL,
    step_id VARCHAR2(255),
    event_type VARCHAR2(100) NOT NULL,
    timestamp TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    payload CLOB,
    idempotency_key VARCHAR2(255) UNIQUE
);

CREATE INDEX idx_workflow_events_run ON core_workflow_events(run_id, timestamp);
CREATE INDEX idx_workflow_events_step ON core_workflow_events(step_id);
CREATE INDEX idx_workflow_events_type ON core_workflow_events(event_type);
