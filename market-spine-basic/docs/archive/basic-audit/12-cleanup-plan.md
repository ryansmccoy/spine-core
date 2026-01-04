# Cleanup Plan

Generated: 2026-01-03

## Overview

This plan addresses the findings from the Basic Tier Audit Report. Changes are grouped into logical commits that can be applied incrementally while keeping tests green.

---

## Commit 1: Remove Duplicate Tier Logic from CLI Console

**Files to modify:**
- `src/market_spine/cli/console.py` - Remove TIER_VALUES, TIER_ALIASES, normalize_tier()
- `src/market_spine/cli/params.py` - Remove tier normalization (let commands handle it)

**Changes:**
1. Remove `TIER_VALUES`, `TIER_ALIASES`, `normalize_tier()` from console.py
2. Create helper function that gets values from TierNormalizer
3. Update params.py to not normalize tiers (pass raw to commands)

**Tests affected:** None expected (commands handle normalization)

---

## Commit 2: Update Interactive Module to Use Service Values

**Files to modify:**
- `src/market_spine/cli/interactive/menu.py` - Use service for tier values
- `src/market_spine/cli/interactive/prompts.py` - Use service for tier values

**Changes:**
1. Replace `from ..console import TIER_VALUES` with service call
2. Keep registry imports (acceptable for interactive introspection)

**Tests affected:** None (interactive not tested)

---

## Commit 3: Refactor DataSourceConfig to Import from spine-domains

**Files to modify:**
- `src/market_spine/app/services/data.py` - Import from spine-domains

**Changes:**
1. Import TABLES from spine.domains.finra.otc_transparency.schema
2. Use TABLES values instead of hardcoded strings

**Tests affected:** Run to verify no regressions

---

## Commit 4: Refactor doctor.py to Use DataSourceConfig

**Files to modify:**
- `src/market_spine/cli/commands/doctor.py` - Use DataSourceConfig

**Changes:**
1. Import DataSourceConfig
2. Use table name properties instead of hardcoded strings

**Tests affected:** Run to verify no regressions

---

## Commit 5: Refactor verify.py to Use Services

**Files to modify:**
- `src/market_spine/cli/commands/verify.py` - Use DataSourceConfig and TierNormalizer

**Changes:**
1. Import DataSourceConfig and TierNormalizer
2. Replace hardcoded table names with service calls
3. Replace local normalize_tier with TierNormalizer

**Tests affected:** Run to verify no regressions

---

## Commit 6: Remove Framework Lane Import from CLI

**Files to modify:**
- `src/market_spine/cli/commands/run.py` - Pass lane as string

**Changes:**
1. Remove `from spine.framework.dispatcher import Lane`
2. Pass lane as string directly to command

**Tests affected:** Run to verify no regressions

---

## Commit 7: Remove Framework Lane Import from API

**Files to modify:**
- `src/market_spine/api/routes/v1/pipelines.py` - Map lanes without enum

**Changes:**
1. Remove `from spine.framework.dispatcher import Lane`
2. Create simple string mapping

**Tests affected:** Run API tests

---

## Commit 8: Refactor ui.py to Accept Data Instead of Fetching

**Files to modify:**
- `src/market_spine/cli/ui.py` - Accept pipeline data as parameter

**Changes:**
1. Modify `create_pipeline_table()` to accept list of (name, description) tuples
2. Remove registry import
3. Update callers to pass data from command results

**Tests affected:** None (UI helpers not directly tested)

---

## Commit 9: Remove Unused param_resolver from QuerySymbolsCommand

**Files to modify:**
- `src/market_spine/app/commands/queries.py` - Remove unused parameter

**Changes:**
1. Remove `param_resolver` parameter from `__init__`

**Tests affected:** Run command tests

---

## Execution Order

1. ✅ Commit 1: Remove duplicate tier logic (console.py, params.py)
2. ✅ Commit 2: Update interactive module
3. ✅ Commit 3: Refactor DataSourceConfig
4. ✅ Commit 4: Refactor doctor.py
5. ✅ Commit 5: Refactor verify.py
6. ✅ Commit 6: Remove Lane from CLI run.py
7. ✅ Commit 7: Remove Lane from API
8. ✅ Commit 8: Refactor ui.py
9. ✅ Commit 9: Remove unused param

**Total estimated changes:** ~15 files, ~100 lines modified

---

## Validation Checkpoints

After each commit:
```bash
uv run pytest tests/ -q
```

Final validation:
```bash
uv run spine --help
uv run spine pipelines list
uv run spine run finra.otc_transparency.normalize_week --dry-run --tier tier1 --week-ending 2025-12-19
```
