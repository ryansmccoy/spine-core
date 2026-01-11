# Cleanup TODOs — Ordered Checklist

> Generated: January 2026 | Post Phase 1-4 Consolidation

This document provides an ordered checklist of cleanup actions.

---

## Priority Order

Changes are ordered by:
1. **Risk** - Lower risk first
2. **Dependencies** - Prerequisites before dependents
3. **Value** - Higher impact items prioritized

---

## Phase 1: Low-Risk Cleanup (No Behavior Change)

### ☐ 1.1 Remove TIER_VALUES Compatibility Shim

**Scope:** Minimal  
**Files:**
- `cli/console.py` - Remove line 20
- `cli/interactive/menu.py` - Update imports
- `cli/interactive/prompts.py` - Update imports

**Changes:**
```python
# cli/console.py - REMOVE this line:
TIER_VALUES = get_tier_values()

# cli/interactive/menu.py - CHANGE:
# FROM:
from ..console import TIER_VALUES, console
# TO:
from ..console import console, get_tier_values

# And replace TIER_VALUES usage with get_tier_values():
tier = questionary.select(
    "Select tier:",
    choices=get_tier_values(),  # Was: TIER_VALUES
    ...
)
```

**Tests to run:**
```bash
uv run pytest tests/ -q
uv run spine pipelines list  # Smoke test CLI
```

**Verification:**
- [ ] No import errors
- [ ] Interactive mode still works: `uv run spine ui` (if available)
- [ ] Tests pass

---

### ☐ 1.2 Delete Unused ParameterResolver Methods

**Scope:** Minimal  
**Files:**
- `app/services/params.py`

**Audit first:**
```bash
# Check if merge_from_sources is called anywhere
grep -r "merge_from_sources" src/
```

If not called, remove:
- `merge_from_sources()` method
- `_parse_key_value()` method (if only used by merge_from_sources)

**Keep:** `resolve()` method (used by commands)

**Tests to run:**
```bash
uv run pytest tests/test_parameter_resolver.py -v
```

---

### ☐ 1.3 Delete Unused ParamParser Methods

**Scope:** Minimal  
**Files:**
- `cli/params.py`

**Audit first:**
```bash
grep -r "validate_file_exists" src/
grep -r "validate_date" src/
```

If not called, consider removing (or keep for future use).

---

## Phase 2: Documentation and Organization

### ☐ 2.1 Add Intentional Design Comment for Interactive Subprocess

**Scope:** Documentation only  
**Files:**
- `cli/interactive/menu.py`

Add comment explaining the subprocess pattern:

```python
"""Interactive menu using questionary.

Design Note: Interactive actions use subprocess.run() to invoke CLI commands
rather than calling the command layer directly. This is intentional:
1. Ensures exact CLI output formatting (Rich panels, etc.)
2. Interactive is a secondary UX, not primary interface
3. Avoids duplicating CLI rendering logic

Trade-off: Spawns new process per action (acceptable for interactive use).
"""
```

---

### ☐ 2.2 Decide on CLI README Location

**Options:**
1. Keep in `cli/README.md` (near code)
2. Move to `docs/cli/` (centralized)
3. Keep both (README as pointer, full docs in docs/)

**Recommendation:** Keep as-is unless consolidating all docs.

---

## Phase 3: Consider Future Refactors (DEFER)

These items are noted but not required for Basic tier stability.

### ☐ 3.1 Interactive Command Layer Refactor

**Current:** Interactive uses `subprocess.run()` and direct registry imports.

**Future option:** Have interactive call commands directly:

```python
# Instead of:
subprocess.run(["uv", "run", "spine", "query", "weeks", ...])

# Could do:
from market_spine.app.commands.queries import QueryWeeksCommand, QueryWeeksRequest
result = QueryWeeksCommand().execute(QueryWeeksRequest(tier=tier, limit=limit))
# Then render result with Rich
```

**Why defer:**
- Works fine as-is
- Would need to duplicate Rich rendering
- Interactive is secondary UX

**Trigger to implement:** If interactive becomes primary UX or needs structured results.

---

### ☐ 3.2 VerifyCommand and HealthCheckCommand

**Current:** `verify.py` and `doctor.py` do direct SQL.

**Future option:** Create commands for consistency.

**Why defer:**
- No API endpoints for verify (yet)
- `/health/detailed` exists but uses different code path
- Low complexity, little duplication

**Trigger to implement:** If API needs `/verify` endpoints.

---

### ☐ 3.3 DataSourceConfig Import from Domain

**Current:** `app/services/data.py` defines table name constants.

**Future option:** Import from `spine.domains.finra.otc_transparency.schema.TABLES`:

```python
from spine.domains.finra.otc_transparency.schema import TABLES

class DataSourceConfig:
    @property
    def normalized_data_table(self) -> str:
        return TABLES["venue_volume"]  # Use domain constants
```

**Why defer:**
- Current duplication is minimal
- Domain TABLES uses different keys ("raw" vs "raw_data_table")
- Would need mapping layer anyway

---

## Checklist Summary

### Must Do (Phase 1)

- [ ] 1.1 Remove TIER_VALUES shim from console.py
- [ ] 1.1 Update interactive imports to use get_tier_values()
- [ ] 1.2 Audit and remove unused ParameterResolver methods

### Should Do (Phase 2)

- [ ] 2.1 Add design comment to interactive/menu.py

### Consider Later (Phase 3)

- [ ] 3.1 Interactive command layer refactor
- [ ] 3.2 VerifyCommand and HealthCheckCommand
- [ ] 3.3 DataSourceConfig import from domain

---

## Test Verification After Cleanup

Run full test suite after any changes:

```bash
# Unit tests
uv run pytest tests/ -v

# CLI smoke tests
uv run spine --help
uv run spine pipelines list
uv run spine query weeks --tier OTC  # May fail if no data, that's OK
uv run spine doctor doctor

# API smoke tests
uv run uvicorn market_spine.api.app:app --host 0.0.0.0 --port 8000 &
curl http://localhost:8000/health
curl http://localhost:8000/v1/capabilities
```
