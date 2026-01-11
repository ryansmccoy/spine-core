# Spine CLI UX Guide

## How to Think About Spine CLI

The Spine CLI is designed around three core concepts:

### 1. **Pipelines** - The What

Pipelines are named data processing operations. Each pipeline:
- Has a clear, single responsibility
- Accepts well-defined parameters
- Produces predictable outcomes

Think of pipelines as **verbs** - they describe actions:
- `ingest_week` - Bring raw data into the system
- `normalize_week` - Clean and standardize data
- `aggregate_week` - Compute summary statistics

### 2. **Parameters** - The How

Parameters configure pipeline behavior. The CLI supports **three equivalent ways** to pass them:

```bash
# 1. Friendly options (recommended for interactive use)
spine run finra.otc_transparency.normalize_week \
  --week-ending 2025-12-19 \
  --tier OTC

# 2. Key=value positional args (good for scripts)
spine run finra.otc_transparency.normalize_week \
  week_ending=2025-12-19 \
  tier=OTC

# 3. -p flags (backward compatible)
spine run finra.otc_transparency.normalize_week \
  -p week_ending=2025-12-19 \
  -p tier=OTC
```

**Precedence:** Friendly options > Key=value > -p flags

### 3. **Tiers** - Data Source Contexts

Tiers are not arbitrary strings - they represent **distinct data sources**:

| Tier | Meaning |
|------|---------|
| `OTC` | Over-the-counter non-ATS aggregated trades |
| `NMS_TIER_1` | NMS Tier 1 securities (higher reporting standards) |
| `NMS_TIER_2` | NMS Tier 2 securities (lower reporting standards) |

**Aliases accepted** for convenience:
- `Tier1`, `tier1` → `NMS_TIER_1`
- `Tier2`, `tier2` → `NMS_TIER_2`
- `otc` → `OTC`

## How Ingest Works

Ingest is the process of bringing external data files into the Spine database. Understanding ingest is critical because **it's where data enters the system**.

### Three Ingest Modes

#### Mode 1: Explicit File (Full Control)

You specify exactly which file to ingest:

```bash
spine run finra.otc_transparency.ingest_week \
  --file /path/to/my/data.csv \
  --week-ending 2025-12-19 \
  --tier OTC
```

**When to use:**
- Custom file locations
- Non-standard filenames
- Testing with sample data

#### Mode 2: Derived Local Resolution (Convenience)

Spine derives the file path from `week_ending` and `tier`:

```bash
spine run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-19 \
  --tier OTC

# Resolves to: data/finra/finra_otc_weekly_otc_20251219.csv
```

**Path derivation logic:**
1. Convert tier to lowercase filename component (`OTC` → `otc`, `NMS_TIER_1` → `tier1`)
2. Format date as YYYYMMDD
3. Construct path: `data/finra/finra_otc_weekly_{tier}_{date}.csv`

**See what will be used:**
```bash
spine run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-19 \
  --tier OTC \
  --explain-source
```

#### Mode 3: Remote Fetch (Future)

**Not implemented in Basic tier.** Would fetch directly from FINRA API:

```bash
# Future capability (not available yet)
spine run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-19 \
  --tier OTC \
  --source finra

# Error: "Remote fetch not available in Basic tier."
```

### Why Ingest Resolution Matters

**Problem:** Users reasonably ask "where does my data come from?"

**Solution:** Spine makes data provenance **explicit and visible**:

1. **Before execution:** Use `--explain-source` or `--dry-run`
2. **In errors:** File paths appear in error messages
3. **In logs:** Ingest operations log source files

## How Parameters Are Resolved

Parameter resolution happens in **three stages**:

### Stage 1: Collection

Gather parameters from all three input methods:

```bash
spine run normalize_week \
  -p tier=OTC \              # Priority 3
  week_ending=2025-12-19 \   # Priority 2
  --tier NMS_TIER_1          # Priority 1 (wins)
```

### Stage 2: Normalization

Transform user-friendly inputs to canonical forms:

- **Tiers:** `Tier1` → `NMS_TIER_1`
- **Dates:** Validate YYYY-MM-DD format
- **Paths:** Resolve relative paths

### Stage 3: Validation

Check against pipeline's parameter spec:

- Required params present?
- Types correct?
- Values within allowed ranges?

**If validation fails:**
```
╭─ Parameter Validation Failed ─╮
│ Missing required: tier         │
│                                │
│ Run 'spine pipelines describe  │
│   normalize_week' for details  │
╰────────────────────────────────╯
```

## Discovering What's Available

### List All Pipelines

```bash
spine pipelines list
```

**Output:**
```
Available Pipelines
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Name                    ┃ Description         ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ finra.otc...ingest_week │ Ingest FINRA data   │
│ ...                     │ ...                 │
└─────────────────────────┴─────────────────────┘
```

### Filter by Prefix

```bash
spine pipelines list --prefix finra.otc_transparency.normalize
```

### Inspect a Pipeline

```bash
spine pipelines describe finra.otc_transparency.normalize_week
```

**Shows:**
- Full description
- Required vs optional parameters
- Parameter types and validation rules
- Ingest resolution logic (for ingest pipelines)
- Example commands
- Helpful hints

## Understanding Execution

### Preview Without Running

```bash
spine run normalize_week \
  --week-ending 2025-12-19 \
  --tier OTC \
  --dry-run
```

