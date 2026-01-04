# Market Spine CLI Reference

The Market Spine CLI provides commands for managing pipelines, querying data, and verifying system state.

## Installation

```bash
cd market-spine-basic
uv sync
```

## Commands Overview

```
spine --help

Commands:
  db      Database commands
  list    List available pipelines
  query   Query pipeline data and results
  run     Run a pipeline
  shell   Start interactive Python shell
  status  Show system status
  ui      Start interactive UI
  verify  Verify data integrity
```

## Pipeline Commands

### List Pipelines

```bash
spine list
```

Shows all registered pipelines with their descriptions.

### Run Pipeline

```bash
spine run <pipeline_name> [-p key=value ...] [--lane normal|backfill|slow] [--help-params]
```

**Options:**
- `-p`, `--param`: Pass parameters as `key=value` (can be repeated)
- `--lane`: Execution lane (default: normal)
- `--help-params`: Show parameter help for the pipeline

**Examples:**

```bash
# Show parameter help
spine run finra.otc_transparency.ingest_week --help-params

# Run with parameters
spine run finra.otc_transparency.ingest_week -p file_path=data/week_2025-01-03.psv

# Force re-processing
spine run finra.otc_transparency.normalize_week -p week_ending=2025-01-03 -p tier=Tier1 -p force=true
```

## Database Commands

### Initialize Database

```bash
spine db init
```

Creates all required tables with migrations.

### Reset Database

```bash
spine db reset
```

⚠️ Deletes all data and reinitializes the database.

### Dump Schema

```bash
spine db dump-schema [-o output.sql]
```

Exports the database schema to SQL.

## Verify Commands

### Check Tables

```bash
spine verify tables
```

Shows all expected tables with row counts and status (✓/✗).

### Check Data Completeness

```bash
spine verify data [--tier Tier1|Tier2|OTC] [--week YYYY-MM-DD]
```

Shows record counts across all pipeline stages.

### Check Quality Results

```bash
spine verify quality [--week YYYY-MM-DD]
```

Shows results of data quality checks.

## Query Commands

### Run SQL

```bash
spine query sql "SELECT * FROM otc_symbol_summary LIMIT 10" [--format table|csv|json]
```

Execute arbitrary SQL against the database.

### Show Weeks

```bash
spine query weeks [--tier Tier1|Tier2|OTC]
```

List available weeks with symbol counts and volumes.

### Query Symbols

```bash
# Top symbols by volume
spine query symbols [--top 20] [--tier Tier1|Tier2|OTC]

# Specific symbol history
spine query symbols AAPL [--week YYYY-MM-DD]
```

### Show Rejects

```bash
spine query rejects [--limit 20] [--stage ingest|normalize]
```

List rejected records from pipeline processing.

## Interactive Mode

```bash
spine ui
```

Starts an interactive menu-driven interface for:
- Browsing pipelines
- Running pipelines with guided parameter input
- Verifying data
- Querying results

## Utility Commands

### System Status

```bash
spine status
```

Shows version, database path, and migration status.

### Interactive Shell

```bash
spine shell
```

Opens a Python REPL with database connection and utilities pre-loaded.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SPINE_LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | INFO |
| `SPINE_LOG_FORMAT` | Output format (json, console) | console |
| `SPINE_DATABASE_PATH` | Path to SQLite database | data/spine.db |
| `SPINE_DATA_DIR` | Data directory for files | data/ |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (pipeline failed, validation error, etc.) |

## Error Messages

The CLI provides clear, actionable error messages:

**Missing Parameters:**
```
Parameter validation failed:
  Missing required parameters: file_path
Missing required parameters: file_path
Run 'spine run finra.otc_transparency.ingest_week --help-params' for parameter details.
```

**Unknown Pipeline:**
```
Pipeline not found: unknown.pipeline
Run 'spine list' to see available pipelines.
```

**Invalid Parameters:**
```
Parameter validation failed:
  Invalid parameter 'tier': tier must be Tier1, Tier2, or OTC
```

## Available Pipelines

| Pipeline | Description |
|----------|-------------|
| `finra.otc_transparency.ingest_week` | Ingest raw OTC transparency data from file |
| `finra.otc_transparency.normalize_week` | Normalize raw records to venue-level data |
| `finra.otc_transparency.aggregate_week` | Aggregate to symbol-level summaries |
| `finra.otc_transparency.compute_rolling` | Compute 6-week rolling metrics |
| `finra.otc_transparency.backfill_range` | Orchestrate multi-week backfill |
