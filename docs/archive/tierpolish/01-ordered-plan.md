# Basic Tier Polish - Ordered Plan

**Date:** January 3, 2026  
**Status:** Ready for Implementation

## Implementation Order

The parts will be executed in this order to minimize dependencies and allow for incremental testing:

### Phase 1: Foundation (Structure + Tooling)

#### **Task 1: Part E - Reorganize Domains Packaging Layout**
**Why first:** This affects all other work. Must be done before adding new features.

**Decision:** Option A - Single Domains Monorepo Package
```
packages/spine-domains/src/spine/domains/finra/otc_transparency/
```

**Rationale:**
- Simpler structure for managing multiple FINRA datasets
- Single `pyproject.toml` for all domains
- Easier to share utilities across FINRA domains
- Cleaner namespace packaging

**Actions:**
1. Create new structure: `packages/spine-domains/src/spine/domains/finra/otc_transparency/`
2. Move all files from `packages/spine-domains/finra/otc-transparency/src/spine/domains/finra/otc_transparency/`
3. Update `pyproject.toml` paths
4. Update all imports in `market-spine-basic`
5. Update tests
6. Remove old structure
7. Run full test suite to verify

**Files affected:**
- New: `packages/spine-domains/pyproject.toml`
- New: `packages/spine-domains/src/spine/domains/finra/otc_transparency/*.py`
- Modified: `market-spine-basic/pyproject.toml`
- Modified: All test files

---

#### **Task 2: Part F - Add Modern Tooling (Ruff, Pre-commit)**
**Why second:** Establishes code quality standards before writing new code.

**Actions:**
1. Add `ruff` to all `pyproject.toml` files
2. Create `.pre-commit-config.yaml` at workspace root
3. Configure ruff for formatting + linting
4. Add `pytest` configuration
5. Run `ruff format` on all existing code
6. Add CI commands to README

**New files:**
- `.pre-commit-config.yaml`
- `ruff.toml` (optional, can use pyproject.toml)

**Modified files:**
- `packages/spine-core/pyproject.toml`
- `packages/spine-domains/pyproject.toml`
- `market-spine-basic/pyproject.toml`
- `README.md`

---

### Phase 2: Error Handling & Validation

#### **Task 3: Part A1 - Add Parameter Validation Framework**
**Why third:** Foundation for improved CLI and error messages.

**Actions:**
1. Create exception types in `spine-core`:
   - `BadParamsError`
   - `PipelineNotFoundError` (might already exist)
   - `ValidationError`
2. Create `PipelineSpec` class with:
   - `required_params: dict[str, ParamDef]`
   - `optional_params: dict[str, ParamDef]`
   - `validate(params: dict) -> ValidationResult`
3. Create `ParamDef` with:
   - `name: str`
   - `type: type`
   - `description: str`
   - `validator: Callable | None`
   - `default: Any | None`
4. Add validators:
   - `file_exists(path)`
   - `enum_value(enum_class)`
   - `date_format(format_str)`
5. Update all 5 pipelines with `.spec` attribute

**New files:**
- `packages/spine-core/src/spine/framework/params.py`

**Modified files:**
- `packages/spine-core/src/spine/framework/exceptions.py`
- `packages/spine-domains/src/spine/domains/finra/otc_transparency/pipelines.py`

---

#### **Task 4: Part A2 & A3 - Improve CLI Help and Error Classification**
**Why fourth:** Uses the validation framework from Task 3.

**Actions:**
1. Update `spine run PIPELINE --help`:
   - Show required params from `.spec`
   - Show optional params with defaults
   - Show examples
   - Show notes about auto-detection
2. Update runner to call `.spec.validate()` before `.run()`
3. Update error handling chain:
   - `BadParamsError` → clear user message
   - `PipelineNotFoundError` → "pipeline not found"
   - Don't catch `KeyError` as "pipeline not found"
4. Update dispatcher logging:
   - Correct event names for each error type
   - Include error context

**Modified files:**
- `packages/spine-core/src/spine/cli.py`
- `packages/spine-core/src/spine/framework/runner.py`
- `packages/spine-core/src/spine/framework/dispatcher.py`

---

### Phase 3: CLI Enhancements

#### **Task 5: Part C - Add Built-in Verify/Query Commands**
**Why fifth:** Independent feature, can be added anytime.

**Actions:**
1. Add dependencies to `spine-core`:
   - No new deps needed (use stdlib `sqlite3`)
2. Create `spine verify` command:
   - `spine verify finra.otc_transparency --week YYYY-MM-DD --tier TIER`
   - Show counts for all tables
   - Show sample top symbols
   - Verify invariants
3. Create `spine query` command:
   - `spine query "SELECT ..." [--format table|json|csv]`
4. Add canned verifications for FINRA OTC:
   - Raw data count
   - Normalized data count
   - Symbol summaries count
   - Rolling metrics count
   - Capture ID consistency

