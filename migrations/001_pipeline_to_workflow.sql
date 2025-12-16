-- Migration 001: Rename 'pipeline' columns to 'workflow'
--
-- This migration renames all 'pipeline' column references across the
-- spine-core database schema to 'workflow', aligning the data layer
-- with the project's terminology convention.
--
-- The Pipeline ABC (framework/pipelines/) is a distinct concept (a single-stage
-- data processor) and is NOT affected by this migration.
--
-- Tables affected:
--   core_executions        : pipeline → workflow
--   core_anomalies         : pipeline → workflow
--   core_dead_letters      : pipeline → workflow
--   core_work_items        : pipeline → workflow
--   core_expected_schedules: pipeline → workflow
--
-- Tables NOT affected:
--   core_calc_dependencies : calc_pipeline stays (refers to Pipeline ABC)
--   core_schedules         : target_type DEFAULT 'pipeline' stays (StepType.PIPELINE)
--   core_schedule_locks    : no pipeline column
--
-- Run with: sqlite3 spine.db < migrations/001_pipeline_to_workflow.sql
--   or:     psql -d spine_db -f migrations/001_pipeline_to_workflow.sql
--
-- Date: 2026-02-17

-- ============================================================================
-- SQLite version (ALTER TABLE ... RENAME COLUMN requires SQLite 3.25.0+)
-- ============================================================================

-- 1. core_executions
ALTER TABLE core_executions RENAME COLUMN pipeline TO workflow;

-- Recreate index with new name
DROP INDEX IF EXISTS idx_core_executions_pipeline;
CREATE INDEX IF NOT EXISTS idx_core_executions_workflow
    ON core_executions(workflow);

-- 2. core_anomalies
ALTER TABLE core_anomalies RENAME COLUMN pipeline TO workflow;

-- 3. core_dead_letters
ALTER TABLE core_dead_letters RENAME COLUMN pipeline TO workflow;

-- Recreate index with new name
DROP INDEX IF EXISTS idx_core_dead_letters_pipeline;
CREATE INDEX IF NOT EXISTS idx_core_dead_letters_workflow
    ON core_dead_letters(workflow);

-- 4. core_work_items
ALTER TABLE core_work_items RENAME COLUMN pipeline TO workflow;

-- 5. core_expected_schedules
ALTER TABLE core_expected_schedules RENAME COLUMN pipeline TO workflow;


-- ============================================================================
-- PostgreSQL version (uncomment if using PostgreSQL)
-- ============================================================================
--
-- ALTER TABLE core_executions RENAME COLUMN pipeline TO workflow;
-- DROP INDEX IF EXISTS idx_core_executions_pipeline;
-- CREATE INDEX IF NOT EXISTS idx_core_executions_workflow
--     ON core_executions(workflow);
--
-- ALTER TABLE core_anomalies RENAME COLUMN pipeline TO workflow;
--
-- ALTER TABLE core_dead_letters RENAME COLUMN pipeline TO workflow;
-- DROP INDEX IF EXISTS idx_core_dead_letters_pipeline;
-- CREATE INDEX IF NOT EXISTS idx_core_dead_letters_workflow
--     ON core_dead_letters(workflow);
--
-- ALTER TABLE core_work_items RENAME COLUMN pipeline TO workflow;
--
-- ALTER TABLE core_expected_schedules RENAME COLUMN pipeline TO workflow;
