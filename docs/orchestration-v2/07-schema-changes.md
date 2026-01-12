# Database Schema Changes

> **Document**: SQL schema changes for Orchestration v2

## Overview

Orchestration v2 extends the existing schema to support:
1. **Workflow definitions** (parallel to pipeline groups)
2. **Workflow runs with context** (captures context at each step)
3. **Checkpoints** (resume from failure)
4. **Quality metrics** (per-step quality tracking)

## New Tables

### core_workflows

Stores workflow definitions (alternative to code definitions):

```sql
-- =============================================================================
-- WORKFLOWS (Workflow Definitions)
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_workflows (
    id TEXT PRIMARY KEY,                    -- ULID
    name TEXT NOT NULL UNIQUE,              -- e.g., "finra.weekly_etl"
    domain TEXT NOT NULL,                   -- e.g., "finra.otc_transparency"
    version INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    spec TEXT NOT NULL,                     -- JSON: Full workflow spec
    tags TEXT,                              -- JSON array
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_core_workflows_domain 
    ON core_workflows(domain);
CREATE INDEX IF NOT EXISTS idx_core_workflows_active 
    ON core_workflows(is_active) WHERE is_active = 1;
```

**spec JSON schema:**
```json
{
  "name": "finra.weekly_etl",
  "steps": [
    {
      "type": "pipeline",
      "name": "fetch",
      "pipeline": "finra.otc_transparency.ingest_week",
      "params": {"tier": "NMS_TIER_1"}
    },
    {
      "type": "lambda",
      "name": "validate",
      "handler": "finra.validate_otc_data",
      "config": {"strict": true}
    },
    {
      "type": "choice",
      "name": "route",
      "condition": "quality_score > 0.95",
      "then_step": "fast_load",
      "else_step": "full_reprocess"
    }
  ]
}
```

### core_workflow_runs

Tracks each execution of a workflow:

```sql
-- =============================================================================
-- WORKFLOW RUNS (Execution History with Context)
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_workflow_runs (
    id TEXT PRIMARY KEY,                    -- ULID
    workflow_name TEXT NOT NULL,
    workflow_version INTEGER NOT NULL,
    
    -- Context snapshot at start
    run_id TEXT NOT NULL,                   -- Same as context.run_id
    trace_id TEXT NOT NULL,                 -- For distributed tracing
    batch_id TEXT,                          -- Batch grouping
    
    -- Parameters
    params TEXT,                            -- JSON: Initial params
    partition TEXT,                         -- JSON: PartitionKey
    as_of_date TEXT,                        -- Business date
    capture_id TEXT,                        -- Idempotency key
    
    -- Execution state
    status TEXT NOT NULL DEFAULT 'pending', -- pending, running, completed, failed, partial
    trigger_source TEXT NOT NULL,           -- cli, api, scheduler, backfill
    
    -- Step tracking
    total_steps INTEGER NOT NULL,
    completed_steps INTEGER NOT NULL DEFAULT 0,
    failed_steps INTEGER NOT NULL DEFAULT 0,
    skipped_steps INTEGER NOT NULL DEFAULT 0,
    
    -- Timing
    started_at TEXT,
    completed_at TEXT,
    
    -- Error info
    error TEXT,
    error_step TEXT,                        -- Which step failed
    
    -- Checkpoint (for resume)
    checkpoint_state TEXT,                  -- JSON: CheckpointState
    
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_core_workflow_runs_status 
    ON core_workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_core_workflow_runs_workflow 
    ON core_workflow_runs(workflow_name);
CREATE INDEX IF NOT EXISTS idx_core_workflow_runs_batch_id 
    ON core_workflow_runs(batch_id);
CREATE INDEX IF NOT EXISTS idx_core_workflow_runs_trace_id 
    ON core_workflow_runs(trace_id);
CREATE INDEX IF NOT EXISTS idx_core_workflow_runs_partition 
    ON core_workflow_runs(partition);
CREATE INDEX IF NOT EXISTS idx_core_workflow_runs_as_of_date 
    ON core_workflow_runs(as_of_date);
```

### core_workflow_run_steps

Tracks each step within a workflow run:

