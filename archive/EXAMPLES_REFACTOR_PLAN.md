# Spine-Core Examples Refactor Plan

## Goals

1. **Smaller, focused examples** - Each example demonstrates ONE concept
2. **FeedSpine + EntitySpine focus** - Remove genai-spine and document-spine examples
3. **Mock API layer** - Examples use a `MockAPI` that mimics real behavior
4. **Integration tests** - Examples run as test cases via pytest

---

## Current State

### spine-core/examples/ (11 files)
```
examples/
├── ecosystem/
│   ├── 01_feedspine_pipeline.py      # Keep - demonstrates FeedSpine + Dispatcher
│   ├── 02_entityspine_workflow.py    # Keep - demonstrates EntitySpine + Dispatcher
│   ├── 03_genai_spine_tasks.py       # REMOVE
│   ├── 04_document_spine_ingestion.py # REMOVE
│   ├── 05_workflow_architecture.py   # Refactor - cross-spine workflow
│   ├── run_all.py                    # Refactor - update list
│   └── README.md                     # Update
├── 05_execution_infrastructure.py    # Keep - core infrastructure
├── fastapi_integration_example.py    # Keep - API example
├── feed_ingestion_example.py         # Keep
└── workflow_example.py               # Keep - recently fixed
```

### feedspine/examples/ (17 files)
Well organized, keep as-is but add integration test runner.

### entityspine/examples/ (20+ files)
Well organized, keep as-is but add integration test runner.

---

## Proposed Structure

### spine-core/examples/ (Refactored)

```
examples/
├── README.md                         # Overview and quick start
├── conftest.py                       # Pytest fixtures for mock data
├── run_all.py                        # Run all examples (updated)
│
├── 01_basics/                        # Foundation examples
│   ├── 01_workspec_basics.py         # WorkSpec creation
│   ├── 02_handler_registration.py    # HandlerRegistry usage
│   ├── 03_dispatcher_basics.py       # Basic Dispatcher usage
│   └── 04_run_lifecycle.py           # Run status and lifecycle
│
├── 02_executors/                     # Executor patterns
│   ├── 01_memory_executor.py         # In-memory execution
│   ├── 02_local_executor.py          # Sync execution
│   ├── 03_async_patterns.py          # Async handler patterns
│   └── 04_executor_selection.py      # Choosing the right executor
│
├── 03_workflows/                     # Workflow orchestration
│   ├── 01_simple_workflow.py         # Basic workflow
│   ├── 02_pipeline_vs_workflow.py    # When to use each
│   └── 03_error_handling.py          # Retry and failure patterns
│
├── 04_integration/                   # FeedSpine + EntitySpine
│   ├── 01_feedspine_pipeline.py      # Feed ingestion pattern
│   ├── 02_entityspine_workflow.py    # Entity resolution pattern
│   └── 03_cross_spine_workflow.py    # Combined workflow
│
├── 05_api/                           # FastAPI integration
│   ├── 01_runs_router.py             # Basic /runs API
│   ├── 02_task_submission.py         # Submit tasks via API
│   └── 03_monitoring_endpoints.py    # Status and metrics
│
└── mock/                             # Mock API layer
    ├── __init__.py
    ├── base.py                       # MockAPIBase class
    ├── feedspine_mock.py             # Mock FeedSpine operations
    ├── entityspine_mock.py           # Mock EntitySpine operations
    └── fixtures.py                   # Sample data (companies, filings)
```

---

## Mock API Design

### `examples/mock/base.py`

```python
"""Base mock API for examples."""
from dataclasses import dataclass
from typing import Any, Callable
import asyncio


@dataclass
class MockResponse:
    """Simulates API response."""
    data: Any
    latency_ms: float = 10
    success: bool = True
    error: str | None = None


class MockAPIBase:
    """Base class for mock APIs that mimic real behavior."""
    
    def __init__(self, latency_ms: float = 10, failure_rate: float = 0.0):
        self.latency_ms = latency_ms
        self.failure_rate = failure_rate
        self._call_count = 0
    
    async def _simulate_latency(self):
        """Simulate network latency."""
        await asyncio.sleep(self.latency_ms / 1000)
        self._call_count += 1
```

### `examples/mock/entityspine_mock.py`

