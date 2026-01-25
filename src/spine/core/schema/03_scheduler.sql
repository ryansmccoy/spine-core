-- =============================================================================
-- SPINE CORE - SCHEDULER TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Tables for cron-based pipeline scheduling.
--              Stores schedule definitions and execution history.
--
-- Tier Usage:
--   Basic: Not used (manual/external cron only)
--   Intermediate: Required (APScheduler-based)
--   Advanced/Full: Required (+ distributed locks)
--
-- Design Principles Applied:
--   #5 Immutability: Schedule definitions are versioned, not updated
--   #13 Observable: All schedule executions tracked
--
-- Dependencies: Requires core_workflow_runs table (from 02_workflow_history.sql)
-- =============================================================================


-- =============================================================================
-- SCHEDULES (Schedule Definitions)
-- =============================================================================

-- Stores cron-based schedule definitions for pipelines and workflows
CREATE TABLE IF NOT EXISTS core_schedules (
    -- Identity
    id TEXT PRIMARY KEY,                    -- ULID
    name TEXT NOT NULL UNIQUE,              -- e.g., "finra.weekly_refresh"
    
    -- Target
    target_type TEXT NOT NULL DEFAULT 'pipeline',  -- pipeline, workflow
    target_name TEXT NOT NULL,              -- Pipeline or workflow name
    params TEXT,                            -- JSON: Default parameters
    
    -- Schedule specification
    schedule_type TEXT NOT NULL DEFAULT 'cron',  -- cron, interval, date
    cron_expression TEXT,                   -- e.g., "0 6 * * 1-5" (6 AM Mon-Fri)
    interval_seconds INTEGER,               -- For interval schedules
    run_at TEXT,                            -- For one-time schedules
    timezone TEXT NOT NULL DEFAULT 'UTC',
    
    -- State
    enabled INTEGER NOT NULL DEFAULT 1,     -- 1=enabled, 0=disabled
    
    -- Execution control
    max_instances INTEGER NOT NULL DEFAULT 1,   -- Prevent overlapping runs
    misfire_grace_seconds INTEGER NOT NULL DEFAULT 60,  -- Allow late execution
    
    -- Timing
    last_run_at TEXT,                       -- ISO timestamp
    next_run_at TEXT,                       -- ISO timestamp (computed)
    last_run_status TEXT,                   -- COMPLETED, FAILED
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT,
    
    -- Versioning (for history)
    version INTEGER NOT NULL DEFAULT 1
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON core_schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON core_schedules(next_run_at) WHERE enabled = 1;
CREATE INDEX IF NOT EXISTS idx_schedules_target ON core_schedules(target_type, target_name);
CREATE INDEX IF NOT EXISTS idx_schedules_name ON core_schedules(name);


-- =============================================================================
-- SCHEDULE RUNS (Scheduled Execution History)
-- =============================================================================

-- Tracks each scheduled execution attempt
-- Links schedules to their workflow/pipeline runs
CREATE TABLE IF NOT EXISTS core_schedule_runs (
    -- Identity
    id TEXT PRIMARY KEY,                    -- ULID
    schedule_id TEXT NOT NULL,              -- FK to core_schedules
    schedule_name TEXT NOT NULL,            -- Denormalized for query efficiency
    
    -- Timing
    scheduled_at TEXT NOT NULL,             -- When it was supposed to run
    started_at TEXT,                        -- When it actually started
    completed_at TEXT,                       -- When it finished
    
    -- Status
    status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, MISSED
    
    -- Execution linkage
    run_id TEXT,                            -- FK to core_workflow_runs
    execution_id TEXT,                      -- FK to core_executions (if pipeline)
    
    -- Results
    error TEXT,                             -- Error message if failed
    skip_reason TEXT,                       -- Why skipped (if applicable)
    
    -- Audit
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule ON core_schedule_runs(schedule_id);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_status ON core_schedule_runs(status);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_scheduled ON core_schedule_runs(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_schedule_runs_created ON core_schedule_runs(created_at);


-- =============================================================================
-- SCHEDULE LOCKS (Distributed Lock Support - Advanced Tier)
-- =============================================================================

-- Prevents multiple scheduler instances from running same schedule
-- Only needed for distributed deployments
CREATE TABLE IF NOT EXISTS core_schedule_locks (
    schedule_id TEXT PRIMARY KEY,           -- FK to core_schedules
    locked_by TEXT NOT NULL,                -- Instance ID that holds lock
    locked_at TEXT NOT NULL,                -- When lock was acquired
    expires_at TEXT NOT NULL                -- Auto-release time
);

CREATE INDEX IF NOT EXISTS idx_schedule_locks_expires ON core_schedule_locks(expires_at);
