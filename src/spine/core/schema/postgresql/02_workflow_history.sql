-- =============================================================================
-- SPINE CORE - WORKFLOW HISTORY TABLES (PostgreSQL)
-- =============================================================================
-- Uses: SERIAL, TIMESTAMP, BOOLEAN, JSONB, partial indexes.
-- =============================================================================


CREATE TABLE IF NOT EXISTS core_workflow_runs (
    run_id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    workflow_version INTEGER NOT NULL DEFAULT 1,
    domain TEXT,
    partition_key TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    params JSONB,
    outputs JSONB,
    error TEXT,
    error_category TEXT,
    error_retryable BOOLEAN,
    total_steps INTEGER NOT NULL DEFAULT 0,
    completed_steps INTEGER NOT NULL DEFAULT 0,
    failed_steps INTEGER NOT NULL DEFAULT 0,
    skipped_steps INTEGER NOT NULL DEFAULT 0,
    triggered_by TEXT NOT NULL DEFAULT 'manual',
    parent_run_id TEXT,
    schedule_id TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by TEXT,
    capture_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON core_workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_name ON core_workflow_runs(workflow_name);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_domain ON core_workflow_runs(domain);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started ON core_workflow_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_created ON core_workflow_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_parent ON core_workflow_runs(parent_run_id) WHERE parent_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_runs_schedule ON core_workflow_runs(schedule_id) WHERE schedule_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_runs_failed ON core_workflow_runs(status, created_at) WHERE status = 'FAILED';


CREATE TABLE IF NOT EXISTS core_workflow_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_type TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms INTEGER,
    params JSONB,
    outputs JSONB,
    error TEXT,
    error_category TEXT,
    row_count INTEGER,
    metrics JSONB,
    attempt INTEGER NOT NULL DEFAULT 1,
    max_attempts INTEGER NOT NULL DEFAULT 1,
    execution_id TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(run_id, step_name, attempt)
);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_run ON core_workflow_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_status ON core_workflow_steps(status);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_execution ON core_workflow_steps(execution_id) WHERE execution_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_steps_failed ON core_workflow_steps(run_id, status) WHERE status = 'FAILED';


CREATE TABLE IF NOT EXISTS core_workflow_events (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    payload JSONB,
    idempotency_key TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_workflow_events_run ON core_workflow_events(run_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_workflow_events_step ON core_workflow_events(step_id) WHERE step_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_events_type ON core_workflow_events(event_type);
