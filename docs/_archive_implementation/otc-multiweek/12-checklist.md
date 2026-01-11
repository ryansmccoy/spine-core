# 12: Reviewer Verification Checklist

> **Purpose**: A checklist for reviewers to verify the implementation is complete and "real" (not a toy example).

---

## Pre-Implementation Checklist

Before implementation begins, verify:

- [ ] All fixture files exist in `data/fixtures/otc/`
- [ ] Migration file `021_otc_multiweek_real_example.sql` is present
- [ ] All pipeline files exist in `domains/otc/pipelines/`
- [ ] Test files exist in `tests/domains/otc/`

---

## Database Schema Checklist

After `spine db init`, verify these tables exist:

### Core OTC Tables
- [ ] `otc_raw` - Raw ingested records
- [ ] `otc_venue_volume` - Normalized venue volume
- [ ] `otc_symbol_summary` - Per-symbol weekly aggregates
- [ ] `otc_venue_share` - Per-venue market shares
- [ ] `otc_symbol_rolling_6w` - 6-week rolling metrics
- [ ] `otc_research_snapshot` - Denormalized research view

### Support Tables
- [ ] `otc_week_manifest` - Week processing status
- [ ] `otc_normalization_map` - Raw → normalized mapping
- [ ] `otc_rejects` - Rejected records
- [ ] `otc_quality_checks` - Quality check results

### Verify Key Columns Exist

```sql
-- Check manifest has all columns
PRAGMA table_info(otc_week_manifest);
-- Should include: week_ending, tier, stage, row_count_raw, row_count_parsed,
-- row_count_inserted, row_count_normalized, row_count_rejected,
-- source_sha256, execution_id, batch_id

-- Check rolling has completeness flags
PRAGMA table_info(otc_symbol_rolling_6w);
-- Should include: weeks_in_window, is_complete_window

-- Check lineage columns on data tables
PRAGMA table_info(otc_raw);
-- Should include: execution_id, batch_id, record_hash
```

---

## Pipeline Registration Checklist

All pipelines should be registered and runnable:

```powershell
# Verify pipeline registration (if spine list works)
spine list pipelines | Select-String "otc"
```

Expected pipelines:
- [ ] `otc.ingest_week`
- [ ] `otc.normalize_week`
- [ ] `otc.aggregate_week`
- [ ] `otc.compute_rolling_6w`
- [ ] `otc.research_snapshot_week`
- [ ] `otc.backfill_range`

---

## Full Workflow Verification

### Step 1: Clean Start

```powershell
Remove-Item spine.db -ErrorAction SilentlyContinue
spine db init
```
- [ ] Database created successfully
- [ ] All migrations applied

### Step 2: Run Backfill

```powershell
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc
```

- [ ] Pipeline completes with `COMPLETED` status
- [ ] `weeks_processed: 6`
- [ ] `rolling_computed: true`
- [ ] `snapshot_built: true`
- [ ] No errors in output

### Step 3: Verify Manifest

```sql
SELECT week_ending, stage, row_count_inserted, row_count_normalized
FROM otc_week_manifest WHERE tier = 'NMS_TIER_1' ORDER BY week_ending;
```

- [ ] All 6 weeks present
- [ ] Stages are at least `AGGREGATED`
- [ ] Latest week is `SNAPSHOT`
- [ ] `row_count_inserted > 0` for all weeks

### Step 4: Verify Rejects

```sql
SELECT COUNT(*) FROM otc_rejects WHERE tier = 'NMS_TIER_1';
```

- [ ] Count = 2 (one INVALID_SYMBOL, one NEGATIVE_VOLUME)

```sql
SELECT reason_code, reason_detail FROM otc_rejects;
```

- [ ] `INVALID_SYMBOL` with detail mentioning `BAD$YM`
- [ ] `NEGATIVE_VOLUME` with detail mentioning `-50000`

### Step 5: Verify Rolling Completeness

```sql
SELECT symbol, weeks_in_window, is_complete_window
FROM otc_symbol_rolling_6w
WHERE week_ending = (SELECT MAX(week_ending) FROM otc_symbol_rolling_6w);
```

- [ ] All 5 symbols present (AAPL, TSLA, NVDA, MSFT, META)
- [ ] All have `weeks_in_window = 6`
- [ ] All have `is_complete_window = 1`

### Step 6: Verify Snapshot

```sql
SELECT symbol, total_volume, has_rolling_data, quality_status
FROM otc_research_snapshot
WHERE week_ending = (SELECT MAX(week_ending) FROM otc_research_snapshot);
```

- [ ] All 5 symbols present
- [ ] `total_volume > 0` for all
- [ ] `has_rolling_data = 1` for all
- [ ] `quality_status = 'PASS'` for all

