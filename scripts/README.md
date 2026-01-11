# Scripts Directory

Operational scripts for scheduled data ingestion and maintenance.

## Architecture

Scripts in this directory are **thin wrappers** that delegate to domain-specific scheduler modules:

```
scripts/                                    # Thin CLI wrappers
├── schedule_finra.py                       # → spine.domains.finra.otc_transparency.scheduler
├── schedule_prices.py                      # → spine.domains.market_data.scheduler
├── smoke_prices.py                         # API smoke test
└── build_schema.py                         # Schema compilation

packages/spine-domains/src/spine/domains/   # Business logic lives here
├── finra/otc_transparency/scheduler.py     # FINRA scheduling logic
└── market_data/scheduler.py                # Price scheduling logic
```

This separation ensures:
- **Testability**: Domain schedulers can be imported and tested in pytest
- **Reusability**: Same logic works for CLI, cron, K8s, and API invocation
- **Portability**: Scripts just wire up paths and parse args

---

## Available Scripts

### `schedule_finra.py` - FINRA OTC Weekly Ingestion

Multi-week scheduler for FINRA OTC transparency data with revision detection.

```bash
# Standard weekly run (last 6 weeks, all tiers)
python scripts/schedule_finra.py --lookback-weeks 6

# Backfill specific weeks
python scripts/schedule_finra.py --weeks 2025-12-15,2025-12-22

# Dry-run (validate without database writes)
python scripts/schedule_finra.py --mode dry-run

# Force restatement (ignore revision detection)
python scripts/schedule_finra.py --force --lookback-weeks 4

# CI/CD mode (stop on first failure)
python scripts/schedule_finra.py --fail-fast

# Only run specific stage
python scripts/schedule_finra.py --only-stage ingest
python scripts/schedule_finra.py --only-stage normalize
python scripts/schedule_finra.py --only-stage calc

# JSON output for pipeline parsing
python scripts/schedule_finra.py --json
```

**Exit Codes:**
| Code | Meaning |
|------|---------|
| 0 | All partitions processed successfully |
| 1 | Partial failure (some partitions failed) |
| 2 | All partitions failed or critical error |

---

### `schedule_prices.py` - Price Data Ingestion

Batch price ingestion with rate limiting for Alpha Vantage API.

```bash
# Standard run with symbols
python scripts/schedule_prices.py --symbols AAPL,MSFT,GOOGL

# Load symbols from file
python scripts/schedule_prices.py --symbols-file symbols.txt

# Dry-run (validate without database writes)
python scripts/schedule_prices.py --symbols AAPL --mode dry-run

# Full history (20 years vs 100 days)
python scripts/schedule_prices.py --symbols AAPL --outputsize full

# Custom rate limiting
python scripts/schedule_prices.py --symbols AAPL,MSFT --sleep 15.0

# CI/CD mode (stop on first failure)
python scripts/schedule_prices.py --symbols AAPL,MSFT --fail-fast
```

**Exit Codes:**
| Code | Meaning |
|------|---------|
| 0 | All symbols processed successfully |
| 1 | Partial failure (some symbols failed) |
| 2 | All symbols failed or critical error |
| 3 | Configuration error |

---

### `smoke_prices.py` - Price API Smoke Test

Quick validation that price ingestion works end-to-end.

```bash
python scripts/smoke_prices.py
```

---

### `build_schema.py` - Schema Compilation

Combines SQL modules from spine-core and spine-domains into a single schema file.

```bash
python scripts/build_schema.py
```

---

## Execution Environments

### Local Development

```bash
# Ensure virtual environment is activated
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Run with defaults
python scripts/schedule_finra.py --mode dry-run
```

### Cron (Linux/macOS)

```cron
# Weekly FINRA update: Sundays at 6 AM
0 6 * * 0 cd /path/to/spine-core && /path/to/.venv/bin/python scripts/schedule_finra.py --lookback-weeks 6 >> /var/log/finra-schedule.log 2>&1

# Daily price update: Weekdays at 6 PM (after market close)
0 18 * * 1-5 cd /path/to/spine-core && /path/to/.venv/bin/python scripts/schedule_prices.py --symbols-file data/watchlist.txt >> /var/log/price-schedule.log 2>&1
```

### Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: finra-weekly-schedule
spec:
  schedule: "0 6 * * 0"  # Sundays at 6 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: scheduler
            image: market-spine:latest
            command:
            - python
            - scripts/schedule_finra.py
            - --lookback-weeks=6
            - --fail-fast
            env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: spine-secrets
                  key: database-url
          restartPolicy: OnFailure
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
```

### OpenShift CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: price-daily-schedule
spec:
  schedule: "0 18 * * 1-5"  # Weekdays at 6 PM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: scheduler
            image: image-registry.openshift-image-registry.svc:5000/market-spine/scheduler:latest
            command:
            - python
            - scripts/schedule_prices.py
            - --symbols-file=/config/watchlist.txt
            - --fail-fast
            volumeMounts:
            - name: config
              mountPath: /config
            - name: secrets
              mountPath: /secrets
            env:
            - name: ALPHA_VANTAGE_API_KEY
              valueFrom:
                secretKeyRef:
                  name: alpha-vantage
                  key: api-key
          volumes:
          - name: config
            configMap:
              name: scheduler-config
          - name: secrets
            secret:
              secretName: spine-secrets
          restartPolicy: OnFailure
```

### Docker Compose

```yaml
services:
  finra-scheduler:
    image: market-spine:latest
    command: python scripts/schedule_finra.py --lookback-weeks 6 --fail-fast
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/spine
    volumes:
      - ./data:/app/data
    depends_on:
      - db
```

---

## CI/CD Integration

### GitHub Actions

```yaml
- name: Run FINRA ingestion
  run: |
    python scripts/schedule_finra.py --lookback-weeks 2 --fail-fast --mode dry-run
  continue-on-error: false
```

### Azure DevOps

```yaml
- script: |
    python scripts/schedule_finra.py --lookback-weeks 2 --fail-fast
  displayName: 'Run FINRA Schedule'
  failOnStderr: true
```

---

## Monitoring & Alerting

### Check for failures

```sql
-- Recent anomalies by severity
SELECT 
    severity,
    category,
    COUNT(*) as count
FROM core_anomalies
WHERE detected_at > datetime('now', '-1 day')
  AND resolved_at IS NULL
GROUP BY severity, category
ORDER BY 
    CASE severity 
        WHEN 'CRITICAL' THEN 1 
        WHEN 'ERROR' THEN 2 
        WHEN 'WARN' THEN 3 
        ELSE 4 
    END;
```

### Check data readiness

```sql
SELECT 
    domain,
    json_extract(partition_key, '$.week_ending') as week,
    is_ready,
    blocking_issues,
    updated_at
FROM core_data_readiness
ORDER BY updated_at DESC
LIMIT 10;
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ImportError: No module named 'spine'` | Package not in path | Run from project root or install packages |
| Exit code 1 (partial failure) | Some partitions failed | Check `core_anomalies` for details |
| Exit code 2 (all failed) | Critical error | Check DB connection, API keys |
| `File not found` for fixtures | Wrong working directory | Run from project root |
| Rate limit exceeded | Too many API calls | Increase `--sleep` value |

### Debug Mode

```bash
# Verbose output
python scripts/schedule_finra.py -v --mode dry-run

# JSON output for debugging
python scripts/schedule_finra.py --json 2>/dev/null | jq .
```

---

## Adding New Schedulers

1. Create domain scheduler module:
   ```
   packages/spine-domains/src/spine/domains/{domain}/scheduler.py
   ```

2. Implement `run_{domain}_schedule()` function with:
   - Config dataclass
   - Result dataclass with `has_failures` property
   - Support for `--mode dry-run` and `--fail-fast`

3. Create thin wrapper script:
   ```
   scripts/schedule_{domain}.py
   ```

4. Add to this README with usage examples.

5. Add pytest tests in:
   ```
   tests/{domain}/test_scheduler.py
   ```
