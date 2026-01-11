# Basic Tier Polish - Requirements

**Date:** January 3, 2026  
**Status:** Planning Phase

## Context

We have a working Basic tier:
- Pipelines run and logs are structured
- Tests pass (99)
- `spine list` renders cleanly

However, there are pain points visible in real runs that need to be addressed.

## Observed Issues

### 1. Misleading Error Messages
Running `spine run finra.otc_transparency.ingest_week -p week_ending=...` without `file_path` throws:
- `KeyError('file_path')`
- Gets mislabeled as: `runner.pipeline_not_found`
- Finally shows: `Pipeline not found: finra.otc_transparency.ingest_week`

**This is incorrect.** The pipeline exists; the params are missing.

Similar issue for missing `tier` in normalize/aggregate. Missing required params should be validated cleanly and reported as `BadParams/ValidationError`, not `pipeline-not-found`.

### 2. Data Verification Pain
People want to "verify data" after runs, but:
- DuckDB isn't installed
- Ad-hoc `python -c "... for row in ..."` is annoying and error-prone on Windows

### 3. Backfill UX Could Be Improved
Backfill runs show useful logs, but:
- Progress should be phase-based (not row-count percent)
- Errors should be summarized cleanly at the end ("missing file week_x", etc.)

## Goal

Do a final Basic-tier polish pass focused on:

1. ✅ **Correct param validation + correct error classification**
2. ✅ **Modern interactive CLI (awesome UX) with step-phase progress**
3. ✅ **First-class built-in verification / querying (SQLite)**
4. ✅ **Packaging/layout decision for domains scalability**
5. ✅ **Modern Python tooling best practices** (ruff, mypy optional, etc.) without overengineering

**DO NOT** add Intermediate features:
- ❌ Execution events table
- ❌ Celery backend
- ❌ Temporal
- etc.

Keep it **Basic**.

---

## Part A — Correct Error Handling + Param Validation (MUST FIX)

### A1) Add Explicit Parameter Schemas Per Pipeline

For each pipeline, define:
- **Required params** (e.g., ingest: `file_path`, `tier` (optional if detectable), `week_ending` (optional if derivable))
- **Optional params + defaults**
- **Validation rules** (file exists, enum values, date format)

Implement a shared mechanism in `spine-core`:
- `PipelineSpec` or `ParamSpec`
- Pipelines expose something like `spec = PipelineSpec(...)` or `@pipeline_params(...)`

### A2) CLI Uses Specs to Improve `--help`

Update `spine run PIPELINE --help` to show:
- Required params
- Optional params
- Examples (1–2)
- Notes about auto-detection (tier/week ending)

### A3) Runner/Dispatcher Error Classification

Fix the misleading error chain:
- Missing params must raise a `BadParamsError` (or similar)
- Pipeline registry lookup failure must raise `PipelineNotFoundError`
- Runner must not log `runner.pipeline_not_found` for `KeyError/ValueError` from inside pipeline logic

**Deliver:**
- Updated exception types
- Updated mapping from exception → log event name + CLI user message
- Tests:
  - Missing `file_path` shows "missing required param: file_path"
  - Missing `tier` shows "missing required param: tier"
  - Unknown pipeline still shows "pipeline not found"
- Ensure logs still include `error_message`, `error_type`, and stack when debug is enabled

---

## Part B — Interactive CLI (Modern, Awesome, Windows-Safe)

We want Basic to feel like a **product**.

### B1) Two Modes

**Non-interactive mode** remains compatible:
- `spine list`
- `spine run ...`
- `spine db init`

**Add interactive mode:**
- Either `spine` (no args) or `spine ui`

### B2) Interactive Features (MUST)

1. **Pipeline browser** (searchable list)
2. **Guided param entry** using pipeline param specs
   - Highlight required params
   - Detect file path existence live
   - For enums show a selection list
