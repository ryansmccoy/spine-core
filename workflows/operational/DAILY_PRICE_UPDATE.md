# Daily Price Update Workflow

**Type:** Operational  
**Frequency:** Daily (weekdays after market close)  
**Duration:** ~10-30 minutes (depending on symbol count)  
**Owner:** Data Operations

---

## Trigger

Run this workflow every weekday after market close (typically 4:30 PM ET).

---

## Prerequisites

- [ ] Access to production database
- [ ] Alpha Vantage API key configured (`ALPHA_VANTAGE_API_KEY` env var)
- [ ] Python environment configured
- [ ] Symbol watchlist available

---

## Steps

### 1. Prepare Symbol List

**Create or update watchlist:**
```bash
# Check existing watchlist
cat data/watchlist.txt

# Add new symbols (one per line)
echo "NVDA" >> data/watchlist.txt
```

**Example watchlist.txt:**
```
# Core holdings
AAPL
MSFT
GOOGL
AMZN

# Tech sector
NVDA
AMD
INTC
```

### 2. Run Price Scheduler

**Standard run (from file):**
```bash
python scripts/schedule_prices.py \
  --symbols-file data/watchlist.txt \
  -v
```

**Quick run (specific symbols):**
```bash
python scripts/schedule_prices.py \
  --symbols AAPL,MSFT,GOOGL
```

**What it does:**
- Fetches daily price data for each symbol
- Applies rate limiting (12s between calls = 5 req/min)
- Stores with capture_id for versioning
- Records anomalies for failures

**Expected duration:** ~12 seconds per symbol

### 3. Monitor Execution

**Watch for:**
- ✓ Success messages with row counts
- ⚠ Warnings for empty data
- ✗ Errors for failed fetches

**Example output:**
```
2026-01-09T18:30:15Z [INFO] schedule_prices: [1/5] Processing AAPL...
2026-01-09T18:30:17Z [INFO] schedule_prices: ✓ AAPL: inserted 100 rows
2026-01-09T18:30:29Z [INFO] schedule_prices: [2/5] Processing MSFT...
```

### 4. Review Summary

**Check final summary:**
```
SUMMARY
======================================================================
Success: 5 symbols
Failed: 0 symbols
Skipped: 0 symbols
Total rows: 500
Duration: 61.2s
```

### 5. Verify Data Quality

**Query latest prices:**
```sql
SELECT 
    symbol,
    date,
    close,
    volume,
    captured_at
FROM market_data_prices_daily
WHERE date = (SELECT MAX(date) FROM market_data_prices_daily)
ORDER BY symbol;
```

### 6. Check for Anomalies

**Query unresolved issues:**
```sql
SELECT 
    severity,
    category,
    partition_key as symbol,
    message,
    detected_at
FROM core_anomalies
WHERE domain = 'market_data'
  AND resolved_at IS NULL
ORDER BY detected_at DESC
LIMIT 20;
```

---

## Success Criteria

- [ ] All symbols in watchlist processed (no failures)
- [ ] Price data available for current day
- [ ] No CRITICAL anomalies

---

## Common Issues

### Issue: "Rate limit exceeded"

**Cause:** Too many API calls too quickly  
**Fix:** 
```bash
# Increase delay between calls
python scripts/schedule_prices.py \
  --symbols-file data/watchlist.txt \
  --sleep 15.0
```

### Issue: "API key invalid or missing"

**Cause:** ALPHA_VANTAGE_API_KEY not set  
**Fix:**
```bash
export ALPHA_VANTAGE_API_KEY=your-api-key
# Or add to .env file
```

### Issue: "No data returned for symbol"

**Cause:** Invalid symbol or market closed  
**Fix:** Verify symbol is valid on Alpha Vantage

### Issue: "Partial failure"

**Cause:** Some symbols failed  
**Fix:** Check anomalies and retry failed symbols:
```bash
python scripts/schedule_prices.py \
  --symbols FAILED_SYMBOL1,FAILED_SYMBOL2
```

---

## Dry Run Mode

**Test without database writes:**
```bash
python scripts/schedule_prices.py \
  --symbols AAPL,MSFT \
  --mode dry-run \
  -v
```

---

## CI/CD Integration

**Stop on first failure (for pipelines):**
```bash
python scripts/schedule_prices.py \
  --symbols-file data/watchlist.txt \
  --fail-fast
```

**JSON output for parsing:**
```bash
python scripts/schedule_prices.py \
  --symbols AAPL \
  --json 2>/dev/null | jq '.success'
```

---

## Scheduled Execution

### Cron Example

```cron
# Weekdays at 4:30 PM ET (21:30 UTC)
30 21 * * 1-5 cd /path/to/spine-core && python scripts/schedule_prices.py --symbols-file data/watchlist.txt >> /var/log/price-schedule.log 2>&1
```

### Kubernetes CronJob

See [scripts/README.md](../../scripts/README.md#kubernetes-cronjob) for full example.

---

## References

- **Script:** `scripts/schedule_prices.py`
- **Domain Logic:** `packages/spine-domains/src/spine/domains/market_data/scheduler.py`
- **Scripts Guide:** `scripts/README.md`
- **Alpha Vantage Docs:** https://www.alphavantage.co/documentation/

---

## Monitoring Dashboard Queries

**Daily ingestion trend:**
```sql
SELECT 
    date,
    COUNT(DISTINCT symbol) as symbols_updated,
    COUNT(*) as total_rows,
    MAX(captured_at) as last_update
FROM market_data_prices_daily
WHERE date >= date('now', '-7 days')
GROUP BY date
ORDER BY date DESC;
```

**Symbol coverage:**
```sql
SELECT 
    symbol,
    COUNT(*) as data_points,
    MIN(date) as first_date,
    MAX(date) as last_date
FROM market_data_prices_daily
GROUP BY symbol
ORDER BY last_date DESC;
```
