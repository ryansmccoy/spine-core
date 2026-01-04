# Market Spine CLI Documentation

A modern, user-friendly command-line interface for the Market Spine analytics pipeline system, built with Typer, Rich, and Questionary.

## Table of Contents

- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Understanding the CLI](#understanding-the-cli) ⭐
- [Commands](#commands)
  - [Discover & Inspect Pipelines](#discover--inspect-pipelines)
  - [Run Pipelines](#run-pipelines)
  - [Query Data](#query-data)
  - [Verify Database](#verify-database)
  - [Database Operations](#database-operations)
  - [Health Check](#health-check)
- [Parameter Passing](#parameter-passing)
- [Tier Normalization](#tier-normalization)
- [Interactive Mode](#interactive-mode)
- [Logging Configuration](#logging-configuration)
- [Examples](#examples)

---

## Understanding the CLI

**New to Spine?** Start with the [UX Guide](UX_GUIDE.md) to understand:
- How to think about pipelines, parameters, and tiers
- How ingest resolution works
- How parameters are resolved
- Typical workflows and best practices

**Quick tip:** Use `spine pipelines describe <pipeline>` to see detailed information about any pipeline before running it.

---

## Overview

The Market Spine CLI provides a modern, polished command-line experience for managing FINRA OTC transparency data pipelines. Key features include:

- ✨ **Beautiful UI** - Rich formatting with tables, panels, and progress indicators
- 🔄 **Three-Way Parameter Passing** - Friendly options, key=value args, or -p flags
- 🎯 **Smart Tier Normalization** - Automatically converts tier aliases (Tier1, tier2) to DB values
- 📊 **Interactive Mode** - Full questionary-based menu when run without arguments
- 📝 **Configurable Logging** - Control log destination (stdout/stderr/file) and format
- 🔍 **Dry Run Support** - Preview pipeline execution without running

## Installation

The CLI is automatically installed when you install the market-spine-basic package:

```bash
# Install with uv
uv sync

# Verify installation
uv run spine --version
```

**Output:**
```
spine, version 0.1.0
```

## Quick Start

```bash
# Show help
uv run spine --help

# List available pipelines
uv run spine pipelines list

# Describe a specific pipeline
uv run spine pipelines describe finra.otc_transparency.normalize_week

# Run a pipeline (friendly syntax)
uv run spine run finra.otc_transparency.normalize_week --week-ending 2025-12-05 --tier OTC

# Interactive mode (no arguments)
uv run spine
```

---

## Commands

### Discover & Inspect Pipelines

**Command:** `spine pipelines {list|describe} [OPTIONS]`

Discover available pipelines and inspect their details.

#### List Pipelines

**Command:** `spine pipelines list [OPTIONS]`

List all available pipelines with descriptions.

**Options:**
- `--prefix TEXT` - Filter pipelines by prefix

**Example 1: List all pipelines**

```bash
uv run spine pipelines list
```

**Output:**
```
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

Found 5 pipeline(s)
```

**Example 2: Filter by prefix**

```bash
uv run spine pipelines list --prefix finra.otc_transparency.normalize
```

**Output:**
```
                                       Available Pipelines                                        
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name                                   ┃ Description                                            ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ finra.otc_transparency.normalize_week  │ Normalize raw FINRA OTC transparency data for one week │
└────────────────────────────────────────┴────────────────────────────────────────────────────────┘

Found 1 pipeline(s)
```

#### Describe Pipeline

**Command:** `spine pipelines describe PIPELINE`

Show detailed information about a specific pipeline including parameters, ingest resolution logic, and examples.

**Example:**

```bash
uv run spine pipelines describe finra.otc_transparency.ingest_week
```

**Output:**
```
Pipeline: finra.otc_transparency.ingest_week
Description: Ingest FINRA OTC transparency file for one week

Parameters:

  Required:
    • file_path
      Path to the FINRA OTC transparency PSV file

  Optional:
    • tier
      Market tier (auto-detected from filename if not provided)
    • week_ending
      Week ending date in ISO format (auto-detected if not provided)

Ingest Source Resolution:

  When --file is provided:
    • Uses the specified file path directly

  When --file is omitted:
    • Derives file path from week_ending and tier
    • Pattern: data/finra/finra_otc_weekly_{tier}_{date}.csv
    • Use --dry-run to see resolved path before execution

Example Usage:

  # With explicit file:
  spine run finra.otc_transparency.ingest_week \
    --file data/finra/weekly_otc.csv \
    --week-ending 2025-12-19 \
    --tier OTC

  # With derived file path:
  spine run finra.otc_transparency.ingest_week \
    --week-ending 2025-12-19 \
    --tier OTC

Helpful Commands:

  spine run finra.otc_transparency.ingest_week --dry-run     # Preview execution
  spine run finra.otc_transparency.ingest_week --help        # Show all CLI options
```

---

### Run Pipelines

**Command:** `spine run run PIPELINE [PARAMETERS] [OPTIONS]`

Execute a pipeline with parameters. Supports three different parameter passing methods (see [Parameter Passing](#parameter-passing)).

> **Note:** The command is `spine run run` - the first `run` is the command group, the second `run` is the execution command.

**Options:**
- `--week-ending DATE` / `--week DATE` - Week ending date (YYYY-MM-DD)
- `--tier TIER` - Market tier (OTC, NMS_TIER_1, NMS_TIER_2, or aliases)
- `--file PATH` - File path for ingest operations
- `-p KEY=VALUE` - Generic parameter (repeatable, backward compatible)
- `--lane LANE` - Execution lane [default: normal]
- `--dry-run` - Show what would execute without running
- `--explain-source` - Show how ingest source is resolved (ingest pipelines only)
- `--help-params` - Show pipeline parameter documentation
- `--quiet` / `-q` - Suppress logs, show only summary

**Example 1: Show pipeline parameters**

```bash
uv run spine run run finra.otc_transparency.normalize_week --help-params
```

**Output:**
```
Pipeline: finra.otc_transparency.normalize_week
Description: Normalize raw FINRA OTC transparency data for one week

Parameters:
  • week_ending (required)
    Week ending date in ISO format (YYYY-MM-DD)
  • tier (required)
    Market tier
  • force (optional)
    Re-normalize even if already normalized
    Default: False
```

**Example 2: Dry run with friendly options**

```bash
uv run spine run run finra.otc_transparency.normalize_week --week-ending 2025-12-05 --tier OTC --dry-run
```

**Output:**
```
╭──────────────────────────────────────────────────────────────────────── Dry Run ─────────────────────────────────────────────────────────────────────────╮
│ Pipeline: finra.otc_transparency.normalize_week                                                                                                          │
│                                                                                                                                                          │
│ Resolved Parameters:                                                                                                                                     │
│   • week_ending: 2025-12-05                                                                                                                              │
│   • tier: OTC                                                                                                                                            │
│                                                                                                                                                          │
│ Would execute with these parameters.                                                                                                                     │
│ (Use without --dry-run to actually run)                                                                                                                  │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

**Example 3: Execute pipeline (actual run)**

```bash
uv run spine run run finra.otc_transparency.normalize_week --week-ending 2025-12-05 --tier OTC
```

**Output (Success):**
```
╭──────────────────────────────────────────────────────────────────── Pipeline Complete ───────────────────────────────────────────────────────────────────╮
│ Status: Completed                                                                                                                                        │
│ Duration: 3.45s                                                                                                                                          │
│                                                                                                                                                          │
│ Metrics:                                                                                                                                                 │
│   • rows_processed: 1,234                                                                                                                                │
│   • rows_inserted: 1,234                                                                                                                                 │
│   • capture_id: cap_20250105_143022                                                                                                                      │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

**Output (Error):**
```
╭────────────────────────────────────────────────────────────────── Invalid Parameters ───────────────────────────────────────────────────────────────────╮
│ Parameter validation failed.                                                                                                                             │
│                                                                                                                                                          │
│ Missing required: week_ending, tier                                                                                                                      │
│                                                                                                                                                          │
│ Run with --help-params to see all parameters                                                                                                             │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

---

### Query Data

**Command:** `spine query {weeks|symbols} [OPTIONS]`

Query available data in the database.

#### Query Available Weeks

```bash
uv run spine query weeks --tier OTC [--limit N]
```

**Example:**

```bash
uv run spine query weeks --tier NMS_TIER_1 --limit 5
```

**Output:**
```
              Available Weeks - NMS_TIER_1              
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Week Ending ┃ Symbol Count ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 2025-12-19  │        1,456 │
│ 2025-12-12  │        1,423 │
│ 2025-12-05  │        1,401 │
│ 2025-11-28  │        1,389 │
│ 2025-11-21  │        1,412 │
└─────────────┴──────────────┘

Showing 5 week(s)
```

#### Query Top Symbols

```bash
uv run spine query symbols --week YYYY-MM-DD --tier TIER [--top N]
```

**Example:**

```bash
uv run spine query symbols --week 2025-12-19 --tier NMS_TIER_1 --top 10
```

**Output:**
```
                  Top 10 Symbols - NMS_TIER_1 - 2025-12-19                   
┏━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Symbol ┃       Volume ┃ Avg Price ┃
┡━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━┩
│ AAPL   │ 125,456,789  │   $185.23 │
│ TSLA   │  98,765,432  │   $245.67 │
│ NVDA   │  87,654,321  │   $512.34 │
│ AMZN   │  76,543,210  │   $178.90 │
│ META   │  65,432,109  │   $425.67 │
│ GOOGL  │  54,321,098  │   $142.45 │
│ MSFT   │  43,210,987  │   $378.12 │
│ AMD    │  32,109,876  │   $156.78 │
│ NFLX   │  21,098,765  │   $567.89 │
│ INTC   │  10,987,654  │    $45.23 │
└────────┴──────────────┴───────────┘
```

---

### Verify Database

**Command:** `spine verify {table|data} [OPTIONS]`

Verify database integrity and data quality.

#### Verify Table Exists

```bash
uv run spine verify table TABLE_NAME
```

**Example:**

```bash
uv run spine verify table finra_otc_transparency_normalized
```

**Output (Success):**
```
✓ Table 'finra_otc_transparency_normalized' exists
╭────────────────────────────────────────────────────────────────────────── Table Info ────────────────────────────────────────────────────────────────────────╮
│ Table: finra_otc_transparency_normalized                                                                                                                     │
│ Rows: 145,678                                                                                                                                                │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

**Output (Not Found):**
```
✗ Table 'unknown_table' not found
```

#### Verify Data Quality

```bash
uv run spine verify data --tier TIER --week YYYY-MM-DD
```

**Example:**

```bash
uv run spine verify data --tier OTC --week 2025-12-19
```

**Output (Success):**
```
✓ Data quality checks passed for 2025-12-19 (OTC)
1,234 rows verified
```

**Output (Issues Found):**
```
⚠ Found 2 issue(s):
  • 15 rows have null values in required fields
  • Duplicate records found for symbols: AAPL, TSLA
```

---

### Database Operations

**Command:** `spine db {init|reset} [OPTIONS]`

Manage database schema.

#### Initialize Database

```bash
uv run spine db init [--force]
```

**Example:**

```bash
uv run spine db init
```

**Output:**
```
Initialize database schema? [y/N]: y
╭────────────────────────────────────────────────────────────────── Database Initialized ──────────────────────────────────────────────────────────────────╮
│ Schema tables created successfully                                                                                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

#### Reset Database

```bash
uv run spine db reset [--force]
```

**Example:**

```bash
uv run spine db reset
```

**Output:**
```
WARNING: This will delete ALL data!
Are you sure you want to reset the database? [y/N]: y
╭──────────────────────────────────────────────────────────────────── Database Reset ──────────────────────────────────────────────────────────────────────╮
│ All tables dropped and recreated                                                                                                                         │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

---

### Health Check

**Command:** `spine doctor doctor`

Run comprehensive health checks on the system.

**Example:**

```bash
uv run spine doctor doctor
```

**Output (All Passing):**
```
                Health Check Results                 
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Check                                    ┃ Status ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Database Connection                      │   ✓    │
│ Table: finra_otc_transparency_raw        │   ✓    │
│ Table: finra_otc_transparency_normalized │   ✓    │
│ Table: finra_otc_transparency_aggregated │   ✓    │
└──────────────────────────────────────────┴────────┘

All checks passed
```

**Output (Some Failing):**
```
                Health Check Results                 
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Check                                    ┃ Status ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Database Connection                      │   ✓    │
│ Table: finra_otc_transparency_raw        │   ✓    │
│ Table: finra_otc_transparency_normalized │   ✗    │
│ Table: finra_otc_transparency_aggregated │   ✗    │
└──────────────────────────────────────────┴────────┘

Some checks failed
```

---

## Parameter Passing

The CLI supports **three different methods** for passing parameters to pipelines, with clear precedence rules:

### 1. Friendly Options (Highest Priority)

Use intuitive command-line flags:

```bash
uv run spine run run finra.otc_transparency.normalize_week \
  --week-ending 2025-12-05 \
  --tier OTC
```

**Supported friendly options:**
- `--week-ending DATE` or `--week DATE` - Week ending date
- `--tier TIER` - Market tier
- `--file PATH` - File path

### 2. Key=Value Arguments (Medium Priority)

Pass parameters as positional arguments:

```bash
uv run spine run run finra.otc_transparency.normalize_week \
  week_ending=2025-12-05 \
  tier=OTC
```

### 3. -p Flags (Lowest Priority, Backward Compatible)

Use the traditional `-p` flag syntax:

```bash
uv run spine run run finra.otc_transparency.normalize_week \
  -p week_ending=2025-12-05 \
  -p tier=OTC
```

### Precedence Example

When multiple methods are used, higher priority wins:

```bash
uv run spine run run finra.otc_transparency.normalize_week \
  -p tier=OTC \
  tier=NMS_TIER_1 \
  --tier NMS_TIER_2 \
  --dry-run
```

**Result:** `tier=NMS_TIER_2` (friendly option wins)

---

## Tier Normalization

The CLI automatically normalizes tier values to their canonical database representations:

### Tier Aliases

| Input Alias          | Normalized DB Value |
|---------------------|---------------------|
| `OTC`, `otc`        | `OTC`               |
| `Tier1`, `tier1`    | `NMS_TIER_1`        |
| `Tier2`, `tier2`    | `NMS_TIER_2`        |
| `nms_tier_1`        | `NMS_TIER_1`        |
| `nms_tier_2`        | `NMS_TIER_2`        |

### Examples

```bash
# All of these produce tier=NMS_TIER_1
uv run spine run run normalize_week --tier Tier1 --dry-run
uv run spine run run normalize_week --tier tier1 --dry-run
uv run spine run run normalize_week --tier nms_tier_1 --dry-run
```

**Output (all the same):**
```
Resolved Parameters:
  • tier: NMS_TIER_1
```

---

## Interactive Mode

When you run `spine` without any arguments, it launches an interactive menu powered by Questionary.

**Launch:**

```bash
uv run spine
```

**Output:**

```
Market Spine - Interactive Mode

? What would you like to do?
❯ Run a pipeline
  List available pipelines
  Query data
  Verify database
  Database operations
  Health check
  Exit
```

### Interactive Pipeline Execution

1. Select "Run a pipeline"
2. Choose from autocomplete list of pipelines
3. Enter parameters interactively with validation
4. Choose dry-run or execute

**Example Flow:**

```
? What would you like to do? Run a pipeline
? Select pipeline: finra.otc_transparency.normalize_week

Pipeline: finra.otc_transparency.normalize_week
Normalize raw FINRA OTC transparency data for one week

? week_ending (required): 2025-12-05
? Select tier: NMS_TIER_1
? force (optional): 
? Dry run? (show what would execute without running) No

Running: uv run spine run run finra.otc_transparency.normalize_week --week-ending 2025-12-05 --tier NMS_TIER_1

[Pipeline executes...]
```

---

## Logging Configuration

Control logging behavior with global options.

### Log Level

```bash
uv run spine --log-level DEBUG run run normalize_week ...
uv run spine --log-level WARNING run run normalize_week ...
```

**Levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL

### Log Format

```bash
# Pretty format (default, human-readable)
uv run spine --log-format pretty run run normalize_week ...

# JSON format (machine-readable)
uv run spine --log-format json run run normalize_week ...
```

### Log Destination

```bash
# stdout (default, PowerShell-friendly)
uv run spine --log-to stdout run run normalize_week ...

# stderr (traditional)
uv run spine --log-to stderr run run normalize_week ...

# file
uv run spine --log-to file run run normalize_week ...
```

### Quiet Mode

Suppress all logs except errors, show only final summary:

```bash
uv run spine --quiet run run normalize_week --week 2025-12-05 --tier OTC
```

**Output (quiet mode):**
```
╭────────────────────────────────────────────────────────────── Pipeline Complete ─────────────────────────────────────────────────────────────╮
│ Status: Completed                                                                                                                            │
│ Duration: 3.45s                                                                                                                              │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

---

## Examples

### Example 1: Complete Data Pipeline Workflow

```bash
# 1. Check system health
uv run spine doctor doctor

# 2. Initialize database if needed
uv run spine db init

# 3. Discover available pipelines
uv run spine pipelines list --prefix finra.otc_transparency

# 4. Inspect a pipeline in detail
uv run spine pipelines describe finra.otc_transparency.ingest_week

# 5. Understand ingest source resolution
uv run spine run run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-05 \
  --tier OTC \
  --explain-source

# 6. Dry run to verify parameters
uv run spine run run finra.otc_transparency.ingest_week \
  --file data/otc_20251205.txt \
  --week-ending 2025-12-05 \
  --tier OTC \
  --dry-run

# 7. Execute ingest
uv run spine run run finra.otc_transparency.ingest_week \
  --file data/otc_20251205.txt \
  --week-ending 2025-12-05 \
  --tier OTC

# 8. Execute normalization
uv run spine run run finra.otc_transparency.normalize_week \
  --week-ending 2025-12-05 \
  --tier OTC

# 9. Verify data quality
uv run spine verify data --tier OTC --week 2025-12-05

# 10. Query results
uv run spine query symbols --week 2025-12-05 --tier OTC --top 20
```

### Example 2: Multi-Tier Processing

```bash
# Process all three tiers for a week
for tier in OTC Tier1 Tier2; do
  echo "Processing $tier..."
  uv run spine run run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-05 \
    --tier $tier
done

# Query each tier
uv run spine query weeks --tier OTC --limit 5
uv run spine query weeks --tier NMS_TIER_1 --limit 5
uv run spine query weeks --tier NMS_TIER_2 --limit 5
```

### Example 3: Backfill Range

```bash
# Show backfill pipeline parameters
uv run spine run run finra.otc_transparency.backfill_range --help-params

# Execute backfill for a date range
uv run spine run run finra.otc_transparency.backfill_range \
  start_date=2025-11-01 \
  end_date=2025-12-31 \
  tier=NMS_TIER_1
```

### Example 4: Error Handling

```bash
# Missing required parameter
uv run spine run run finra.otc_transparency.normalize_week --week-ending 2025-12-05
# Output: Error panel showing "Missing required: tier"

# Invalid tier value
uv run spine run run finra.otc_transparency.normalize_week \
  --week-ending 2025-12-05 \
  --tier INVALID
# Output: Error panel showing "Invalid tier: INVALID. Must be one of: OTC, NMS_TIER_1, NMS_TIER_2"

# Invalid date format
uv run spine run run finra.otc_transparency.normalize_week \
  --week-ending 12/05/2025 \
  --tier OTC
# Output: Error panel showing date format error
```

---

## Architecture

### Directory Structure

```
src/market_spine/cli/
├── __init__.py           # Main Typer app, command registration
├── console.py            # Rich console singleton, tier normalization
├── params.py             # ParamParser for 3-way parameter merging
├── ui.py                 # Rich UI components (panels, tables, progress)
├── logging_config.py     # Logging configuration (destination, format)
├── commands/
│   ├── __init__.py
│   ├── run.py            # Pipeline execution (run, dry-run, help-params)
│   ├── list_.py          # List pipelines with filtering
│   ├── query.py          # Query weeks and symbols
│   ├── verify.py         # Verify tables and data quality
│   ├── db.py             # Database init/reset
│   └── doctor.py         # Health checks
└── interactive/
    ├── __init__.py
    ├── menu.py           # Main interactive menu
    └── prompts.py        # Parameter prompting logic
```

### Key Design Principles

1. **Modularity** - Each command in its own module
2. **Type Safety** - Full type hints with Annotated parameters
3. **User-Friendly** - Clear error messages, helpful examples
4. **Backward Compatible** - `-p` flags still work
5. **PowerShell-Friendly** - Logs to stdout by default
6. **Extensible** - Easy to add new commands and options

---

## Troubleshooting

### PowerShell Shows Red Error Text

**Cause:** PowerShell treats stderr as errors (red text)

**Solution:** Use default stdout logging or explicitly set:
```bash
uv run spine --log-to stdout run run ...
```

### Parameters Not Working

**Check precedence:** Friendly options > key=value > -p flags

**Example:**
```bash
# This will use tier=OTC (friendly option wins)
uv run spine run run normalize_week \
  -p tier=NMS_TIER_1 \
  --tier OTC
```

### Unknown Pipeline Error

**Verify pipeline name:**
```bash
uv run spine pipelines list
```

Pipeline names must match exactly (case-sensitive).

**Get details about a pipeline:**
```bash
uv run spine pipelines describe <pipeline-name>
```

### Tier Not Normalizing

Tier normalization happens automatically. Verify with dry-run:
```bash
uv run spine run run normalize_week \
  --week-ending 2025-12-05 \
  --tier Tier1 \
  --dry-run
```

Should show `tier: NMS_TIER_1` in output.

---

## Contributing

To add a new command:

1. Create `commands/your_command.py` with a Typer app
2. Import and register in `cli/__init__.py`:
   ```python
   from .commands import your_command
   app.add_typer(your_command.app, name="your-command", help="Description")
   ```

To add a friendly parameter option:

1. Add to `commands/run.py` function signature
2. Update `params.py` `merge_params()` to handle it
3. Update this README with examples

---

## Support

For issues or questions:
- Check `--help` for any command
- Use `--help-params` to see pipeline parameters
- Run `spine doctor doctor` to check system health
- Try `--dry-run` to preview execution

---

**Version:** 0.1.0  
**Last Updated:** January 3, 2026
