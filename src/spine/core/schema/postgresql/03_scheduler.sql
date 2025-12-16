-- =============================================================================
-- SPINE CORE - SCHEDULER TABLES (PostgreSQL)
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_schedules (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    target_type TEXT NOT NULL DEFAULT 'pipeline',
    target_name TEXT NOT NULL,
    params JSONB,
    schedule_type TEXT NOT NULL DEFAULT 'cron',
    cron_expression TEXT,
    interval_seconds INTEGER,
    run_at TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    max_instances INTEGER NOT NULL DEFAULT 1,
    misfire_grace_seconds INTEGER NOT NULL DEFAULT 60,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    last_run_status TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by TEXT,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON core_schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON core_schedules(next_run_at) WHERE enabled = TRUE;
CREATE INDEX IF NOT EXISTS idx_schedules_target ON core_schedules(target_type, target_name);
CREATE INDEX IF NOT EXISTS idx_schedules_name ON core_schedules(name);


CREATE TABLE IF NOT EXISTS core_schedule_runs (
    id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    schedule_name TEXT NOT NULL,
    scheduled_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'PENDING',
    run_id TEXT,
    execution_id TEXT,
    error TEXT,
    skip_reason TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule_id ON core_schedule_runs(schedule_id);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_status ON core_schedule_runs(status);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_scheduled_at ON core_schedule_runs(scheduled_at);


CREATE TABLE IF NOT EXISTS core_schedule_locks (
    schedule_id TEXT PRIMARY KEY,
    locked_by TEXT NOT NULL,
    locked_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_schedule_locks_expires ON core_schedule_locks(expires_at);
