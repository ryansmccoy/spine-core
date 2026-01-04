# Basic Tier Audit Report

Generated: 2026-01-03

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 4 |
| Medium | 6 |
| Low | 3 |

---

## 1. Architecture Violations

### HIGH-001: Duplicate TIER_VALUES/TIER_ALIASES in CLI

**Files:**
- [src/market_spine/cli/console.py](../src/market_spine/cli/console.py#L9-L30)

**Problem:**
`console.py` defines `TIER_VALUES`, `TIER_ALIASES`, and `normalize_tier()` which duplicate the canonical definitions in `spine.domains.finra.otc_transparency.schema`.

```python
# console.py (lines 9-30) - DUPLICATE
TIER_VALUES = ["OTC", "NMS_TIER_1", "NMS_TIER_2"]
TIER_ALIASES = { ... }
def normalize_tier(tier: str | None) -> str | None:
    ...
```

**Impact:**
- Two sources of truth for tier values
- Changes to domain schema won't propagate to CLI
- `cli/interactive/menu.py` and `cli/interactive/prompts.py` import from console.py

**Recommendation:**
Remove `TIER_VALUES`, `TIER_ALIASES`, and `normalize_tier()` from `console.py`. Import from `TierNormalizer` service or create a thin CLI helper that delegates.

**Safe to remove:** Yes, with migration to use `TierNormalizer.get_valid_values()`

---

### HIGH-002: CLI params.py Uses Local normalize_tier

**Files:**
- [src/market_spine/cli/params.py](../src/market_spine/cli/params.py#L68)

**Problem:**
`ParamParser.merge_params()` calls `normalize_tier()` from `console.py`, not from the service layer.

```python
# params.py line 68
params["tier"] = normalize_tier(params["tier"])
```

**Impact:**
- CLI parameter parsing uses duplicated normalization logic
- Inconsistent with command layer which uses `TierNormalizer`

**Recommendation:**
Remove tier normalization from `ParamParser`. Let commands handle normalization via `ParameterResolver`.

**Safe to remove:** Yes, commands already normalize tiers

---

### HIGH-003: CLI verify.py Has Direct SQL and Hardcoded Table Names

**Files:**
- [src/market_spine/cli/commands/verify.py](../src/market_spine/cli/commands/verify.py#L27-L107)

**Problem:**
`verify.py` contains direct database access with hardcoded FINRA table names:

```python
# Line 90
"SELECT COUNT(*) FROM finra_otc_transparency_normalized WHERE..."

# Line 101-105
SELECT COUNT(*) FROM finra_otc_transparency_normalized
WHERE week_ending = ? AND tier = ?
```

**Impact:**
- CLI command contains domain-specific constants
- Bypasses command layer entirely
- Uses local `normalize_tier()` from console.py

**Recommendation:**
Either:
1. Create a `VerifyDataCommand` in `app/commands/` that uses `DataSourceConfig`, OR
2. Keep as CLI-only utility but import table names from `DataSourceConfig`

**Safe to remove:** Needs migration to command layer or service delegation

---

### HIGH-004: CLI doctor.py Has Hardcoded Table Names

**Files:**
- [src/market_spine/cli/commands/doctor.py](../src/market_spine/cli/commands/doctor.py#L34-L36)

**Problem:**
Doctor command has hardcoded table names:

```python
required_tables = [
    "finra_otc_transparency_raw",
    "finra_otc_transparency_normalized",
    "finra_otc_transparency_aggregated",
]
```

**Impact:**
- FINRA-specific constants in CLI layer
- Not using `DataSourceConfig` service

**Recommendation:**
Import table names from `DataSourceConfig` service.

**Safe to remove:** No, needs migration to use `DataSourceConfig`

---

## 2. Dead/Obsolete Code

### MEDIUM-001: Interactive Module Uses Framework Registry Directly

**Files:**
- [src/market_spine/cli/interactive/menu.py](../src/market_spine/cli/interactive/menu.py#L8)
- [src/market_spine/cli/interactive/prompts.py](../src/market_spine/cli/interactive/prompts.py#L8)

**Problem:**
Interactive module imports directly from `spine.framework.registry`:

```python
# menu.py line 8
from spine.framework.registry import list_pipelines

# prompts.py line 8
from spine.framework.registry import get_pipeline
```

**Impact:**
- Bypasses command layer
- Inconsistent with CLI commands which use `ListPipelinesCommand`

**Recommendation:**
Interactive module should call commands or shell out to CLI (which it does for execution). For listing/describing, it could use commands.

**Safe to change:** Yes, but low priority since interactive shells out for execution

---

### MEDIUM-002: cli/ui.py Uses Framework Registry Directly

**Files:**
- [src/market_spine/cli/ui.py](../src/market_spine/cli/ui.py#L102)

**Problem:**
`create_pipeline_table()` imports from `spine.framework.registry`:

```python
# ui.py line 102
from spine.framework.registry import get_pipeline
```

**Impact:**
- UI helper depends on framework directly
- Could use command result data instead

**Recommendation:**
Refactor to accept pipeline data as parameter, not fetch from registry.

**Safe to change:** Yes, minor refactor

---

### MEDIUM-003: CLI run.py Uses Framework Dispatcher Lane Enum

**Files:**
- [src/market_spine/cli/commands/run.py](../src/market_spine/cli/commands/run.py#L10)

**Problem:**
```python
from spine.framework.dispatcher import Lane
```

**Impact:**
- CLI depends on framework enum directly
- Commands accept lane as string, so CLI doesn't need the enum

**Recommendation:**
Pass lane as string to command. Remove framework import.

**Safe to change:** Yes, commands accept string lane

---

### MEDIUM-004: Interactive Module Shells Out to CLI

**Files:**
- [src/market_spine/cli/interactive/menu.py](../src/market_spine/cli/interactive/menu.py#L100-L125)

**Problem:**
Interactive mode uses `subprocess.run()` to call the CLI:

```python
cmd_parts = ["uv", "run", "spine", "run", "run", pipeline]
...
result = subprocess.run(cmd_parts)
```

**Assessment:**
This is actually **acceptable** for Basic tier:
- Keeps interactive mode simple
- Reuses CLI formatting and error handling
- No code duplication

**Recommendation:**
Keep as-is. This is a valid pattern for Basic tier.

**Safe to keep:** Yes, intentional design choice

---

### MEDIUM-005: API routes/v1/pipelines.py Imports Lane Enum Inline

**Files:**
- [src/market_spine/api/routes/v1/pipelines.py](../src/market_spine/api/routes/v1/pipelines.py#L234)

**Problem:**
```python
# Line 234
from spine.framework.dispatcher import Lane
```

**Impact:**
- API layer imports framework enum
- Enum is only used to get `.value` string

**Recommendation:**
Map lane strings directly without importing enum.

**Safe to change:** Yes, minor refactor

---

### MEDIUM-006: DataSourceConfig Duplicates spine-domains Table Names

**Files:**
- [src/market_spine/app/services/data.py](../src/market_spine/app/services/data.py#L27-L29)

**Problem:**
`DataSourceConfig` hardcodes table names that are also defined in `spine.domains.finra.otc_transparency.schema.TABLES`:

```python
NORMALIZED_TABLE = "finra_otc_transparency_normalized"
RAW_TABLE = "finra_otc_transparency_raw"
AGGREGATED_TABLE = "finra_otc_transparency_aggregated"
```

**Assessment:**
This is **partially acceptable**:
- It encapsulates table names for commands (good)
- But duplicates definitions from spine-domains (not ideal)

**Recommendation:**
Import from spine-domains schema:
```python
from spine.domains.finra.otc_transparency.schema import TABLES
NORMALIZED_TABLE = TABLES["normalized"]
```

**Safe to change:** Yes, import from canonical source

---

## 3. Code Smells / Maintainability

### LOW-001: ParamParser Class Has Only Static Methods

**Files:**
- [src/market_spine/cli/params.py](../src/market_spine/cli/params.py)

**Problem:**
`ParamParser` is a class with only `@staticmethod` methods. Could be a module or namespace.

**Recommendation:**
Keep as-is. Static methods are fine for grouping related functions.

**Safe to ignore:** Yes, stylistic preference

---

### LOW-002: Inconsistent Error Message Formatting

**Files:**
- Various command files

**Problem:**
Error messages sometimes include quotes around values, sometimes don't.

**Recommendation:**
Low priority. Current formatting is acceptable.

**Safe to ignore:** Yes

---

### LOW-003: Unused ParameterResolver in QuerySymbolsCommand

**Files:**
- [src/market_spine/app/commands/queries.py](../src/market_spine/app/commands/queries.py#L163)

**Problem:**
`QuerySymbolsCommand.__init__` accepts `param_resolver` but doesn't use it:

```python
def __init__(
    self,
    tier_normalizer: TierNormalizer | None = None,
    param_resolver: ParameterResolver | None = None,  # Never used
    data_source: DataSourceConfig | None = None,
) -> None:
```

**Recommendation:**
Remove unused parameter.

**Safe to change:** Yes, remove unused parameter

---

## 4. Spine-Core Package Review

**Status:** ✅ Clean

No FINRA/OTC-specific constants found in `packages/spine-core/`. The framework properly delegates domain specifics to `spine-domains`.

---

## 5. Spine-Domains Package Review

**Status:** ✅ Appropriate

Domain constants are correctly located:
- `TIER_VALUES`, `TIER_ALIASES` in `schema.py`
- `TABLES` dictionary in `schema.py`
- Pipeline implementations with `@register_pipeline`

---

## Cleanup Priority

### Must Fix (High)
1. HIGH-001: Remove duplicate tier constants from `console.py`
2. HIGH-002: Remove tier normalization from `ParamParser`
3. HIGH-003: Refactor `verify.py` to use services
4. HIGH-004: Refactor `doctor.py` to use `DataSourceConfig`

### Should Fix (Medium)
5. MEDIUM-003: Remove Lane enum import from `run.py`
6. MEDIUM-005: Remove Lane enum import from API
7. MEDIUM-006: Import table names from spine-domains in `DataSourceConfig`
8. MEDIUM-002: Refactor `ui.py` to not use registry directly

### Can Defer (Medium - Lower Priority)
9. MEDIUM-001: Interactive module registry imports (acceptable pattern)
10. MEDIUM-004: Interactive subprocess pattern (intentional design)

### Optional (Low)
11. LOW-003: Remove unused param_resolver from QuerySymbolsCommand
