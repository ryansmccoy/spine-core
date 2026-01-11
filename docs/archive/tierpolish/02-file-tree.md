# Basic Tier Polish - Proposed File Tree

**Date:** January 3, 2026

## Current Structure (Before)

```
spine-core/
├── market-spine-basic/
│   ├── pyproject.toml
│   ├── README.md
│   ├── src/
│   │   └── spine/
│   │       └── cli.py
│   ├── tests/
│   │   ├── domains/otc/
│   │   │   └── test_otc.py
│   │   ├── data_scenarios/
│   │   │   └── test_messy_data.py
│   │   ├── test_pipelines.py
│   │   ├── test_registry.py
│   │   └── ...
│   └── data/fixtures/otc/
│
├── packages/
│   ├── spine-core/
│   │   ├── pyproject.toml
│   │   └── src/spine/
│   │       ├── core/
│   │       │   └── db.py
│   │       └── framework/
│   │           ├── dispatcher.py
│   │           ├── registry.py
│   │           ├── runner.py
│   │           ├── pipelines/
│   │           │   └── base.py
│   │           └── logging/
│   │               ├── context.py
│   │               └── timing.py
│   │
│   └── spine-domains/
│       └── finra/
│           └── otc-transparency/
│               ├── pyproject.toml
│               ├── README.md
│               ├── docs/
│               │   ├── overview.md
│               │   ├── data_dictionary.md
│               │   ├── timing_and_clocks.md
│               │   └── pipelines.md
│               └── src/spine/domains/finra/otc_transparency/
│                   ├── __init__.py
│                   ├── schema.py
│                   ├── connector.py
│                   ├── normalizer.py
│                   ├── calculations.py
│                   └── pipelines.py
```

---

## Proposed Structure (After)

```
spine-core/
├── .pre-commit-config.yaml          # NEW: Pre-commit hooks
├── CONTRIBUTING.md                  # NEW: Development guidelines
├── README.md                        # MODIFIED: Add new commands, tooling
│
├── docs/                            # NEW: Documentation directory
│   └── CLI.md                       # NEW: CLI usage guide
│
├── planning/                        # NEW: Planning documents
│   └── basic-tier-polish/
│       ├── 00-requirements.md
│       ├── 01-ordered-plan.md
│       ├── 02-file-tree.md
│       └── demo-transcript.md       # To be created
│
├── market-spine-basic/
│   ├── pyproject.toml               # MODIFIED: Update domain dependency
│   ├── README.md
│   ├── src/spine/
│   │   └── cli.py
│   ├── tests/
│   │   ├── domains/finra/           # RENAMED: domains/otc → domains/finra
│   │   │   └── test_otc_transparency.py  # RENAMED: test_otc.py
│   │   ├── data_scenarios/
│   │   │   └── test_messy_data.py
│   │   ├── test_pipelines.py
│   │   ├── test_registry.py
│   │   ├── test_param_validation.py  # NEW: Param validation tests
│   │   ├── test_error_handling.py    # NEW: Error handling tests
│   │   ├── test_verify_commands.py   # NEW: Verify/query tests
│   │   └── test_backfill_exit_codes.py  # NEW: Backfill tests
│   └── data/fixtures/otc/
│
├── packages/
│   ├── spine-core/
│   │   ├── pyproject.toml           # MODIFIED: Add rich dependency
│   │   └── src/spine/
│   │       ├── core/
│   │       │   └── db.py
│   │       ├── framework/
│   │       │   ├── dispatcher.py    # MODIFIED: Error classification
│   │       │   ├── registry.py
│   │       │   ├── runner.py        # MODIFIED: Param validation
│   │       │   ├── exceptions.py    # NEW: Exception types
│   │       │   ├── params.py        # NEW: Parameter framework
│   │       │   ├── pipelines/
│   │       │   │   └── base.py      # MODIFIED: Add spec attribute
│   │       │   └── logging/
│   │       │       ├── context.py
│   │       │       └── timing.py
│   │       └── cli/                 # NEW: CLI module
│   │           ├── __init__.py
│   │           ├── interactive.py   # NEW: Interactive mode
│   │           ├── progress.py      # NEW: Progress tracking
│   │           ├── verify.py        # NEW: Verify commands
│   │           └── query.py         # NEW: Query commands
│   │
│   └── spine-domains/               # RESTRUCTURED: Monorepo layout
│       ├── pyproject.toml           # NEW: Single package for all domains
│       ├── README.md                # NEW: Domains package docs
│       └── src/spine/domains/
│           ├── __init__.py
│           └── finra/
│               ├── __init__.py
│               └── otc_transparency/
│                   ├── __init__.py
│                   ├── schema.py
│                   ├── connector.py
│                   ├── normalizer.py
│                   ├── calculations.py
│                   ├── pipelines.py  # MODIFIED: Add .spec to each pipeline
│                   └── docs/         # MOVED: From parent directory
│                       ├── overview.md
│                       ├── data_dictionary.md
│                       ├── timing_and_clocks.md
│                       └── pipelines.md
```

