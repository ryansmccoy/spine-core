# Top Cleanup Commits — Highest Leverage Changes

> Generated: January 2026 | Post Phase 1-4 Consolidation

These are the 5 highest-leverage cleanup commits, ordered by priority. Each is scoped to be a single commit.

---

## Commit 1: Remove TIER_VALUES Compatibility Shim

**Priority:** HIGH  
**Risk:** LOW  
**Effort:** 15 minutes

### Scope

Remove the backwards-compatibility shim in `console.py` and update interactive imports.

### Files Changed

1. `cli/console.py` - Remove line 20
2. `cli/interactive/menu.py` - Update import and usages
3. `cli/interactive/prompts.py` - Update import and usages

### Changes

```python
# cli/console.py - DELETE:
# For backwards compatibility in interactive module (will be removed)
TIER_VALUES = get_tier_values()
```

```python
# cli/interactive/menu.py - UPDATE imports:
from ..console import console, get_tier_values
# Remove TIER_VALUES from import

# UPDATE usages (3 places):
choices=get_tier_values()  # Was: choices=TIER_VALUES
```

```python
# cli/interactive/prompts.py - UPDATE imports:
from ..console import console, get_tier_values
# Remove TIER_VALUES from import

# UPDATE usages (1 place):
choices=get_tier_values()  # Was: choices=TIER_VALUES
```

### Commit Message

```
refactor(cli): remove TIER_VALUES compatibility shim

- Remove module-level TIER_VALUES constant from console.py
- Update interactive/menu.py to use get_tier_values()
- Update interactive/prompts.py to use get_tier_values()

The shim was added for backwards compatibility during the Phase 1
refactor. Interactive module now calls get_tier_values() directly.
```

### Verification

```bash
uv run pytest tests/ -q
uv run spine pipelines list
# Test interactive if available
```

---

## Commit 2: Add Design Intent Documentation to Interactive

**Priority:** MEDIUM  
**Risk:** NONE  
**Effort:** 5 minutes

### Scope

Document the intentional subprocess pattern in interactive module.

### Files Changed

1. `cli/interactive/menu.py` - Add module docstring

### Changes

```python
"""Interactive menu using questionary.

Design Note:
    This module uses subprocess.run() to invoke CLI commands rather than
    calling the command layer directly. This is intentional:
    
    1. Reuses exact CLI output formatting (Rich panels, progress bars)
    2. Ensures CLI and interactive modes have identical behavior
    3. Avoids duplicating Rich rendering logic in interactive
    
    Trade-off: Each action spawns a new process (~200ms overhead).
    This is acceptable for interactive (human-speed) usage.
    
    If structured results are needed, refactor to use commands directly.
"""
```

### Commit Message

```
docs(cli): document interactive subprocess pattern as intentional

Add module docstring explaining why interactive mode shells out to CLI
rather than calling commands directly. This documents a deliberate
design decision, not technical debt.
```

---

## Commit 3: Remove Unused ParameterResolver Methods

**Priority:** MEDIUM  
**Risk:** LOW  
**Effort:** 10 minutes

### Scope

Remove `merge_from_sources()` and `_parse_key_value()` from ParameterResolver if unused.

### Pre-Check

```bash
# Verify not used in production code
grep -r "merge_from_sources" src/
grep -r "_parse_key_value" src/
# Only match should be definition itself
```

### Files Changed

1. `app/services/params.py` - Remove unused methods

### Changes

Remove these methods from `ParameterResolver` class:
- `merge_from_sources()` (lines ~65-112)
- `_parse_key_value()` (lines ~113-120)

Keep:
- `resolve()` method (actively used by commands)

### Commit Message

```
refactor(app): remove unused ParameterResolver methods

- Remove merge_from_sources() - CLI uses ParamParser.merge_params()
- Remove _parse_key_value() - only used by merge_from_sources()

The resolve() method remains, used by RunPipelineCommand for tier
normalization. Parameter merging is CLI-specific and stays in
cli/params.py.
```

### Verification

```bash
uv run pytest tests/test_parameter_resolver.py -v
uv run pytest tests/ -q
```

---

## Commit 4: Clarify ParamParser vs ParameterResolver Roles

**Priority:** LOW  
**Risk:** NONE  
**Effort:** 10 minutes

### Scope

Add docstrings clarifying the distinct responsibilities.

### Files Changed

1. `cli/params.py` - Add clarifying docstring
2. `app/services/params.py` - Add clarifying docstring

### Changes

```python
# cli/params.py
"""
CLI-specific parameter parsing.

This module handles CLI-specific concerns:
- Parsing key=value strings from command line
- Merging parameters from multiple CLI sources
- Handling typer context args

For normalization (tier aliases, validation), see app/services/params.py.
Commands call ParameterResolver.resolve() after CLI parsing.

Separation of concerns:
    CLI layer:     ParamParser.merge_params() - raw string handling
    Command layer: ParameterResolver.resolve() - normalization
"""
```

```python
# app/services/params.py
"""
Parameter resolution service.

This module handles cross-adapter concerns:
- Normalizing tier values (tier1 → NMS_TIER_1)
- Validating parameter formats
- Shared between CLI and API

For CLI-specific parsing (key=value strings), see cli/params.py.

Separation of concerns:
    CLI layer:     Parses strings, merges sources
    API layer:     Deserializes JSON via Pydantic
    Command layer: ParameterResolver.resolve() - normalization (this module)
"""
```

### Commit Message

```
docs: clarify ParamParser vs ParameterResolver responsibilities

Add module docstrings explaining the separation of concerns:
- cli/params.py: CLI-specific parsing (key=value strings)
- app/services/params.py: Cross-adapter normalization

This documents why both exist and prevents accidental merging.
```

---

## Commit 5: Remove Unused CLI Validation Methods (Optional)

**Priority:** LOW  
**Risk:** LOW  
**Effort:** 5 minutes

### Pre-Check

```bash
grep -r "validate_date" src/
grep -r "validate_file_exists" src/
```

### Scope

If `validate_date()` and `validate_file_exists()` in `cli/params.py` are unused, remove them.

### Files Changed

1. `cli/params.py` - Remove unused methods

### Decision

**Keep if:** They serve as utility functions that might be used in future.
**Remove if:** Truly dead code with no future use.

### Commit Message

```
refactor(cli): remove unused validation methods

- Remove ParamParser.validate_date() - unused
- Remove ParamParser.validate_file_exists() - unused

Date validation happens in pipelines; file validation in IngestResolver.
```

---

## Summary

| # | Commit | Priority | Risk | Effort |
|---|--------|----------|------|--------|
| 1 | Remove TIER_VALUES shim | HIGH | LOW | 15 min |
| 2 | Document interactive pattern | MEDIUM | NONE | 5 min |
| 3 | Remove unused ParameterResolver methods | MEDIUM | LOW | 10 min |
| 4 | Clarify ParamParser/ParameterResolver | LOW | NONE | 10 min |
| 5 | Remove unused CLI validation | LOW | LOW | 5 min |

**Total effort:** ~45 minutes

---

## Not Recommended at This Time

The following were considered but **deferred**:

1. **Refactor interactive to use commands** - High effort, low ROI
2. **Create VerifyCommand/HealthCheckCommand** - No API need yet
3. **Import table names from domain** - Minimal benefit
4. **Move CLI README to docs/** - Preference, not requirement

These can be revisited when:
- Interactive becomes primary UX
- API needs `/verify` endpoints
- Major docs restructure happens
