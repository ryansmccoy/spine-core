# Add Datasource Workflow

**Type:** Development  
**Duration:** 2-4 hours  
**Owner:** Engineering

---

## Trigger

When you need to integrate a new data source (vendor API, file connector, database).

---

## Prerequisites

- [ ] LLM agent or developer
- [ ] Access to source documentation
- [ ] Test credentials/sample data
- [ ] Read `llm-prompts/CONTEXT.md`

---

## Steps

### 1. Copy LLM Prompt

**Get the datasource implementation prompt:**
```bash
cat llm-prompts/prompts/A_DATASOURCE.md
```

**Provide to LLM with context:**
```
Context: [paste llm-prompts/CONTEXT.md]

Prompt: [paste A_DATASOURCE.md]

Datasource details:
- Name: sec_edgar
- Type: API
- Domain: sec.filings
- Authentication: API key
```

### 2. Create Source File

**Location:** `src/market_spine/domains/{domain}/sources/{source_name}.py`

**Template:**
```python
from market_spine.framework.sources import Source
from market_spine.framework.registry import SOURCES

@SOURCES.register("sec_edgar")
class SecEdgarSource(Source):
    def __init__(self, config: dict):
        self.validate_config(config)
        self.api_key = config["api_key"]
    
    def validate_config(self, config: dict):
        required = ["api_key"]
        missing = [f for f in required if f not in config]
        if missing:
            raise ValueError(f"Missing: {missing}")
    
    def fetch(self, params: dict) -> tuple[list[dict], list[dict]]:
        try:
            # Fetch logic here
            return data, []
        except Exception as e:
            anomaly = {
                "domain": "sec.filings",
                "stage": "INGEST",
                "severity": "ERROR",
                "category": "NETWORK",
                "message": str(e)
            }
            return [], [anomaly]
```

### 3. Write Tests

**Location:** `tests/test_sources.py`

```python
def test_sec_edgar_source_fetch():
    """Test SEC EDGAR source fetches data."""
    source = SOURCES.get("sec_edgar")({
        "api_key": "test_key"
    })
    
    data, anomalies = source.fetch({"cik": "0000320193"})
    
    assert len(data) > 0
    assert anomalies == []

def test_sec_edgar_source_network_error(mock_requests):
    """Test network error returns anomaly."""
    mock_requests.get.side_effect = ConnectionError()
    
    source = SOURCES.get("sec_edgar")({"api_key": "test"})
    data, anomalies = source.fetch({"cik": "0000320193"})
    
    assert data == []
    assert len(anomalies) == 1
    assert anomalies[0]["category"] == "NETWORK"
```

### 4. Document

**Create:** `docs/sources/SEC_EDGAR.md`

```markdown
# SEC EDGAR Source

## Overview
Fetches company filings from SEC EDGAR API.

## Configuration
- `api_key` (required): SEC API key
- `base_url` (optional): Override API endpoint

## Rate Limits
10 requests per second

## Example
```python
source = SOURCES.get("sec_edgar")({
    "api_key": "YOUR_KEY"
})
data, anomalies = source.fetch({"cik": "0000320193"})
```
```

### 5. Run Tests

```bash
pytest tests/test_sources.py::test_sec_edgar_source_fetch -v
```

### 6. Update README

Add to `README.md`:
```markdown
## Data Sources

- **FINRA OTC Transparency** (`finra_otc`) - Weekly OTC volume data
- **SEC EDGAR** (`sec_edgar`) - Company filings ← NEW
```

---

## Success Criteria

- [ ] Source class created and registered
- [ ] 5+ tests written and passing
- [ ] Documentation created
- [ ] README updated
- [ ] No anti-patterns (check `llm-prompts/ANTI_PATTERNS.md`)

---

## Review Checklist

Use `llm-prompts/prompts/E_REVIEW.md` to audit:

- [ ] Registry compliance (no if/elif factories)
- [ ] Error surfacing (returns anomalies, not exceptions)
- [ ] Idempotency (same params → same data)
- [ ] Tests cover success + failure cases
- [ ] Documentation complete

---

## References

- **Prompt:** `llm-prompts/prompts/A_DATASOURCE.md`
- **Context:** `llm-prompts/CONTEXT.md`
- **Anti-Patterns:** `llm-prompts/ANTI_PATTERNS.md`
- **Template:** `llm-prompts/templates/source.py`
