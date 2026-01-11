# ADR 002: Capture ID and Data Versioning

**Status**: Accepted  
**Date**: January 2026  
**Context**: Data provenance and versioning in Market Spine

## Decision

Every data capture (ingest) generates a unique `capture_id` that tracks data provenance. This enables:

1. **Version tracking** — Multiple ingests of the same week/tier
2. **Downstream lineage** — Normalized data links to its raw capture
3. **Time-travel queries** — Query data as of a specific capture

Format:
```
{domain}:{tier}:{week_ending}:{timestamp_hash}
```

Example:
```
otc:NMS_TIER_1:2025-12-26:a3f5b2
```

## Context

FINRA publishes weekly OTC data every Friday. But:
- Files may be republished with corrections
- We may re-ingest after bug fixes
- Multiple systems may ingest the same data

Without versioning, we can't answer:
- "What data did yesterday's report use?"
- "When was this week's data last updated?"
- "Which records came from the corrected file?"

## The Three Clocks

Every record has three temporal dimensions:

| Clock | Column | Description | Example |
|-------|--------|-------------|---------|
| **Business time** | `week_ending` | When did this trading happen? | `2025-12-26` |
| **Source time** | `source_last_update_date` | When did FINRA publish? | `2025-12-27` |
| **System time** | `captured_at` | When did we ingest? | `2025-12-28T14:30:00Z` |

The `capture_id` is derived from business time + tier + system time.

## How It Works

### Ingest

```python
def ingest_week(week_ending, tier, file_path):
    captured_at = datetime.now(timezone.utc)
    capture_id = generate_capture_id(week_ending, tier, captured_at)
    
    for record in parse_file(file_path):
        insert_raw(
            record,
            captured_at=captured_at,
            capture_id=capture_id,
        )
```

### Normalize

Normalize operates on a specific capture:

```python
def normalize_week(week_ending, tier, capture_id=None):
    if capture_id is None:
        # Use latest capture
        capture_id = get_latest_capture(week_ending, tier)
    
    raw_records = load_raw(week_ending, tier, capture_id)
    normalized = validate(raw_records)
    
    for record in normalized:
        insert_venue_volume(
            record,
            capture_id=capture_id,  # Preserve lineage
        )
```

### Querying

Find all captures for a week:

```sql
SELECT DISTINCT capture_id, captured_at
FROM otc_raw
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
ORDER BY captured_at DESC;
```

Query data from a specific capture:

```sql
SELECT * FROM otc_venue_volume
WHERE capture_id = 'otc:NMS_TIER_1:2025-12-26:a3f5b2';
```

## Consequences

### Positive

1. **Full lineage** — Every record traces to its capture
2. **Safe re-ingests** — New captures don't overwrite old data
3. **Reproducibility** — Re-run processing on a specific capture
4. **Debugging** — Compare captures to find differences

### Negative

1. **Storage overhead** — Multiple captures = more rows
2. **Query complexity** — Must filter by capture or use "latest"
3. **Cleanup needed** — Old captures should be pruned

### Mitigation

For storage:
- Prune old captures after N days
- Or keep only latest N captures per week

For query complexity:
- Create views for "latest" data
- Default to latest capture in pipelines

## Schema

```sql
-- Raw data with capture tracking
CREATE TABLE otc_raw (
    id INTEGER PRIMARY KEY,
    week_ending TEXT NOT NULL,
    tier TEXT NOT NULL,
    -- ... data columns ...
    
    -- Clock 2: Source time
    source_last_update_date TEXT,
    
    -- Clock 3: System time
    captured_at TEXT NOT NULL,
    capture_id TEXT NOT NULL,
    
    -- Lineage
    execution_id TEXT,
    batch_id TEXT,
    ingested_at TEXT NOT NULL
);

CREATE INDEX idx_otc_raw_capture ON otc_raw(week_ending, tier, capture_id);
```

## Related

- [Pipeline Model](../architecture/03_pipeline_model.md)
- The `generate_capture_id()` function in `spine/domains/otc/pipelines.py`
