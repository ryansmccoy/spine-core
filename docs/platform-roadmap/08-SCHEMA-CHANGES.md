# Schema Changes

> **Purpose:** Document all database schema changes for new features.
> **Tier:** All
> **Last Updated:** 2026-01-11

---

## Overview

This document catalogs all database schema changes required by the platform roadmap. Changes are organized by tier and include:
- Table definitions
- Indexes
- Migration scripts
- Dialect-specific differences

---

## Current Schema (Baseline)

Existing tables in `spine-core`:

| Table | Description |
|-------|-------------|
| `core_data_manifests` | Data pipeline manifests |
| `core_load_records` | Load operation tracking |
| `core_quality_checks` | Quality validation results |
| `core_anomalies` | Detected anomalies |

---

## New Tables by Tier

### Basic Tier Tables

#### `core_source_configs`
Store source configuration for registry.

```sql
-- migrations/basic/0001_source_configs.sql

CREATE TABLE IF NOT EXISTS core_source_configs (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,  -- file, http, database
    name TEXT NOT NULL UNIQUE,
    config TEXT NOT NULL,  -- JSON configuration
    enabled INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_configs_type 
ON core_source_configs(source_type);

CREATE INDEX IF NOT EXISTS idx_source_configs_name 
ON core_source_configs(name);
```

**PostgreSQL version:**
```sql
CREATE TABLE IF NOT EXISTS core_source_configs (
    source_id VARCHAR(50) PRIMARY KEY,
    source_type VARCHAR(20) NOT NULL,
    name VARCHAR(100) NOT NULL UNIQUE,
    config JSONB NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**DB2 version:**
```sql
CREATE TABLE CORE_SOURCE_CONFIGS (
    SOURCE_ID VARCHAR(50) NOT NULL PRIMARY KEY,
    SOURCE_TYPE VARCHAR(20) NOT NULL,
    NAME VARCHAR(100) NOT NULL UNIQUE,
    CONFIG CLOB(1M) NOT NULL,
    ENABLED SMALLINT DEFAULT 1,
    CREATED_AT TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP,
    UPDATED_AT TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);
```

---

### Intermediate Tier Tables

#### `scheduler_schedules`
Scheduler configuration.

```sql
-- migrations/intermediate/0001_scheduler_schedules.sql

