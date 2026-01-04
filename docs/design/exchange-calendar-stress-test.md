# Exchange Calendar Domain — Architecture Stress Test

> **Purpose**: Add a new domain with different ingestion cadence, source type, and calculations to validate modularity.

---

## Part 1 — Change Surface Map

### Domain Characteristics

| Aspect | FINRA OTC Transparency | Exchange Calendar |
|--------|------------------------|-------------------|
| **Ingestion cadence** | Weekly (every Monday) | Annual (updated yearly) |
| **Source type** | PSV files, API | Static JSON reference data |
| **Period granularity** | week_ending (Friday) | year (e.g., 2025) |
| **Core entity** | Trade volume records | Holiday/trading day records |
| **Calculations** | Rolling averages, venue share | Trading days between dates, next trading day |

### Files Touched Analysis

| Layer | File(s) Touched | Why | Action |
|-------|----------------|-----|--------|
| **spine-core** | (none) | Core primitives are domain-agnostic | ✅ No changes needed |
| **spine-domains** | `domains/reference/exchange_calendar/` (new folder) | New domain lives in domains package | ➕ Add new code |
| **app/commands** | (none) | Commands are pipeline-agnostic | ✅ No changes needed |
| **app/services** | (none) | Services route by pipeline name | ✅ No changes needed |
| **CLI** | (none) | CLI uses registry lookup | ✅ No changes needed |
| **API** | (none) | API uses registry lookup | ✅ No changes needed |
| **DB schema** | `migrations/schema.sql` | New tables for calendar data | ➕ Add DDL |
| **Registry loader** | `spine/framework/registry.py` | Need to import new domain | ➕ Add 4 lines |

### Key Architecture Questions

#### Were new pipeline parameters required?

**Yes, but domain-specific**:
- `year` — The calendar year to ingest (e.g., "2025")
- `exchange_code` — MIC code for exchange (e.g., "XNYS", "XNAS")

These are **domain-specific** and do not affect existing pipelines.

#### Did any existing pipeline spec need to change?

**No**. FINRA pipelines are completely untouched.

#### Did any registry require changes?

| Registry | Changed? | Details |
|----------|----------|---------|
| `PIPELINE_REGISTRY` | ➕ Yes (auto) | New pipelines auto-register via `@register_pipeline` |
| `SOURCE_REGISTRY` | ➕ Yes (opt-in) | New `JsonSource` registered in domain module |
| `PERIOD_REGISTRY` | ➕ Yes (opt-in) | New `AnnualPeriod` registered in domain module |
| `CALCS_REGISTRY` | N/A | Calcs don't use global registry (domain-contained) |

#### Were any abstractions missing or awkward?

1. **`SOURCE_REGISTRY` is FINRA-specific**: Currently lives in `finra.otc_transparency.sources`. Need to decide:
   - Option A: Keep source registries domain-local (current)
   - Option B: Promote `IngestionSource` + `PeriodStrategy` ABCs to spine-core
   
   **Decision**: Keep domain-local for now. Each domain can define its own source types.

2. **Period strategies assume date derivation**: `PeriodStrategy.derive_period_end(publish_date)` makes sense for weekly/monthly but less so for annual reference data where the "period" is just the year.
   
   **Decision**: Annual period still works — `derive_period_end(2025-01-15)` → `2025-12-31`.

3. **No awkwardness in pipeline registry**: The `@register_pipeline` pattern works perfectly for new domains.

### Summary Assessment

| Metric | Result |
|--------|--------|
| Existing code modified | 1 file (registry loader) — 4 lines |
| New code added | ~400 lines (new domain) |
| FINRA pipeline changes | 0 |
| Core primitive changes | 0 |
| CLI/API changes | 0 |

**Verdict**: Architecture is well-modular. Adding a domain requires:
1. New domain folder with sources/pipelines/schema/calculations
2. New DB tables in schema.sql
3. Import line in registry loader

---

## Part 2 — Implementation Plan

### Folder Structure

```
packages/spine-domains/src/spine/domains/reference/
├── __init__.py
└── exchange_calendar/
    ├── __init__.py
    ├── sources.py      # JsonSource, AnnualPeriod
    ├── pipelines.py    # ingest_year, compute_trading_days
    ├── calculations.py # trading_days_between, next_trading_day
    ├── schema.py       # DOMAIN, TABLES, Exchange enum
    └── data/           # Static JSON files (mock data)
        └── holidays_2025.json
```

### Pipelines

