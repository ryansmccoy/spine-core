# Capture Semantics Reference

---

## Capture ID Format

```
{domain}.{stage}.{partition_key}.{timestamp_utc}

Example:
finra.otc_transparency.ROLLING.2026-01-09|NMS_TIER_1.20260104T143022Z
```

---

## Required Columns

Every output table MUST have:

```sql
capture_id TEXT NOT NULL,      -- Unique per run
captured_at TEXT NOT NULL,     -- ISO timestamp
execution_id TEXT,             -- Groups related runs  
batch_id TEXT                  -- Groups batch operations
```

---

## Idempotency Pattern

```python
def write_output(conn, rows, capture_id):
    # DELETE existing, then INSERT new
    conn.execute(
        "DELETE FROM output WHERE capture_id = ?", 
        (capture_id,)
    )
    conn.executemany("INSERT INTO output ...", rows)
```

---

## Manifest Tracking

```python
conn.execute("""
    INSERT INTO core_manifest 
    (capture_id, domain, stage, partition_key, 
     captured_at, status, row_count)
    VALUES (?, ?, ?, ?, ?, 'complete', ?)
""", (capture_id, domain, stage, partition, now, len(rows)))
```

---

## Provenance (Rolled-Up Data)

```python
# Track which inputs contributed
output_row = {
    "avg_volume": avg,
    "input_min_capture_id": min(input_captures),
    "input_max_capture_id": max(input_captures),
}
```
