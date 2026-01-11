# API & Command Layer Consolidation

> Status: ✅ **COMPLETE** (Jan 2026)

## Completed Actions

| # | Action | Phase | Status |
|---|--------|-------|--------|
| 1 | Refactor `cli/commands/query.py` to use `QueryWeeksCommand`, `QuerySymbolsCommand` | 1 | ✅ |
| 2 | Refactor `cli/commands/list_.py` to use `ListPipelinesCommand` | 1 | ✅ |
| 3 | Refactor `cli/commands/run.py` to use `RunPipelineCommand` | 1 | ✅ |
| 4 | Audit API error responses for consistency | 2 | ✅ |
| 5 | Create API tests with TestClient | 4 | ✅ |

## Optional Future Enhancements

| # | Action | Effort | Priority |
|---|--------|--------|----------|
| 1 | Add `api_version` to capabilities response | Trivial | Low |
| 2 | Document capability contract in README | Low | Low |

## Definition of Done for Basic Tier API ✅

- [x] CLI and API both use command layer (no duplicate logic)
- [x] All API errors use `ErrorCode` enum
- [x] `/v1/capabilities` documents all feature flags
- [x] API endpoints have TestClient coverage
- [x] No regressions in existing CLI behavior

## Phase Completion Checklist

### Phase 1: CLI → Command Refactor ✅
- [x] `query.py` refactored
- [x] `list_.py` refactored
- [x] `run.py` refactored
- [x] CLI tests pass
- [x] Manual smoke test

### Phase 2: API Surface Hardening ✅
- [x] Error codes audited
- [x] Reserved fields present

### Phase 3: Capabilities & Versioning ✅
- [x] Capability schema finalized

### Phase 4: Testing Gaps ✅
- [x] API health tests (in test_api.py)
- [x] API pipeline tests (in test_api.py)
- [x] API query tests (in test_api.py)
- [x] Error path coverage (in test_api.py)
