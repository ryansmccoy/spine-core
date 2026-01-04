# Phase 4: Testing Gaps

> Status: 🔴 Not Started | Priority: MEDIUM

## Goal

Ensure critical paths have automated coverage.

## Current Test Coverage

| Layer | File | Status |
|-------|------|--------|
| Services | `test_tier_normalizer.py` | ✅ Complete |
| Services | `test_parameter_resolver.py` | ✅ Complete |
| Services | `test_ingest_resolver.py` | ✅ Complete |
| Commands | `test_commands.py` | ✅ Partial (List, Describe) |
| API | (none) | ❌ Missing |
| CLI | (none) | ❌ Missing |

## What Is Missing

| Gap | Priority | Effort | Status |
|-----|----------|--------|--------|
| API endpoint tests (FastAPI TestClient) | High | Medium | ⬜ Not Started |
| CLI integration tests (Typer CliRunner) | Medium | Medium | ⬜ Not Started |
| RunPipelineCommand test (mocked dispatcher) | High | Low | ⬜ Not Started |
| Error path coverage (invalid tier, missing params) | Medium | Low | ⬜ Not Started |

## Files to Create

| File | Purpose | Status |
|------|---------|--------|
| `tests/test_api_health.py` | Health endpoint tests | ⬜ Not Started |
| `tests/test_api_pipelines.py` | Pipeline CRUD endpoint tests | ⬜ Not Started |
| `tests/test_api_query.py` | Query endpoint tests | ⬜ Not Started |
| `tests/test_api_capabilities.py` | Capabilities endpoint tests | ⬜ Not Started |

## Test Patterns

### API Test Example

```python
from fastapi.testclient import TestClient
from market_spine.api.app import app

client = TestClient(app)

def test_list_pipelines():
    response = client.get("/v1/pipelines")
    assert response.status_code == 200
    data = response.json()
    assert "pipelines" in data
    assert "count" in data

def test_pipeline_not_found():
    response = client.get("/v1/pipelines/nonexistent.pipeline")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["code"] == "PIPELINE_NOT_FOUND"
```

### CLI Test Example

```python
from typer.testing import CliRunner
from market_spine.cli import app

runner = CliRunner()

def test_query_weeks_invalid_tier():
    result = runner.invoke(app, ["query", "weeks", "--tier", "invalid"])
    assert result.exit_code == 1
    assert "Invalid" in result.stdout
```

## What Does NOT Change

- Existing unit tests remain
- No test framework changes (pytest stays)

## Why This Phase Exists

The command layer has tests; the API layer calling commands does not. A bug in request parsing or response mapping won't be caught.

---

## TODO

- [ ] Create `tests/test_api_health.py`
- [ ] Create `tests/test_api_pipelines.py`
- [ ] Create `tests/test_api_query.py`
- [ ] Create `tests/test_api_capabilities.py`
- [ ] Add RunPipelineCommand test with mocked Dispatcher
- [ ] Add error path tests for invalid tier values
- [ ] Add error path tests for missing required params
- [ ] Consider CLI integration tests (lower priority)
