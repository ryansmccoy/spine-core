# OpenAPI & Testing Strategy

> Last Updated: 2026-01-04  
> Version: 1.0  
> Status: **AUTHORITATIVE**

This document defines conventions for maintaining clean OpenAPI documentation and a comprehensive testing strategy for the Market Spine API.

---

## 1. OpenAPI Conventions

### FastAPI OpenAPI Generation

Market Spine uses FastAPI's automatic OpenAPI generation. The spec is available at:

- `/docs` — Swagger UI (interactive)
- `/redoc` — ReDoc (reference)
- `/openapi.json` — Raw OpenAPI 3.0 spec

### Maintaining Clean Documentation

#### Route Docstrings

Every endpoint must have a docstring that appears in OpenAPI:

```python
@router.get("/v1/data/calcs/{calc_name}")
async def query_calc(
    calc_name: str = Path(..., description="Calculation name with version suffix"),
    tier: str = Query(..., description="Tier: NMS_TIER_1, NMS_TIER_2, OTC"),
    week: str = Query(..., description="Week ending date (YYYY-MM-DD)"),
) -> QueryCalcResponse:
    """
    Query a specific calculation.
    
    Returns rows from the requested calculation, filtered by tier and week.
    Results are paginated and include capture metadata.
    
    **Example:**
    ```
    GET /v1/data/calcs/weekly_symbol_volume_by_tier_v1?tier=NMS_TIER_1&week=2025-12-22
    ```
    
    **Notes:**
    - Use explicit version suffix (e.g., `_v1`) for reproducibility
    - Omitting version returns the latest non-deprecated version
    - As-of queries: include `capture_id` parameter
    """
    ...
```

#### Response Models

Use Pydantic models with Field descriptions:

```python
class QueryCalcResponse(BaseModel):
    """Response from querying a calculation."""
    
    calc_name: str = Field(
        ..., 
        description="Full calculation name including version",
        example="weekly_symbol_volume_by_tier_v1"
    )
    calc_version: str = Field(
        ..., 
        description="Extracted version string",
        example="v1"
    )
    calc_deprecated: bool = Field(
        default=False,
        description="Whether this calc version is deprecated"
    )
    rows: list[dict] = Field(
        ..., 
        description="Query result rows"
    )
    pagination: PaginationInfo = Field(
        ..., 
        description="Pagination metadata"
    )
```

#### Tags for Organization

Group endpoints logically:

```python
# In route modules
router = APIRouter(tags=["Data Plane"])

# Or per-endpoint
@router.get("/calcs", tags=["Data Plane", "Discovery"])
async def list_calcs():
    ...
```

Standard tags:
- `Health` — Liveness/readiness checks
- `Discovery` — Capabilities, schema introspection
- `Control Plane` — Pipeline operations, execution management
- `Data Plane` — Data queries
- `Admin` — Tenant/user management (Full tier)

#### Error Response Documentation

Document error responses explicitly:

```python
from fastapi import HTTPException

@router.get(
    "/calcs/{calc_name}",
    responses={
        200: {"description": "Calculation results"},
        400: {"description": "Invalid parameters", "model": ErrorResponse},
        404: {"description": "Calculation not found", "model": ErrorResponse},
        409: {"description": "Data not ready", "model": ErrorResponse},
    }
)
async def query_calc(...):
    ...
```

### OpenAPI Spec Validation

Run schema validation in CI:

```bash
# Validate OpenAPI spec
uv run python -c "
import json
from openapi_spec_validator import validate_spec
spec = json.load(open('openapi.json'))
validate_spec(spec)
print('OpenAPI spec is valid')
"
```

### Versioning in OpenAPI

Include version info in the spec:

```python
app = FastAPI(
    title="Market Spine API",
    description="Analytics Pipeline System",
    version=__version__,  # From package
    openapi_tags=[
        {"name": "Health", "description": "Health and readiness checks"},
        {"name": "Discovery", "description": "API capabilities and schema discovery"},
        {"name": "Control Plane", "description": "Pipeline and execution management"},
        {"name": "Data Plane", "description": "Data queries and calculations"},
    ]
)
```

---

## 2. Testing Strategy

### Test Pyramid

