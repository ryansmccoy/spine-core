# SQL Patterns Reference

Common SQL patterns for Market Spine.

---

## Latest-Per-Partition (As-Of Query)

```sql
-- Get latest row for each partition (week/tier/symbol)
SELECT * FROM (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY week_ending, tier, symbol 
               ORDER BY captured_at DESC
           ) as rn
    FROM my_table
) WHERE rn = 1
```

**Why not MAX()?**
```sql
-- ❌ WRONG: Non-deterministic with ties
SELECT * FROM t WHERE captured_at = (SELECT MAX(captured_at) FROM t)

-- ✅ CORRECT: ROW_NUMBER breaks ties deterministically
```

---

## Scoped Anomaly Filtering

```sql
-- Only hide data for partitions with errors
SELECT d.* FROM data_table d
WHERE NOT EXISTS (
    SELECT 1 FROM core_anomalies a
    WHERE a.domain = 'my.domain'
      AND a.stage = 'MY_STAGE'
      AND a.partition_key = d.week_ending || '|' || d.tier
      AND a.severity IN ('ERROR', 'CRITICAL')
      AND a.resolved_at IS NULL
)
```

---

## Consecutive Weeks Check

```sql
-- Find symbols with all required weeks
SELECT symbol
FROM data_table
WHERE week_ending IN ('2025-12-26','2025-12-19','2025-12-12',
                      '2025-12-05','2025-11-28','2025-11-21')
  AND tier = ?
GROUP BY symbol
HAVING COUNT(DISTINCT week_ending) = 6
```

---

## Idempotent Upsert

```sql
-- SQLite upsert pattern
INSERT INTO output_table (capture_id, symbol, value, captured_at)
VALUES (?, ?, ?, ?)
ON CONFLICT (capture_id, symbol) 
DO UPDATE SET 
    value = excluded.value,
    captured_at = excluded.captured_at
```

---

## Provenance Tracking

```sql
-- Track input captures for rolled-up data
SELECT 
    symbol,
    AVG(volume) as avg_volume,
    MIN(capture_id) as input_min_capture_id,
    MAX(capture_id) as input_max_capture_id,
    MIN(captured_at) as input_min_captured_at,
    MAX(captured_at) as input_max_captured_at
FROM input_table
WHERE week_ending IN (...)
GROUP BY symbol
```
