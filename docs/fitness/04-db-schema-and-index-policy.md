# 04 — Database Schema and Index Policy

> **Constraints, indexes, replay correctness, and scale testing**

---

## 1. Uniqueness Constraints

### Design Principle

Every output table includes `capture_id` in its unique constraint. This enables:
1. **Point-in-time snapshots**: Multiple captures of same business keys
2. **Replay safety**: Re-running same capture replaces (DELETE + INSERT)
3. **Temporal queries**: "Latest" vs "as of" selection

### Constraint Pattern

```sql
-- Pattern: UNIQUE(business_keys..., capture_id, calc_version)
UNIQUE(week_ending, tier, symbol, capture_id)           -- symbol_summary
UNIQUE(week_ending, tier, mpid, capture_id, calc_version)  -- venue_concentration
```

### Current Table Constraints

| Table | Unique Constraint |
|-------|-------------------|
| `_raw` | `(week_ending, tier, symbol, mpid, capture_id)` |
| `_venue_volume` | `(week_ending, tier, symbol, mpid, capture_id)` |
| `_symbol_summary` | `(week_ending, tier, symbol, capture_id)` |
| `_venue_share` | `(week_ending, tier, mpid, capture_id)` |
| `_symbol_rolling_6w` | `(week_ending, tier, symbol, capture_id)` |
| `_liquidity_score` | `(week_ending, tier, symbol, capture_id)` |
| `_research_snapshot` | `(week_ending, tier, symbol, capture_id)` |

### Reconciled Identity Rule

**Policy**: All domain tables use `capture_id` in unique constraints. `captured_at` is for ordering only.

- `capture_id`: Deterministic identifier for replay (part of uniqueness)
- `captured_at`: Timestamp for _latest view ordering (NOT in uniqueness)

### Constraint Stress Tests

```python
def test_duplicate_insert_fails():
    """Same business key + capture should fail on second insert."""
    insert_row(week="2025-12-26", tier="OTC", symbol="AAPL", capture_id="cap-001")
    with pytest.raises(IntegrityError):
        insert_row(week="2025-12-26", tier="OTC", symbol="AAPL", capture_id="cap-001")

def test_different_capture_succeeds():
    """Same business key with different capture should succeed."""
    insert_row(week="2025-12-26", tier="OTC", symbol="AAPL", capture_id="cap-001")
    insert_row(week="2025-12-26", tier="OTC", symbol="AAPL", capture_id="cap-002")  # OK

def test_different_version_succeeds():
    """Same capture with different calc version should succeed."""
    insert_row(week="2025-12-26", tier="OTC", mpid="ETRD", capture_id="cap-001", calc_version="v1")
    insert_row(week="2025-12-26", tier="OTC", mpid="ETRD", capture_id="cap-001", calc_version="v2")  # OK
```

---

## 2. Index Policy

### Index Categories

1. **Primary Query Indexes**: Support common read patterns
2. **Capture Indexes**: Enable efficient DELETE before INSERT
3. **Administrative Indexes**: Support monitoring/cleanup queries

### Index Patterns

```sql
-- Primary query: Get latest data for a week/tier
CREATE INDEX idx_{table}_primary ON {table}(week_ending, tier);

-- Capture operations: DELETE WHERE capture_id = ?
CREATE INDEX idx_{table}_capture ON {table}(capture_id);

-- Latest selection: Window function partitioning
CREATE INDEX idx_{table}_latest ON {table}(week_ending, tier, symbol, captured_at DESC);

-- Admin: Find old data for cleanup
CREATE INDEX idx_{table}_cleanup ON {table}(captured_at);
```

### Current Indexes

| Table | Indexes |
|-------|---------|
| `_raw` | `idx_raw_week`, `idx_raw_symbol` |
| `_venue_volume` | `idx_venue_volume_capture` |
| `_symbol_summary` | `idx_symbol_summary_capture`, ❌ missing: `idx_symbol_summary_symbol` |
| `_symbol_rolling_6w` | `idx_rolling_capture` |
| `_venue_concentration` | `idx_venue_concentration_capture`, `idx_venue_concentration_rank` |

### Gap: Add Missing Indexes

```sql
-- Symbol lookup for research queries
CREATE INDEX IF NOT EXISTS idx_symbol_summary_symbol 
    ON finra_otc_transparency_symbol_summary(symbol);

-- Tier filtering for venue concentration
CREATE INDEX IF NOT EXISTS idx_venue_concentration_tier
    ON finra_otc_transparency_venue_concentration(tier, week_ending);
```

### Index Stress Tests

```python
def test_query_uses_index():
    """Verify EXPLAIN QUERY PLAN shows index usage."""
    plan = db.execute("EXPLAIN QUERY PLAN SELECT * FROM _symbol_summary WHERE week_ending = ?").fetchall()
    assert "idx_symbol_summary_capture" in str(plan) or "USING INDEX" in str(plan)

def test_capture_delete_uses_index():
    """DELETE by capture_id should use index."""
    plan = db.execute("EXPLAIN QUERY PLAN DELETE FROM _symbol_summary WHERE capture_id = ?").fetchall()
    assert "idx_" in str(plan) or "USING INDEX" in str(plan)
```

