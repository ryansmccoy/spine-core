# Backfill Calculations Playbook

> **Safe backfill and recompute procedures for Market Spine calculations.**

---

## When to Backfill

| Scenario | Action | Risk Level |
|----------|--------|------------|
| New calc version released | Backfill with new version | 🟢 Low |
| Bug fix in existing calc | Recompute affected periods | 🟡 Medium |
| Source data correction | Re-ingest, then recompute | 🟡 Medium |
| Schema migration | Full recompute after migration | 🔴 High |

---

## Pre-Backfill Checklist

Before running any backfill:

- [ ] Identify affected date range (`start_date`, `end_date`)
- [ ] Confirm which tiers need recompute (`OTC`, `OTC_BLOCKS`, `ATSB`, `ATS`)
- [ ] Verify source data is available for all periods
- [ ] Check calc version to use (`get_current_version()` or explicit)
- [ ] Estimate runtime (rows × calcs × versions)
- [ ] Schedule during low-traffic window
- [ ] Alert downstream consumers of refresh

---

## Core Principle: capture_id Isolation

Each backfill run creates a **new capture_id**. This provides:

1. **Auditability**: Old and new rows both exist, traceable by capture_id
2. **Rollback capability**: Delete rows by capture_id to revert
3. **No overwrites**: Never mutates existing data
4. **Determinism**: Same inputs + version = same outputs

```sql
-- View all captures for a week
SELECT DISTINCT capture_id, captured_at, COUNT(*) as rows
FROM finra_otc_transparency_venue_share
WHERE week_ending = '2025-12-26' AND tier = 'OTC'
GROUP BY capture_id, captured_at
ORDER BY captured_at DESC;
```

---

## Standard Backfill Commands

### Single Week Recompute

```bash
# Recompute venue share for one week
spine run finra.otc_transparency.compute_venue_share \
    -p week_ending=2025-12-26 \
    -p tier=OTC \
    -p force=true
```

### Date Range Backfill

```bash
# Backfill multiple weeks
spine run finra.otc_transparency.backfill_range \
    -p start_date=2025-01-01 \
    -p end_date=2025-12-26 \
    -p tier=OTC \
    -p calc=venue_share \
    -p force=true
```

### Specific Calc Version

```bash
# Backfill with explicit version (for comparison)
spine run finra.otc_transparency.compute_venue_share \
    -p week_ending=2025-12-26 \
    -p tier=OTC \
    -p calc_version=v2 \
    -p force=true
```

---

## Backfill Ordering

Calcs have dependencies. Respect this order:

```
1. ingest_week      → raw data
2. normalize_week   → validated data
3. aggregate_week   → symbol summaries
4. compute_venue_share → venue market shares
5. compute_rolling  → 6-week rolling metrics
6. research_snapshot → combined snapshot
```

To recompute from scratch:

```bash
# Full recompute for a week
spine run finra.otc_transparency.ingest_week -p file_path=<path> -p tier=OTC -p force=true
spine run finra.otc_transparency.normalize_week -p week_ending=2025-12-26 -p tier=OTC -p force=true
spine run finra.otc_transparency.aggregate_week -p week_ending=2025-12-26 -p tier=OTC -p force=true
spine run finra.otc_transparency.compute_venue_share -p week_ending=2025-12-26 -p tier=OTC -p force=true
```

---

## Validation After Backfill

### 1. Row Count Check

```sql
SELECT capture_id, COUNT(*) as rows
FROM finra_otc_transparency_venue_share
WHERE week_ending = '2025-12-26' AND tier = 'OTC'
GROUP BY capture_id
ORDER BY captured_at DESC
LIMIT 2;
```

Compare new vs previous capture row counts.

### 2. Invariant Check

```sql
-- Venue shares must sum to 1.0
SELECT week_ending, tier, capture_id, SUM(market_share_pct) as total_share
FROM finra_otc_transparency_venue_share
WHERE capture_id = '<new_capture_id>'
GROUP BY week_ending, tier, capture_id
HAVING ABS(total_share - 1.0) > 0.001;
```

Should return zero rows.

### 3. Determinism Verification

If backfilling with same version as existing data:

```python
from spine.domains.finra.otc_transparency.calculations import rows_equal_deterministic

# Fetch old and new rows (excluding audit fields)
old_rows = query("SELECT * FROM ... WHERE capture_id = ?", old_id)
new_rows = query("SELECT * FROM ... WHERE capture_id = ?", new_id)

assert rows_equal_deterministic(old_rows, new_rows)
```

---

## Rollback Procedure

If a backfill produces incorrect results:

```sql
-- Identify bad capture
SELECT DISTINCT capture_id, captured_at
FROM finra_otc_transparency_venue_share
WHERE week_ending = '2025-12-26'
ORDER BY captured_at DESC;

-- Delete bad capture (preserves older captures)
DELETE FROM finra_otc_transparency_venue_share
WHERE capture_id = '<bad_capture_id>';

-- Verify rollback
SELECT COUNT(*) FROM finra_otc_transparency_venue_share
WHERE capture_id = '<bad_capture_id>';  -- Should be 0
```

---

## Monitoring During Backfill

Watch for:

| Metric | Healthy | Unhealthy |
|--------|---------|-----------|
| Rows per second | 1000+ | < 100 |
| Memory usage | Stable | Growing unbounded |
| Failed batches | 0 | > 0 |
| Quality check failures | 0 | > 0 |

```bash
# Monitor execution log
spine logs -f

# Check quality failures
SELECT * FROM core_quality
WHERE status = 'FAIL'
ORDER BY created_at DESC
LIMIT 10;
```

---

## Large-Scale Backfill Tips

For multi-year backfills:

1. **Batch by month**: Don't attempt all at once
2. **Use --dry-run first**: Verify params before execution
3. **Checkpoint progress**: Log completed weeks
4. **Parallelize by tier**: Different tiers are independent
5. **Off-peak scheduling**: Run during low-traffic hours

```bash
# Example monthly batching
for month in 01 02 03 04 05 06 07 08 09 10 11 12; do
    spine run finra.otc_transparency.backfill_range \
        -p start_date=2024-${month}-01 \
        -p end_date=2024-${month}-28 \
        -p tier=OTC \
        -p force=true
    echo "Completed 2024-${month}"
done
```

---

## Related Documentation

- [02-calc-contract-and-conventions.md](../fitness/02-calc-contract-and-conventions.md) — Version selection rules
- [03-calc-lifecycle-scenarios.md](../fitness/03-calc-lifecycle-scenarios.md) — VERSION / DEPRECATE flows
- [04-db-schema-and-index-policy.md](../fitness/04-db-schema-and-index-policy.md) — Constraint design