**New files:**
- `packages/spine-core/src/spine/cli/verify.py`
- `packages/spine-core/src/spine/cli/query.py`

**Modified files:**
- `packages/spine-core/src/spine/cli.py` (add commands)

---

#### **Task 6: Part B - Add Interactive CLI with Rich**
**Why sixth:** Depends on param validation (Task 3) and verify commands (Task 5).

**Actions:**
1. Add dependencies:
   - `typer` (might already have)
   - `rich`
2. Create interactive mode:
   - `spine ui` or `spine` (no args)
3. Implement features:
   - Pipeline browser (searchable)
   - Guided param entry using `.spec`
   - Phase-based progress display
   - Clean execution summary
   - Recent executions view
4. Use `rich.progress` for phase tracking
5. Use `rich.table` for results
6. Use `rich.panel` for summaries

**New files:**
- `packages/spine-core/src/spine/cli/interactive.py`
- `packages/spine-core/src/spine/cli/progress.py`

**Modified files:**
- `packages/spine-core/src/spine/cli.py` (add ui command)
- `packages/spine-core/pyproject.toml` (add rich dependency)

---

#### **Task 7: Part D - Improve Backfill UX**
**Why seventh:** Uses progress tracking from Task 6.

**Actions:**
1. Update backfill pipeline logging:
   - Add `week_index`, `weeks_total` to context
   - Add `current_week_ending` to context
2. Add phase tracking:
   - Track: `ingest → normalize → aggregate → rolling`
   - Emit phase events
3. Improve error summary:
   - Collect all errors during run
   - Display clean summary at end
   - Return exit code 1 if any errors (but still process what we can)
4. Update interactive UI:
   - Show outer progress: `[week 2/3]`
   - Show inner phases
5. Add non-interactive progress option:
   - `--progress` flag for CLI

**Modified files:**
- `packages/spine-domains/src/spine/domains/finra/otc_transparency/pipelines.py`
- `packages/spine-core/src/spine/cli/interactive.py`

---

### Phase 4: Testing & Documentation

#### **Task 8: Add Comprehensive Tests**
**Why eighth:** Test all new features.

**New test files:**
- `tests/test_param_validation.py`
  - Test required param validation
  - Test optional param defaults
  - Test validators (file_exists, enum, date)
- `tests/test_error_handling.py`
  - Test BadParamsError on missing params
  - Test PipelineNotFoundError on unknown pipeline
  - Test error messages are correct
- `tests/test_verify_commands.py`
  - Test spine verify output
  - Test spine query output
  - Test invariant checks
- `tests/test_backfill_exit_codes.py`
  - Test backfill with missing file
  - Test exit code is non-zero on errors
  - Test summary includes all errors

**Modified test files:**
- Update existing tests to use new error types

---

#### **Task 9: Update Documentation**
**Why ninth:** Document all changes.

**Actions:**
1. Update `README.md`:
   - New commands section
   - Tooling setup (ruff, pre-commit)
   - CI commands
   - Interactive mode usage
2. Create `docs/CLI.md`:
   - All commands with examples
   - Interactive mode guide
   - Verify/query examples
3. Update `packages/spine-domains/README.md`:
   - New structure explanation
   - How to add more FINRA domains
4. Create `CONTRIBUTING.md`:
   - Code quality setup
   - Pre-commit hooks
   - Testing guidelines

**New files:**
- `docs/CLI.md`
- `CONTRIBUTING.md`

**Modified files:**
- `README.md`
- `packages/spine-domains/README.md`

---

#### **Task 10: Full Verification & Demo Transcript**
**Why last:** Validate everything works end-to-end.

**Actions:**
1. Run full test suite: `uv run pytest tests/`
2. Run ruff: `uv run ruff check .`
3. Test interactive mode:
   - Run `spine ui`
   - Select pipeline
   - Enter params guided
   - Watch phase progress
   - View summary
4. Test verify commands:
   - `spine verify finra.otc_transparency --week 2025-12-05`
   - `spine query "SELECT COUNT(*) FROM otc_raw"`
5. Test error handling:
   - Run pipeline with missing param
   - Verify correct error message
6. Create demo transcript showing:
   - Interactive run
   - Phase progress
   - Clean summary
   - Verify command output

**Deliverable:**
- `planning/basic-tier-polish/demo-transcript.md`

---

## Summary

**Total tasks:** 10  
**Estimated lines of code:**
- New: ~2,000 lines
- Modified: ~500 lines
- Tests: ~800 lines

**Key dependencies:**
```
typer (already have)
rich (new)
```

**Breaking changes:**
- Domain package import path changes (one-time migration)
- No API breaking changes

**Risk mitigation:**
- Each task has clear acceptance criteria
- Tests at each phase
- Incremental rollout