---

## 3. Replay Correctness

### Idempotency Model

```
replay(capture_id) = DELETE existing rows + INSERT new rows
```

### Implementation

```python
def write_with_idempotency(table: str, rows: list[dict], capture_id: str):
    """Idempotent write: delete existing, insert new."""
    with db.transaction():
        db.execute(f"DELETE FROM {table} WHERE capture_id = ?", [capture_id])
        db.executemany(f"INSERT INTO {table} (...) VALUES (...)", rows)
```

### Replay Stress Tests

```python
def test_replay_same_capture_is_idempotent():
    """Re-running same capture produces identical output."""
    # First run
    run_pipeline("compute_venue_concentration", week="2025-12-26", capture_id="cap-001")
    rows_1 = query("SELECT * FROM _venue_concentration WHERE capture_id = ?", ["cap-001"])
    
    # Second run (replay)
    run_pipeline("compute_venue_concentration", week="2025-12-26", capture_id="cap-001")
    rows_2 = query("SELECT * FROM _venue_concentration WHERE capture_id = ?", ["cap-001"])
    
    # Same count, same content
    assert len(rows_1) == len(rows_2)
    assert rows_1 == rows_2

def test_new_capture_creates_separate_rows():
    """New capture creates additional rows, not replacement."""
    run_pipeline("compute_venue_concentration", week="2025-12-26", capture_id="cap-001")
    count_1 = query("SELECT COUNT(*) FROM _venue_concentration")[0][0]
    
    run_pipeline("compute_venue_concentration", week="2025-12-26", capture_id="cap-002")
    count_2 = query("SELECT COUNT(*) FROM _venue_concentration")[0][0]
    
    # Should have rows from both captures
    assert count_2 == count_1 * 2

def test_latest_view_returns_newest_capture():
    """_latest view returns most recent capture only."""
    run_pipeline("compute_venue_concentration", week="2025-12-26", capture_id="cap-001")
    run_pipeline("compute_venue_concentration", week="2025-12-26", capture_id="cap-002")
    
    latest = query("SELECT DISTINCT capture_id FROM _venue_concentration_latest")
    assert latest == [("cap-002",)]
```

---

## 4. Backfill Correctness

### Backfill vs Forward-Fill

| Mode | Use Case | Behavior |
|------|----------|----------|
| Forward | Daily production | Ingest new week, compute, append |
| Backfill | Historical gap | Ingest range, compute each, append |
| Re-backfill | Fix/update | DELETE existing captures, re-ingest, re-compute |

### Backfill Pipeline

```python
class BackfillRangePipeline(Pipeline):
    def run(self):
        start_week = self.params["start_week"]
        end_week = self.params["end_week"]
        force = self.params.get("force", False)
        
        for week in week_range(start_week, end_week):
            capture_id = f"backfill-{week}"
            
            if not force and manifest_has(capture_id):
                log.info("skip.exists", capture_id=capture_id)
                continue
            
            # DELETE existing (replay safety)
            delete_capture(capture_id)
            
            # Ingest + compute
            run_pipeline("ingest_week", week=week, capture_id=capture_id)
            run_pipeline("aggregate_week", week=week, capture_id=capture_id)
```

### Backfill Stress Tests

```python
def test_backfill_fills_gaps():
    """Backfill correctly fills missing weeks."""
    # Ingest weeks 1, 2, skip 3, ingest 4
    run_pipeline("ingest_week", week="2025-01-03")
    run_pipeline("ingest_week", week="2025-01-10")
    run_pipeline("ingest_week", week="2025-01-24")
    
    # Backfill should fill week 3
    run_pipeline("backfill_range", start="2025-01-01", end="2025-01-31")
    
    weeks = query("SELECT DISTINCT week_ending FROM _symbol_summary ORDER BY week_ending")
    assert "2025-01-17" in [w[0] for w in weeks]

def test_backfill_force_replaces():
    """force=True replaces existing captures."""
    run_pipeline("ingest_week", week="2025-01-03", capture_id="prod-001")
    original = query("SELECT captured_at FROM _symbol_summary LIMIT 1")[0][0]
    
    time.sleep(0.1)
    run_pipeline("backfill_range", start="2025-01-01", end="2025-01-07", force=True)
    
    updated = query("SELECT captured_at FROM _symbol_summary LIMIT 1")[0][0]
    assert updated > original

def test_backfill_without_force_skips():
    """Without force, existing captures are skipped."""
    run_pipeline("ingest_week", week="2025-01-03", capture_id="prod-001")
    original = query("SELECT captured_at FROM _symbol_summary LIMIT 1")[0][0]
    
    run_pipeline("backfill_range", start="2025-01-01", end="2025-01-07", force=False)
    
    after = query("SELECT captured_at FROM _symbol_summary LIMIT 1")[0][0]
    assert after == original  # Not replaced
```