```sql
-- =============================================================================
-- WORKFLOW RUN STEPS (Step-level tracking with context)
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_workflow_run_steps (
    id TEXT PRIMARY KEY,                    -- ULID
    workflow_run_id TEXT NOT NULL,          -- FK to core_workflow_runs
    
    -- Step identity
    step_name TEXT NOT NULL,
    step_type TEXT NOT NULL,                -- pipeline, lambda, choice, wait, map
    step_handler TEXT,                      -- Pipeline name or lambda handler
    sequence_order INTEGER NOT NULL,
    
    -- Execution
    status TEXT NOT NULL DEFAULT 'pending', -- pending, running, completed, failed, skipped
    execution_id TEXT,                      -- FK to core_executions (for pipeline steps)
    
    -- Input/Output
    context_snapshot TEXT,                  -- JSON: Context at step start
    step_output TEXT,                       -- JSON: StepResult.output
    context_updates TEXT,                   -- JSON: StepResult.context_updates
    
    -- Quality metrics
    quality_record_count INTEGER,
    quality_valid_count INTEGER,
    quality_null_rate REAL,
    quality_passed INTEGER,                 -- 1=passed, 0=failed
    quality_details TEXT,                   -- JSON: Full QualityMetrics
    
    -- Timing
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    
    -- Error info
    error TEXT,
    error_category TEXT,                    -- NETWORK, VALIDATION, etc.
    
    -- Events
    events TEXT,                            -- JSON array: Structured logs
    
    UNIQUE(workflow_run_id, step_name)
);

CREATE INDEX IF NOT EXISTS idx_core_workflow_run_steps_run 
    ON core_workflow_run_steps(workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_core_workflow_run_steps_status 
    ON core_workflow_run_steps(status);
CREATE INDEX IF NOT EXISTS idx_core_workflow_run_steps_quality 
    ON core_workflow_run_steps(quality_passed);
```

### core_workflow_checkpoints

Persistent checkpoints for resume:

```sql
-- =============================================================================
-- WORKFLOW CHECKPOINTS (Resume from failure)
-- =============================================================================

CREATE TABLE IF NOT EXISTS core_workflow_checkpoints (
    id TEXT PRIMARY KEY,                    -- ULID
    workflow_run_id TEXT NOT NULL,          -- FK to core_workflow_runs
    
    -- Checkpoint state
    last_completed_step TEXT NOT NULL,
    step_outputs TEXT NOT NULL,             -- JSON: All step outputs so far
    context_snapshot TEXT NOT NULL,         -- JSON: Full context at checkpoint
    
    -- Timing
    created_at TEXT NOT NULL,
    expires_at TEXT,                        -- Optional TTL
    
    UNIQUE(workflow_run_id)
);

CREATE INDEX IF NOT EXISTS idx_core_workflow_checkpoints_run 
    ON core_workflow_checkpoints(workflow_run_id);
```

## Views

### v_workflow_run_summary

Summary view for dashboards:

```sql
-- =============================================================================
-- WORKFLOW RUN SUMMARY VIEW
-- =============================================================================

CREATE VIEW IF NOT EXISTS v_workflow_run_summary AS
SELECT 
    r.id,
    r.workflow_name,
    r.status,
    r.trigger_source,
    r.total_steps,
    r.completed_steps,
    r.failed_steps,
    r.skipped_steps,
    r.started_at,
    r.completed_at,
    -- Duration in seconds
    CASE 
        WHEN r.completed_at IS NOT NULL AND r.started_at IS NOT NULL
        THEN (julianday(r.completed_at) - julianday(r.started_at)) * 86400
    END as duration_seconds,
    -- Partition info
    json_extract(r.partition, '$.date') as partition_date,
    json_extract(r.partition, '$.tier') as partition_tier,
    r.as_of_date,
    r.batch_id,
    r.trace_id,
    r.error,
    r.error_step
FROM core_workflow_runs r
ORDER BY r.created_at DESC;
```

### v_workflow_step_quality

Quality metrics by step:

