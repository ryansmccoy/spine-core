# Consolidation: Refactor Findings and Plan

**Date**: January 3, 2026  
**Phase**: Post-logging stabilization, pre-UI

---

## Executive Summary

Market Spine Basic is **functionally stable**:
- 54 tests passing
- Logging system complete with tracing
- End-to-end pipelines working
- Performance validated (12x improvement)

The codebase needs **documentation alignment** and **minor cleanup**:
- Root README is outdated
- Stray debug scripts in repo root
- Legacy docs should be archived
- Minor naming inconsistencies

This is a low-risk cleanup focused on making the codebase "boringly obvious."

---

## Key Architectural Truths (The Constitution)

These invariants are now documented and must be preserved:

1. **All pipeline execution goes through the Dispatcher**
2. **Domains never import from `market_spine`** (only from `spine.core`)
3. **Business logic lives in `calculations.py`** — Pipelines orchestrate, don't calculate
4. **Pipelines are idempotent** — Same params = same result
5. **Every row has lineage** — `execution_id`, `batch_id`, `capture_id`
6. **Logging uses stable event schema** — Dashboard-ready structured logs
7. **UTC timestamps everywhere** — ISO-8601 with Z suffix
8. **WorkManifest tracks stage progression** — No implicit state

---

## Refactor Findings

### Category 1: Outdated Documentation

| Finding | Location | Impact |
|---------|----------|--------|
| Root README shows old structure | `README.md` | Confuses new contributors |
| CLEANUP_PLAN.md is stale | `docs/CLEANUP_PLAN.md` | Already executed |
| CLEANUP_SUMMARY.md is stale | `docs/CLEANUP_SUMMARY.md` | Archive material |
| ORIENTATION.md overlaps new docs | `docs/ORIENTATION.md` | Consolidate or archive |
| PIT_IMPLEMENTATION_SUMMARY.md | Root | Archive material |

### Category 2: Stray Files

| Finding | Location | Action |
|---------|----------|--------|
| `check_dates.py` | Root | Delete (debug script) |
| `check_schema.py` | Root | Delete (debug script) |
| `query_otc.py` | Root | Move to `scripts/` or delete |

### Category 3: Minor Code Issues

| Finding | Location | Impact |
|---------|----------|--------|
| `bind_context` imported but not used | `runner.py` | Dead import |
| `idem` variable created but unused | Multiple pipelines | Minor noise |

### Category 4: Things That Are Already Good

| Finding | Status |
|---------|--------|
| Registry loads from `spine.domains` | ✅ Done |
| No `market_spine/domains/` folder | ✅ Cleaned |
| No `market_spine/services/` folder | ✅ Cleaned |
| Domain purity tests exist | ✅ Passing |
| Logging schema documented | ✅ Complete |

---

## Refactor Plan

### Phase 1: Documentation Alignment (No Code Changes)

**Goal**: Make README accurate and consolidate docs.

#### 1.1 Update Root README.md

Replace with accurate structure and examples:
- Remove references to `services/`, `otc.py`
- Add `spine/` library structure
- Fix pipeline names (`otc.ingest_week` not `otc_ingest`)
- Update quick start commands

#### 1.2 Archive Legacy Docs

Move to `docs/archive/`:
- `CLEANUP_PLAN.md`
- `CLEANUP_SUMMARY.md`
- `ORIENTATION.md` (content merged into new docs)
- Root `PIT_IMPLEMENTATION_SUMMARY.md`

### Phase 2: Remove Stray Files

**Goal**: Clean repo root.

Delete:
- `check_dates.py`
- `check_schema.py`
- `query_otc.py` (or move to `scripts/`)

### Phase 3: Minor Code Cleanup

**Goal**: Remove dead code.

#### 3.1 Remove Unused Imports

- `runner.py`: Remove `bind_context` import if unused

#### 3.2 Remove Unused Variables

- Review `idem` variable in pipelines (created but never used)

### Phase 4: Verify and Close

**Goal**: Ensure nothing broke.

- Run all 54 tests
- Manual smoke test: `spine run otc.ingest_week ...`
- Verify docs render correctly

---

## File Mapping

### Deletions

| File | Reason |
|------|--------|
| `check_dates.py` | Debug script, not needed |
| `check_schema.py` | Debug script, not needed |
| `query_otc.py` | Debug script, not needed |

### Moves

| From | To | Reason |
|------|-----|--------|
| `docs/CLEANUP_PLAN.md` | `docs/archive/CLEANUP_PLAN.md` | Historical reference |
| `docs/CLEANUP_SUMMARY.md` | `docs/archive/CLEANUP_SUMMARY.md` | Historical reference |
| `docs/ORIENTATION.md` | `docs/archive/ORIENTATION.md` | Superseded by new docs |
| `PIT_IMPLEMENTATION_SUMMARY.md` | `docs/archive/PIT_IMPLEMENTATION_SUMMARY.md` | Historical reference |

### Updates

| File | Change |
|------|--------|
| `README.md` | Complete rewrite with accurate structure |
| `runner.py` | Remove unused import (if confirmed) |

---

## Post-Refactor Checklist

After refactor, the following should be true:

### Clarity
- [ ] New contributor can understand structure from README
- [ ] No stray scripts in repo root
- [ ] All docs in `docs/` are current and linked

### Safety
- [ ] All 54 tests pass
- [ ] `spine db init` works
- [ ] `spine run otc.ingest_week ...` works
- [ ] No dead imports

### Maintainability
- [ ] Adding a new domain is documented
- [ ] Pipeline pattern is clear from examples
- [ ] Logging schema is documented

---

## What This Refactor Does NOT Do

- No behavior changes
- No performance tuning
- No new functionality
- No architecture redesign
- No schema changes
- No logging format changes

---

## Estimated Effort

| Phase | Time | Risk |
|-------|------|------|
| 1. Docs alignment | 15 min | None |
| 2. Remove stray files | 5 min | None |
| 3. Code cleanup | 5 min | Very low |
| 4. Verify | 5 min | None |
| **Total** | **30 min** | **Low** |