---

## 5. Scale Stress Testing

### Volume Targets

| Table | Expected Rows/Week | 52-Week Estimate |
|-------|-------------------|------------------|
| `_raw` | 50,000 | 2.6M |
| `_venue_volume` | 50,000 | 2.6M |
| `_symbol_summary` | 10,000 | 520K |
| `_venue_concentration` | 50 | 2,600 |
| `_symbol_rolling_6w` | 10,000 | 520K |

### Performance Benchmarks

```python
SCALE_THRESHOLDS = {
    "ingest_50k_rows": 30.0,      # seconds
    "aggregate_10k_symbols": 5.0, # seconds
    "query_latest_view": 0.5,     # seconds
    "delete_by_capture": 1.0,     # seconds
}

def test_ingest_scale():
    """Ingest 50K rows within threshold."""
    rows = generate_mock_rows(50_000)
    start = time.perf_counter()
    write_rows("_raw", rows)
    elapsed = time.perf_counter() - start
    assert elapsed < SCALE_THRESHOLDS["ingest_50k_rows"]

def test_query_latest_scale():
    """Query latest view responds within threshold."""
    # Setup: 52 weeks of data
    for week in last_52_weeks():
        run_pipeline("aggregate_week", week=week)
    
    start = time.perf_counter()
    results = query("SELECT * FROM _symbol_summary_latest WHERE tier = 'OTC'")
    elapsed = time.perf_counter() - start
    
    assert elapsed < SCALE_THRESHOLDS["query_latest_view"]
    assert len(results) > 0
```

### Memory Stress Tests

```python
def test_streaming_ingest():
    """Large ingests don't load all rows into memory."""
    import tracemalloc
    tracemalloc.start()
    
    run_pipeline("ingest_week", week="2025-12-26")
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Peak memory should be < 500MB for 50K rows
    assert peak < 500 * 1024 * 1024

def test_streaming_aggregation():
    """Aggregation uses bounded memory."""
    import tracemalloc
    tracemalloc.start()
    
    run_pipeline("aggregate_week", week="2025-12-26")
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    assert peak < 200 * 1024 * 1024
```

---

## 6. Data Quality Gates

### Pre-Insert Checks

```python
def validate_before_insert(table: str, rows: list[dict]) -> list[str]:
    """Validate rows before inserting."""
    errors = []
    
    # Non-empty
    if not rows:
        errors.append("No rows to insert")
    
    # Required fields
    for i, row in enumerate(rows):
        if not row.get("week_ending"):
            errors.append(f"Row {i}: missing week_ending")
        if not row.get("capture_id"):
            errors.append(f"Row {i}: missing capture_id")
    
    # Invariant checks by table
    if table == "_venue_concentration":
        errors.extend(validate_concentration_invariants(rows))
    
    return errors

def validate_concentration_invariants(rows: list[dict]) -> list[str]:
    """Venue concentration must sum to 1.0 per (week, tier)."""
    errors = []
    by_group = defaultdict(list)
    for r in rows:
        by_group[(r["week_ending"], r["tier"])].append(r)
    
    for (week, tier), group in by_group.items():
        total = sum(float(r["market_share_pct"]) for r in group)
        if abs(total - 1.0) > 0.001:
            errors.append(f"Share invariant failed: {week}/{tier} sums to {total}")
    
    return errors
```

### Post-Insert Checks

```sql
-- Quality check: shares sum to 1.0
SELECT week_ending, tier, SUM(CAST(market_share_pct AS REAL)) as total
FROM finra_otc_transparency_venue_concentration
WHERE capture_id = ?
GROUP BY week_ending, tier
HAVING ABS(total - 1.0) > 0.001;

-- Quality check: no duplicate ranks
SELECT week_ending, tier, rank, COUNT(*) as cnt
FROM finra_otc_transparency_venue_concentration
WHERE capture_id = ?
GROUP BY week_ending, tier, rank
HAVING cnt > 1;
```

---

## 7. Schema Migration Checklist

### Adding a New Table

- [ ] DDL in `migrations/schema.sql`
- [ ] Add to `TABLES` dict in `schema.py`
- [ ] Create `_latest` view if temporal
- [ ] Add indexes for primary queries
- [ ] Add capture_id index for replay
- [ ] Add to core_manifest stages
- [ ] Document in `01-current-state-map.md`

### Adding a New Column

- [ ] ALTER TABLE migration
- [ ] Update INSERT statements in pipelines
- [ ] Update SELECT * queries if explicit columns
- [ ] Update dataclass if applicable
- [ ] Update _latest view if column affects ordering

### Adding a New Index

- [ ] CREATE INDEX IF NOT EXISTS (idempotent)
- [ ] Test query plan uses index
- [ ] Document in this file
