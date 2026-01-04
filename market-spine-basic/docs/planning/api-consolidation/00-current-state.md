# Current State Summary

> Status: ✅ **COMPLETE** | Basic Tier API Consolidation Done (Jan 2026)

## Final State

All phases of the API consolidation are complete. CLI and API now share the same command layer.

### Services Layer (`market_spine/app/services/`)

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `tier.py` | `TierNormalizer` | Alias → canonical tier resolution | ✅ Complete |
| `params.py` | `ParameterResolver` | Merge params, validate dates, normalize tiers | ✅ Complete |
| `ingest.py` | `IngestResolver` | Derive file paths for ingest pipelines | ✅ Complete |

### Commands Layer (`market_spine/app/commands/`)

| File | Commands | Status |
|------|----------|--------|
| `pipelines.py` | `ListPipelinesCommand`, `DescribePipelineCommand` | ✅ Complete |
| `executions.py` | `RunPipelineCommand` | ✅ Complete |
| `queries.py` | `QueryWeeksCommand`, `QuerySymbolsCommand` | ✅ Complete |

### Models (`market_spine/app/models.py`)

- `ErrorCode` enum with 10 codes
- `CommandError` dataclass
- `Result` base class with `success` / `error` fields
- Domain models: `PipelineSummary`, `PipelineDetail`, `WeekInfo`, `SymbolInfo`, etc.
- Reserved async fields: `ExecutionStatus`, `poll_url`, `execution_id`

### API (`market_spine/api/`)

| Endpoint | Method | Handler |
|----------|--------|---------|
| `/health` | GET | Basic liveness |
| `/health/detailed` | GET | DB connectivity check |
| `/v1/capabilities` | GET | Tier feature flags |
| `/v1/pipelines` | GET | List pipelines (uses `ListPipelinesCommand`) |
| `/v1/pipelines/{name}` | GET | Describe pipeline (uses `DescribePipelineCommand`) |
| `/v1/pipelines/{name}/run` | POST | Execute pipeline (uses `RunPipelineCommand`) |
| `/v1/query/weeks` | GET | Query weeks (uses `QueryWeeksCommand`) |
| `/v1/query/symbols` | GET | Query symbols (uses `QuerySymbolsCommand`) |

### CLI (`market_spine/cli/commands/`)

| File | Uses Command | Status |
|------|--------------|--------|
| `run.py` | `RunPipelineCommand` | ✅ Refactored |
| `query.py` | `QueryWeeksCommand`, `QuerySymbolsCommand` | ✅ Refactored |
| `list_.py` | `ListPipelinesCommand`, `DescribePipelineCommand` | ✅ Refactored |

### Tests

| File | Coverage | Status |
|------|----------|--------|
| `test_api.py` | 25 tests - health, capabilities, pipelines, run, weeks, symbols, errors | ✅ |
| `test_commands.py` | 6 tests - ListPipelinesCommand, DescribePipelineCommand | ✅ |
| `test_tier_normalizer.py` | TierNormalizer service | ✅ |
| `test_parameter_resolver.py` | ParameterResolver service | ✅ |
| `test_ingest_resolver.py` | IngestResolver service | ✅ |

**Total: 98 tests passing, 3 skipped (domain purity)**

---

## Completed

- [x] CLI and API both use command layer (no duplicate logic)
- [x] All API errors use `ErrorCode` enum
- [x] `/v1/capabilities` returns tier and feature flags
- [x] API endpoints have TestClient coverage
- [x] No regressions in CLI behavior