### Step 7: Verify Quality Checks

```sql
SELECT check_name, status, COUNT(*) 
FROM otc_quality_checks 
WHERE tier = 'NMS_TIER_1'
GROUP BY check_name, status;
```

- [ ] All checks have `status = 'PASS'` or `status = 'WARN'`
- [ ] No `status = 'FAIL'`

### Step 8: Verify Lineage

```sql
SELECT COUNT(DISTINCT batch_id) FROM otc_raw WHERE batch_id IS NOT NULL;
```

- [ ] Returns 1 (single backfill batch)

```sql
SELECT COUNT(*) FROM otc_raw WHERE execution_id IS NOT NULL;
```

- [ ] Returns total raw records (all have execution_id)

---

## Idempotency Verification

### Test 1: Re-run backfill without force

```powershell
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc
```

- [ ] Pipeline completes quickly (skips existing)
- [ ] No duplicate records created

```sql
SELECT COUNT(*) FROM otc_raw WHERE tier = 'NMS_TIER_1';
```

- [ ] Same count as before re-run

### Test 2: Force re-process

```powershell
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc `
  -p force=true
```

- [ ] Pipeline processes all weeks
- [ ] No duplicate records

---

## Test Suite Verification

```powershell
pytest tests/domains/otc/ -v
```

- [ ] All unit tests pass
- [ ] All golden tests pass
- [ ] No failures or errors

### Key Golden Test Assertions

These specific assertions must pass:

1. **Manifest All Weeks Present**
   - [ ] `test_manifest_all_weeks_present` passes

2. **Rejects Contain Expected**
   - [ ] `test_rejects_invalid_symbol` passes
   - [ ] `test_rejects_negative_volume` passes

3. **Rolling Complete Windows**
   - [ ] `test_rolling_complete_windows` passes (all symbols have 6 weeks)

4. **Snapshot Totals Correct**
   - [ ] `test_snapshot_aapl_totals` passes (verifies exact volume calculation)

5. **Quality Checks Pass**
   - [ ] `test_quality_checks_pass` passes (no FAIL status)

6. **Batch Lineage**
   - [ ] `test_batch_id_consistent` passes

---

## Documentation Verification

- [ ] [00-overview.md](00-overview.md) explains the file structure
- [ ] [01-schema-migration.md](01-schema-migration.md) has complete DDL
- [ ] Each pipeline has its own documentation with:
  - [ ] Parameter schema
  - [ ] Idempotency level
  - [ ] CLI usage examples
- [ ] [09-fixtures.md](09-fixtures.md) documents expected values
- [ ] [10-golden-tests.md](10-golden-tests.md) shows specific assertions

---

## "Real" Example Criteria

This implementation is "real" (not a toy) if it meets ALL of these:

### Business Logic ✅
- [ ] Processes 6 weeks of data (not just one)
- [ ] Handles rolling windows with completeness tracking
- [ ] Computes market shares correctly (sum to ~100%)
- [ ] Calculates trends based on volume changes

### Data Quality ✅
- [ ] Validates week_ending is a Friday
- [ ] Validates symbol format (rejects `BAD$YM`)
- [ ] Validates volume is non-negative (rejects `-50000`)
- [ ] Records all rejects with reason codes
- [ ] Runs quality checks and records results

### Lineage ✅
- [ ] Every record has `execution_id`
- [ ] Related work shares `batch_id`
- [ ] Can trace from snapshot back to raw

### Idempotency ✅
- [ ] Re-running same backfill doesn't duplicate data
- [ ] Force flag allows reprocessing
- [ ] Each pipeline documents its idempotency level

### Testing ✅
- [ ] Unit tests for validators
- [ ] Golden tests for full workflow
- [ ] Tests verify exact expected values

---

## Final Sign-Off

| Criterion | Verified By | Date |
|-----------|-------------|------|
| Schema complete | | |
| Pipelines registered | | |
| Full backfill runs | | |
| Rejects correct | | |
| Rolling complete | | |
| Snapshot correct | | |
| Quality checks pass | | |
| Idempotency verified | | |
| All tests pass | | |
| Documentation complete | | |

**Implementation Status**: ☐ Ready for Use

---

## Summary

This checklist ensures the OTC multi-week example is:

1. **Complete**: All tables, pipelines, tests, and fixtures exist
2. **Correct**: Calculations produce expected results
3. **Institutional**: Handles rejects, quality, lineage, idempotency
4. **Documented**: Clear explanations for every component
5. **Testable**: Golden tests verify exact expected behavior

When all checkboxes are marked, the implementation demonstrates Market Spine's core value proposition: **temporal data processing with full lineage and quality guarantees**.