CREATE TABLE IF NOT EXISTS scheduler_schedules (
    name TEXT PRIMARY KEY,
    pipeline TEXT NOT NULL,
    schedule_type TEXT NOT NULL,  -- cron, interval, date
    cron_expression TEXT,
    interval_minutes INTEGER,
    interval_hours INTEGER,
    run_at TEXT,
    timezone TEXT DEFAULT 'UTC',
    params TEXT,  -- JSON
    enabled INTEGER DEFAULT 1,
    max_instances INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_schedules_pipeline 
ON scheduler_schedules(pipeline);

CREATE INDEX IF NOT EXISTS idx_schedules_enabled 
ON scheduler_schedules(enabled);
```

#### `scheduler_runs`
Scheduler execution history.

```sql
-- migrations/intermediate/0002_scheduler_runs.sql

CREATE TABLE IF NOT EXISTS scheduler_runs (
    run_id TEXT PRIMARY KEY,
    schedule_name TEXT NOT NULL,
    pipeline TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, running, completed, failed, skipped
    scheduled_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error TEXT,
    result TEXT,  -- JSON
    FOREIGN KEY (schedule_name) REFERENCES scheduler_schedules(name)
);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_schedule 
ON scheduler_runs(schedule_name);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status 
ON scheduler_runs(status);

CREATE INDEX IF NOT EXISTS idx_scheduler_runs_scheduled_at 
ON scheduler_runs(scheduled_at);
```

#### `workflow_runs`
Workflow execution history.

```sql
-- migrations/intermediate/0003_workflow_runs.sql

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id TEXT PRIMARY KEY,
    workflow_name TEXT NOT NULL,
    domain TEXT,
    partition_key TEXT,
    status TEXT NOT NULL,  -- PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    started_at TEXT,
    completed_at TEXT,
    params TEXT,  -- JSON
    outputs TEXT,  -- JSON
    error TEXT,
    error_category TEXT,
    metrics TEXT,  -- JSON
    triggered_by TEXT NOT NULL,  -- manual, schedule, api
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_name 
ON workflow_runs(workflow_name);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status 
ON workflow_runs(status);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_domain 
ON workflow_runs(domain);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_started 
ON workflow_runs(started_at);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_created 
ON workflow_runs(created_at);
```

#### `workflow_step_runs`
Step execution within workflows.

```sql
-- migrations/intermediate/0004_workflow_step_runs.sql

CREATE TABLE IF NOT EXISTS workflow_step_runs (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_type TEXT NOT NULL,  -- lambda, pipeline, choice, wait, map
    step_order INTEGER NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    input_params TEXT,  -- JSON
    output_data TEXT,  -- JSON
    error TEXT,
    error_category TEXT,
    records_processed INTEGER,
    quality_passed INTEGER,
    quality_metrics TEXT,  -- JSON
    FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_step_runs_run 
ON workflow_step_runs(run_id);

CREATE INDEX IF NOT EXISTS idx_step_runs_status 
ON workflow_step_runs(status);
```

#### `alert_history`
Sent alert records.

```sql
-- migrations/intermediate/0005_alert_history.sql

CREATE TABLE IF NOT EXISTS alert_history (
    alert_id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,  -- CRITICAL, ERROR, WARNING, INFO
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    source TEXT NOT NULL,
    execution_id TEXT,
    channel TEXT NOT NULL,  -- slack, email, servicenow
    sent_at TEXT NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    metadata TEXT  -- JSON
);

CREATE INDEX IF NOT EXISTS idx_alerts_severity 
ON alert_history(severity);

CREATE INDEX IF NOT EXISTS idx_alerts_source 
ON alert_history(source);

CREATE INDEX IF NOT EXISTS idx_alerts_sent_at 
ON alert_history(sent_at);
```

---

### Advanced Tier Tables

#### `dead_letter_queue`
Failed message storage for retry.

```sql
-- migrations/advanced/0001_dead_letter_queue.sql

CREATE TABLE IF NOT EXISTS dead_letter_queue (
    dlq_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,  -- workflow, step, message
    source_id TEXT NOT NULL,
    payload TEXT NOT NULL,  -- JSON
    error TEXT NOT NULL,
    error_category TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    first_failed_at TEXT NOT NULL,
    last_failed_at TEXT NOT NULL,
    next_retry_at TEXT,
    status TEXT DEFAULT 'pending',  -- pending, retrying, exhausted, resolved
    resolved_at TEXT,
    metadata TEXT  -- JSON
);

CREATE INDEX IF NOT EXISTS idx_dlq_status 
ON dead_letter_queue(status);

CREATE INDEX IF NOT EXISTS idx_dlq_next_retry 
ON dead_letter_queue(next_retry_at);

CREATE INDEX IF NOT EXISTS idx_dlq_source 
ON dead_letter_queue(source_type, source_id);
```

#### `circuit_breakers`
Circuit breaker state tracking.

```sql
-- migrations/advanced/0002_circuit_breakers.sql

CREATE TABLE IF NOT EXISTS circuit_breakers (
    breaker_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'closed',  -- closed, open, half_open
    failure_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    last_failure_at TEXT,
    last_success_at TEXT,
    opened_at TEXT,
    half_opened_at TEXT,
    config TEXT,  -- JSON (thresholds, timeouts)
    updated_at TEXT NOT NULL
);
```

---

## PostgreSQL-Specific Schema

For Intermediate+ tiers using PostgreSQL:

```sql
-- migrations/pg/0001_pg_optimizations.sql

-- Use JSONB for better query performance
ALTER TABLE workflow_runs 
    ALTER COLUMN params TYPE JSONB USING params::jsonb,
    ALTER COLUMN outputs TYPE JSONB USING outputs::jsonb,
    ALTER COLUMN metrics TYPE JSONB USING metrics::jsonb;

-- Add GIN indexes for JSON queries
CREATE INDEX IF NOT EXISTS idx_workflow_runs_params_gin 
ON workflow_runs USING GIN (params);

-- Use timestamp type
ALTER TABLE workflow_runs
    ALTER COLUMN started_at TYPE TIMESTAMP USING started_at::timestamp,
    ALTER COLUMN completed_at TYPE TIMESTAMP USING completed_at::timestamp,
    ALTER COLUMN created_at TYPE TIMESTAMP USING created_at::timestamp;

-- Add partitioning for large tables (optional)
-- Partition workflow_runs by month
CREATE TABLE workflow_runs_partitioned (
    LIKE workflow_runs INCLUDING ALL
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE workflow_runs_2025_01 
    PARTITION OF workflow_runs_partitioned
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

---

## DB2-Specific Schema

For Advanced/Enterprise tiers using DB2:

```sql
-- migrations/db2/0001_db2_schema.sql

-- Workflow runs table for DB2
CREATE TABLE WORKFLOW_RUNS (
    RUN_ID VARCHAR(50) NOT NULL PRIMARY KEY,
    WORKFLOW_NAME VARCHAR(200) NOT NULL,
    DOMAIN VARCHAR(100),
    PARTITION_KEY VARCHAR(200),
    STATUS VARCHAR(20) NOT NULL,
    STARTED_AT TIMESTAMP,
    COMPLETED_AT TIMESTAMP,
    PARAMS CLOB(1M),
    OUTPUTS CLOB(1M),
    ERROR VARCHAR(4000),
    ERROR_CATEGORY VARCHAR(50),
    METRICS CLOB(100K),
    TRIGGERED_BY VARCHAR(50) NOT NULL,
    CREATED_AT TIMESTAMP NOT NULL DEFAULT CURRENT TIMESTAMP
);

-- Create indexes
CREATE INDEX IDX_WR_NAME ON WORKFLOW_RUNS(WORKFLOW_NAME);
CREATE INDEX IDX_WR_STATUS ON WORKFLOW_RUNS(STATUS);
CREATE INDEX IDX_WR_DOMAIN ON WORKFLOW_RUNS(DOMAIN);
CREATE INDEX IDX_WR_STARTED ON WORKFLOW_RUNS(STARTED_AT);

-- Step runs table
CREATE TABLE WORKFLOW_STEP_RUNS (
    STEP_ID VARCHAR(50) NOT NULL PRIMARY KEY,
    RUN_ID VARCHAR(50) NOT NULL,
    STEP_NAME VARCHAR(200) NOT NULL,
    STEP_TYPE VARCHAR(50) NOT NULL,
    STEP_ORDER INTEGER NOT NULL,
    STATUS VARCHAR(20) NOT NULL,
    STARTED_AT TIMESTAMP,
    COMPLETED_AT TIMESTAMP,
    INPUT_PARAMS CLOB(1M),
    OUTPUT_DATA CLOB(1M),
    ERROR VARCHAR(4000),
    ERROR_CATEGORY VARCHAR(50),
    RECORDS_PROCESSED INTEGER,
    QUALITY_PASSED SMALLINT,
    QUALITY_METRICS CLOB(100K),
    CONSTRAINT FK_STEP_RUN FOREIGN KEY (RUN_ID) 
        REFERENCES WORKFLOW_RUNS(RUN_ID) ON DELETE CASCADE
);

CREATE INDEX IDX_SR_RUN ON WORKFLOW_STEP_RUNS(RUN_ID);
```

---

## Migration Runner

```python
# spine/core/storage/migrations.py
"""
Database migration runner.
"""

import os
import logging
from pathlib import Path
from datetime import datetime

from .types import DatabaseAdapter


log = logging.getLogger(__name__)


class MigrationRunner:
    """
    Runs database migrations.
    
    Features:
    - Tracks applied migrations
    - Dialect-aware migration selection
    - Rollback support (manual)
    """
    
    def __init__(self, db: DatabaseAdapter, migrations_dir: Path | str):
        self.db = db
        self.migrations_dir = Path(migrations_dir)
    
    def initialize(self) -> None:
        """Create migrations tracking table."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
        """)
    
    def get_applied(self) -> set[str]:
        """Get set of applied migration IDs."""
        result = self.db.query("SELECT migration_id FROM _migrations")
        return {row["migration_id"] for row in result}
    
    def run(self, target_tier: str = "basic") -> int:
        """
        Run pending migrations up to target tier.
        
        Returns number of migrations applied.
        """
        self.initialize()
        applied = self.get_applied()
        
        # Get migration files
        migrations = self._get_migrations(target_tier)
        
        count = 0
        for migration_id, sql_path in migrations:
            if migration_id in applied:
                continue
            
            log.info(f"Applying migration: {migration_id}")
            
            # Read and execute SQL
            with open(sql_path) as f:
                sql = f.read()
            
            # Split on semicolons for multiple statements
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    self.db.execute(statement)
            
            # Record migration
            self.db.execute(
                "INSERT INTO _migrations (migration_id, applied_at) VALUES (?, ?)",
                (migration_id, datetime.utcnow().isoformat()),
            )
            
            count += 1
        
        log.info(f"Applied {count} migrations")
        return count
    
    def _get_migrations(self, target_tier: str) -> list[tuple[str, Path]]:
        """Get migrations for tier in order."""
        tier_order = ["basic", "intermediate", "advanced"]
        target_index = tier_order.index(target_tier)
        
        migrations = []
        
        for tier in tier_order[:target_index + 1]:
            tier_dir = self.migrations_dir / tier
            if tier_dir.exists():
                for sql_file in sorted(tier_dir.glob("*.sql")):
                    migration_id = f"{tier}/{sql_file.stem}"
                    migrations.append((migration_id, sql_file))
        
        # Add dialect-specific migrations
        dialect_dir = self.migrations_dir / self.db.dialect
        if dialect_dir.exists():
            for sql_file in sorted(dialect_dir.glob("*.sql")):
                migration_id = f"{self.db.dialect}/{sql_file.stem}"
                migrations.append((migration_id, sql_file))
        
        return migrations
```

---

## Migration Order

Execute migrations in this order:

1. **Basic Tier**
   - `basic/0001_source_configs.sql`

2. **Intermediate Tier** (includes Basic)
   - `intermediate/0001_scheduler_schedules.sql`
   - `intermediate/0002_scheduler_runs.sql`
   - `intermediate/0003_workflow_runs.sql`
   - `intermediate/0004_workflow_step_runs.sql`
   - `intermediate/0005_alert_history.sql`

3. **Advanced Tier** (includes Intermediate)
   - `advanced/0001_dead_letter_queue.sql`
   - `advanced/0002_circuit_breakers.sql`

4. **Dialect-Specific**
   - `pg/0001_pg_optimizations.sql` (PostgreSQL only)
   - `db2/0001_db2_schema.sql` (DB2 only)

---

## Schema Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Core Tables (Existing)                         │
├─────────────────────────────────────────────────────────────────────────┤
│ core_data_manifests    core_load_records    core_quality_checks        │
│ core_anomalies                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Basic Tier (New)                               │
├─────────────────────────────────────────────────────────────────────────┤
│ core_source_configs                                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       Intermediate Tier (New)                           │
├─────────────────────────────────────────────────────────────────────────┤
│ scheduler_schedules ◄──────┐                                            │
│                            │                                            │
│ scheduler_runs ────────────┘                                            │
│                                                                         │
│ workflow_runs ◄────────────┐                                            │
│                            │                                            │
│ workflow_step_runs ────────┘                                            │
│                                                                         │
│ alert_history                                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Advanced Tier (New)                              │
├─────────────────────────────────────────────────────────────────────────┤
│ dead_letter_queue                                                       │
│ circuit_breakers                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Dialect Differences Summary

| Feature | SQLite | PostgreSQL | DB2 |
|---------|--------|------------|-----|
| JSON column | TEXT | JSONB | CLOB |
| Boolean | INTEGER (0/1) | BOOLEAN | SMALLINT |
| Timestamp | TEXT (ISO) | TIMESTAMP | TIMESTAMP |
| Auto ID | AUTOINCREMENT | SERIAL | GENERATED ALWAYS |
| UPSERT | ON CONFLICT | ON CONFLICT | MERGE |
| Index type | B-tree only | B-tree, GIN, GiST | B-tree |
| Partitioning | Not supported | PARTITION BY | PARTITION BY |

---

## Rollback Strategy

For rollback, create down migrations:

```sql
-- migrations/intermediate/0003_workflow_runs_down.sql

DROP INDEX IF EXISTS idx_workflow_runs_created;
DROP INDEX IF EXISTS idx_workflow_runs_started;
DROP INDEX IF EXISTS idx_workflow_runs_domain;
DROP INDEX IF EXISTS idx_workflow_runs_status;
DROP INDEX IF EXISTS idx_workflow_runs_name;
DROP TABLE IF EXISTS workflow_runs;
```

---

## Next Steps

1. See integration flow: [09-INTEGRATION-FLOW.md](./09-INTEGRATION-FLOW.md)
2. View FINRA example: [10-FINRA-EXAMPLE.md](./10-FINRA-EXAMPLE.md)
3. Review implementation order: [11-IMPLEMENTATION-ORDER.md](./11-IMPLEMENTATION-ORDER.md)
