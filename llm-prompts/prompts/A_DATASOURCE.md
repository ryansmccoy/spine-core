# Prompt A: Add Datasource

**Use this prompt when:** Implementing a new data source (vendor API, file connector, database, etc.).

---

## Copy-Paste Prompt

```
I need to implement a new datasource for Market Spine.

CONTEXT:
- Read llm-prompts/CONTEXT.md first for repository structure
- Datasources live in: packages/spine-domains/src/spine/domains/{domain}/sources/{source_name}.py
- Sources are CALLED BY pipelines - they don't run standalone
- Factory pattern: create_source() returns configured source from environment

DATASOURCE DETAILS:
- Name: {source_name}
- Domain: {domain_name}
- Data type: {API / File / Database / Other}
- Update frequency: {Daily / Weekly / Real-time}
- Authentication: {API key / OAuth / None}

---

ARCHITECTURE PATTERN:

Sources fetch raw data; pipelines orchestrate the ingestion:

┌─────────────────────────────────────────────────────────────┐
│    CLI: spine run run {domain}.ingest_{data} -p symbol=X    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Pipeline: @register_pipeline("{domain}.ingest_{data}")     │
│    source = create_source()  # Factory from env config      │
│    data, anomalies = source.fetch(params)                   │
│    # ... validate, transform, insert to DB                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Source: AlphaVantageSource, PolygonSource, etc.            │
│    fetch() → (data, anomalies)                              │
│    validate_config() → check API key, etc.                  │
└─────────────────────────────────────────────────────────────┘

---

IMPLEMENTATION CHECKLIST:

### 1. Source Class
Location: `packages/spine-domains/src/spine/domains/{domain}/sources/{source_name}.py`

Required structure:
```python
"""
{SourceName} data source.

Fetches {description} from {vendor}.
Rate limits: {X requests/day, Y requests/minute}
"""
from typing import Any
import httpx

class RateLimiter:
    """Simple rate limiter for API calls."""
    def __init__(self, calls_per_minute: int = 5):
        ...
    def wait_if_needed(self) -> None:
        ...

