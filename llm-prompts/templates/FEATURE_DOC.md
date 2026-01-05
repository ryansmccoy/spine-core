# {Feature Name}

## Overview

{What this feature does and why it exists.}

## Components Implemented

| File | Purpose |
|------|---------|
| `pipelines.py` | {Description} |
| `validators.py` | {Description} |
| `schema/00_tables.sql` | {Description} |

## Usage Examples

### Python API

```python
from spine.domains.{domain}.pipelines import {Pipeline}

pipeline = {Pipeline}(conn, params={
    "week_ending": "2026-01-09",
    "tier": "NMS_TIER_1",
})
result = pipeline.run()
```

### SQL Queries

```sql
-- Get latest data
SELECT * FROM {domain}_{feature}_latest
WHERE week_ending = '2026-01-09';
```

## Behavior Changes

| Before | After |
|--------|-------|
| {Old behavior} | {New behavior} |

## Edge Cases

- **Empty input**: Returns empty result
- **Partial data**: Computes valid items, skips invalid

## Monitoring

```sql
-- Check anomalies
SELECT * FROM core_anomalies
WHERE domain = '{domain}'
  AND stage = '{stage}'
  AND resolved_at IS NULL;
```