3. **Step-phase progress** (NO fake percent)
   - Show progress as `[phase i / N] PHASE_NAME`
   - For backfill: show outer progress `[week i / total]` plus inner phases
4. **Clean execution summary**
   - Status, duration, capture_id, key metrics
5. **Execution history view** (Basic-safe)
   - Query recent executions from existing executions table
   - Display the summary and key metrics (no new tables)

**Recommended libs:**
- `typer` + `rich`
- Optionally `textual` only if you can keep it stable and small

---

## Part C — Built-in "verify/query" Commands (Replace Ad-hoc DuckDB)

We need a first-class way to check results after a run.

### C1) Add `spine verify` (or `spine query`) Commands

**Examples:**
```bash
spine verify finra.otc_transparency --week 2025-12-05 --tier OTC
spine query "select count(*) from otc_raw"
```

**Must work on SQLite** without extra deps.

**Provide helpful canned verifications:**
- Counts per table (raw/normalized/summary)
- Sample top symbols for that week
- Verify invariants: normalized rows exist for capture_id, aggregates exist, rolling exists

**If you want optional DuckDB support**, it must be:
- Optional extra dependency
- And documented as such

But **default should be SQLite-only**.

---

## Part D — Backfill UX Improvements (Based on Real Output)

The backfill already works and emits metrics like:
- `weeks_processed`, `weeks_total`, `errors`, `batch_id`

**Improve:**
- **Log structure:** include `week_index`, `weeks_total`, `current_week_ending`
- **Interactive UI** should show:
  - Overall: `[week 2/3]`
  - Inner phases: `ingest → normalize → aggregate → rolling`
- **End summary:**
  - "Processed 2/3 weeks"
  - List missing files cleanly
  - Return non-zero exit code if any errors (but still run what it can)

**Add tests for:**
- Backfill with one missing file returns a clean summary and correct exit code semantics

---

## Part E — Domains Packaging/Layout Decision (Scales for More FINRA Data)

Current deep layout works but might get unwieldy:
```
packages/spine-domains/finra/otc-transparency/src/spine/domains/finra/otc_transparency
```

**You must choose the best scalable option** (either is fine):

### Option A (Single Domains Monorepo Package)
```
packages/spine-domains/src/spine/domains/finra/otc_transparency
```

### Option B (Family Package: FINRA)
```
packages/spine-domains-finra/src/spine/domains/finra/otc_transparency
```

**Pick one**, implement it, and update docs/imports accordingly.

Also ensure namespace packaging (`spine.domains.*`) is correct and stable.

---

## Part F — Modern Python Project Best Practices (Don't Overdo It)

Update project tooling to match modern standards.

**Must add:**
- `ruff` (format + lint)
- `pre-commit` config
- Consistent `pyproject.toml` configuration (ruff, pytest, mypy optional)
- Basic CI command set in README

**Optional if low friction:**
- `mypy` with a small strictness baseline
- `pyright` (probably too much unless already desired)

**Constraints:**
- Keep changes reviewable
- Do not break Windows dev workflow
- Keep `uv` as primary workflow

---

## Required Deliverables in Your Response

1. **Ordered plan**
2. **Proposed file tree**
3. **Unified diffs**
4. **New/updated docs summary** (README + CLI + domains layout)
5. **New tests summary** (what's added and why)
6. **Verification commands** (Windows + bash)
7. **A short "demo transcript":**
   - Interactive run of ingest/normalize/aggregate
   - Showing phase-based progress
   - Showing a nice summary at the end

---

## Success Criteria

- ✅ No more "Pipeline not found" when params are missing
- ✅ `spine run PIPELINE --help` clearly shows required params + examples
- ✅ Interactive CLI guides users correctly and shows phase progress
- ✅ Built-in `verify`/`query` works without DuckDB
- ✅ Domains packaging choice scales cleanly for more FINRA feeds
- ✅ Ruff + pre-commit are in place and documented
