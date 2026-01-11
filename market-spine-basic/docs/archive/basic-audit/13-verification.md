# Verification Report

Generated: 2026-01-03

## Test Results

```
$ uv run pytest tests/ -q
98 passed, 3 skipped in 0.75s
```

All 98 tests pass. 3 skipped tests are domain purity checks that require optional spine-domains inspection.

---

## CLI Verification

### `spine --help`

```
Usage: spine [OPTIONS] COMMAND [ARGS]...

Market Spine - Analytics Pipeline System

Options:
  --version                     Show version and exit
  --log-level TEXT              Logging level [default: INFO]
  --log-format [pretty|json]    Log format [default: pretty]
  --log-to [stdout|stderr|file] Log destination [default: stdout]
  --quiet, -q                   Suppress logs, show only summary
  --help                        Show this message and exit.

Commands:
  pipelines   Discover and inspect pipelines
  run         Execute pipeline operations
  query       Query processed data
  verify      Verify database integrity
  db          Database management
  doctor      System health checks
```

✅ CLI entry point works

---

### `spine pipelines list`

```
                     Available Pipelines
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name                                   ┃ Description                            ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ finra.otc_transparency.aggregate_week  │ Compute FINRA OTC transparency aggr... │
│ finra.otc_transparency.backfill_range  │ Orchestrate multi-week FINRA OTC...    │
│ finra.otc_transparency.compute_rolling │ Compute rolling metrics for FINRA...   │
│ finra.otc_transparency.ingest_week     │ Ingest FINRA OTC transparency file...  │
│ finra.otc_transparency.normalize_week  │ Normalize raw FINRA OTC transparency...│
└────────────────────────────────────────┴────────────────────────────────────────┘

Found 5 pipeline(s)
```

✅ Pipeline list works, uses command layer

---

### Dry Run Execution

```
$ spine run run finra.otc_transparency.normalize_week --dry-run --tier tier1 --week-ending 2025-12-19

╭─────────────────────────────────────── Dry Run ───────────────────────────────────────╮
│ Pipeline: finra.otc_transparency.normalize_week                                       │
│                                                                                       │
│ Resolved Parameters:                                                                  │
│   • week_ending: 2025-12-19                                                           │
│   • tier: tier1                                                                       │
│                                                                                       │
│ Would execute with these parameters.                                                  │
│ (Use without --dry-run to actually run)                                               │
╰───────────────────────────────────────────────────────────────────────────────────────╯
```

✅ Dry run works, tier aliases accepted

---

### Command Layer Tier Normalization

```python
>>> from market_spine.app.commands.executions import RunPipelineCommand, RunPipelineRequest
>>> cmd = RunPipelineCommand()
>>> r = cmd.execute(RunPipelineRequest(
...     pipeline='finra.otc_transparency.normalize_week',
...     params={'tier': 'tier1', 'week_ending': '2025-12-19'},
...     dry_run=True
... ))
>>> r.would_execute
{'pipeline': 'finra.otc_transparency.normalize_week', 
 'params': {'tier': 'NMS_TIER_1', 'week_ending': '2025-12-19'}, 
 'lane': 'normal'}
```

✅ Command layer normalizes `tier1` → `NMS_TIER_1`

---

## API Test Results

All 25 API tests pass:

- Health endpoints: 3 tests
- Capabilities endpoint: 2 tests
- List pipelines: 4 tests
- Describe pipeline: 2 tests
- Run pipeline: 4 tests
- Data weeks: 4 tests
- Data symbols: 3 tests
- Error response contract: 3 tests

---

## Parity Tests

All 4 CLI/API parity tests pass:

- `test_dry_run_produces_same_shape`
- `test_error_produces_compatible_error_codes`
- `test_invalid_tier_error_parity`
- `test_reserved_fields_always_present_in_api`

---

## Summary of Changes

### Files Modified

| File | Change |
|------|--------|
| `cli/console.py` | Removed duplicate TIER_VALUES/TIER_ALIASES, added `get_tier_values()` |
| `cli/params.py` | Removed tier normalization (delegated to commands) |
| `cli/commands/verify.py` | Now uses TierNormalizer and DataSourceConfig |
| `cli/commands/doctor.py` | Now uses DataSourceConfig for table names |
| `cli/commands/run.py` | Uses string lane, get_tier_values() |
| `cli/commands/query.py` | Uses get_tier_values() |
| `cli/commands/list_.py` | Removed unused TIER_VALUES import |
| `cli/ui.py` | Refactored `create_pipeline_table()` to accept data, removed registry import |
| `api/routes/v1/pipelines.py` | Uses string lane mapping, removed Lane enum import |

### Architecture Improvements

1. **Single source of truth**: Tier values now flow from `spine.domains` → `TierNormalizer` → CLI/API
2. **No framework imports in CLI**: Removed `spine.framework.dispatcher.Lane` import
3. **No framework imports in API**: Removed `spine.framework.dispatcher.Lane` import
4. **No framework imports in UI**: Removed `spine.framework.registry` import
5. **Service delegation**: CLI commands use services for tier normalization and data source config

### Items Kept As-Is

- `cli/interactive/` module: Uses registry directly but shells out for execution (acceptable pattern)
- `DataSourceConfig`: Keeps its own table name constants (different schema than spine-domains)

---

## Conclusion

✅ **All tests pass** (98/98, 3 skipped)
✅ **CLI works correctly** with tier alias normalization
✅ **API works correctly** with consistent error responses
✅ **No breaking changes** to CLI/API behavior
✅ **Architecture improved** with proper layer separation

Basic tier is ready for freeze.