```python
"""Mock EntitySpine API for examples."""
from .base import MockAPIBase, MockResponse
from .fixtures import MOCK_COMPANIES, MOCK_FILINGS


class MockEntitySpine(MockAPIBase):
    """Mock EntitySpine that mimics real resolution behavior."""
    
    async def resolve_by_cik(self, cik: str) -> MockResponse:
        """Resolve company by CIK."""
        await self._simulate_latency()
        company = MOCK_COMPANIES.get(cik)
        if company:
            return MockResponse(data=company, success=True)
        return MockResponse(data=None, success=False, error="Not found")
    
    async def resolve_by_ticker(self, ticker: str) -> MockResponse:
        """Resolve company by ticker symbol."""
        await self._simulate_latency()
        for cik, company in MOCK_COMPANIES.items():
            if company.get("ticker") == ticker:
                return MockResponse(data=company, success=True)
        return MockResponse(data=None, success=False, error="Not found")
    
    async def get_filings(self, cik: str, form_type: str = None) -> MockResponse:
        """Get SEC filings for a company."""
        await self._simulate_latency()
        filings = MOCK_FILINGS.get(cik, [])
        if form_type:
            filings = [f for f in filings if f.get("form") == form_type]
        return MockResponse(data=filings, success=True)
```

### `examples/mock/feedspine_mock.py`

```python
"""Mock FeedSpine API for examples."""
from .base import MockAPIBase, MockResponse
from .fixtures import MOCK_FEED_RECORDS


class MockFeedSpine(MockAPIBase):
    """Mock FeedSpine that mimics real feed collection behavior."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._collected_ids = set()
    
    async def collect(self, feed_name: str) -> MockResponse:
        """Collect records from a feed."""
        await self._simulate_latency()
        
        records = MOCK_FEED_RECORDS.get(feed_name, [])
        new_records = []
        duplicates = 0
        
        for record in records:
            if record["id"] in self._collected_ids:
                duplicates += 1
            else:
                self._collected_ids.add(record["id"])
                new_records.append(record)
        
        return MockResponse(data={
            "total_processed": len(records),
            "new": len(new_records),
            "duplicates": duplicates,
            "records": new_records,
        }, success=True)
```

### `examples/mock/fixtures.py`

```python
"""Mock data fixtures for examples."""

MOCK_COMPANIES = {
    "0000320193": {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "ticker": "AAPL",
        "exchange": "NASDAQ",
        "sic": "3571",
        "sic_description": "Electronic Computers",
        "state": "CA",
    },
    "0000789019": {
        "cik": "0000789019",
        "name": "Microsoft Corporation",
        "ticker": "MSFT",
        "exchange": "NASDAQ",
        "sic": "7372",
        "sic_description": "Prepackaged Software",
        "state": "WA",
    },
    "0001318605": {
        "cik": "0001318605",
        "name": "Tesla, Inc.",
        "ticker": "TSLA",
        "exchange": "NASDAQ",
        "sic": "3711",
        "sic_description": "Motor Vehicles & Passenger Car Bodies",
        "state": "TX",
    },
}

MOCK_FILINGS = {
    "0000320193": [
        {"accession": "0000320193-24-000081", "form": "10-K", "filed": "2024-11-01"},
        {"accession": "0000320193-24-000045", "form": "10-Q", "filed": "2024-08-01"},
        {"accession": "0000320193-24-000020", "form": "10-Q", "filed": "2024-05-01"},
    ],
}

MOCK_FEED_RECORDS = {
    "sec_filings": [
        {"id": "sec-001", "title": "Apple 10-K Filed", "cik": "0000320193"},
        {"id": "sec-002", "title": "Microsoft 10-Q Filed", "cik": "0000789019"},
    ],
    "market_data": [
        {"id": "mkt-001", "symbol": "AAPL", "price": 185.50, "volume": 45000000},
        {"id": "mkt-002", "symbol": "MSFT", "price": 415.75, "volume": 22000000},
    ],
}
```

---

## Integration Tests

### `tests/integration/test_examples.py`

