# Basic Release Checklist

Market Spine Basic graduation checklist and smoke test guide.

## One-Command Smoke Test

### Windows PowerShell

```powershell
# Full golden path test (copy-paste as one block)
cd C:\projects\spine-core\market-spine-basic
Remove-Item -Path "spine.db" -ErrorAction SilentlyContinue
$env:SPINE_LOG_LEVEL="INFO"
.venv\Scripts\spine.exe db init
.venv\Scripts\spine.exe run otc.ingest_week -p file_path=../data/finra/finra_otc_weekly_tier1_20251222.csv
.venv\Scripts\spine.exe run otc.normalize_week -p week_ending=2025-12-19 -p tier=NMS_TIER_1
.venv\Scripts\python.exe -c "from market_spine.db import get_connection; c = get_connection(); print(f'Raw: {c.execute(chr(39)SELECT COUNT(*) FROM otc_raw chr(39)).fetchone()[0]}'); print(f'Normalized: {c.execute(chr(39)SELECT COUNT(*) FROM otc_venue_volume chr(39)).fetchone()[0]}')"
```

### Bash/Zsh

```bash
cd /path/to/market-spine-basic
rm -f spine.db
export SPINE_LOG_LEVEL=INFO
.venv/bin/spine db init
.venv/bin/spine run otc.ingest_week -p file_path=../data/finra/finra_otc_weekly_tier1_20251222.csv
.venv/bin/spine run otc.normalize_week -p week_ending=2025-12-19 -p tier=NMS_TIER_1
.venv/bin/python -c "from market_spine.db import get_connection; c = get_connection(); print(f'Raw: {c.execute(\"SELECT COUNT(*) FROM otc_raw\").fetchone()[0]}'); print(f'Normalized: {c.execute(\"SELECT COUNT(*) FROM otc_venue_volume\").fetchone()[0]}')"
```

## Expected Outcomes

| Step | Expected Result |
|------|-----------------|
| `spine db init` | "Database initialized successfully!" |
| `spine run otc.ingest_week` | "Pipeline completed successfully!" + rows ingested |
| `spine run otc.normalize_week` | "Pipeline completed successfully!" + rows normalized |
| Row counts | Raw: ~50,000, Normalized: ~50,000 |

### Key Log Events to Verify

```
ingest.dates_resolved   file_date=2025-12-22 week_ending=2025-12-19
ingest.tier_detected    tier=NMS_TIER_1 source=filename
ingest.parsed           rows=50889
ingest.bulk_insert.end  rows=50889
execution.summary       status=completed
```

## If It Fails

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| "No such file or directory" | Wrong file path | Use `../data/finra/` (parent directory) |
| "week_ending must be Friday" | Manual override with wrong date | Remove `-p week_ending=...` to auto-detect |
| "Tier not specified" | File has no tier in name | Add `-p tier=NMS_TIER_1` |
| DEBUG logs at INFO level | Old code | Ensure `_load_pipelines()` is lazy-loaded |
| UnicodeEncodeError | Windows terminal | Use PowerShell 7 or set `$env:PYTHONIOENCODING="utf-8"` |
| "Database locked" | Concurrent access | Close other connections |

## Definition of Done for Basic

### Core Functionality ✅
- [x] Clean slate workflow: `rm spine.db; spine db init` works
- [x] Golden path: ingest → normalize → aggregate runs end-to-end
- [x] 5 OTC pipelines load correctly
- [x] Date inference from FINRA files (file_date → week_ending)
- [x] Tier inference from filename

### Logging Contract ✅
- [x] SPINE_LOG_LEVEL respected (no DEBUG at INFO)
- [x] UTC ISO-8601 timestamps with Z suffix
- [x] Structured events with span_id/parent_span_id
- [x] Errors include actionable info (error_message, error_type, error_stack)

### Data Lineage ✅
- [x] Every row has execution_id
- [x] Every capture has capture_id
- [x] Three clocks tracked: week_ending, source_last_update_date, captured_at

### Documentation ✅
- [x] Quickstart works as written
- [x] Architecture docs match actual code
- [x] FINRA date semantics documented

### Tests ✅
- [x] 75 tests pass
- [x] Date derivation tests (21 new tests)
- [x] Registry guardrails
- [x] Domain purity tests

## Test Summary

```
75 passed in 0.36s

- 11 OTC domain tests (schema, connector, normalizer, calculations)
- 21 date derivation tests (week_ending inference)
- 5 registry integrity tests
- 3 domain purity tests
- 35 framework tests (dispatcher, runner, logging)
```

## Architecture Invariants (Must Hold)

1. **All execution goes through Dispatcher** - No direct pipeline instantiation
2. **Domains never import from `market_spine`** - Only from `spine.core`
3. **Business logic in `calculations.py`** - Pipelines are orchestrators
4. **Pipelines are idempotent** - Safe to re-run
5. **Every row has lineage** - execution_id, batch_id, capture_id
6. **Logging uses stable event schema** - No breaking changes
7. **UTC timestamps everywhere** - ISO-8601 with Z suffix
8. **Week-ending inference in pipeline** - CLI is thin wrapper

## Files Changed in Final Hardening

| File | Change |
|------|--------|
| `registry.py` | Lazy loading (_ensure_loaded) |
| `cli.py` | ASCII-safe output (no Unicode checkmarks) |
| `connector.py` | `get_file_metadata()`, date extraction |
| `pipelines.py` | Auto-detect week_ending/tier from file |
| `tests/domains/otc/test_otc.py` | 21 new date derivation tests |
| `docs/tutorial/01_quickstart.md` | Updated with date semantics |
