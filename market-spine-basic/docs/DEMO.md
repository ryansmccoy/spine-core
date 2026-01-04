# Market Spine CLI Demo Transcript

This document demonstrates the key features of the Market Spine CLI.

## System Overview

```
$ spine --help
Usage: spine [OPTIONS] COMMAND [ARGS]...

  Market Spine - Analytics Pipeline System.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  db      Database commands.
  list    List available pipelines.
  query   Query pipeline data and results.
  run     Run a pipeline.
  shell   Start interactive Python shell with context loaded.
  status  Show system status.
  ui      Start interactive UI for pipeline management.
  verify  Verify data integrity and pipeline results.
```

## System Status

```
$ spine status
Market Spine Status
  Version: 0.1.0
  Database: spine.db
  Data directory: data
  Migrations applied: 4
```

## Available Pipelines

```
$ spine list
                                        Available Pipelines                                        
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name                                   ┃ Description                                            ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ finra.otc_transparency.aggregate_week  │ Compute FINRA OTC transparency aggregates for one week │
│ finra.otc_transparency.backfill_range  │ Orchestrate multi-week FINRA OTC transparency backfill │
│ finra.otc_transparency.compute_rolling │ Compute rolling metrics for FINRA OTC transparency     │
│ finra.otc_transparency.ingest_week     │ Ingest FINRA OTC transparency file for one week        │
│ finra.otc_transparency.normalize_week  │ Normalize raw FINRA OTC transparency data for one week │
└────────────────────────────────────────┴────────────────────────────────────────────────────────┘
```

## Pipeline Parameter Help

```
$ spine run finra.otc_transparency.ingest_week --help-params
Required Parameters:
  file_path (Path): Path to the FINRA OTC transparency PSV file

Optional Parameters:
  tier (str): Market tier (auto-detected from filename if not provided)
  week_ending (str): Week ending date in ISO format (auto-detected if not provided)
  file_date (str): File publication date (auto-detected if not provided)
  force (bool): Re-ingest even if already ingested

Examples:
  spine run finra.otc_transparency.ingest_week -p file_path=data/week_2025-12-05.psv
  spine run finra.otc_transparency.ingest_week -p file_path=data/tier1.psv -p tier=NMS_TIER_1 -p week_ending=2025-12-05

Notes:
  - The tier and week_ending can be auto-detected from filename patterns
  - Use force=True to re-ingest data (will delete existing data for that week/tier)
```

## Data Verification

### Verify Tables

```
$ spine verify tables
                Database Tables                
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┓
┃ Table                 ┃ Status  ┃ Row Count ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━┩
│ _migrations           │ ✓       │         4 │
│ core_manifest         │ ✓       │        16 │
│ core_rejects          │ ✓       │         0 │
│ core_quality          │ ✓       │         0 │
│ otc_raw               │ ✓       │     51139 │
│ otc_venue_volume      │ ✓       │     51089 │
│ otc_symbol_summary    │ ✓       │         8 │
│ otc_symbol_rolling_6w │ ✓       │         2 │
│ executions            │ (extra) │         0 │
│ otc_liquidity_score   │ (extra) │         0 │
│ otc_research_snapshot │ (extra) │         0 │
│ otc_venue_share       │ (extra) │         0 │
└───────────────────────┴─────────┴───────────┘

All expected tables present!
```

### Verify Data Pipeline Stages

```
$ spine verify data
Data Verification Report

           Pipeline Stage Summary            
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━┳━━━━━━━━┓
┃ Stage          ┃ Records ┃ Weeks ┃ Status ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━╇━━━━━━━━┩
│ Raw Records    │   51139 │     - │ ✓      │
│ Venue Volume   │   51089 │     5 │ ✓      │
│ Symbol Summary │       8 │     4 │ ✓      │
│ Rolling 6W     │       2 │     1 │ ✓      │
└────────────────┴─────────┴───────┴────────┘
```

## Data Queries

### List Processed Weeks

```
$ spine query weeks
                Available Weeks                
┏━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Week Ending ┃ Tier ┃ Symbols ┃ Total Volume ┃
┡━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 2026-01-02  │ OTC  │       2 │    6,938,176 │
│ 2025-12-26  │ OTC  │       2 │    6,938,176 │
│ 2025-12-05  │ OTC  │       2 │    6,938,176 │
│ 2025-11-28  │ OTC  │       2 │    6,938,176 │
└─────────────┴──────┴─────────┴──────────────┘
```

### Top Symbols by Volume

```
$ spine query symbols
        Top 20 Symbols by Volume        
┏━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Symbol ┃ Tier ┃ Total Volume ┃ Weeks ┃
┡━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━┩
│ A      │ OTC  │   15,311,480 │     4 │
│ AA     │ OTC  │   12,441,224 │     4 │
└────────┴──────┴──────────────┴───────┘
```

### Custom SQL Query

```
$ spine query sql "SELECT COUNT(*) as total FROM otc_raw"
  Query  
 Results 
┏━━━━━━━┓
┃ total ┃
┡━━━━━━━┩
│ 51139 │
└───────┘
1 rows
```

## Interactive Mode

```
$ spine ui

Market Spine Interactive Mode

What would you like to do?

[1] Browse and run pipelines
[2] Verify data integrity
[3] Query data
[4] Show system status
[5] Exit

Enter choice [1]:
```

## Test Suite

```
$ pytest tests/ -q
127 passed, 3 skipped in 0.45s
```

---

## Summary

Market Spine Basic provides a complete CLI for managing data pipelines:

- **Discovery**: `spine list` and `--help-params` for exploration
- **Execution**: `spine run` with parameter validation
- **Verification**: `spine verify tables|data|quality`
- **Querying**: `spine query weeks|symbols|sql|rejects`
- **Interactive**: `spine ui` for guided usage

All commands use Rich for beautiful terminal output with tables and formatting.