```
                    ┌─────────────┐
                    │   E2E       │  ← Smoke tests, full stack
                   ┌┴─────────────┴┐
                   │  Integration  │  ← API + DB, multi-component
                  ┌┴───────────────┴┐
                  │    Contract     │  ← Response shape validation
                 ┌┴─────────────────┴┐
                 │       Unit        │  ← Commands, services, utilities
                └─────────────────────┘
```

### 2.1 Unit Tests

Test individual components in isolation.

**Location:** `tests/unit/`

**What to test:**
- Command handlers
- Service logic
- Utility functions
- Validators

**Example:**

```python
# tests/unit/test_query_calc_command.py

def test_query_calc_returns_rows():
    """QueryCalcCommand returns rows for valid request."""
    command = QueryCalcCommand()
    result = command.execute(QueryCalcRequest(
        calc_name="weekly_symbol_volume_by_tier_v1",
        filters={"tier": "NMS_TIER_1", "week": "2025-12-22"},
    ))
    
    assert result.success
    assert len(result.rows) > 0
    assert all("symbol" in row for row in result.rows)


def test_query_calc_invalid_tier_returns_error():
    """QueryCalcCommand returns error for invalid tier."""
    command = QueryCalcCommand()
    result = command.execute(QueryCalcRequest(
        calc_name="weekly_symbol_volume_by_tier_v1",
        filters={"tier": "INVALID", "week": "2025-12-22"},
    ))
    
    assert not result.success
    assert result.error.code == ErrorCode.INVALID_TIER
```

### 2.2 Contract Tests

Validate API response shapes match documented contracts.

**Location:** `tests/contract/`

**Purpose:** Ensure responses match TypeScript types / client expectations.

**Example:**

```python
# tests/contract/test_data_endpoints_contract.py

import pytest
from fastapi.testclient import TestClient
from jsonschema import validate

from market_spine.api.app import app

client = TestClient(app)

# Schema matching TypeScript interface
QUERY_CALC_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["calc_name", "calc_version", "rows", "pagination"],
    "properties": {
        "calc_name": {"type": "string"},
        "calc_version": {"type": "string"},
        "calc_deprecated": {"type": "boolean"},
        "query_time": {"type": "string", "format": "date-time"},
        "capture": {
            "type": "object",
            "properties": {
                "capture_id": {"type": "string"},
                "captured_at": {"type": "string"},
                "is_latest": {"type": "boolean"},
            }
        },
        "rows": {"type": "array"},
        "pagination": {
            "type": "object",
            "required": ["offset", "limit", "total", "has_more"],
            "properties": {
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "total": {"type": "integer"},
                "has_more": {"type": "boolean"},
            }
        }
    }
}


def test_query_calc_response_matches_contract():
    """GET /v1/data/calcs/{name} response matches documented schema."""
    response = client.get(
        "/v1/data/calcs/weekly_symbol_volume_by_tier_v1",
        params={"tier": "NMS_TIER_1", "week": "2025-12-22"}
    )
    
    assert response.status_code == 200
    validate(instance=response.json(), schema=QUERY_CALC_RESPONSE_SCHEMA)


def test_error_response_matches_contract():
    """Error responses have consistent structure."""
    response = client.get(
        "/v1/data/calcs/nonexistent_calc_v1",
        params={"tier": "NMS_TIER_1", "week": "2025-12-22"}
    )
    
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
```

### 2.3 Golden Response Tests

Validate specific queries produce expected output.

**Location:** `tests/golden/`

**Purpose:** Catch regressions in calculation logic.

**Example:**

```python
# tests/golden/test_weekly_volume_calc.py

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from market_spine.api.app import app

client = TestClient(app)
GOLDEN_DIR = Path(__file__).parent / "golden_responses"


def test_weekly_volume_matches_golden():
    """Weekly volume calc matches saved golden response."""
    response = client.get(
        "/v1/data/calcs/weekly_symbol_volume_by_tier_v1",
        params={"tier": "NMS_TIER_1", "week": "2025-12-22", "limit": 5}
    )
    
    assert response.status_code == 200
    actual = response.json()
    
    golden_file = GOLDEN_DIR / "weekly_volume_nms_tier1_2025-12-22.json"
    
    if golden_file.exists():
        expected = json.loads(golden_file.read_text())
        # Compare rows only (metadata may vary)
        assert actual["rows"] == expected["rows"]
    else:
        # First run: save golden file
        golden_file.write_text(json.dumps(actual, indent=2))
        pytest.skip("Golden file created, re-run to validate")
```