1. `reference.exchange_calendar.ingest_year` — Ingest holiday data for a year
2. `reference.exchange_calendar.compute_trading_days` — Calculate trading days for date ranges

### Calculations

1. `is_trading_day(date, exchange_code)` — Check if date is trading day
2. `trading_days_between(start, end, exchange_code)` — Count trading days
3. `next_trading_day(date, exchange_code)` — Find next trading day
4. `previous_trading_day(date, exchange_code)` — Find previous trading day

---

## Assumptions

1. **Mock data is acceptable** — Will create static JSON with NYSE holidays for 2025
2. **Annual cadence** — Calendar data is published once per year
3. **MIC codes** — Use standard ISO 10383 Market Identifier Codes
4. **US exchanges only** — Focus on XNYS (NYSE) and XNAS (NASDAQ) for demo
5. **JSON source** — Use local JSON files as the "reference data source"

---

## Part 3 — Parameter & API Pressure Test

### New Parameters Required

| Parameter | Domain | Semantic | Reusable? |
|-----------|--------|----------|-----------|
| `year` | exchange_calendar | Calendar year (int) | Domain-specific |
| `exchange_code` | exchange_calendar | MIC code (enum) | Potentially reusable |
| `file_path` | (generic) | Path to source file | ✅ Already generic |
| `force` | (generic) | Re-run even if done | ✅ Already generic |

### Analysis

#### Were new CLI flags required?

**No new flags needed**. The existing `--param year=2025 --param exchange_code=XNYS` pattern works:

```bash
spine run reference.exchange_calendar.ingest_year \
  --file /path/to/holidays.json \
  --param year=2025 \
  --param exchange_code=XNYS
```

The generic `-p key=value` flag handles domain-specific parameters without CLI changes.

#### Were parameter semantics reusable?

| Semantic | FINRA | Exchange Calendar | Verdict |
|----------|-------|-------------------|---------|
| `week_ending` | Friday date | Not used | Domain-specific ✅ |
| `tier` | Market tier | Not used | Domain-specific ✅ |
| `year` | Not used | Calendar year | Domain-specific ✅ |
| `exchange_code` | Not used | MIC code | Could be promoted |
| `file_path` | PSV file | JSON file | Generic ✅ |
| `force` | Re-ingest | Re-ingest | Generic ✅ |

#### Did any "generic" parameter turn out not to be generic?

**No**. The generic parameters (`file_path`, `force`) work identically across domains.

The FINRA-specific parameters (`week_ending`, `tier`) were correctly kept domain-local and did not pollute the exchange calendar domain.

#### Parameter Location Summary

| Parameter | Where It Belongs | Reason |
|-----------|-----------------|--------|
| `year` | Domain | Only meaningful for annual data |
| `exchange_code` | Domain (candidate for core) | Used by one domain but could be shared |
| `week_ending` | Domain | FINRA-specific temporal key |
| `tier` | Domain | FINRA market tier enum |
| `file_path` | App/Adapter | Generic file source parameter |
| `force` | Core | Universal idempotency override |

### Verdict

**The parameter design is clean**:
- Generic params stay generic
- Domain params stay domain-local
- No parameter pollution between domains
- CLI works without modification

---

## Part 4 — Tests as Evidence

### Test Summary

| Test Class | Tests | Purpose |
|------------|-------|---------|
| `TestDomainIsolation` | 3 | Prove new domain doesn't affect FINRA |
| `TestSourceRegistry` | 5 | Prove JsonSource works via registry |
| `TestPeriodRegistry` | 5 | Prove AnnualPeriod works via registry |
| `TestCalculationLifecycle` | 5 | Prove calcs follow lifecycle rules |
| `TestDeterminismAndReplay` | 3 | Prove replay semantics hold |
| `TestCalculationCorrectness` | 7 | Verify calculation logic |
| `TestParseHolidays` | 2 | Test JSON parsing |
| `TestSchema` | 3 | Test schema definitions |
| **Total** | **33** | |

### Critical Test

The test that would **FAIL if architecture were poorly modular**:

```python
def test_finra_pipelines_unaffected_by_calendar_import(self):
    """
    Importing exchange_calendar should not modify FINRA registry.
    
    This would FAIL if:
    - Exchange calendar polluted global registries
    - Source/Period registries were shared incorrectly
    - Pipeline registration had side effects
    """
    # Import FINRA first
    from spine.domains.finra.otc_transparency import sources as finra_sources
    
    finra_source_count = len(finra_sources.SOURCE_REGISTRY)
    finra_period_count = len(finra_sources.PERIOD_REGISTRY)
    
    # Now import exchange calendar
    from spine.domains.reference.exchange_calendar import sources as calendar_sources
    
    # FINRA registries should be unchanged
    assert len(finra_sources.SOURCE_REGISTRY) == finra_source_count
    assert len(finra_sources.PERIOD_REGISTRY) == finra_period_count
    
    # Calendar has its own separate registries
    assert calendar_sources.SOURCE_REGISTRY is not finra_sources.SOURCE_REGISTRY
```