---

## File Changes Summary

### New Files (19)

#### Configuration & Tooling
1. `.pre-commit-config.yaml` - Pre-commit hook configuration
2. `CONTRIBUTING.md` - Development guidelines
3. `docs/CLI.md` - CLI documentation

#### Planning Documents
4. `planning/basic-tier-polish/00-requirements.md`
5. `planning/basic-tier-polish/01-ordered-plan.md`
6. `planning/basic-tier-polish/02-file-tree.md`
7. `planning/basic-tier-polish/demo-transcript.md` (to be created)

#### Core Framework
8. `packages/spine-core/src/spine/framework/exceptions.py` - Custom exceptions
9. `packages/spine-core/src/spine/framework/params.py` - Parameter validation framework
10. `packages/spine-core/src/spine/framework/cli/__init__.py`
11. `packages/spine-core/src/spine/framework/cli/interactive.py` - Interactive mode
12. `packages/spine-core/src/spine/framework/cli/progress.py` - Progress display
13. `packages/spine-core/src/spine/framework/cli/verify.py` - Verify commands
14. `packages/spine-core/src/spine/framework/cli/query.py` - Query commands

#### Domains Package
15. `packages/spine-domains/pyproject.toml` - Monorepo package config
16. `packages/spine-domains/README.md` - Domains documentation

#### Tests
17. `market-spine-basic/tests/test_param_validation.py`
18. `market-spine-basic/tests/test_error_handling.py`
19. `market-spine-basic/tests/test_verify_commands.py`
20. `market-spine-basic/tests/test_backfill_exit_codes.py`

### Modified Files (11)

1. `README.md` - Add tooling, new commands
2. `market-spine-basic/pyproject.toml` - Update dependency path
3. `packages/spine-core/pyproject.toml` - Add rich dependency
4. `packages/spine-core/src/spine/framework/dispatcher.py` - Error classification
5. `packages/spine-core/src/spine/framework/runner.py` - Param validation
6. `packages/spine-core/src/spine/framework/pipelines/base.py` - Add spec attribute
7. `packages/spine-domains/src/spine/domains/finra/otc_transparency/pipelines.py` - Add specs
8. `market-spine-basic/tests/domains/finra/test_otc_transparency.py` - Update imports
9. `market-spine-basic/tests/data_scenarios/test_messy_data.py` - Update imports
10. `market-spine-basic/tests/test_pipelines.py` - Update imports
11. `market-spine-basic/tests/test_registry.py` - Update imports

### Renamed/Moved Files (3)

1. `packages/spine-domains/finra/otc-transparency/` → `packages/spine-domains/src/spine/domains/finra/otc_transparency/`
2. `market-spine-basic/tests/domains/otc/` → `market-spine-basic/tests/domains/finra/`
3. `test_otc.py` → `test_otc_transparency.py`

### Deleted Directories (1)

1. `packages/spine-domains/finra/` - Old nested structure

---

## Directory Size Estimates

```
.pre-commit-config.yaml              ~50 lines
CONTRIBUTING.md                      ~200 lines
docs/CLI.md                          ~300 lines

packages/spine-core/src/spine/framework/
  exceptions.py                      ~100 lines
  params.py                          ~350 lines
  cli/
    interactive.py                   ~500 lines
    progress.py                      ~200 lines
    verify.py                        ~300 lines
    query.py                         ~150 lines

packages/spine-domains/
  pyproject.toml                     ~50 lines
  README.md                          ~150 lines
  src/spine/domains/finra/otc_transparency/
    pipelines.py (additions)         ~200 lines

tests/
  test_param_validation.py           ~300 lines
  test_error_handling.py             ~200 lines
  test_verify_commands.py            ~200 lines
  test_backfill_exit_codes.py        ~100 lines
```

**Total new code:** ~2,700 lines  
**Total modified code:** ~500 lines  
**Total test code:** ~800 lines

---

## Import Path Changes

### Before
```python
from spine.domains.finra.otc_transparency import schema
from spine.domains.finra.otc_transparency.pipelines import IngestWeekPipeline
```

### After
```python
# Same! No change needed due to namespace packaging
from spine.domains.finra.otc_transparency import schema
from spine.domains.finra.otc_transparency.pipelines import IngestWeekPipeline
```

The import paths remain the same because we're using proper namespace packaging with `__path__ = __import__('pkgutil').extend_path(__path__, __name__)`.

---

## Dependency Changes

### packages/spine-core/pyproject.toml

**Add:**
```toml
[project]
dependencies = [
    "typer>=0.9.0",
    "rich>=13.7.0",      # NEW
    # ... existing deps
]
```

### market-spine-basic/pyproject.toml

**Before:**
```toml
[tool.uv.sources]
spine-domains-finra-otc-transparency = { path = "../packages/spine-domains/finra/otc-transparency", editable = true }
```

**After:**
```toml
[tool.uv.sources]
spine-domains = { path = "../packages/spine-domains", editable = true }
```