```sql
-- =============================================================================
-- WORKFLOW STEP QUALITY VIEW
-- =============================================================================

CREATE VIEW IF NOT EXISTS v_workflow_step_quality AS
SELECT 
    r.workflow_name,
    s.step_name,
    s.step_type,
    COUNT(*) as run_count,
    SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) as success_count,
    SUM(CASE WHEN s.status = 'failed' THEN 1 ELSE 0 END) as failure_count,
    AVG(s.duration_ms) as avg_duration_ms,
    AVG(s.quality_null_rate) as avg_null_rate,
    SUM(CASE WHEN s.quality_passed = 1 THEN 1 ELSE 0 END) as quality_pass_count,
    SUM(CASE WHEN s.quality_passed = 0 THEN 1 ELSE 0 END) as quality_fail_count
FROM core_workflow_run_steps s
JOIN core_workflow_runs r ON s.workflow_run_id = r.id
GROUP BY r.workflow_name, s.step_name, s.step_type;
```

## Migration Script

Add to `packages/spine-core/src/spine/core/schema/02_orchestration_v2.sql`:

```sql
-- =============================================================================
-- SPINE CORE - ORCHESTRATION V2 TABLES
-- =============================================================================
-- Owner: spine-core package
-- Description: Tables for workflow orchestration with context passing.
--              Extends v1 tables (core_pipeline_groups, core_group_runs).
--
-- Dependencies: 
--   - 00_core.sql (core_executions)
--   - 01_orchestration.sql (v1 tables)
-- =============================================================================

-- [Include all CREATE TABLE statements from above]

-- =============================================================================
-- MIGRATION HELPERS
-- =============================================================================

-- View to help migrate v1 group runs to v2 workflow runs
CREATE VIEW IF NOT EXISTS v_migrate_group_to_workflow AS
SELECT 
    id as v1_id,
    group_name as workflow_name,
    group_version as workflow_version,
    id as run_id,  -- Use same ID
    id as trace_id,  -- No trace_id in v1
    batch_id,
    params,
    NULL as partition,  -- v1 doesn't have partition
    NULL as as_of_date,
    status,
    trigger_source,
    total_steps,
    completed_steps,
    failed_steps,
    skipped_steps,
    started_at,
    completed_at,
    error,
    NULL as error_step,
    NULL as checkpoint_state,
    created_at
FROM core_group_runs;
```

## Indexes for Query Patterns

### Common Queries

1. **Active runs for a workflow:**
```sql
SELECT * FROM core_workflow_runs 
WHERE workflow_name = ? AND status IN ('pending', 'running');

-- Index: idx_core_workflow_runs_workflow + status
```

2. **Failed runs in date range:**
```sql
SELECT * FROM core_workflow_runs 
WHERE status = 'failed' AND as_of_date BETWEEN ? AND ?;

-- Index: idx_core_workflow_runs_as_of_date
```

3. **Runs by partition:**
```sql
SELECT * FROM core_workflow_runs 
WHERE json_extract(partition, '$.tier') = ?;

-- Index: Expression index on partition
CREATE INDEX IF NOT EXISTS idx_core_workflow_runs_partition_tier 
    ON core_workflow_runs(json_extract(partition, '$.tier'));
```

4. **Steps with quality failures:**
```sql
SELECT * FROM core_workflow_run_steps 
WHERE quality_passed = 0 AND status = 'completed';

-- Index: idx_core_workflow_run_steps_quality
```

## Retention Policy

Add retention for workflow history:

```sql
-- Delete workflow runs older than 90 days
DELETE FROM core_workflow_run_steps 
WHERE workflow_run_id IN (
    SELECT id FROM core_workflow_runs 
    WHERE created_at < datetime('now', '-90 days')
);

DELETE FROM core_workflow_runs 
WHERE created_at < datetime('now', '-90 days');

-- Delete checkpoints older than 7 days
DELETE FROM core_workflow_checkpoints 
WHERE created_at < datetime('now', '-7 days');
```

## Comparison: v1 vs v2 Schema

| Feature | v1 Tables | v2 Tables |
|---------|-----------|-----------|
| Definitions | `core_pipeline_groups` | `core_workflows` |
| Runs | `core_group_runs` | `core_workflow_runs` |
| Steps | `core_group_run_steps` | `core_workflow_run_steps` |
| Context | N/A | In `workflow_run_steps.context_snapshot` |
| Quality | N/A | In `workflow_run_steps.quality_*` |
| Checkpoints | N/A | `core_workflow_checkpoints` |
| Partitions | N/A | In `workflow_runs.partition` |
