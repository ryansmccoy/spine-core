# Basic Tier Polish - Implementation Checklist

**Date:** January 3, 2026  
**Status:** Ready to Execute

## Progress Tracker

Use this checklist to track implementation progress.

---

## Phase 1: Foundation (Structure + Tooling)

### ✅ Task 1: Reorganize Domains Packaging Layout

**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** None

**Sub-tasks:**
- [ ] Create `packages/spine-domains/` directory structure
- [ ] Create `packages/spine-domains/pyproject.toml`
- [ ] Move source files to `packages/spine-domains/src/spine/domains/finra/otc_transparency/`
- [ ] Update namespace `__init__.py` files
- [ ] Update `market-spine-basic/pyproject.toml` dependency
- [ ] Update all test imports
- [ ] Run `uv sync`
- [ ] Run `uv run pytest tests/` (verify 99 tests pass)
- [ ] Remove old `packages/spine-domains/finra/` directory
- [ ] Commit: "refactor: reorganize domains as monorepo package"

**Validation:**
```bash
uv sync
uv run pytest tests/ -v
# Should see: 99 passed
```

---

### ✅ Task 2: Add Modern Tooling (Ruff, Pre-commit)

**Status:** Not Started  
**Estimated Time:** 20 minutes  
**Dependencies:** Task 1

**Sub-tasks:**
- [ ] Add ruff to `packages/spine-core/pyproject.toml`
- [ ] Add ruff to `packages/spine-domains/pyproject.toml`
- [ ] Add ruff to `market-spine-basic/pyproject.toml`
- [ ] Create `.pre-commit-config.yaml`
- [ ] Configure ruff rules (extend-select, ignore)
- [ ] Run `uv run ruff format .`
- [ ] Run `uv run ruff check .`
- [ ] Fix any linting issues
- [ ] Update README with tooling setup
- [ ] Commit: "chore: add ruff and pre-commit configuration"

**Validation:**
```bash
uv run ruff check .
uv run ruff format --check .
# Should see: All checks passed!
```

---

## Phase 2: Error Handling & Validation

### ✅ Task 3: Add Parameter Validation Framework

**Status:** Not Started  
**Estimated Time:** 60 minutes  
**Dependencies:** Task 2

**Sub-tasks:**
- [ ] Create `packages/spine-core/src/spine/framework/exceptions.py`
  - [ ] `BadParamsError`
  - [ ] `PipelineNotFoundError`
  - [ ] `ValidationError`
- [ ] Create `packages/spine-core/src/spine/framework/params.py`
  - [ ] `ParamDef` dataclass
  - [ ] `PipelineSpec` class
  - [ ] Validators: `file_exists`, `enum_value`, `date_format`
- [ ] Update `packages/spine-core/src/spine/framework/pipelines/base.py`
  - [ ] Add `spec: PipelineSpec | None` attribute
- [ ] Update all 5 pipelines with `.spec`:
  - [ ] `IngestWeekPipeline`
  - [ ] `NormalizeWeekPipeline`
  - [ ] `AggregateWeekPipeline`
  - [ ] `ComputeRollingPipeline`
  - [ ] `BackfillRangePipeline`
- [ ] Commit: "feat: add parameter validation framework"

**Validation:**
```python
# Test that specs are defined
from spine.domains.finra.otc_transparency.pipelines import IngestWeekPipeline
assert IngestWeekPipeline.spec is not None
assert 'file_path' in IngestWeekPipeline.spec.required_params
```

---

### ✅ Task 4: Improve CLI Help and Error Classification

**Status:** Not Started  
**Estimated Time:** 45 minutes  
**Dependencies:** Task 3

**Sub-tasks:**
- [ ] Update `packages/spine-core/src/spine/framework/runner.py`
  - [ ] Call `pipeline.spec.validate(params)` before `.run()`
  - [ ] Raise `BadParamsError` for validation failures