### Full Suite Results

```
196 passed, 3 skipped in 1.05s
```

---

## Part 5 — What This Stress Test Taught Us

### ✅ What Worked Well

1. **Pipeline Registry Pattern**
   - `@register_pipeline` works perfectly for new domains
   - Zero changes to registry internals
   - Pipeline discovery is automatic
   - Namespace convention (`reference.exchange_calendar.*`) provides natural organization

2. **Domain Isolation**
   - FINRA and Exchange Calendar share no state
   - Source/Period registries are correctly domain-local
   - Schema constants are independent
   - No cross-domain pollution

3. **Parameter Handling**
   - Generic `-p key=value` flag handles domain-specific params
   - No CLI changes required
   - `file_path` and `force` work identically across domains
   - Domain params stay in domain

4. **Calculation Pattern**
   - Pure functions with no side effects
   - `calc_name` and `calc_version` tracking
   - `strip_audit_fields` for determinism testing
   - Same pattern as FINRA calcs

5. **Core Primitives**
   - `WorkManifest` works for any domain
   - `new_context()` and `new_batch_id()` are domain-agnostic
   - Core tables (`core_manifest`, `core_quality`) handle multiple domains

### ⚠️ What Felt Awkward

1. **Registry Loader Requires Explicit Import**
   
   Adding a new domain requires editing `registry.py` to add an import line:
   ```python
   import spine.domains.reference.exchange_calendar.pipelines  # noqa: F401
   ```
   
   **Recommendation**: Keep this explicit. Auto-discovery would add magic.

2. **Source/Period Registries Are Domain-Local (Duplication)**
   
   Both FINRA and Exchange Calendar define:
   - `IngestionSource` ABC
   - `PeriodStrategy` ABC
   - `SOURCE_REGISTRY` dict
   - `PERIOD_REGISTRY` dict
   
   **Recommendation**: Consider promoting ABCs to spine-core, keep registries domain-local.

3. **Annual Period Derivation Feels Forced**
   
   `PeriodStrategy.derive_period_end(publish_date)` makes sense for weekly/monthly but less so for annual data where "period" is just the year.
   
   **Recommendation**: Pattern still works, but semantics are slightly awkward. Acceptable.

### 🔮 Abstraction Candidates for Core

| Abstraction | Promote to Core? | Reason |
|-------------|------------------|--------|
| `IngestionSource` ABC | Maybe later | 2+ domains use same pattern |
| `PeriodStrategy` ABC | Maybe later | 2+ domains use same pattern |
| `Payload` dataclass | Maybe later | Common content+metadata pattern |
| Source/Period registries | **No** | Keep domain-local for isolation |
| `strip_audit_fields()` | Maybe later | Useful for all calc testing |
| `Exchange` enum | **No** | Reference data, not framework |

### 🚫 Should Explicitly Remain Domain-Only

| Abstraction | Reason to Keep Domain-Local |
|-------------|------------------------------|
| `Exchange` enum | Reference data, not framework |
| `Holiday` dataclass | Exchange calendar specific |
| `TradingDayResult` | Exchange calendar specific |
| `Tier` enum (FINRA) | FINRA-specific market tier |
| `WeeklyPeriod` | FINRA-specific temporal semantics |

### Summary Metrics

| Metric | Value |
|--------|-------|
| Files modified in existing code | 2 (registry.py, schema.sql) |
| Lines added to existing code | ~50 |
| New domain code | ~600 lines |
| New tests | 33 |
| FINRA tests still passing | ✅ All 163 |
| Total tests passing | 196 |

### Conclusion

The architecture is **well-modular**. Adding a completely new domain with:
- Different ingestion cadence (annual vs weekly)
- Different source type (JSON vs PSV/API)
- Different calculations (trading days vs rolling averages)

Required:
- ✅ New domain folder (expected)
- ✅ New DB tables (expected)
- ✅ 1 import line in registry loader (minimal)
- ❌ No changes to core primitives
- ❌ No changes to CLI/API
- ❌ No changes to FINRA domain

**The "extensibility without branching" principle holds.**