**Updating goldens:**

```bash
# Delete existing golden files to regenerate
rm tests/golden/golden_responses/*.json

# Run tests to regenerate
uv run pytest tests/golden/ -v

# Review and commit
git diff tests/golden/golden_responses/
```

### 2.4 Integration Tests

Test multiple components together with real database.

**Location:** `tests/integration/`

**Example:**

```python
# tests/integration/test_ingest_to_query.py

import pytest

from market_spine.app.commands.executions import RunPipelineCommand, RunPipelineRequest
from market_spine.app.commands.queries import QueryCalcCommand, QueryCalcRequest


@pytest.fixture
def seeded_db(test_db):
    """Database with ingested test data."""
    # Run ingest pipeline
    run = RunPipelineCommand()
    result = run.execute(RunPipelineRequest(
        pipeline="finra.otc_transparency.ingest_week",
        params={
            "week_ending": "2025-12-22",
            "tier": "NMS_TIER_1",
            "file": "tests/fixtures/otc/week_2025-12-22.psv",
        }
    ))
    assert result.success
    
    # Run normalize pipeline
    result = run.execute(RunPipelineRequest(
        pipeline="finra.otc_transparency.normalize_week",
        params={"week_ending": "2025-12-22", "tier": "NMS_TIER_1"}
    ))
    assert result.success
    
    return test_db


def test_query_reflects_ingested_data(seeded_db):
    """Query returns data that was just ingested."""
    query = QueryCalcCommand()
    result = query.execute(QueryCalcRequest(
        calc_name="weekly_symbol_volume_by_tier_v1",
        filters={"tier": "NMS_TIER_1", "week": "2025-12-22"},
    ))
    
    assert result.success
    assert result.total > 0
    
    # Verify known fixture data
    symbols = {row["symbol"] for row in result.rows}
    assert "AAPL" in symbols
```

### 2.5 End-to-End Smoke Tests

Test full stack via CLI and API.

**Location:** `scripts/smoke_test.py`

**Example:**