class {SourceName}Source:
    """
    Fetches {description} from {vendor}.
    
    Config:
        api_key: API key for authentication
        base_url: Base URL (optional, has default)
        timeout: Request timeout in seconds (default: 30)
    """
    
    def __init__(self, config: dict[str, Any]):
        self.validate_config(config)
        self.api_key = config["api_key"]
        self.base_url = config.get("base_url", "https://default.url")
        self.timeout = config.get("timeout", 30)
        self._rate_limiter = RateLimiter(calls_per_minute=5)
    
    def validate_config(self, config: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate required config fields. Returns (is_valid, error_message)."""
        if "api_key" not in config:
            return False, "Missing required config: api_key"
        return True, None
    
    def fetch(self, params: dict[str, Any]) -> tuple[list[dict], list[dict]]:
        """
        Fetch data for given parameters.
        
        Args:
            params: Dict with symbol, date range, etc.
        
        Returns:
            (data, anomalies) tuple
            - data: List of records (empty on error)
            - anomalies: List of anomaly dicts (empty on success)
        """
        self._rate_limiter.wait_if_needed()
        
        try:
            response = self._make_request(params)
            data = self._parse_response(response, params)
            return data, []
        except httpx.TimeoutException as e:
            return [], [self._create_anomaly("NETWORK", f"Timeout: {e}", params)]
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return [], [self._create_anomaly("RATE_LIMIT", "Rate limit exceeded", params)]
            return [], [self._create_anomaly("NETWORK", f"HTTP {e.response.status_code}", params)]
    
    def _create_anomaly(self, category: str, message: str, params: dict) -> dict:
        return {
            "domain": "{domain}",
            "stage": "INGEST",
            "severity": "ERROR" if category != "RATE_LIMIT" else "WARN",
            "category": category,
            "message": message,
        }
```

### 2. Source Factory
Location: `packages/spine-domains/src/spine/domains/{domain}/sources/__init__.py`

```python
"""
{Domain} sources - provider-agnostic data fetching.

Usage:
    source = create_source()  # Auto-detect from env
    source = create_source("{source_name}")  # Explicit
    data, anomalies = source.fetch({"symbol": "AAPL"})
"""
import os
from .{source_name} import {SourceName}Source

class IngestionError(Exception):
    """Raised when data ingestion fails."""
    pass

_SOURCE_REGISTRY: dict[str, type] = {
    "{source_name}": {SourceName}Source,
}

def create_source(source_type: str | None = None):
    """Factory to create source based on type or environment."""
    if source_type:
        if source_type not in _SOURCE_REGISTRY:
            raise ValueError(f"Unknown source: {source_type}")
        # Get config from env
        ...
        return _SOURCE_REGISTRY[source_type](config)
    
    # Auto-detect from environment
    api_key = os.environ.get("{SOURCE_NAME}_API_KEY")
    if api_key:
        return {SourceName}Source({"api_key": api_key})
    
    raise ValueError("No {domain} source configured. Set {SOURCE_NAME}_API_KEY")
```

### 3. Ingestion Pipeline
Location: `packages/spine-domains/src/spine/domains/{domain}/pipelines.py`

```python
from datetime import datetime, UTC
from spine.framework.registry import register_pipeline
from spine.framework.pipelines import Pipeline, PipelineResult, PipelineStatus
from spine.framework.db import get_connection
from spine.domains.{domain}.sources import create_source, IngestionError

@register_pipeline("{domain}.ingest_{data}")
class Ingest{Data}Pipeline(Pipeline):
    """Ingest {data} from external sources."""
    
    name = "{domain}.ingest_{data}"
    description = "Fetch {data} from configured external sources"
    
    def run(self) -> PipelineResult:
        started = datetime.now(UTC)
        conn = get_connection()
        
        # 1. Create source via factory (provider-agnostic)
        try:
            source = create_source()
        except ValueError as e:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(UTC),
                error=str(e),
            )
        
        # 2. Fetch data
        data, anomalies = source.fetch(self.params)
        if anomalies:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                started_at=started,
                completed_at=datetime.now(UTC),
                error=anomalies[0]["message"],
            )
        
        # 3. Insert to database with capture_id
        capture_id = f"{domain}.{data}.{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
        # ... insert logic ...
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(UTC),
            metrics={"rows_inserted": len(data), "capture_id": capture_id},
        )
```

### 4. Register Pipeline in Framework
Location: `packages/spine-core/src/spine/framework/registry.py`

Add import to `_load_pipelines()`:
```python
def _load_pipelines() -> None:
    # ... existing domains ...
    
    # {Domain}: {description}
    try:
        import spine.domains.{domain}.pipelines  # noqa: F401
        logger.debug("domain_pipelines_loaded", domain="{domain}")
    except ImportError as e:
        logger.warning("domain_pipelines_not_found", domain="{domain}", error=str(e))
```

### 5. Error Handling
Map errors to anomaly categories:
| Error Type | Category | Severity |
|-----------|----------|----------|
| Network timeout | NETWORK | ERROR |
| HTTP 4xx | NETWORK | ERROR |
| HTTP 5xx | NETWORK | ERROR (retry) |
| Invalid response format | DATA_QUALITY | ERROR |
| Missing required fields | DATA_QUALITY | ERROR |
| Rate limit hit | RATE_LIMIT | WARN |
| Partial data | DATA_QUALITY | WARN |

### 6. Tests
Location: `packages/spine-domains/tests/{domain}/sources/test_{source_name}.py`

Required tests:
```python
class Test{SourceName}Source:
    def test_fetch_success(self, mock_api):
        """Happy path: valid response parsed correctly."""
        
    def test_fetch_network_error(self, mock_api):
        """Network error returns anomaly, not exception."""
        
    def test_fetch_invalid_response(self, mock_api):
        """Malformed response returns anomaly."""
        
    def test_fetch_rate_limit(self, mock_api):
        """Rate limit returns WARN anomaly."""
        
    def test_config_validation_missing_required(self):
        """Missing required config raises ValueError."""
        
    def test_config_validation_optional_defaults(self):
        """Optional config uses defaults."""
```

### 7. Documentation
Location: `docs/sources/{SOURCE_NAME}.md`

Required sections:
- Overview (what data, from where)
- Configuration (all params with types)
- Rate limits and quotas
- Example usage
- Error scenarios
- Troubleshooting

---

ANTI-PATTERNS TO AVOID:
- ❌ Creating standalone CLI commands for ingestion (use pipelines)
- ❌ Hardcoded credentials (use config from environment)
- ❌ Global state for rate limiting (use instance state)
- ❌ Swallowing exceptions (return anomalies)
- ❌ Returning None on error (return empty list + anomaly)
- ❌ Putting business logic in app tier commands
- ❌ Modifying spine-core base classes without escalation

---

EXPECTED FILES:
```
packages/spine-domains/src/spine/domains/{domain}/sources/{source_name}.py  [NEW]
packages/spine-domains/src/spine/domains/{domain}/sources/__init__.py       [NEW/UPDATE]
packages/spine-domains/src/spine/domains/{domain}/pipelines.py              [NEW/UPDATE]
packages/spine-core/src/spine/framework/registry.py                         [UPDATE - add import]
packages/spine-domains/tests/{domain}/sources/test_{source_name}.py         [NEW]
docs/sources/{SOURCE_NAME}.md                                               [NEW]
```

---

DEFINITION OF DONE:
- [ ] Source class with validate_config() and fetch() methods
- [ ] Source factory in sources/__init__.py with create_source()
- [ ] Ingestion pipeline registered via @register_pipeline
- [ ] Pipeline added to registry._load_pipelines()
- [ ] fetch() returns (data, anomalies) tuple
- [ ] Network errors → anomalies (not exceptions)
- [ ] Rate limiter for API sources
- [ ] 6+ tests written and passing
- [ ] Documentation created

PROCEED with Change Surface Map, then implementation.
```

---

## Checklist Summary

| Step | File | Action |
|------|------|--------|
| 1 | `sources/{name}.py` | Create source class with fetch() and validate_config() |
| 2 | `sources/__init__.py` | Add create_source() factory |
| 3 | `pipelines.py` | Add @register_pipeline ingestion pipeline |
| 4 | `registry.py` | Add import to _load_pipelines() |
| 5 | `tests/.../test_{name}.py` | Write 6+ tests |
| 6 | `docs/sources/{NAME}.md` | Write documentation |

---

## Workflow Integration (Multi-Source Ingestion)

When orchestrating multiple datasource pipelines with validation between steps, use the **Workflow** system.

### When to Use Workflow

| Scenario | Use |
|----------|-----|
| Single source ingestion | Pipeline only |
| Multiple sources, independent | Multiple pipelines (CLI or scheduler) |
| Multiple sources, dependent (A before B) | Workflow |
| Quality gates between ingestions | Workflow with lambda steps |

### Example: Multi-Source Workflow

```python
from spine.orchestration import Workflow, Step, StepResult


def validate_base_data(ctx, config):
    """Lambda: Validate base ingestion before enrichment."""
    result = ctx.get_output("ingest_base")
    if not result or result.get("row_count", 0) < 1000:
        return StepResult.fail("Insufficient base data", "QUALITY_GATE")
    return StepResult.ok(output={"base_ready": True})


MULTI_SOURCE_REFRESH = Workflow(
    name="{domain}.multi_source_refresh",
    domain="{domain}",
    description="Ingest from multiple sources with dependencies",
    steps=[
        # First: ingest base data (references registered pipeline)
        Step.pipeline("ingest_base", "{domain}.ingest_base"),
        
        # Validate before enrichment (lightweight lambda)
        Step.lambda_("validate_base", validate_base_data),
        
        # Second: ingest enrichment data (references registered pipeline)
        Step.pipeline("ingest_enrichment", "{domain}.ingest_enrichment"),
        
        # Third: merge sources (references registered pipeline)
        Step.pipeline("merge", "{domain}.merge_sources"),
    ],
)
```

**Key Points:**
- Each `Step.pipeline()` references a REGISTERED pipeline by name
- Lambda steps only VALIDATE - they don't fetch data
- Create all pipelines first (using this prompt), then create the workflow
- See [F_WORKFLOW.md](F_WORKFLOW.md) for full workflow implementation guide

### Tracking Multi-Source Execution

```python
from spine.core.manifest import WorkManifest

manifest = WorkManifest(
    conn,
    domain="workflow.{domain}.multi_source_refresh",
    stages=["STARTED", "BASE_INGESTED", "VALIDATED", "ENRICHED", "MERGED", "COMPLETED"]
)

# After workflow completes
manifest.advance_to(
    key={"date": "2025-01-09"},
    stage="COMPLETED",
    execution_id=result.run_id,
)
```

---

## Related Documents

- [../CONTEXT.md](../CONTEXT.md) - Repository structure
- [../ANTI_PATTERNS.md](../ANTI_PATTERNS.md) - What not to do
- [../templates/pipeline.py](../templates/pipeline.py) - Pipeline template
- [F_WORKFLOW.md](F_WORKFLOW.md) - Workflow implementation guide