**Shows:**
- Resolved parameters
- Ingest source (if applicable)
- What would execute

### See Parameter Help

```bash
spine run normalize_week --help-params
```

**Quick reference for:**
- Parameter names
- Required vs optional
- Defaults

### Explain Ingest Source

```bash
spine run ingest_week \
  --week-ending 2025-12-19 \
  --tier OTC \
  --explain-source
```

**Shows:**
- Mode (explicit vs derived)
- Resolved file path
- How path was determined

## Typical Workflows

### Workflow 1: Ingest → Normalize → Aggregate

```bash
# 1. Discover available pipelines
spine pipelines list --prefix finra.otc_transparency

# 2. Learn about ingest
spine pipelines describe finra.otc_transparency.ingest_week

# 3. Preview ingest
spine run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-19 \
  --tier OTC \
  --dry-run

# 4. Execute ingest
spine run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-19 \
  --tier OTC

# 5. Normalize
spine run finra.otc_transparency.normalize_week \
  --week-ending 2025-12-19 \
  --tier OTC

# 6. Aggregate
spine run finra.otc_transparency.aggregate_week \
  --week-ending 2025-12-19 \
  --tier OTC
```

### Workflow 2: Multi-Tier Processing

```bash
# Process all tiers for a week
for tier in OTC Tier1 Tier2; do
  echo "Processing $tier..."
  
  spine run finra.otc_transparency.ingest_week \
    --week-ending 2025-12-19 \
    --tier $tier
    
  spine run finra.otc_transparency.normalize_week \
    --week-ending 2025-12-19 \
    --tier $tier
done
```

### Workflow 3: Backfill Historical Data

```bash
# Check backfill pipeline
spine pipelines describe finra.otc_transparency.backfill_range

# Execute backfill
spine run finra.otc_transparency.backfill_range \
  start_date=2025-11-01 \
  end_date=2025-12-31 \
  tier=OTC
```

## Design Principles

### Principle 1: Visibility Over Magic

**Bad:** Hidden behavior that "just works" (until it doesn't)
**Good:** Explicit behavior that users can inspect

```bash
# Instead of silently deriving file paths...
spine run ingest_week --week 2025-12-19 --tier OTC --explain-source

# Shows exactly what will happen:
# Mode: Derived Local Resolution
# Resolved path: data/finra/finra_otc_weekly_otc_20251219.csv
```

### Principle 2: Progressive Disclosure

**Start simple, reveal complexity only when needed:**

```bash
# Simple:
spine pipelines list

# More detail:
spine pipelines describe normalize_week

# Full detail:
spine run normalize_week --help-params
spine run normalize_week --explain-source
```

### Principle 3: Fail Helpfully

**Never just say "error" - always explain and suggest:**

```bash
# Bad error:
# Error: Invalid tier

# Good error:
# Parameter Validation Failed
# Invalid tier: "Tier3"
# 
# Valid tier values: OTC, NMS_TIER_1, NMS_TIER_2
# Tier aliases also accepted:
#   Tier1, tier1 → NMS_TIER_1
#   Tier2, tier2 → NMS_TIER_2
```

### Principle 4: Consistency

**Commands follow predictable patterns:**

```bash
spine <noun> <verb>    # Discovery/inspection
spine run <pipeline>   # Execution

# Not:
spine <verb> <verb>    # Confusing!
```

## Common Questions

### Q: Why `spine pipelines list` instead of `spine list pipelines`?

A: Consistency. The pattern is `<noun> <verb>`:
- `pipelines list` - list the pipelines
- `pipelines describe` - describe a pipeline
- `query weeks` - query weeks
- `verify data` - verify data

### Q: Why does ingest require week_ending if it's auto-detected?

A: **Explicit is better than implicit.** Even if the filename contains the date, requiring `--week-ending` ensures:
1. User knows what week they're ingesting
2. Validation catches filename mismatches
3. Future API fetching will need explicit dates

### Q: How do I know if a pipeline will skip already-processed data?

A: Check the pipeline description:

```bash
spine pipelines describe finra.otc_transparency.normalize_week
```

Look for `force` parameter:
- If present: pipeline is idempotent, use `force=true` to re-run
- If absent: pipeline always processes

### Q: What's the difference between `--help` and `--help-params`?

- `--help`: CLI options (dry-run, quiet, lanes, etc.)
- `--help-params`: Pipeline parameters (week_ending, tier, etc.)

### Q: Why do some commands show logs and others don't?

By default, Spine shows:
- **Execution summary** (always)
- **Logs** (configurable)

Control logging:
```bash
--quiet       # Summary only
--log-level   # Control verbosity
--log-to      # stdout/stderr/file
```

## Mental Model Summary

```
┌─────────────────────────────────────┐
│         Spine CLI                   │
│                                     │
│  Discover → Inspect → Execute       │
│                                     │
│  1. pipelines list                  │
│     └─> What can I run?             │
│                                     │
│  2. pipelines describe <name>       │
│     └─> How do I configure it?      │
│                                     │
│  3. run <name> --dry-run            │
│     └─> What will it do?            │
│                                     │
│  4. run <name>                      │
│     └─> Execute!                    │
└─────────────────────────────────────┘
```

**Key Insight:** Spine CLI is designed for **iterative exploration**, not blind execution.

---

**Version:** 0.1.0  
**Last Updated:** January 3, 2026
