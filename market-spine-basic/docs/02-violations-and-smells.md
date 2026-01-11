# Violations and Code Smells Report

> Generated: January 2026 | Post Phase 1-4 Consolidation

This document identifies architectural violations, code smells, and areas for cleanup.

---

## Constraint Validation Summary

| Constraint | Status | Notes |
|------------|--------|-------|
| No tier/domain logic in spine-core | ✅ PASS | spine-core is generic |
| No DI containers / command bus / middleware | ✅ PASS | No frameworks |
| No generic Command[I,O] ABC | ✅ PASS | Concrete classes only |
| Basic remains sync execution only | ✅ PASS | async only in FastAPI routes |
| Pydantic only at API boundary | ✅ PASS | Commands use dataclasses |

---

## Findings Table

### Severity Levels

- 🔴 **HIGH**: Violates architecture constraints, must fix
- 🟡 **MEDIUM**: Code smell, causes maintenance burden
- 🟢 **LOW**: Minor issue, cosmetic or documentation

---

### 🟡 MEDIUM-001: Duplicate ParamParser

**Location:** `cli/params.py` vs `app/services/params.py`

**Problem:**
Two separate implementations of parameter parsing exist:

```python
# cli/params.py
class ParamParser:
    @staticmethod
    def merge_params(...) -> dict[str, Any]:
        ...
    
    @staticmethod
    def parse_key_value(arg: str) -> tuple[str, str] | None:
        ...

# app/services/params.py
class ParameterResolver:
    def merge_from_sources(...) -> dict[str, Any]:
        ...
    
    def _parse_key_value(self, arg: str) -> tuple[str, str] | None:
        ...
```

Both classes parse `key=value` strings and merge parameters.