- [ ] Update `packages/spine-core/src/spine/framework/dispatcher.py`
  - [ ] Map `BadParamsError` → `execution.params_invalid` log event
  - [ ] Map `PipelineNotFoundError` → `execution.pipeline_not_found` log event
  - [ ] Don't catch generic `KeyError` as pipeline not found
- [ ] Update CLI help in `market-spine-basic/src/spine/cli.py`
  - [ ] Show required params from spec
  - [ ] Show optional params with defaults
  - [ ] Show 1-2 examples
- [ ] Test error messages
- [ ] Commit: "feat: improve error handling and CLI help"

**Validation:**
```bash
# Should show clear error, not "pipeline not found"
uv run spine run finra.otc_transparency.ingest_week
# Expected: "Missing required parameter: file_path"

# Should still work
uv run spine run finra.otc_transparency.ingest_week --help
# Expected: Shows required/optional params
```

---

## Phase 3: CLI Enhancements

### ✅ Task 5: Add Built-in Verify/Query Commands

**Status:** Not Started  
**Estimated Time:** 45 minutes  
**Dependencies:** Task 4

**Sub-tasks:**
- [ ] Create `packages/spine-core/src/spine/cli/` directory
- [ ] Create `packages/spine-core/src/spine/cli/__init__.py`
- [ ] Create `packages/spine-core/src/spine/cli/verify.py`
  - [ ] `verify_finra_otc_transparency(week, tier)` function
  - [ ] Count queries for all tables
  - [ ] Invariant checks
  - [ ] Sample data display
- [ ] Create `packages/spine-core/src/spine/cli/query.py`
  - [ ] `execute_query(sql, format)` function
  - [ ] Support formats: table, json, csv
- [ ] Add commands to main CLI
- [ ] Add tests in `tests/test_verify_commands.py`
- [ ] Commit: "feat: add verify and query commands"

**Validation:**
```bash
uv run spine verify finra.otc_transparency --week 2025-12-05 --tier OTC
# Expected: Shows table counts and sample data

uv run spine query "SELECT COUNT(*) FROM otc_raw"
# Expected: Shows result in table format
```

---

### ✅ Task 6: Add Interactive CLI with Rich

**Status:** Not Started  
**Estimated Time:** 90 minutes  
**Dependencies:** Task 3, Task 5

**Sub-tasks:**
- [ ] Add `rich>=13.7.0` to `packages/spine-core/pyproject.toml`
- [ ] Run `uv sync`
- [ ] Create `packages/spine-core/src/spine/cli/interactive.py`
  - [ ] Pipeline browser with `rich.table`
  - [ ] Guided param entry with `rich.prompt`
  - [ ] Enum selection with `rich.prompt.Confirm`
  - [ ] File path validation
- [ ] Create `packages/spine-core/src/spine/cli/progress.py`
  - [ ] Phase-based progress with `rich.progress`
  - [ ] No fake percentages
  - [ ] Context manager for phases
- [ ] Add execution history view
  - [ ] Query executions table
  - [ ] Display with `rich.table`
- [ ] Add `spine ui` command to main CLI
- [ ] Test on Windows
- [ ] Commit: "feat: add interactive CLI with rich"

**Validation:**
```bash
uv run spine ui
# Expected: Shows interactive pipeline browser
# Can select pipeline, enter params, see progress
```

---

### ✅ Task 7: Improve Backfill UX

**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** Task 6

**Sub-tasks:**
- [ ] Update `BackfillRangePipeline` in pipelines.py
  - [ ] Add `week_index`, `weeks_total` to log context
  - [ ] Add `current_week_ending` to context
  - [ ] Track phases per week
  - [ ] Collect errors during run
  - [ ] Return non-zero exit code if errors
- [ ] Update interactive UI for backfill
  - [ ] Show outer progress: `[week 2/3]`
  - [ ] Show inner phases
- [ ] Add clean error summary at end
- [ ] Add tests in `tests/test_backfill_exit_codes.py`
- [ ] Commit: "feat: improve backfill UX with phase tracking"

