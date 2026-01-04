# OTC Operations

## Monitoring

### Key Metrics

| Metric | Query | Alert Threshold |
|--------|-------|-----------------|
| Ingest freshness | `MAX(now() - ingested_at)` | > 24h after expected |
| Validation failures | `rejected / total * 100` | > 5% |
| Missing venues | Expected - actual | > 0 major venues |
| Computation age | `MAX(now() - computed_at)` | > 1 day |
| Quality grade | Grade distribution | Any grade F |

### Weekly Quality Report

```sql
SELECT
    week_ending,
    venue_count,
    symbol_count,
    quality_grade,
    volume_change_pct,
    zero_volume_count
FROM otc.weekly_quality_metrics
WHERE week_ending >= CURRENT_DATE - INTERVAL '8 weeks'
ORDER BY week_ending DESC;
```

---

## Alerting

| Condition | Severity | Action |
|-----------|----------|--------|
| Ingest failed | P1 | Page on-call |
| Quality grade F | P1 | Page on-call |
| Quality grade D | P2 | Slack alert |
| Volume swing >50% | P3 | Log for review |
| Missing venue | P3 | Log for review |

---

## Lineage & Auditability

### Capture ID Tracking

Every row traces back to source:

```
raw_weekly.capture_id ──┐
                        │
venue_volume ───────────┼── capture_id
                        │
symbol_weekly_summary ──┼── execution_id
                        │
symbol_rolling_avg ─────┘
```

### Trace a metric to source

```sql
SELECT 
    s.symbol,
    s.week_ending,
    s.total_volume,
    s.execution_id,
    v.capture_id,
    r.ingested_at
FROM otc.symbol_weekly_summary s
JOIN otc.venue_volume v 
    ON s.symbol = v.symbol AND s.week_ending = v.week_ending
JOIN otc.raw_weekly r 
    ON v.raw_id = r.id
WHERE s.symbol = 'AAPL' AND s.week_ending = '2025-12-29'
LIMIT 1;
```

### Point-in-time query

```sql
-- What did we know on Jan 15, 2026?
SELECT * FROM otc.venue_volume
WHERE symbol = 'AAPL'
  AND week_ending = '2025-12-29'
  AND ingested_at <= '2026-01-15 10:00:00'::timestamptz
ORDER BY ingested_at DESC
LIMIT 1;
```

---

## Recovery Procedures

### Reprocess a week

```bash
spine pipeline trigger ingest_otc_weekly \
  --param week_ending=2025-12-29 \
  --param tier=T2 \
  --lane backfill
```

### Recompute summaries

```sql
-- Mark old summaries as superseded
UPDATE otc.symbol_weekly_summary
SET superseded_at = now()
WHERE week_ending = '2025-12-29';

-- Pipeline will recompute on next run
```

### Backfill missing weeks

```python
async def backfill_range(start: date, end: date, tier: str):
    current = start
    while current <= end:
        await dispatcher.submit(
            pipeline="ingest_otc_weekly",
            params={"week_ending": current.isoformat(), "tier": tier},
            lane="backfill"
        )
        current += timedelta(days=7)
```

### Fix bad data

```sql
BEGIN;

-- 1. Mark bad venue_volume as superseded
UPDATE otc.venue_volume
SET superseded_at = now()
WHERE week_ending = '2025-12-29' 
  AND mpid = 'BADV';

-- 2. Recompute affected summaries
DELETE FROM otc.symbol_weekly_summary 
WHERE week_ending = '2025-12-29';

DELETE FROM otc.venue_market_share
WHERE week_ending = '2025-12-29';

-- Pipeline will recompute
COMMIT;
```

---

## Scheduling Reference

| Job | Schedule | Trigger |
|-----|----------|---------|
| `ingest_t1` | Wed 6am | 2 weeks after week end |
| `ingest_t2` | Wed 6am | 4 weeks after week end |
| `normalize` | On ingest success | Downstream of ingest |
| `compute` | On normalize success | Downstream of normalize |
| `rolling_avg` | On compute success | Downstream of compute |
| `quality_check` | Daily 7am | Validate recent weeks |

---

## Runbook

### Ingest failure

1. Check FINRA website for outage announcements
2. Verify file is available for download
3. Check error logs for parsing issues
4. Retry with `--force` flag
5. If persistent, alert data team

### Quality grade F

1. Review `weekly_quality_metrics.warnings`
2. Check for FINRA corrections/republications
3. Compare to prior weeks for anomalies
4. If data issue, contact FINRA
5. If our issue, fix and reprocess

### Missing venue

1. Check if venue was acquired/renamed
2. Update MPID mapping if needed
3. Check FINRA announcements
4. Update expected venues list
