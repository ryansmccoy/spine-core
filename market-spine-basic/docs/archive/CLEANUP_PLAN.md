# Cleanup Plan: Remove Duplicate OTC Domain Code

**Goal**: Make `src/spine/domains/otc/` the ONLY OTC implementation.

**Safety**: Minimal changes, preserves all working functionality.

**Timeline**: 3 commits, ~30 minutes of work.

---

## Problem Analysis

### Current State

**Two OTC implementations exist**:

1. **`src/market_spine/domains/otc/`** - OLD, uses legacy imports
   - Files: `calculations.py`, `models.py`, `normalizer.py`, `parser.py`, `pipelines.py`
   - Imports: `from market_spine.domains.otc.models import ...`
   - Status: **Outdated, not compatible with new spine.core primitives**

2. **`src/spine/domains/otc/`** - CANONICAL, uses new architecture
   - Files: `calculations.py`, `connector.py`, `normalizer.py`, `pipelines.py`, `schema.py`
   - Imports: `from spine.core import ..., from spine.domains.otc.schema import ...`
   - Status: **Current, actively maintained**

**How they're discovered**:

- **Registry** ([src/market_spine/registry.py](../src/market_spine/registry.py#L47-68)):
  ```python
  def _load_pipelines():
      # Loads from market_spine/domains/{name}/pipelines.py
      domains_path = Path(__file__).parent / "domains"
      for _, name, is_pkg in pkgutil.iter_modules([str(domains_path)]):
          importlib.import_module(f"market_spine.domains.{name}.pipelines")
  ```

- **Manual import** ([src/spine/domains/otc/__init__.py](../src/spine/domains/otc/__init__.py#L12)):
  ```python
  from spine.domains.otc import pipelines  # noqa: F401 - registers pipelines
  ```

**Risk**: Both could register pipelines with same names → conflicts or duplicates.

### Why It's Safe to Delete `market_spine/domains/`

**Evidence that `market_spine/domains/otc` is NOT used**:

1. **No imports from new code**:
   ```bash
   # grep reveals NO imports of market_spine.domains in spine/ code
   grep -r "from market_spine.domains" src/spine/
   # → No results
   ```

2. **Old pipelines incompatible with new primitives**:
   - Old code uses `market_spine.domains.otc.models` (doesn't use spine.core)
   - New pipelines use `WorkManifest(conn, domain=DOMAIN, stages=STAGES)` API
   - Old code would fail with new manifest schema

3. **Registry currently broken for `market_spine/domains/`**:
   - Registry tries to import `market_spine.domains.{name}.pipelines`
   - But old OTC pipelines have incompatible imports
   - Would raise `ImportError` if actually loaded

4. **Actual working pipelines**:
   - Come from `spine.domains.otc.pipelines`
   - Registered via manual import in `spine/domains/otc/__init__.py`
   - This is what `spine pipeline list` shows

**What would break if we delete it**: **Nothing**, because it's not being imported.

---

## Three-Commit Cleanup Plan

### Commit 1: Fix Registry + Add Orientation

**Goal**: Change registry to discover from `spine.domains/` instead of `market_spine/domains/`.

**Why first**: Makes the canonical code path explicit before deleting duplicates.

#### 1.1. Update Registry Discovery

**File**: [src/market_spine/registry.py](../src/market_spine/registry.py)

**Change**:

```python
def _load_pipelines() -> None:
    """
    Load all pipeline modules to trigger registration.
    
    Pipelines are auto-discovered from spine.domains/ (shared library).
    Each domain module should use @register_pipeline decorator.
    """
    import importlib
    import pkgutil
    from pathlib import Path
    
    # NEW: Load from spine.domains/ (shared library)
    # This is src/spine/domains/ relative to src/
    import spine.domains
    domains_pkg_path = Path(spine.domains.__file__).parent
    
    if domains_pkg_path.exists():
        for _, name, is_pkg in pkgutil.iter_modules([str(domains_pkg_path)]):
            if not is_pkg:
                continue  # Only process packages (directories)
            try:
                # Import spine.domains.{name}.pipelines
                importlib.import_module(f"spine.domains.{name}.pipelines")
                logger.debug("domain_pipelines_loaded", domain=name)
            except ImportError as e:
                logger.debug("domain_pipelines_not_found", domain=name, error=str(e))
```

**Why this works**:
- `spine.domains` is importable because `src/` is in PYTHONPATH
- Registry now discovers any domain in `src/spine/domains/{name}/`
- `spine/domains/otc/__init__.py` already imports `pipelines`, so registration happens

**Alternative (simpler)**:
```python
def _load_pipelines() -> None:
    """Load all pipeline modules to trigger registration."""
    # Explicit import - simpler, more maintainable
    try:
        import spine.domains.otc.pipelines  # noqa: F401
        logger.debug("domain_pipelines_loaded", domain="otc")
    except ImportError as e:
        logger.debug("domain_pipelines_not_found", domain="otc", error=str(e))
    
    # Add more domains here as needed:
    # import spine.domains.equity.pipelines
    # import spine.domains.options.pipelines
```

**Recommendation**: Use **explicit import approach** (simpler, clearer, easier to debug).

#### 1.2. Add Orientation Doc

**File**: Already created above as [docs/ORIENTATION.md](../docs/ORIENTATION.md)

#### 1.3. Test Registry

**Verification**:
```powershell
# Clear any cached imports
python -c "
import sys
# Remove cached modules
for mod in list(sys.modules.keys()):
    if 'market_spine.domains' in mod or 'spine.domains' in mod:
        del sys.modules[mod]

# Test registry
from market_spine.registry import list_pipelines
pipelines = list_pipelines()
print('Registered pipelines:')
for p in pipelines:
    print(f'  - {p}')

# Should see:
# - otc.aggregate_week
# - otc.backfill_range
# - otc.ingest_week
# - otc.normalize_week
# - otc.rolling_week
"
```

#### 1.4. Commit

```bash
git add src/market_spine/registry.py docs/ORIENTATION.md
git commit -m "fix: registry now discovers domains from spine.domains/

- Changed registry._load_pipelines() to import from spine.domains.*
- Removed discovery from market_spine/domains/ (legacy path)
- Added ORIENTATION.md with repo structure and entrypoints

This makes spine.domains.otc the canonical OTC implementation.
market_spine/domains/ is now unused and will be removed in next commit.
"
```

---

### Commit 2: Remove Duplicate Domain Code

**Goal**: Delete `src/market_spine/domains/` directory.

**Why safe**: Not imported by any working code (verified in Commit 1).

#### 2.1. Delete Directories

```powershell
# Remove old domain code
rm -r src/market_spine/domains/
rm -r src/market_spine/services/

# These are legacy structures, not used by new architecture
```

#### 2.2. Verify No Broken Imports

**Search for any remaining imports**:
```powershell
# Should return NO results
grep -r "from market_spine.domains" src/ tests/
grep -r "import market_spine.domains" src/ tests/
```

**If any found**: Update them to use `spine.domains` instead.

#### 2.3. Update pyproject.toml

**File**: [pyproject.toml](../pyproject.toml)

**Current**:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/market_spine"]
```

**New**:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/market_spine", "src/spine"]
```

**Why**: Package spine/ as part of the wheel (even though it's shareable library).

#### 2.4. Test Basic Commands

```powershell
# List pipelines (should still work)
spine pipeline list

# Should output:
# otc.aggregate_week
# otc.backfill_range
# otc.ingest_week
# otc.normalize_week
# otc.rolling_week

# Test ingest
spine run otc.ingest_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1 \
  --file-path data/finra/nms_tier1_2026-01-02.csv
```

#### 2.5. Commit

```bash
git add -A
git commit -m "refactor: remove duplicate domain code in market_spine/domains/

Deleted:
- src/market_spine/domains/otc/  (old OTC implementation)
- src/market_spine/domains/example/  (unused example)
- src/market_spine/services/  (empty legacy structure)

Canonical domain code is now ONLY in src/spine/domains/.

Updated pyproject.toml to package both market_spine and spine.

Verified: 'spine pipeline list' still shows all OTC pipelines.
"
```

---

### Commit 3: Fix Tests and Verify

**Goal**: Ensure all tests pass and add safeguards.

#### 3.1. Check Tests

```powershell
# Run tests
pytest tests/ -v

# Expected: All tests pass
# If failures: Update imports from market_spine.domains → spine.domains
```

#### 3.2. Add Registry Test

**File**: [tests/test_registry.py](../tests/test_registry.py) (create new)

```python
"""Test pipeline registry."""

import pytest
from market_spine.registry import list_pipelines, get_pipeline, clear_registry


def test_otc_pipelines_registered():
    """Verify OTC pipelines are registered."""
    pipelines = list_pipelines()
    
    expected = [
        "otc.aggregate_week",
        "otc.backfill_range",
        "otc.ingest_week",
        "otc.normalize_week",
        "otc.rolling_week",
    ]
    
    for name in expected:
        assert name in pipelines, f"Pipeline '{name}' not registered"


def test_pipeline_names_unique():
    """Ensure no duplicate pipeline registrations."""
    pipelines = list_pipelines()
    
    # Check for duplicates (e.g., old and new OTC both registering)
    assert len(pipelines) == len(set(pipelines)), \
        f"Duplicate pipeline names found: {pipelines}"


def test_get_pipeline():
    """Test retrieving a pipeline class."""
    cls = get_pipeline("otc.ingest_week")
    assert cls.name == "otc.ingest_week"
    assert cls.description
    assert hasattr(cls, "run")


def test_get_nonexistent_pipeline():
    """Test error when getting non-existent pipeline."""
    with pytest.raises(KeyError, match="Pipeline 'fake.pipeline' not found"):
        get_pipeline("fake.pipeline")
```

#### 3.3. Add Domain Purity Test (if missing)

**File**: [tests/test_domain_purity.py](../tests/test_domain_purity.py)

**Purpose**: Ensure domains don't import forbidden libraries (sqlite3, asyncpg, etc.).

```python
"""Test that domains remain pure (no forbidden imports)."""

import ast
from pathlib import Path

FORBIDDEN_IMPORTS = {
    "sqlite3",       # DB-specific
    "asyncpg",       # Async DB
    "psycopg2",      # DB-specific
    "celery",        # Task queue
    "redis",         # Cache/queue
    "boto3",         # AWS SDK
    "requests",      # HTTP client
    "httpx",         # HTTP client
    "fastapi",       # Web framework
    "flask",         # Web framework
}


def get_imports_from_file(filepath: Path) -> set[str]:
    """Extract all imported modules from a Python file."""
    with open(filepath) as f:
        tree = ast.parse(f.read(), filename=str(filepath))
    
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    
    return imports


def test_domain_purity():
    """Check that domain code doesn't import forbidden libraries."""
    domains_dir = Path(__file__).parent.parent / "src" / "spine" / "domains"
    
    if not domains_dir.exists():
        pytest.skip("spine/domains/ directory not found")
    
    violations = []
    
    for py_file in domains_dir.rglob("*.py"):
        if py_file.name == "__pycache__":
            continue
        
        imports = get_imports_from_file(py_file)
        forbidden = imports & FORBIDDEN_IMPORTS
        
        if forbidden:
            rel_path = py_file.relative_to(domains_dir.parent.parent)
            violations.append(f"{rel_path}: {', '.join(forbidden)}")
    
    assert not violations, \
        f"Domains have forbidden imports:\n" + "\n".join(violations)


def test_domains_use_spine_core():
    """Verify domains import from spine.core (not tier infrastructure)."""
    domains_dir = Path(__file__).parent.parent / "src" / "spine" / "domains"
    
    if not domains_dir.exists():
        pytest.skip("spine/domains/ directory not found")
    
    found_spine_core = False
    
    for py_file in domains_dir.rglob("*.py"):
        if "pipelines.py" not in py_file.name:
            continue
        
        with open(py_file) as f:
            content = f.read()
            if "from spine.core import" in content or "import spine.core" in content:
                found_spine_core = True
                break
    
    assert found_spine_core, \
        "No domain pipelines import from spine.core (check domain structure)"
```

#### 3.4. Run Full Test Suite

```powershell
# Run all tests
pytest tests/ -v --cov=src --cov-report=term-missing

# Should pass:
# - test_registry.py::test_otc_pipelines_registered
# - test_registry.py::test_pipeline_names_unique
# - test_domain_purity.py::test_domain_purity
# - test_domain_purity.py::test_domains_use_spine_core
# - All existing tests
```

#### 3.5. Verify End-to-End

```powershell
# Full OTC workflow test
spine db reset
spine db init

spine run otc.ingest_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1 \
  --file-path data/finra/nms_tier1_2026-01-02.csv

spine run otc.normalize_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1

spine run otc.aggregate_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1

# Check results
python query_otc.py
```

#### 3.6. Commit

```bash
git add tests/
git commit -m "test: add registry and domain purity tests

Added:
- tests/test_registry.py: Verify OTC pipelines register, no duplicates
- tests/test_domain_purity.py: Ensure domains don't import forbidden libs

All tests pass. End-to-end OTC workflow verified.

Cleanup complete: spine.domains.otc is now the only OTC implementation.
"
```

---

## Import Update Patterns

### If You Find Stale Imports

**Pattern to find**:
```python
from market_spine.domains.otc import ...
from market_spine.domains.otc.models import ...
from market_spine.domains.otc.pipelines import ...
```

**Replace with**:
```python
from spine.domains.otc import ...
from spine.domains.otc.connector import ...  # Note: no models.py in new structure
from spine.domains.otc.pipelines import ...
```

**Key differences in new structure**:

| Old (`market_spine/domains/otc/`) | New (`spine/domains/otc/`) |
|-----------------------------------|----------------------------|
| `models.py` | **No models.py** - uses dataclasses in calculations.py |
| `parser.py` | `connector.py` - parse FINRA files |
| Imports `from market_spine.domains.otc.models` | Imports `from spine.domains.otc.schema` |
| No `schema.py` | `schema.py` - DOMAIN, Tier, TABLES, STAGES |
| Uses old manifest API | Uses new WorkManifest(domain=...) API |

**Search commands**:
```bash
# Find all imports from old structure
grep -r "from market_spine.domains" src/ tests/

# Find imports of market_spine.domains anywhere
grep -r "import market_spine.domains" src/ tests/

# Should return ZERO results after cleanup
```

---

## Sanity Checklist (Run After Cleanup)

After completing all 3 commits, verify:

### 1. ✅ Registry Discovery

```powershell
python -c "from market_spine.registry import list_pipelines; print(list_pipelines())"
# Expected: ['otc.aggregate_week', 'otc.backfill_range', 'otc.ingest_week', 'otc.normalize_week', 'otc.rolling_week']
```

### 2. ✅ No Duplicate Registrations

```powershell
spine pipeline list
# Should show exactly 5 OTC pipelines (no duplicates)
```

### 3. ✅ Old Directories Removed

```powershell
# Should NOT exist
ls src/market_spine/domains/     # → Error: Path not found
ls src/market_spine/services/    # → Error: Path not found
```

### 4. ✅ Canonical Domain Exists

```powershell
# Should exist
ls src/spine/domains/otc/
# → calculations.py, connector.py, normalizer.py, pipelines.py, schema.py, __init__.py
```

### 5. ✅ No Stale Imports

```bash
grep -r "from market_spine.domains" src/ tests/
# → No results

grep -r "import market_spine.domains" src/ tests/
# → No results
```

### 6. ✅ Tests Pass

```powershell
pytest tests/ -v
# All tests pass, including:
# - test_registry.py::test_otc_pipelines_registered
# - test_registry.py::test_pipeline_names_unique
# - test_domain_purity.py::test_domain_purity
```

### 7. ✅ Database Init Works

```powershell
spine db reset
spine db init
# No errors
```

### 8. ✅ Ingest Pipeline Runs

```powershell
spine run otc.ingest_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1 \
  --file-path data/finra/nms_tier1_2026-01-02.csv
# Success
```

### 9. ✅ Normalize Pipeline Runs

```powershell
spine run otc.normalize_week --week-ending 2025-12-26 --tier NMS_TIER_1
# Success
```

### 10. ✅ Aggregate Pipeline Runs

```powershell
spine run otc.aggregate_week --week-ending 2025-12-26 --tier NMS_TIER_1
# Success, quality checks pass
```

### 11. ✅ Query Results

```powershell
python query_otc.py
# Shows venue shares for 2025-12-26
```

### 12. ✅ Core Tables Created

```powershell
sqlite3 spine.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'core_%'"
# → core_manifest
# → core_rejects
# → core_quality
```

### 13. ✅ Manifest Tracks Progress

```powershell
sqlite3 spine.db "SELECT domain, partition_key, stage, stage_rank FROM core_manifest WHERE domain='otc'"
# Shows INGESTED, NORMALIZED, AGGREGATED stages
```

### 14. ✅ Package Builds

```powershell
pip install -e .
# No errors
```

### 15. ✅ CLI Command Works

```powershell
spine --version
spine --help
spine pipeline list
# All work
```

---

## Rollback Plan (If Something Breaks)

If cleanup causes issues, rollback is simple:

```bash
# Undo last commit
git reset --soft HEAD~1

# Or revert all 3 commits
git revert HEAD~2..HEAD

# Or checkout before cleanup
git checkout <commit-before-cleanup>
```

**Safe because**:
- All changes are in version control
- No database schema changes
- No external dependencies changed
- Tests verify everything works before each commit

---

## Post-Cleanup: Adding New Domains

After cleanup, adding a new domain is straightforward:

1. **Create domain structure**:
   ```
   src/spine/domains/equity/
   ├── __init__.py
   ├── schema.py
   ├── connector.py
   ├── normalizer.py
   ├── calculations.py
   └── pipelines.py
   ```

2. **Update registry** (if using explicit imports):
   ```python
   # src/market_spine/registry.py
   def _load_pipelines():
       import spine.domains.otc.pipelines
       import spine.domains.equity.pipelines  # Add new domain
   ```

3. **Done** - pipelines auto-register via `@register_pipeline` decorator.

**That's it.** No more dealing with duplicate paths or legacy structures.

---

## Summary

**What we're doing**:
1. Change registry to load from `spine.domains/` (canonical path)
2. Delete `market_spine/domains/` (duplicate legacy code)
3. Add tests to prevent regressions

**What we're NOT doing**:
- Changing domain architecture (still thin domain, thick platform)
- Adding async, FastAPI, or packaging changes
- Modifying database schemas or migrations
- Changing how pipelines work

**Result**:
- Clean, single source of truth for domain code
- `spine.domains.otc` is the only OTC implementation
- Easy to add new domains in the future
- Clear separation: app layer vs shared library

**Risk level**: **Low** (old code wasn't being used anyway)

**Effort**: ~30 minutes, 3 small commits

**Benefit**: Eliminates confusion, simplifies codebase, enables cross-tier sharing