**Validation:**
```bash
uv run spine run finra.otc_transparency.backfill_range -p tier=OTC -p weeks_back=3
# Expected: Shows [week 1/3], [week 2/3], with phase progress
# Expected: Clean error summary at end
```

---

## Phase 4: Testing & Documentation

### ✅ Task 8: Add Comprehensive Tests

**Status:** Not Started  
**Estimated Time:** 60 minutes  
**Dependencies:** Tasks 3-7

**Sub-tasks:**
- [ ] Create `tests/test_param_validation.py`
  - [ ] Test required param validation
  - [ ] Test optional param defaults
  - [ ] Test file_exists validator
  - [ ] Test enum_value validator
  - [ ] Test date_format validator
- [ ] Create `tests/test_error_handling.py`
  - [ ] Test BadParamsError on missing param
  - [ ] Test PipelineNotFoundError on unknown pipeline
  - [ ] Test error messages are correct
  - [ ] Test log event names are correct
- [ ] Create `tests/test_verify_commands.py`
  - [ ] Test verify output format
  - [ ] Test query with different formats
  - [ ] Test invariant checks
- [ ] Create `tests/test_backfill_exit_codes.py`
  - [ ] Test exit code on errors
  - [ ] Test error summary
- [ ] Run full test suite
- [ ] Commit: "test: add comprehensive tests for new features"

**Validation:**
```bash
uv run pytest tests/ -v
# Expected: All tests pass (99 + new tests)
```

---

### ✅ Task 9: Update Documentation

**Status:** Not Started  
**Estimated Time:** 45 minutes  
**Dependencies:** Task 8

**Sub-tasks:**
- [ ] Create `docs/CLI.md`
  - [ ] All commands with examples
  - [ ] Interactive mode guide
  - [ ] Verify/query examples
- [ ] Update `README.md`
  - [ ] New commands section
  - [ ] Tooling setup (ruff, pre-commit)
  - [ ] CI commands
  - [ ] Quick start with interactive mode
- [ ] Update `packages/spine-domains/README.md`
  - [ ] New structure explanation
  - [ ] How to add more FINRA domains
- [ ] Create `CONTRIBUTING.md`
  - [ ] Code quality setup
  - [ ] Pre-commit hooks
  - [ ] Testing guidelines
  - [ ] Development workflow
- [ ] Commit: "docs: update documentation for new features"

**Validation:**
- [ ] All links work
- [ ] Code examples are correct
- [ ] Installation steps verified

---

### ✅ Task 10: Full Verification & Demo Transcript

**Status:** Not Started  
**Estimated Time:** 30 minutes  
**Dependencies:** Task 9

**Sub-tasks:**
- [ ] Run full test suite: `uv run pytest tests/ -v`
- [ ] Run ruff check: `uv run ruff check .`
- [ ] Run ruff format check: `uv run ruff format --check .`
- [ ] Test interactive mode end-to-end
- [ ] Test verify commands
- [ ] Test error handling
- [ ] Create demo transcript in `planning/basic-tier-polish/demo-transcript.md`
- [ ] Commit: "docs: add demo transcript"

**Validation:**
- [ ] All 99+ tests passing
- [ ] No linting errors
- [ ] Interactive mode works on Windows
- [ ] Demo transcript complete

---

## Final Checklist

Before marking as complete:

- [ ] All 10 tasks completed
- [ ] All tests passing
- [ ] Ruff checks passing
- [ ] Documentation updated
- [ ] Demo transcript created
- [ ] No breaking changes introduced
- [ ] Windows workflow verified
- [ ] Git history is clean (good commit messages)

---

## Rollback Plan

If issues arise:

1. **Task 1-2 issues:** Revert to git commit before reorganization
2. **Task 3-4 issues:** Keep new structure, revert params.py changes
3. **Task 5-7 issues:** Disable new CLI commands, keep error handling
4. **Task 8-10 issues:** Fix incrementally

Each task should be a clean commit for easy rollback.