**Why it's a problem:**
- Logic duplication
- CLI uses ParamParser directly (doesn't go through ParameterResolver for merging)
- Risk of divergence

**Recommendation:** `MERGE`
- CLI should use `ParameterResolver.merge_from_sources()` 
- Or: Delete `merge_from_sources()` from ParameterResolver since CLI already merges
- Keep `ParamParser` as thin CLI-specific parsing, delegate normalization to ParameterResolver

---

### 🟡 MEDIUM-002: TIER_VALUES Compatibility Shim

**Location:** `cli/console.py` line 20

**Problem:**
```python
# For backwards compatibility in interactive module (will be removed)
TIER_VALUES = get_tier_values()
```

This exists because `interactive/menu.py` and `interactive/prompts.py` import it:
```python
from ..console import TIER_VALUES, console
```

**Why it's a problem:**
- Module-level constant evaluated at import time
- Backwards compatibility shim that should have been removed
- Interactive could call `get_tier_values()` directly

**Recommendation:** `DELETE shim + UPDATE interactive`
- Change interactive imports to use `get_tier_values()` function
- Remove `TIER_VALUES = ...` line from console.py

---

### 🟡 MEDIUM-003: Interactive Mode Uses Subprocess

**Location:** `cli/interactive/menu.py`

**Problem:**
All interactive menu actions shell out to the CLI:

```python
def run_pipeline_interactive():
    cmd_parts = ["uv", "run", "spine", "run", "run", pipeline]
    ...
    result = subprocess.run(cmd_parts)

def query_data_interactive():
    cmd_parts = ["uv", "run", "spine", "query", "weeks", ...]
    subprocess.run(cmd_parts)
```

**Why it's a problem:**
- Spawns new process for each action (slow, extra resource usage)
- Cannot capture structured results (only exit code)
- Bypasses in-process command layer

**Why it might be OK:**
- Interactive mode is a secondary UX
- Subprocess ensures exact CLI behavior
- Avoids duplicating CLI output rendering

**Recommendation:** `DEFER` (see 04-prune-plan)
- Consider whether interactive should use commands directly
- If subprocess pattern is acceptable, document it as intentional

---

### 🟡 MEDIUM-004: Direct Framework Import in Interactive

**Location:** `cli/interactive/menu.py` line 7, `cli/interactive/prompts.py` line 8

**Problem:**
```python
from spine.framework.registry import list_pipelines  # menu.py
from spine.framework.registry import get_pipeline    # prompts.py
```

Interactive modules import directly from `spine.framework` rather than going through commands.

**Why it's a problem:**
- Breaks layering (adapters should use commands, not framework directly)
- Inconsistent with CLI commands which use command layer

**Recommendation:** `REFACTOR`
- Replace `list_pipelines()` with `ListPipelinesCommand().execute(...).pipelines`
- Replace `get_pipeline()` with `DescribePipelineCommand().execute(...).pipeline`
- Or: Accept registry access for UI-only metadata (no execution)

---

### 🟢 LOW-001: Verify Command Not Using Commands

**Location:** `cli/commands/verify.py`

**Problem:**
Unlike other CLI commands, verify.py does direct SQL queries instead of using a command:

```python
@app.command("data")
def verify_data(tier, week):
    normalized_tier = _tier_normalizer.normalize(tier)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE ...")
```

**Why it's a problem:**
- Inconsistent with run.py, query.py, list_.py which use commands
- No corresponding VerifyCommand exists

**Why it might be OK:**
- Verify is CLI-only (no API equivalent needed currently)
- Low complexity, no business logic

**Recommendation:** `DEFER`
- Create `VerifyCommand` only if API needs /verify endpoints
- Current state is acceptable for Basic tier

---

### 🟢 LOW-002: Doctor Command Not Using Commands

**Location:** `cli/commands/doctor.py`

**Problem:**
Similar to verify.py, doctor.py does direct health checks without a command layer.

**Why it might be OK:**
- `/health/detailed` endpoint exists in API with similar logic
- Doctor is a diagnostic tool, not business operation

**Recommendation:** `DEFER`
- Could create `HealthCheckCommand` if wanted
- Current duplication is minimal

---

### 🟢 LOW-003: Unused Imports or Dead Code

**Scanned locations:**
- `cli/params.py` - `validate_file_exists()` never called
- `app/services/params.py` - `merge_from_sources()` never called from production code

**Recommendation:** `AUDIT` during next cleanup pass

---

### 🟢 LOW-004: README Files in Source

**Location:** `cli/README.md`, `cli/UX_GUIDE.md`

**Problem:**
Documentation files inside src/ directory rather than docs/.

**Why it might be OK:**
- CLI-specific docs that live near the code
- Some teams prefer this pattern

**Recommendation:** `KEEP` or `MOVE` based on preference

---

## Domain Boundary Check

### Correct Placement ✅

| Item | Location | Correct? |
|------|----------|----------|
| Tier enum (`Tier`) | spine-domains | ✅ |
| TIER_ALIASES, TIER_VALUES | spine-domains | ✅ |
| TABLES dict | spine-domains | ✅ |
| Pipeline implementations | spine-domains | ✅ |
| TierNormalizer | market_spine/app/services | ✅ |
| IngestResolver | market_spine/app/services | ✅ |
| DataSourceConfig | market_spine/app/services | ✅ |
| Pydantic models | market_spine/api/routes | ✅ |

### Questionable Placement 🟡

| Item | Location | Issue |
|------|----------|-------|
| Table name constants | `app/services/data.py` | Duplicates spine-domains TABLES |

`DataSourceConfig` defines:
```python
NORMALIZED_TABLE = "finra_otc_transparency_normalized"
RAW_TABLE = "finra_otc_transparency_raw"
AGGREGATED_TABLE = "finra_otc_transparency_aggregated"
```

While spine-domains has:
```python
TABLES = {
    "raw": "finra_otc_transparency_raw",
    "venue_volume": "finra_otc_transparency_venue_volume",
    ...
}
```

**Recommendation:** Consider importing from spine-domains instead of duplicating.

---

## Summary Action Items

| ID | Severity | Action | Scope |
|----|----------|--------|-------|
| MEDIUM-001 | 🟡 | Clarify ParamParser vs ParameterResolver roles | cli/params.py, app/services/params.py |
| MEDIUM-002 | 🟡 | Remove TIER_VALUES shim, update interactive | cli/console.py, cli/interactive/*.py |
| MEDIUM-003 | 🟡 | Document or refactor interactive subprocess | cli/interactive/menu.py |
| MEDIUM-004 | 🟡 | Consider command layer for interactive | cli/interactive/*.py |
| LOW-001 | 🟢 | Consider VerifyCommand | cli/commands/verify.py |
| LOW-002 | 🟢 | Consider HealthCheckCommand | cli/commands/doctor.py |
| LOW-003 | 🟢 | Audit unused methods | Multiple |
| LOW-004 | 🟢 | Decide on README placement | cli/README.md |

**No HIGH severity violations found.** The architecture is sound.