```python
#!/usr/bin/env python
"""
End-to-end smoke test for Market Spine Basic.

Validates:
1. CLI commands work
2. API endpoints respond correctly
3. Data flows from ingestion to query
"""

import subprocess
import sys
import time
import httpx

API_BASE = "http://localhost:8000"


def run_cli(*args):
    """Run CLI command and return output."""
    result = subprocess.run(
        ["uv", "run", "spine", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"CLI failed: {result.stderr}")
        sys.exit(1)
    return result.stdout


def test_health():
    """API health check."""
    print("Testing: GET /health")
    response = httpx.get(f"{API_BASE}/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    print("  ✓ Health OK")


def test_capabilities():
    """Capabilities discovery."""
    print("Testing: GET /v1/capabilities")
    response = httpx.get(f"{API_BASE}/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "basic"
    assert data["sync_execution"] is True
    print("  ✓ Capabilities OK")


def test_pipelines_list():
    """Pipeline listing."""
    print("Testing: GET /v1/pipelines")
    response = httpx.get(f"{API_BASE}/v1/pipelines")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    print(f"  ✓ Found {data['count']} pipelines")


def test_data_query():
    """Data query (if data exists)."""
    print("Testing: GET /v1/data/weeks")
    response = httpx.get(f"{API_BASE}/v1/data/weeks", params={"tier": "NMS_TIER_1"})
    assert response.status_code == 200
    data = response.json()
    print(f"  ✓ Found {data['count']} weeks")


def main():
    print("=" * 60)
    print("Market Spine Smoke Test")
    print("=" * 60)
    
    # Wait for API to be ready
    print("\nWaiting for API...")
    for _ in range(30):
        try:
            httpx.get(f"{API_BASE}/health", timeout=1)
            break
        except httpx.RequestError:
            time.sleep(1)
    else:
        print("API not available")
        sys.exit(1)
    
    print("\nRunning tests...\n")
    
    test_health()
    test_capabilities()
    test_pipelines_list()
    test_data_query()
    
    print("\n" + "=" * 60)
    print("All smoke tests passed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

---

## 3. Definition of Done

### Adding a New Endpoint

An endpoint is "done" when:

- [ ] **Route implemented** with proper HTTP method and path
- [ ] **Docstring written** with description, example, and notes
- [ ] **Response model defined** with Field descriptions
- [ ] **Error responses documented** in `responses={}` parameter
- [ ] **Unit tests** for the command/service layer
- [ ] **Contract test** validating response schema
- [ ] **OpenAPI reviewed** — check `/docs` renders correctly
- [ ] **README updated** (if user-facing change)

### Adding a New Calc

A calc is "done" when:

- [ ] **CalcDefinition registered** in CalcRegistry
- [ ] **SQL/query implemented** to produce the calc output
- [ ] **Output columns documented** in the definition
- [ ] **Version assigned** (e.g., `_v1` suffix)
- [ ] **Unit test** for the calculation logic
- [ ] **Golden test** for expected output
- [ ] **Queryable via API** at `/v1/data/calcs/{name}`
- [ ] **CLI support** via `spine query calc {name}`
- [ ] **Documentation updated** in API docs

### Deprecating an Endpoint/Calc

Deprecation is "done" when:

- [ ] **Deprecation flag set** (`deprecated=True`)
- [ ] **Deprecation message** with migration guidance
- [ ] **Replacement documented** (new endpoint/calc name)
- [ ] **Warning logged** when deprecated item is accessed
- [ ] **Timeline communicated** (minimum 2 releases before removal)
- [ ] **Clients notified** (changelog, release notes)

---

## 4. CI Pipeline Recommendations

### Test Stages

```yaml
# .github/workflows/test.yml

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      
      - name: Install dependencies
        run: uv sync
      
      - name: Unit tests
        run: uv run pytest tests/unit/ -v
      
      - name: Contract tests
        run: uv run pytest tests/contract/ -v
      
      - name: Golden tests
        run: uv run pytest tests/golden/ -v
      
      - name: Integration tests
        run: |
          uv run spine db init
          uv run pytest tests/integration/ -v
      
      - name: OpenAPI validation
        run: |
          uv run uvicorn market_spine.api.app:app --host 0.0.0.0 --port 8000 &
          sleep 5
          curl http://localhost:8000/openapi.json > openapi.json
          uv run python -c "
          import json
          from openapi_spec_validator import validate_spec
          validate_spec(json.load(open('openapi.json')))
          "
```

### Coverage Requirements

```ini
# pyproject.toml

[tool.coverage.run]
branch = true
source = ["market_spine"]

[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

---

## 5. Testing Tools

| Tool | Purpose |
|------|---------|
| `pytest` | Test framework |
| `pytest-cov` | Coverage reporting |
| `httpx` | HTTP client for smoke tests |
| `jsonschema` | JSON schema validation |
| `openapi-spec-validator` | OpenAPI spec validation |
| `pytest-asyncio` | Async test support |
| `factory_boy` | Test data factories |
| `freezegun` | Time mocking |

### Recommended pytest plugins

```toml
# pyproject.toml

[project.optional-dependencies]
test = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "jsonschema>=4.0",
    "openapi-spec-validator>=0.7",
]
```

---

## 6. Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| OpenAPI shows wrong types | Check Pydantic model field types |
| Response schema mismatch | Ensure `response_model=` matches return |
| Golden test drift | Delete golden file, regenerate, review diff |
| Contract test failing | Check if API response shape changed intentionally |
| Smoke test timeout | Increase wait time, check if API starts correctly |

### Debug Tips

```bash
# View actual OpenAPI spec
curl http://localhost:8000/openapi.json | jq .

# Compare response to schema
curl http://localhost:8000/v1/data/weeks?tier=NMS_TIER_1 | \
  python -c "import sys, json; print(json.dumps(json.load(sys.stdin), indent=2))"

# Run single test with output
uv run pytest tests/contract/test_data_endpoints.py::test_query_calc_response -v -s
```