```python
"""Integration tests that run examples as test cases."""
import pytest
import subprocess
import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


def get_example_files():
    """Discover all example Python files."""
    examples = []
    for folder in ["01_basics", "02_executors", "03_workflows", "04_integration", "05_api"]:
        folder_path = EXAMPLES_DIR / folder
        if folder_path.exists():
            for py_file in folder_path.glob("*.py"):
                if not py_file.name.startswith("_"):
                    examples.append((folder, py_file.name, py_file))
    return examples


@pytest.fixture(scope="session")
def examples_env():
    """Set up environment for examples."""
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(EXAMPLES_DIR.parent / "src")
    return env


class TestExamples:
    """Test suite that runs each example as a test case."""
    
    @pytest.mark.parametrize("folder,name,path", get_example_files(), 
                             ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else x)
    def test_example_runs(self, folder, name, path, examples_env):
        """Each example should run without errors."""
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            env=examples_env,
        )
        
        assert result.returncode == 0, f"{folder}/{name} failed:\n{result.stderr}"
    
    @pytest.mark.parametrize("folder,name,path", get_example_files(),
                             ids=lambda x: f"{x[0]}/{x[1]}" if isinstance(x, tuple) else x)  
    def test_example_has_docstring(self, folder, name, path):
        """Each example should have a module docstring."""
        content = path.read_text()
        assert content.strip().startswith('"""') or content.strip().startswith("'''"), \
            f"{folder}/{name} missing module docstring"
```

### Running Integration Tests

```bash
# Run all example integration tests
pytest tests/integration/test_examples.py -v

# Run specific folder
pytest tests/integration/test_examples.py -v -k "01_basics"

# Run with coverage
pytest tests/integration/test_examples.py --cov=spine --cov-report=term-missing
```

---

## Implementation Steps

### Phase 1: Clean Up (1 hour)
1. Remove `03_genai_spine_tasks.py` and `04_document_spine_ingestion.py`
2. Update `run_all.py` to exclude removed examples
3. Update `ecosystem/README.md`

### Phase 2: Create Mock Layer (2 hours)
1. Create `examples/mock/` directory structure
2. Implement `MockAPIBase`, `MockEntitySpine`, `MockFeedSpine`
3. Create `fixtures.py` with sample data

### Phase 3: Reorganize Examples (3 hours)
1. Create new folder structure
2. Break down existing examples into smaller focused files
3. Add comprehensive docstrings to each

### Phase 4: Integration Tests (1 hour)
1. Create `tests/integration/test_examples.py`
2. Add pytest markers for slow tests
3. Verify all examples pass

### Phase 5: Documentation (1 hour)
1. Update main README.md with examples section
2. Add README.md to each examples subfolder
3. Create examples/README.md with index

---

## Files to Remove

```
examples/ecosystem/03_genai_spine_tasks.py
examples/ecosystem/04_document_spine_ingestion.py
```

## Files to Create

```
examples/mock/__init__.py
examples/mock/base.py
examples/mock/entityspine_mock.py
examples/mock/feedspine_mock.py
examples/mock/fixtures.py
examples/conftest.py
examples/01_basics/01_workspec_basics.py
examples/01_basics/02_handler_registration.py
examples/01_basics/03_dispatcher_basics.py
examples/01_basics/04_run_lifecycle.py
examples/02_executors/01_memory_executor.py
examples/02_executors/02_local_executor.py
examples/02_executors/03_async_patterns.py
examples/03_workflows/01_simple_workflow.py
examples/03_workflows/02_pipeline_vs_workflow.py
examples/03_workflows/03_error_handling.py
examples/04_integration/01_feedspine_pipeline.py
examples/04_integration/02_entityspine_workflow.py
examples/04_integration/03_cross_spine_workflow.py
examples/05_api/01_runs_router.py
examples/05_api/02_task_submission.py
tests/integration/test_examples.py
```

---

## Success Criteria

- [ ] All examples run without external dependencies (use mocks)
- [ ] Each example demonstrates exactly ONE concept
- [ ] Each example has clear docstring explaining what it shows
- [ ] `pytest tests/integration/test_examples.py` passes
- [ ] No genai-spine or document-spine references remain
- [ ] Examples can be run individually or via `run_all.py`

---

## Notes

- Keep existing `fastapi_integration_example.py` as a full example
- Move ecosystem examples to `04_integration/` 
- The mock layer should be realistic enough to teach patterns
- Integration tests catch regressions when APIs change
