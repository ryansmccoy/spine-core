# Quality Gates Reference

---

## Pattern: Validate Before Compute

```python
def run(self):
    # 1. Quality gate FIRST
    ok, issues = require_history_window(
        self.conn, table, week_ending, 
        window_weeks=6, tier=tier
    )
    
    if not ok:
        self.record_anomaly("ERROR", "QUALITY_GATE", 
            f"Failed: {issues}")
        return {"status": "skipped"}
    
    # 2. Proceed only if valid
    return self._compute()
```

---

## Consecutive Week Validation

```python
def require_history_window(conn, table, week_ending, 
                           window_weeks, tier):
    expected = generate_week_range(week_ending, window_weeks)
    found = query_available_weeks(conn, table, tier)
    
    missing = [w for w in expected if w not in found]
    
    if missing:
        return False, missing
    return True, []
```

---

## Partial Success

```python
# Get valid symbols only
valid = get_symbols_with_sufficient_history(
    conn, table, week_ending, window_weeks, tier
)

# Compute for valid, skip invalid
for symbol in all_symbols:
    if symbol in valid:
        results.append(compute(symbol))
    else:
        skipped.append(symbol)

# Record skipped as warning
if skipped:
    record_anomaly("WARN", "QUALITY_GATE", 
        f"Skipped {len(skipped)} symbols")
```

---

## Scoped Anomaly Filtering

```sql
-- Only filter matching partition
WHERE a.partition_key = d.week_ending || '|' || d.tier
```
