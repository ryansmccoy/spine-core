# Timing and Clocks

This document explains the temporal model for FINRA OTC Transparency data.

## The Three-Clock Model

Financial data pipelines must track multiple temporal concepts. This domain implements a **three-clock model**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          THREE-CLOCK MODEL                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Clock 1: BUSINESS TIME              Clock 2: SOURCE TIME               │
│  ─────────────────────               ─────────────────────              │
│  "When did the trading               "When did FINRA publish            │
│   actually happen?"                   this data?"                        │
│                                                                          │
│  Column: week_ending                 Column: source_last_update_date    │
│  Example: 2025-12-19 (Friday)        Example: 2025-12-22 (Monday)       │
│                                                                          │
│                                                                          │
│  Clock 3: CAPTURE TIME                                                   │
│  ─────────────────────                                                   │
│  "When did WE ingest this data?"                                        │
│                                                                          │
│  Column: captured_at                                                     │
│  Example: 2025-12-22T14:30:00Z                                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Clock Definitions

### Clock 1: Business Time (`week_ending`)

**Definition**: The Friday that ends the trading week.

**Semantics**: This answers "when did the economic activity occur?"

**Example**:
- Trading from Mon Dec 16 to Fri Dec 20
- `week_ending = 2025-12-20`

**Usage**:
- Primary grouping key for analysis
- Time-series alignment
- Rolling window calculations

### Clock 2: Source Time (`source_last_update_date`)

**Definition**: When FINRA last updated this record.

**Semantics**: This answers "when was this data version published?"

**Example**:
- FINRA publishes Monday Dec 22
- `source_last_update_date = 2025-12-22`

**Usage**:
- Detecting data corrections/restatements
- Auditing data freshness
- Debugging discrepancies

### Clock 3: Capture Time (`captured_at`)

**Definition**: When our pipeline ingested this data.

**Semantics**: This answers "when did we observe this data?"

**Example**:
- Pipeline runs Monday afternoon
- `captured_at = 2025-12-22T14:30:00Z`

**Usage**:
- Identifying multiple captures of same data
- Point-in-time reconstruction
- Audit trail

## FINRA Publication Schedule

FINRA publishes OTC transparency data on a weekly cadence:

```
Mon-Fri (Trading Week)     Monday (T+3)
────────────────────       ───────────
Trading Activity    →      Publication
Dec 16-20                  Dec 22
Dec 23-27                  Dec 29*
Dec 30 - Jan 3             Jan 6
```

*Holiday adjustments may shift publication dates.

### Key Timing Rules

1. **Publication Day**: Always Monday (barring holidays)
2. **Lag**: T+3 business days from Friday
3. **Coverage**: Monday 00:00 to Friday 23:59:59

### Date Derivation

Given a FINRA file with `lastUpdateDate` (publication date), we derive:

```python
def derive_week_ending(publication_date: date) -> date:
    """
    Publication date is Monday.
    Week ending is previous Friday = Monday - 3 days.
    """
    # Monday (weekday=0) minus 3 = Friday (weekday=4)
    return publication_date - timedelta(days=3)
```

**Examples**:

| Publication Date (Monday) | Week Ending (Friday) |
|---------------------------|---------------------|
| 2025-12-22 | 2025-12-19 |
| 2025-12-29 | 2025-12-26 |
| 2026-01-06 | 2026-01-03 |

## Capture Identity

Each ingestion creates a unique `capture_id`:

```
finra_otc:NMS_TIER_1:2025-12-19:a3f5b2
└──────┘ └────────┘ └────────┘ └────┘
 prefix    tier     week_end   hash
```

### Why Track Captures?

1. **Corrections**: FINRA may restate data
2. **Multiple Runs**: Same week may be ingested multiple times
3. **Debugging**: Trace issues to specific ingestion

### Latest vs All Captures

- **Latest capture**: Use for most analyses (rolling metrics)
- **All captures**: Use for audit, debugging, time-travel

```sql
-- Get latest capture per week
SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY week_ending, tier, symbol
        ORDER BY captured_at DESC
    ) as rn
    FROM otc_symbol_summary
) WHERE rn = 1;
```

## Rolling Window Semantics

Rolling metrics use **latest capture per historical week**:

```
Week Ending | Capture Used
────────────┼─────────────
2025-12-19  | Latest capture for 12-19
2025-12-12  | Latest capture for 12-12  
2025-12-05  | Latest capture for 12-05
...
```

This ensures rolling metrics reflect the best available data (corrections applied).

## Pipeline Parameters

### Date Inference

Pipelines infer dates from:

1. **Filename**: `finra_otc_weekly_tier1_20251222.psv` → Dec 22
2. **Content**: `lastUpdateDate` column value
3. **Override**: Explicit `--week-ending` parameter

Precedence: Override > Filename > Content

### Override Examples

```bash
# Let pipeline infer dates
uv run spine run finra.otc_transparency.ingest_week \
    --file-path data/tier1_20251222.psv \
    --tier NMS_TIER_1

# Explicit override for backfill
uv run spine run finra.otc_transparency.ingest_week \
    --file-path data/manual_file.psv \
    --tier NMS_TIER_1 \
    --week-ending 2025-12-19 \
    --file-date 2025-12-22
```

## Holiday Considerations

FINRA may adjust publication around holidays:

| Holiday | Typical Adjustment |
|---------|-------------------|
| Christmas Week | Early publication or skip |
| New Year's Week | Delayed publication |
| Federal Holidays | Publication day may shift |

For production systems, implement holiday calendar awareness.

## Best Practices

1. **Always use `week_ending`** for business logic, not `captured_at`
2. **Store all clocks** - you'll need them for debugging
3. **Use latest capture** for analyses unless auditing
4. **Document overrides** when using manual date parameters
5. **Monitor for restatements** by comparing capture counts
