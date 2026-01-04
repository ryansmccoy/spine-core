# OTC Domain Plugin Architecture
## FINRA Weekly Summary (OTC Transparency)

> **Version:** 1.0.0  
> **Status:** Design Proposal  
> **Last Updated:** 2026-01-02

---

## Table of Contents

1. [FINRA Dataset Overview](#1-finra-dataset-overview)
2. [Proposed File Tree](#2-proposed-file-tree)
3. [Connector Interface](#3-connector-interface)
4. [Normalizer Interface](#4-normalizer-interface)
5. [Calculation Interface](#5-calculation-interface)
6. [Registry & Wiring](#6-registry--wiring)
7. [Pipelines](#7-pipelines)
8. [Schema Guidance](#8-schema-guidance)
9. [Testing Strategy](#9-testing-strategy)
10. [Worked Example: liquidity_score_v1](#10-worked-example-liquidity_score_v1)
11. [Developer Workflow](#11-developer-workflow)

---

## 1. FINRA Dataset Overview

### 1.1 API Fundamentals

| Property | Value |
|----------|-------|
| **Base URL** | `https://api.finra.org` |
| **Dataset Group** | `otcMarket` |
| **Endpoint Pattern** | `GET /data/group/{group}/name/{dataset}` |
| **Paging** | `limit` / `offset` query params |
| **Auth** | API key header (if required) |

### 1.2 Available Datasets

| Dataset Name | Description | Data Window |
|--------------|-------------|-------------|
| `weeklySummary` | Rolling 12 months of weekly OTC summary | ~52 weeks |
| `weeklySummaryHistoric` | Rolling ~4 years of historical data | ~208 weeks |

### 1.3 Query Rules for `weeklySummaryHistoric`

**MUST use exactly ONE of:**

| Filter | Format | Example | Notes |
|--------|--------|---------|-------|
| `weekStartDate` | `yyyy-MM-dd` | `2025-12-29` | Must be a Monday |
| `historicalWeek` | `yyyy-Www` | `2025-W52` | ISO week number |
| `historicalMonth` | `yyyy-MMM` | `2025-Dec` | Three-letter month |

**MAY also filter by:**
- `tierIdentifier` (e.g., `"OTC"`, `"OTCBB"`, `"PINK"`)

**NOT supported:**
- Sorting
- Other filters beyond the above
- Combining multiple date filters

### 1.4 Historical Data Behavior

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     FINRA DATA FRESHNESS                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ◄──────── STATIC (>1 year old) ────────►│◄── ROLLING (≤1 year) ──►   │
│                                            │                             │
│   • Data does not change                   │ • Data may update weekly    │
│   • Don't repeatedly re-download           │ • Re-capture each week      │
│   • Store capture_date, never refresh      │ • Upsert with latest        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.5 Async API Mode

For large historic downloads that may timeout:

1. **Submit job** → returns `jobId`
2. **Poll status** → wait for `COMPLETE`
3. **Download result** → fetch paginated results

---

## 2. Proposed File Tree

```
app/
└── domains/
    └── otc/
        ├── __init__.py
        ├── contracts.py                  # Pydantic models + Protocols
        ├── registry.py                   # Plugin registries
        ├── exceptions.py                 # Domain exceptions
        │
        ├── connectors/
        │   ├── __init__.py
        │   ├── base.py                   # BaseConnector, HTTP utilities
        │   ├── finra_client.py           # Low-level FINRA API client
        │   ├── finra_weekly_summary.py   # weeklySummary connector
        │   └── finra_weekly_historic.py  # weeklySummaryHistoric connector
        │
        ├── normalizers/
        │   ├── __init__.py
        │   ├── base.py                   # Base normalizer utilities
        │   ├── weekly_summary_v1.py      # V1 normalizer
        │   └── weekly_summary_v2.py      # V2 normalizer (future)
        │
        ├── calculations/
        │   ├── __init__.py
        │   ├── base.py                   # Base calc utilities
        │   ├── weekly_volume_v1.py       # Weekly volume aggregation
        │   ├── tier_breakdown_v1.py      # Volume by tier
        │   └── liquidity_score_v1.py     # Liquidity scoring
        │
        ├── pipelines/
        │   ├── __init__.py
        │   ├── capture_raw.py            # Raw capture pipeline
        │   ├── normalize.py              # Normalization pipeline
        │   └── compute_metrics.py        # Metrics computation pipeline
        │
        ├── repositories/
        │   ├── __init__.py
        │   ├── raw_weekly.py             # Bronze layer
        │   ├── weekly_summary.py         # Silver layer
        │   └── weekly_metrics.py         # Gold layer
        │
        ├── fixtures/
        │   ├── __init__.py
        │   ├── loader.py
        │   ├── connectors/
        │   │   ├── finra_weekly_summary_page1.json
        │   │   ├── finra_weekly_summary_page2.json
        │   │   └── finra_weekly_historic_2025W52.json
        │   ├── normalizers/
        │   │   ├── raw_weekly_v1.json
        │   │   └── expected_weekly_v1.json
        │   └── calculations/
        │       ├── weekly_input.json
        │       └── liquidity_score_expected.json
        │
        └── tests/
            ├── __init__.py
            ├── conftest.py
            ├── connectors/
            │   ├── test_finra_client.py
            │   └── test_finra_weekly.py
            ├── normalizers/
            │   └── test_weekly_summary_v1.py
            ├── calculations/
            │   └── test_liquidity_score.py
            └── pipelines/
                └── test_pipeline_integration.py
```

---

## 3. Connector Interface

### 3.1 Core Contracts

```python
# app/domains/otc/contracts.py

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, Any
from uuid import UUID

from pydantic import BaseModel, Field, computed_field
import hashlib
import json


class FINRADataset(str, Enum):
    """Available FINRA OTC datasets."""
    WEEKLY_SUMMARY = "weeklySummary"
    WEEKLY_SUMMARY_HISTORIC = "weeklySummaryHistoric"


class HistoricQueryMode(str, Enum):
    """Query mode for weeklySummaryHistoric."""
    WEEK_START_DATE = "weekStartDate"      # yyyy-MM-dd (Monday)
    HISTORICAL_WEEK = "historicalWeek"     # yyyy-Www
    HISTORICAL_MONTH = "historicalMonth"   # yyyy-MMM


class OTCTier(str, Enum):
    """FINRA OTC tier identifiers."""
    OTC = "OTC"
    OTCBB = "OTCBB"
    PINK = "PINK"
    GREY = "GREY"


# =============================================================================
# RAW CAPTURE MODELS
# =============================================================================

class RawWeeklyRecord(BaseModel):
    """Single raw record from FINRA weekly summary API."""
    
    source: str = Field(default="finra_otc")
    dataset: FINRADataset
    raw_payload: dict[str, Any]
    captured_at: datetime
    
    @computed_field
    @property
    def record_hash(self) -> str:
        """Deterministic hash for deduplication."""
        # Key fields that define uniqueness
        key_fields = {
            "weekStartDate": self.raw_payload.get("weekStartDate"),
            "securityName": self.raw_payload.get("securityName"),
            "symbol": self.raw_payload.get("symbol"),
            "tierIdentifier": self.raw_payload.get("tierIdentifier"),
        }
        canonical = json.dumps(key_fields, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


class CaptureBatch(BaseModel):
    """Result of a connector capture operation."""
    
    batch_id: UUID
    connector_name: str
    connector_version: str
    dataset: FINRADataset
    captured_at: datetime
    records: list[RawWeeklyRecord] = Field(default_factory=list)
    
    # Query metadata
    query_params: dict[str, Any] = Field(default_factory=dict)
    page_count: int = 0
    total_records_fetched: int = 0
    
    # Async job info (if used)
    job_id: str | None = None
    job_mode: bool = False
    
    @property
    def record_count(self) -> int:
        return len(self.records)
```

### 3.2 Connector Protocol

```python
# app/domains/otc/contracts.py (continued)

class ConnectorParams(BaseModel):
    """Base connector parameters."""
    pass


class WeeklySummaryParams(ConnectorParams):
    """Parameters for weeklySummary (rolling 12 months)."""
    
    tier: OTCTier | None = None
    limit: int = Field(default=5000, ge=1, le=10000)


class WeeklyHistoricParams(ConnectorParams):
    """
    Parameters for weeklySummaryHistoric.
    
    MUST specify exactly one of: week_start_date, historical_week, historical_month
    """
    
    # Exactly one required
    week_start_date: date | None = None       # Must be Monday, yyyy-MM-dd
    historical_week: str | None = None        # yyyy-Www format
    historical_month: str | None = None       # yyyy-MMM format
    
    # Optional filter
    tier: OTCTier | None = None
    
    # Paging
    limit: int = Field(default=5000, ge=1, le=10000)
    
    # Async mode for large requests
    use_async: bool = False
    async_poll_interval: int = Field(default=5, ge=1, le=60)
    async_timeout: int = Field(default=300, ge=30, le=1800)
    
    def model_post_init(self, __context):
        """Validate exactly one date filter is provided."""
        filters = [
            self.week_start_date is not None,
            self.historical_week is not None,
            self.historical_month is not None,
        ]
        if sum(filters) != 1:
            raise ValueError(
                "Must specify exactly one of: week_start_date, "
                "historical_week, historical_month"
            )
        
        # Validate week_start_date is Monday
        if self.week_start_date and self.week_start_date.weekday() != 0:
            raise ValueError(
                f"week_start_date must be a Monday, got: {self.week_start_date}"
            )


class ConnectorProtocol(Protocol):
    """
    Protocol for FINRA OTC connectors.
    
    Responsibilities:
    - Fetch raw data from FINRA API
    - Handle paging, rate limiting, retries
    - Support sync and async (job) modes
    - Return CaptureBatch with RawWeeklyRecord objects
    
    Must NOT:
    - Write to database
    - Transform/normalize data
    - Import orchestration frameworks
    """
    
    @property
    def name(self) -> str: ...
    
    @property
    def version(self) -> str: ...
    
    @property
    def dataset(self) -> FINRADataset: ...
    
    def capture(self, params: ConnectorParams) -> CaptureBatch:
        """Capture raw data from FINRA API."""
        ...
    
    async def capture_async(self, params: ConnectorParams) -> CaptureBatch:
        """Async version of capture."""
        ...
```

### 3.3 FINRA Client (Low-Level)

```python
# app/domains/otc/connectors/finra_client.py

"""
Low-level FINRA API client.

Handles:
- Authentication
- Rate limiting / backoff
- Paging
- Sync vs Async job mode
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator
import time

import httpx

from app.domains.otc.exceptions import (
    FINRAAPIError,
    FINRARateLimitError,
    FINRATimeoutError,
)


@dataclass
class FINRAClientConfig:
    """FINRA API client configuration."""
    
    base_url: str = "https://api.finra.org"
    api_key: str | None = None
    
    # Rate limiting
    requests_per_second: float = 2.0
    retry_attempts: int = 3
    retry_backoff_base: float = 2.0
    
    # Timeouts
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    
    # Async job polling
    job_poll_interval: int = 5
    job_timeout: int = 300


class FINRAClient:
    """
    Low-level FINRA API client.
    
    Thread-safe, handles rate limiting and retries.
    """
    
    def __init__(self, config: FINRAClientConfig | None = None):
        self.config = config or FINRAClientConfig()
        self._last_request_time: float = 0
        self._client: httpx.Client | None = None
    
    def _get_client(self) -> httpx.Client:
        if self._client is None:
            headers = {"Accept": "application/json"}
            if self.config.api_key:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            
            self._client = httpx.Client(
                base_url=self.config.base_url,
                headers=headers,
                timeout=httpx.Timeout(
                    connect=self.config.connect_timeout,
                    read=self.config.read_timeout,
                ),
            )
        return self._client
    
    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        min_interval = 1.0 / self.config.requests_per_second
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()
    
    def fetch_page(
        self,
        group: str,
        dataset: str,
        params: dict[str, Any],
        offset: int = 0,
        limit: int = 5000,
    ) -> dict[str, Any]:
        """
        Fetch a single page from FINRA API.
        
        Returns:
            {"data": [...], "totalCount": N, ...}
        """
        self._rate_limit()
        
        query = {**params, "offset": offset, "limit": limit}
        url = f"/data/group/{group}/name/{dataset}"
        
        for attempt in range(self.config.retry_attempts):
            try:
                response = self._get_client().get(url, params=query)
                
                if response.status_code == 429:
                    wait = self.config.retry_backoff_base ** attempt
                    time.sleep(wait)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except httpx.TimeoutException as e:
                if attempt == self.config.retry_attempts - 1:
                    raise FINRATimeoutError(f"Request timeout: {e}") from e
                time.sleep(self.config.retry_backoff_base ** attempt)
            except httpx.HTTPStatusError as e:
                raise FINRAAPIError(f"HTTP {e.response.status_code}: {e}") from e
        
        raise FINRAAPIError("Max retries exceeded")
    
    def fetch_all_pages(
        self,
        group: str,
        dataset: str,
        params: dict[str, Any],
        limit: int = 5000,
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Iterate through all pages of results.
        
        Yields:
            List of records per page
        """
        offset = 0
        while True:
            result = self.fetch_page(group, dataset, params, offset, limit)
            data = result.get("data", [])
            
            if not data:
                break
            
            yield data
            
            total = result.get("totalCount", len(data))
            offset += limit
            if offset >= total:
                break
    
    # =========================================================================
    # ASYNC JOB MODE
    # =========================================================================
    
    def submit_async_job(
        self,
        group: str,
        dataset: str,
        params: dict[str, Any],
    ) -> str:
        """
        Submit an async job for large data requests.
        
        Returns:
            Job ID
        """
        self._rate_limit()
        
        url = f"/data/group/{group}/name/{dataset}/async"
        response = self._get_client().post(url, json=params)
        response.raise_for_status()
        
        return response.json()["jobId"]
    
    def poll_job_status(self, job_id: str) -> dict[str, Any]:
        """Check status of async job."""
        self._rate_limit()
        
        url = f"/data/async/status/{job_id}"
        response = self._get_client().get(url)
        response.raise_for_status()
        
        return response.json()
    
    def wait_for_job(
        self,
        job_id: str,
        poll_interval: int | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        Wait for async job to complete.
        
        Returns:
            Final job status with download URL
        """
        poll_interval = poll_interval or self.config.job_poll_interval
        timeout = timeout or self.config.job_timeout
        
        start = time.time()
        while time.time() - start < timeout:
            status = self.poll_job_status(job_id)
            
            if status.get("status") == "COMPLETE":
                return status
            elif status.get("status") == "FAILED":
                raise FINRAAPIError(f"Job failed: {status.get('error')}")
            
            time.sleep(poll_interval)
        
        raise FINRATimeoutError(f"Job {job_id} timed out after {timeout}s")
    
    def download_job_result(
        self,
        job_id: str,
        limit: int = 5000,
    ) -> Iterator[list[dict[str, Any]]]:
        """Download paginated results from completed async job."""
        offset = 0
        while True:
            self._rate_limit()
            
            url = f"/data/async/result/{job_id}"
            response = self._get_client().get(
                url, 
                params={"offset": offset, "limit": limit}
            )
            response.raise_for_status()
            
            result = response.json()
            data = result.get("data", [])
            
            if not data:
                break
            
            yield data
            
            offset += limit
            if offset >= result.get("totalCount", len(data)):
                break
```

### 3.4 Weekly Summary Connector

```python
# app/domains/otc/connectors/finra_weekly_summary.py

"""
Connector for FINRA weeklySummary dataset (rolling 12 months).
"""

from datetime import datetime
from uuid import uuid4

from app.domains.otc.contracts import (
    ConnectorProtocol,
    FINRADataset,
    WeeklySummaryParams,
    CaptureBatch,
    RawWeeklyRecord,
)
from app.domains.otc.connectors.finra_client import FINRAClient
from app.core.time import utc_now


class FINRAWeeklySummaryConnector:
    """Connector for weeklySummary (rolling 12 months)."""
    
    name: str = "finra_weekly_summary"
    version: str = "1.0.0"
    dataset: FINRADataset = FINRADataset.WEEKLY_SUMMARY
    
    def __init__(self, client: FINRAClient | None = None):
        self._client = client or FINRAClient()
    
    def capture(self, params: WeeklySummaryParams) -> CaptureBatch:
        """Capture all weekly summary data."""
        captured_at = utc_now()
        batch_id = uuid4()
        
        query_params = {}
        if params.tier:
            query_params["tierIdentifier"] = params.tier.value
        
        records = []
        page_count = 0
        
        for page_data in self._client.fetch_all_pages(
            group="otcMarket",
            dataset=self.dataset.value,
            params=query_params,
            limit=params.limit,
        ):
            page_count += 1
            for row in page_data:
                records.append(RawWeeklyRecord(
                    source="finra_otc",
                    dataset=self.dataset,
                    raw_payload=row,
                    captured_at=captured_at,
                ))
        
        return CaptureBatch(
            batch_id=batch_id,
            connector_name=self.name,
            connector_version=self.version,
            dataset=self.dataset,
            captured_at=captured_at,
            records=records,
            query_params=query_params,
            page_count=page_count,
            total_records_fetched=len(records),
        )
```

### 3.5 Weekly Historic Connector

```python
# app/domains/otc/connectors/finra_weekly_historic.py

"""
Connector for FINRA weeklySummaryHistoric dataset (~4 years).

Supports both sync and async (job) modes.
"""

from datetime import datetime
from uuid import uuid4

from app.domains.otc.contracts import (
    ConnectorProtocol,
    FINRADataset,
    HistoricQueryMode,
    WeeklyHistoricParams,
    CaptureBatch,
    RawWeeklyRecord,
)
from app.domains.otc.connectors.finra_client import FINRAClient
from app.core.time import utc_now


class FINRAWeeklyHistoricConnector:
    """Connector for weeklySummaryHistoric (~4 years)."""
    
    name: str = "finra_weekly_historic"
    version: str = "1.0.0"
    dataset: FINRADataset = FINRADataset.WEEKLY_SUMMARY_HISTORIC
    
    def __init__(self, client: FINRAClient | None = None):
        self._client = client or FINRAClient()
    
    def capture(self, params: WeeklyHistoricParams) -> CaptureBatch:
        """
        Capture historic weekly summary data.
        
        Uses async job mode if params.use_async=True.
        """
        captured_at = utc_now()
        batch_id = uuid4()
        
        # Build query params (exactly one date filter required)
        query_params = self._build_query_params(params)
        
        if params.use_async:
            return self._capture_async_mode(
                batch_id, captured_at, params, query_params
            )
        else:
            return self._capture_sync_mode(
                batch_id, captured_at, params, query_params
            )
    
    def _build_query_params(self, params: WeeklyHistoricParams) -> dict:
        """Build FINRA query params from connector params."""
        query = {}
        
        if params.week_start_date:
            # Format: yyyy-MM-dd
            query["weekStartDate"] = params.week_start_date.strftime("%Y-%m-%d")
        elif params.historical_week:
            # Format: yyyy-Www (already validated)
            query["historicalWeek"] = params.historical_week
        elif params.historical_month:
            # Format: yyyy-MMM (already validated)
            query["historicalMonth"] = params.historical_month
        
        if params.tier:
            query["tierIdentifier"] = params.tier.value
        
        return query
    
    def _capture_sync_mode(
        self,
        batch_id,
        captured_at,
        params: WeeklyHistoricParams,
        query_params: dict,
    ) -> CaptureBatch:
        """Standard sync paging mode."""
        records = []
        page_count = 0
        
        for page_data in self._client.fetch_all_pages(
            group="otcMarket",
            dataset=self.dataset.value,
            params=query_params,
            limit=params.limit,
        ):
            page_count += 1
            for row in page_data:
                records.append(RawWeeklyRecord(
                    source="finra_otc",
                    dataset=self.dataset,
                    raw_payload=row,
                    captured_at=captured_at,
                ))
        
        return CaptureBatch(
            batch_id=batch_id,
            connector_name=self.name,
            connector_version=self.version,
            dataset=self.dataset,
            captured_at=captured_at,
            records=records,
            query_params=query_params,
            page_count=page_count,
            total_records_fetched=len(records),
            job_mode=False,
        )
    
    def _capture_async_mode(
        self,
        batch_id,
        captured_at,
        params: WeeklyHistoricParams,
        query_params: dict,
    ) -> CaptureBatch:
        """Async job mode for large/slow requests."""
        # Submit job
        job_id = self._client.submit_async_job(
            group="otcMarket",
            dataset=self.dataset.value,
            params=query_params,
        )
        
        # Wait for completion
        self._client.wait_for_job(
            job_id,
            poll_interval=params.async_poll_interval,
            timeout=params.async_timeout,
        )
        
        # Download results
        records = []
        page_count = 0
        
        for page_data in self._client.download_job_result(job_id, params.limit):
            page_count += 1
            for row in page_data:
                records.append(RawWeeklyRecord(
                    source="finra_otc",
                    dataset=self.dataset,
                    raw_payload=row,
                    captured_at=captured_at,
                ))
        
        return CaptureBatch(
            batch_id=batch_id,
            connector_name=self.name,
            connector_version=self.version,
            dataset=self.dataset,
            captured_at=captured_at,
            records=records,
            query_params=query_params,
            page_count=page_count,
            total_records_fetched=len(records),
            job_id=job_id,
            job_mode=True,
        )
```

---

*Continued in next section: Normalizer Interface, Calculation Interface, Registry & Wiring*

---

## 4. Normalizer Interface

### 4.1 Canonical Weekly Summary Model

```python
# app/domains/otc/contracts.py (continued)

class CanonicalWeeklySummary(BaseModel):
    """Normalized weekly OTC summary record."""
    
    # Identity
    summary_id: str = Field(..., description="Stable unique identifier")
    source: str = Field(default="finra_otc")
    record_hash: str
    schema_version: str
    
    # Time dimension
    week_start_date: date
    week_end_date: date
    
    # Security identification
    symbol: str
    security_name: str
    tier: OTCTier
    
    # Volume metrics (from FINRA)
    total_shares_traded: Decimal
    total_trades: int
    total_dollar_volume: Decimal
    
    # Price metrics
    open_price: Decimal | None
    high_price: Decimal | None
    low_price: Decimal | None
    close_price: Decimal | None
    
    # Derived
    avg_trade_size: Decimal | None
    avg_price: Decimal | None
    
    # Audit
    normalized_at: datetime


class NormalizationStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class NormalizationResult(BaseModel):
    """Result of normalizing a single record."""
    
    normalizer_name: str
    normalizer_version: str
    input_record_hash: str
    status: NormalizationStatus
    summary: CanonicalWeeklySummary | None = None
    rejection_reason: str | None = None


class NormalizationBatch(BaseModel):
    """Result of normalizing a batch of records."""
    
    normalizer_name: str
    normalizer_version: str
    processed_at: datetime
    results: list[NormalizationResult] = Field(default_factory=list)
    
    @property
    def accepted_count(self) -> int:
        return sum(1 for r in self.results if r.status == NormalizationStatus.ACCEPTED)
    
    @property
    def rejected_count(self) -> int:
        return sum(1 for r in self.results if r.status == NormalizationStatus.REJECTED)
```

### 4.2 Normalizer Protocol

```python
# app/domains/otc/contracts.py (continued)

class NormalizerProtocol(Protocol):
    """
    Protocol for OTC weekly summary normalizers.
    
    Responsibilities:
    - Transform RawWeeklyRecord → CanonicalWeeklySummary
    - Generate stable summary_id for identity
    - Classify as accepted or rejected
    
    Must NOT:
    - Fetch external data
    - Write to database
    - Import orchestration frameworks
    """
    
    @property
    def name(self) -> str:
        """Normalizer name (e.g., 'weekly_summary')."""
        ...
    
    @property
    def version(self) -> str:
        """Version (e.g., 'v1', 'v2')."""
        ...
    
    @property
    def input_schema_version(self) -> str:
        """Expected raw payload schema version."""
        ...
    
    def normalize(self, record: RawWeeklyRecord) -> NormalizationResult:
        """Normalize a single raw record."""
        ...
    
    def normalize_batch(self, records: list[RawWeeklyRecord]) -> NormalizationBatch:
        """Normalize a batch of raw records."""
        ...
```

### 4.3 V1 Normalizer Implementation

```python
# app/domains/otc/normalizers/weekly_summary_v1.py

"""
V1 Normalizer for FINRA Weekly Summary.

Maps raw FINRA API fields to canonical schema.
"""

from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

from app.domains.otc.contracts import (
    RawWeeklyRecord,
    NormalizationResult,
    NormalizationBatch,
    NormalizationStatus,
    CanonicalWeeklySummary,
    OTCTier,
)
from app.core.time import utc_now


class WeeklySummaryNormalizerV1:
    """V1 normalizer for FINRA weekly summary data."""
    
    name: str = "weekly_summary"
    version: str = "v1"
    input_schema_version: str = "finra_v1"
    
    # FINRA field mappings
    FIELD_MAP = {
        "weekStartDate": "week_start_date",
        "symbol": "symbol",
        "securityName": "security_name",
        "tierIdentifier": "tier",
        "totalSharesTraded": "total_shares_traded",
        "totalTrades": "total_trades",
        "totalDollarVolume": "total_dollar_volume",
        "openPrice": "open_price",
        "highPrice": "high_price",
        "lowPrice": "low_price",
        "closePrice": "close_price",
    }
    
    REQUIRED_FIELDS = [
        "weekStartDate",
        "symbol",
        "tierIdentifier",
        "totalSharesTraded",
    ]
    
    def normalize(self, record: RawWeeklyRecord) -> NormalizationResult:
        """Normalize a single raw record."""
        payload = record.raw_payload
        
        # Validate required fields
        missing = [f for f in self.REQUIRED_FIELDS if f not in payload or payload[f] is None]
        if missing:
            return self._reject(record, f"Missing required fields: {missing}")
        
        try:
            week_start = self._parse_date(payload["weekStartDate"])
            week_end = week_start + timedelta(days=6)
            
            symbol = str(payload["symbol"]).upper().strip()
            security_name = str(payload.get("securityName", symbol))
            tier = self._parse_tier(payload["tierIdentifier"])
            
            total_shares = self._parse_decimal(payload["totalSharesTraded"])
            total_trades = int(payload.get("totalTrades", 0))
            total_dollar = self._parse_decimal(payload.get("totalDollarVolume", 0))
            
            # Generate stable ID
            summary_id = self._generate_summary_id(week_start, symbol, tier)
            
            # Derived metrics
            avg_trade_size = None
            if total_trades > 0:
                avg_trade_size = (total_shares / Decimal(total_trades)).quantize(Decimal("0.01"))
            
            avg_price = None
            if total_shares > 0:
                avg_price = (total_dollar / total_shares).quantize(Decimal("0.0001"))
            
            summary = CanonicalWeeklySummary(
                summary_id=summary_id,
                source=record.source,
                record_hash=record.record_hash,
                schema_version=self.version,
                week_start_date=week_start,
                week_end_date=week_end,
                symbol=symbol,
                security_name=security_name,
                tier=tier,
                total_shares_traded=total_shares,
                total_trades=total_trades,
                total_dollar_volume=total_dollar,
                open_price=self._parse_decimal_optional(payload.get("openPrice")),
                high_price=self._parse_decimal_optional(payload.get("highPrice")),
                low_price=self._parse_decimal_optional(payload.get("lowPrice")),
                close_price=self._parse_decimal_optional(payload.get("closePrice")),
                avg_trade_size=avg_trade_size,
                avg_price=avg_price,
                normalized_at=utc_now(),
            )
            
            return NormalizationResult(
                normalizer_name=self.name,
                normalizer_version=self.version,
                input_record_hash=record.record_hash,
                status=NormalizationStatus.ACCEPTED,
                summary=summary,
            )
            
        except (ValueError, InvalidOperation, KeyError) as e:
            return self._reject(record, f"Parse error: {e}")
    
    def normalize_batch(self, records: list[RawWeeklyRecord]) -> NormalizationBatch:
        """Normalize a batch of records."""
        results = [self.normalize(r) for r in records]
        return NormalizationBatch(
            normalizer_name=self.name,
            normalizer_version=self.version,
            processed_at=utc_now(),
            results=results,
        )
    
    def _reject(self, record: RawWeeklyRecord, reason: str) -> NormalizationResult:
        return NormalizationResult(
            normalizer_name=self.name,
            normalizer_version=self.version,
            input_record_hash=record.record_hash,
            status=NormalizationStatus.REJECTED,
            rejection_reason=reason,
        )
    
    def _generate_summary_id(self, week_start: date, symbol: str, tier: OTCTier) -> str:
        """
        Generate stable summary ID.
        
        Format: finra:{week_start}:{symbol}:{tier}
        """
        return f"finra:{week_start.isoformat()}:{symbol}:{tier.value}"
    
    def _parse_date(self, value) -> date:
        if isinstance(value, date):
            return value
        # FINRA format: yyyy-MM-dd
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    
    def _parse_tier(self, value: str) -> OTCTier:
        v = str(value).upper().strip()
        try:
            return OTCTier(v)
        except ValueError:
            # Map unknown tiers to closest match
            if "PINK" in v:
                return OTCTier.PINK
            elif "GREY" in v:
                return OTCTier.GREY
            elif "BB" in v:
                return OTCTier.OTCBB
            return OTCTier.OTC
    
    def _parse_decimal(self, value) -> Decimal:
        if value is None:
            return Decimal(0)
        return Decimal(str(value))
    
    def _parse_decimal_optional(self, value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
```

---

## 5. Calculation Interface

### 5.1 Calculation Contracts

```python
# app/domains/otc/contracts.py (continued)

class CalculationParams(BaseModel):
    """Base parameters for calculations."""
    
    start_date: date
    end_date: date
    symbols: list[str] | None = None
    tiers: list[OTCTier] | None = None


class WeeklyMetricRow(BaseModel):
    """Single metric output row."""
    
    symbol: str
    tier: OTCTier
    week_start_date: date
    calc_name: str
    calc_version: str
    
    # Primary metric value
    value: Decimal
    
    # Additional metric columns as metadata
    metrics: dict[str, Any] = Field(default_factory=dict)
    
    computed_at: datetime


class CalculationResult(BaseModel):
    """Result of a calculation operation."""
    
    calc_name: str
    calc_version: str
    computed_at: datetime
    rows: list[WeeklyMetricRow] = Field(default_factory=list)
    input_summary_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class CalculationProtocol(Protocol):
    """
    Protocol for OTC metric calculations.
    
    Responsibilities:
    - Read from canonical weekly summary only
    - Produce deterministic output
    - Include calc metadata in output
    
    Must NOT:
    - Call connectors or fetch external data
    - Modify source data
    - Produce non-deterministic results
    """
    
    @property
    def name(self) -> str: ...
    
    @property
    def version(self) -> str: ...
    
    @property
    def output_columns(self) -> list[str]: ...
    
    def compute(
        self,
        summaries: list[CanonicalWeeklySummary],
        params: CalculationParams,
    ) -> CalculationResult:
        """Compute metrics from canonical weekly summaries."""
        ...
```

### 5.2 Weekly Volume Calculation

```python
# app/domains/otc/calculations/weekly_volume_v1.py

"""
Weekly Volume V1 Calculation.

Aggregates volume metrics by symbol and week.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.domains.otc.contracts import (
    CalculationProtocol,
    CalculationParams,
    CalculationResult,
    WeeklyMetricRow,
    CanonicalWeeklySummary,
)
from app.core.time import utc_now


class WeeklyVolumeV1:
    """V1 weekly volume aggregation."""
    
    name: str = "weekly_volume"
    version: str = "v1"
    output_columns: list[str] = [
        "total_shares",
        "total_trades",
        "total_dollar_volume",
        "avg_price",
    ]
    
    def compute(
        self,
        summaries: list[CanonicalWeeklySummary],
        params: CalculationParams,
    ) -> CalculationResult:
        """Compute weekly volume metrics."""
        computed_at = utc_now()
        
        if not summaries:
            return CalculationResult(
                calc_name=self.name,
                calc_version=self.version,
                computed_at=computed_at,
                rows=[],
                input_summary_count=0,
            )
        
        rows = []
        for summary in summaries:
            # Apply date filter
            if summary.week_start_date < params.start_date:
                continue
            if summary.week_start_date > params.end_date:
                continue
            
            # Apply symbol filter
            if params.symbols and summary.symbol not in params.symbols:
                continue
            
            # Apply tier filter
            if params.tiers and summary.tier not in params.tiers:
                continue
            
            rows.append(WeeklyMetricRow(
                symbol=summary.symbol,
                tier=summary.tier,
                week_start_date=summary.week_start_date,
                calc_name=self.name,
                calc_version=self.version,
                value=summary.total_dollar_volume,  # Primary value
                metrics={
                    "total_shares": str(summary.total_shares_traded),
                    "total_trades": summary.total_trades,
                    "total_dollar_volume": str(summary.total_dollar_volume),
                    "avg_price": str(summary.avg_price) if summary.avg_price else None,
                },
                computed_at=computed_at,
            ))
        
        return CalculationResult(
            calc_name=self.name,
            calc_version=self.version,
            computed_at=computed_at,
            rows=rows,
            input_summary_count=len(summaries),
        )
```

---

## 6. Registry & Wiring

### 6.1 Plugin Registry

```python
# app/domains/otc/registry.py

from typing import TypeVar, Generic, Callable, Any
from dataclasses import dataclass, field

from app.domains.otc.contracts import (
    ConnectorProtocol,
    NormalizerProtocol,
    CalculationProtocol,
)
from app.domains.otc.exceptions import (
    PluginNotFoundError,
    PluginVersionNotFoundError,
)


T = TypeVar("T")


@dataclass
class PluginEntry(Generic[T]):
    name: str
    version: str
    factory: Callable[[], T]


class PluginRegistry(Generic[T]):
    """Generic plugin registry with name/version resolution."""
    
    def __init__(self, plugin_type: str):
        self._plugin_type = plugin_type
        self._entries: dict[str, dict[str, PluginEntry[T]]] = {}
        self._defaults: dict[str, str] = {}
    
    def register(
        self, name: str, version: str, factory: Callable[[], T], *, is_default: bool = False
    ) -> None:
        if name not in self._entries:
            self._entries[name] = {}
        self._entries[name][version] = PluginEntry(name, version, factory)
        if is_default or name not in self._defaults:
            self._defaults[name] = version
    
    def resolve(self, name: str, version: str | None = None) -> T:
        if name not in self._entries:
            raise PluginNotFoundError(self._plugin_type, name)
        target = version or self._defaults.get(name)
        if target not in self._entries[name]:
            raise PluginVersionNotFoundError(self._plugin_type, name, target)
        return self._entries[name][target].factory()


# Global registries
connectors: PluginRegistry[ConnectorProtocol] = PluginRegistry("connector")
normalizers: PluginRegistry[NormalizerProtocol] = PluginRegistry("normalizer")
calculations: PluginRegistry[CalculationProtocol] = PluginRegistry("calculation")


def resolve_connector(name: str) -> ConnectorProtocol:
    return connectors.resolve(name)

def resolve_normalizer(version: str | None = None) -> NormalizerProtocol:
    return normalizers.resolve("weekly_summary", version)

def resolve_calc(name: str, version: str | None = None) -> CalculationProtocol:
    return calculations.resolve(name, version)
```

### 6.2 Registration at Import

```python
# app/domains/otc/connectors/__init__.py
from app.domains.otc.registry import connectors
from app.domains.otc.connectors.finra_weekly_summary import FINRAWeeklySummaryConnector
from app.domains.otc.connectors.finra_weekly_historic import FINRAWeeklyHistoricConnector

connectors.register("finra_weekly_summary", "1.0.0", FINRAWeeklySummaryConnector, is_default=True)
connectors.register("finra_weekly_historic", "1.0.0", FINRAWeeklyHistoricConnector, is_default=True)
```

```python
# app/domains/otc/normalizers/__init__.py
from app.domains.otc.registry import normalizers
from app.domains.otc.normalizers.weekly_summary_v1 import WeeklySummaryNormalizerV1

normalizers.register("weekly_summary", "v1", WeeklySummaryNormalizerV1, is_default=True)
```

```python
# app/domains/otc/calculations/__init__.py
from app.domains.otc.registry import calculations
from app.domains.otc.calculations.weekly_volume_v1 import WeeklyVolumeV1
from app.domains.otc.calculations.tier_breakdown_v1 import TierBreakdownV1
from app.domains.otc.calculations.liquidity_score_v1 import LiquidityScoreV1

calculations.register("weekly_volume", "v1", WeeklyVolumeV1, is_default=True)
calculations.register("tier_breakdown", "v1", TierBreakdownV1, is_default=True)
calculations.register("liquidity_score", "v1", LiquidityScoreV1, is_default=True)
```

---

## 7. Pipelines

### 7.1 Pipeline Stages

```
┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
│  otc_capture_raw  │───►│   otc_normalize   │───►│otc_compute_metrics│
│                   │    │                   │    │                   │
│  FINRA API → Raw  │    │  Raw → Canonical  │    │ Canonical → Gold  │
│  (Bronze layer)   │    │  (Silver layer)   │    │  (Gold layer)     │
└───────────────────┘    └───────────────────┘    └───────────────────┘
```

### 7.2 Capture Raw Pipeline

```python
# app/domains/otc/pipelines/capture_raw.py

async def run_capture_raw_pipeline(
    execution_id: str,
    params: dict,
    *,
    raw_repo: RawWeeklyRepository,
) -> dict:
    """
    Params:
        connector: "finra_weekly_summary" | "finra_weekly_historic"
        week_start_date: Optional[str] (Monday, yyyy-MM-dd)
        historical_week: Optional[str] (yyyy-Www)
        historical_month: Optional[str] (yyyy-MMM)
        tier: Optional[str]
        use_async: bool
    """
    connector = resolve_connector(params["connector"])
    
    # Build params based on connector type
    if params["connector"] == "finra_weekly_summary":
        connector_params = WeeklySummaryParams(tier=params.get("tier"))
    else:
        connector_params = WeeklyHistoricParams(
            week_start_date=params.get("week_start_date"),
            historical_week=params.get("historical_week"),
            historical_month=params.get("historical_month"),
            tier=params.get("tier"),
            use_async=params.get("use_async", False),
        )
    
    batch = connector.capture(connector_params)
    inserted = await raw_repo.insert_batch(batch.records, batch.batch_id)
    
    return {
        "batch_id": str(batch.batch_id),
        "fetched": batch.record_count,
        "inserted": inserted,
        "duplicates": batch.record_count - inserted,
    }
```

### 7.3 Normalize Pipeline

```python
# app/domains/otc/pipelines/normalize.py

async def run_normalize_pipeline(
    execution_id: str,
    params: dict,
    *,
    raw_repo: RawWeeklyRepository,
    summary_repo: WeeklySummaryRepository,
) -> dict:
    """
    Params:
        batch_id: Optional[str]
        start_date, end_date: Optional date range
        normalizer_version: Optional[str] ("v1", "v2")
    """
    normalizer = resolve_normalizer(params.get("normalizer_version"))
    
    if "batch_id" in params:
        records = await raw_repo.get_batch(params["batch_id"])
    else:
        records = await raw_repo.get_by_date_range(
            params.get("start_date"), params.get("end_date")
        )
    
    result = normalizer.normalize_batch(records)
    accepted = [r.summary for r in result.results if r.summary]
    inserted, updated = await summary_repo.upsert_batch(accepted)
    
    return {
        "normalizer": f"{normalizer.name}:{normalizer.version}",
        "processed": len(records),
        "accepted": result.accepted_count,
        "rejected": result.rejected_count,
    }
```

### 7.4 Compute Metrics Pipeline

```python
# app/domains/otc/pipelines/compute_metrics.py

async def run_compute_metrics_pipeline(
    execution_id: str,
    params: dict,
    *,
    summary_repo: WeeklySummaryRepository,
    metrics_repo: WeeklyMetricsRepository,
) -> dict:
    """
    Params:
        calc: str (e.g., "liquidity_score")
        version: Optional[str] ("v1")
        start_date, end_date: str
        symbols: Optional[list[str]]
        tiers: Optional[list[str]]
    """
    calc = resolve_calc(params["calc"], params.get("version"))
    
    calc_params = CalculationParams(
        start_date=params["start_date"],
        end_date=params["end_date"],
        symbols=params.get("symbols"),
        tiers=params.get("tiers"),
    )
    
    summaries = await summary_repo.get_by_date_range(
        calc_params.start_date, calc_params.end_date,
        symbols=calc_params.symbols, tiers=calc_params.tiers,
    )
    
    result = calc.compute(summaries, calc_params)
    inserted, updated = await metrics_repo.upsert_batch(result.rows)
    
    return {
        "calc": f"{calc.name}:{calc.version}",
        "input": result.input_summary_count,
        "output": len(result.rows),
    }
```

### 7.5 Dispatcher Examples

```python
# Capture rolling 12 months
await dispatcher.submit(
    pipeline="otc_capture_raw",
    params={"connector": "finra_weekly_summary"},
    logical_key="otc:capture:weekly_summary",
)

# Capture specific historic week (async mode)
await dispatcher.submit(
    pipeline="otc_capture_raw",
    params={
        "connector": "finra_weekly_historic",
        "week_start_date": "2025-12-29",
        "use_async": True,
    },
    logical_key="otc:capture:historic:2025-12-29",
)

# Compute liquidity scores
await dispatcher.submit(
    pipeline="otc_compute_metrics",
    params={
        "calc": "liquidity_score",
        "version": "v1",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
    },
    logical_key="otc:compute:liquidity_score:2025",
)
```

---

## 8. Schema Guidance

### 8.1 Bronze Layer (Raw)

```sql
-- otc_raw_weekly
CREATE TABLE otc_raw_weekly (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    finra_record_id VARCHAR(100) UNIQUE,
    raw_json JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Extracted keys for indexing
    week_start_date DATE GENERATED ALWAYS AS ((raw_json->>'weekStartDate')::DATE) STORED,
    symbol VARCHAR(20) GENERATED ALWAYS AS (raw_json->>'issueSymbolIdentifier') STORED,
    tier VARCHAR(50) GENERATED ALWAYS AS (raw_json->>'tierIdentifier') STORED,
    
    CONSTRAINT valid_raw CHECK (
        raw_json ? 'weekStartDate' AND
        raw_json ? 'issueSymbolIdentifier'
    )
);

CREATE INDEX idx_raw_weekly_week ON otc_raw_weekly (week_start_date);
CREATE INDEX idx_raw_weekly_symbol ON otc_raw_weekly (symbol);
CREATE INDEX idx_raw_weekly_batch ON otc_raw_weekly (batch_id);
```

### 8.2 Silver Layer (Normalized)

```sql
-- otc_weekly_summary (canonical)
CREATE TABLE otc_weekly_summary (
    id BIGSERIAL PRIMARY KEY,
    week_start_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    tier VARCHAR(50) NOT NULL,
    
    total_shares_traded NUMERIC(20, 4) NOT NULL,
    total_dollar_volume NUMERIC(24, 4) NOT NULL,
    total_trades INTEGER NOT NULL,
    avg_price_per_share NUMERIC(16, 6),
    
    normalizer_name VARCHAR(50) NOT NULL DEFAULT 'weekly_summary',
    normalizer_version VARCHAR(10) NOT NULL,
    normalized_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT unique_summary UNIQUE (week_start_date, symbol, tier)
);

CREATE INDEX idx_summary_week ON otc_weekly_summary (week_start_date);
CREATE INDEX idx_summary_symbol ON otc_weekly_summary (symbol);
CREATE INDEX idx_summary_tier ON otc_weekly_summary (tier);
```

### 8.3 Gold Layer (Metrics)

```sql
-- otc_weekly_metrics
CREATE TABLE otc_weekly_metrics (
    id BIGSERIAL PRIMARY KEY,
    week_start_date DATE NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    tier VARCHAR(50) NOT NULL,
    
    calc_name VARCHAR(50) NOT NULL,
    calc_version VARCHAR(10) NOT NULL,
    value NUMERIC(24, 8) NOT NULL,
    metrics JSONB DEFAULT '{}',
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT unique_metric UNIQUE (week_start_date, symbol, tier, calc_name, calc_version)
);

CREATE INDEX idx_metrics_calc ON otc_weekly_metrics (calc_name, calc_version);
CREATE INDEX idx_metrics_week ON otc_weekly_metrics (week_start_date);
CREATE INDEX idx_metrics_symbol ON otc_weekly_metrics (symbol);
```

### 8.4 Data Freshness Rules

| Condition | Behavior |
|-----------|----------|
| `week_start_date` > 1 year ago | Static - download once, never re-download |
| `week_start_date` ≤ 1 year ago | May update weekly - re-download from `weeklySummary` |
| Latest available week | May update until following Monday midnight |

```python
# app/domains/otc/freshness.py

def is_static(week_start_date: date) -> bool:
    """Returns True if this week's data is considered immutable."""
    one_year_ago = date.today() - timedelta(days=365)
    return week_start_date < one_year_ago

def should_refresh(week_start_date: date, last_fetched: datetime) -> bool:
    """Determine if we should re-fetch this week's data."""
    if is_static(week_start_date):
        return False
    # Refresh weekly summary data if fetched more than 7 days ago
    return (utc_now() - last_fetched) > timedelta(days=7)
```

---

## 9. Testing Strategy

### 9.1 Fixtures Directory

```
tests/domains/otc/
├── fixtures/
│   ├── finra_responses/
│   │   ├── weekly_summary_page1.json
│   │   ├── weekly_summary_page2.json
│   │   └── weekly_historic_2024_W01.json
│   ├── raw_records/
│   │   └── sample_raw_batch.json
│   ├── normalized/
│   │   └── sample_summaries.json
│   └── golden/
│       ├── liquidity_score_v1_input.json
│       └── liquidity_score_v1_expected.json
├── test_connectors/
│   ├── test_finra_client.py
│   └── test_weekly_summary_connector.py
├── test_normalizers/
│   └── test_weekly_summary_normalizer.py
├── test_calculations/
│   ├── test_weekly_volume_v1.py
│   └── test_liquidity_score_v1.py
└── test_pipelines/
    ├── test_capture_raw.py
    └── test_compute_metrics.py
```

### 9.2 Golden Test Pattern

```python
# tests/domains/otc/test_calculations/test_liquidity_score_v1.py

import json
from pathlib import Path
from decimal import Decimal

import pytest

from app.domains.otc.calculations.liquidity_score_v1 import LiquidityScoreV1
from app.domains.otc.contracts import CanonicalWeeklySummary, CalculationParams


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "golden"


def load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


class TestLiquidityScoreV1Golden:
    """Golden tests for LiquidityScoreV1 calculation."""
    
    @pytest.fixture
    def calc(self) -> LiquidityScoreV1:
        return LiquidityScoreV1()
    
    @pytest.fixture
    def input_data(self) -> list[CanonicalWeeklySummary]:
        raw = load_fixture("liquidity_score_v1_input.json")
        return [CanonicalWeeklySummary(**r) for r in raw]
    
    @pytest.fixture
    def expected_output(self) -> dict:
        return load_fixture("liquidity_score_v1_expected.json")
    
    def test_golden_output(
        self,
        calc: LiquidityScoreV1,
        input_data: list[CanonicalWeeklySummary],
        expected_output: dict,
    ):
        """Verify calculation matches golden output exactly."""
        params = CalculationParams(
            start_date=expected_output["params"]["start_date"],
            end_date=expected_output["params"]["end_date"],
        )
        
        result = calc.compute(input_data, params)
        
        # Compare row count
        assert len(result.rows) == len(expected_output["rows"])
        
        # Compare each row
        for actual, expected in zip(result.rows, expected_output["rows"]):
            assert actual.symbol == expected["symbol"]
            assert actual.week_start_date.isoformat() == expected["week_start_date"]
            assert str(actual.value) == expected["value"]
            assert actual.metrics == expected["metrics"]
    
    def test_version_stability(self, calc: LiquidityScoreV1):
        """Verify calc version hasn't changed unexpectedly."""
        assert calc.version == "v1"
        assert calc.name == "liquidity_score"
```

### 9.3 Connector Mocking

```python
# tests/domains/otc/conftest.py

import pytest
from unittest.mock import Mock, AsyncMock

from app.domains.otc.connectors.finra_client import FINRAClient


@pytest.fixture
def mock_finra_client() -> Mock:
    """Mock FINRA client that returns fixture data."""
    client = Mock(spec=FINRAClient)
    
    def load_page(dataset: str, page: int = 1):
        fixture_path = f"fixtures/finra_responses/{dataset}_page{page}.json"
        with open(fixture_path) as f:
            return json.load(f)
    
    client.fetch_page.side_effect = load_page
    return client


@pytest.fixture
def mock_finra_client_async() -> AsyncMock:
    """Mock FINRA async job client."""
    client = AsyncMock(spec=FINRAClient)
    
    async def submit_job(*args, **kwargs):
        return "job-12345"
    
    async def poll_job(job_id: str):
        return {"status": "completed", "downloadUrl": "https://..."}
    
    client.submit_async_job = submit_job
    client.poll_job_status = poll_job
    return client
```

### 9.4 Normalizer Edge Cases

```python
# tests/domains/otc/test_normalizers/test_weekly_summary_normalizer.py

import pytest
from decimal import Decimal

from app.domains.otc.normalizers.weekly_summary_v1 import WeeklySummaryNormalizerV1
from app.domains.otc.contracts import RawWeeklyRecord


class TestWeeklySummaryNormalizerV1:
    """Unit tests for normalizer edge cases."""
    
    @pytest.fixture
    def normalizer(self) -> WeeklySummaryNormalizerV1:
        return WeeklySummaryNormalizerV1()
    
    def test_rejects_missing_symbol(self, normalizer):
        """Records without symbol are rejected."""
        record = RawWeeklyRecord(
            finra_record_id="123",
            raw_json={"weekStartDate": "2025-01-06"},  # Missing symbol
            fetched_at=utc_now(),
        )
        result = normalizer.normalize_single(record)
        assert result.summary is None
        assert "missing issueSymbolIdentifier" in result.error.lower()
    
    def test_coerces_negative_volume_to_zero(self, normalizer):
        """Negative volumes are normalized to zero."""
        record = RawWeeklyRecord(
            finra_record_id="123",
            raw_json={
                "weekStartDate": "2025-01-06",
                "issueSymbolIdentifier": "AAPL",
                "tierIdentifier": "T1",
                "totalShareQuantity": -100,  # Invalid
                "dollarVolume": 1000.00,
                "tradeCount": 5,
            },
            fetched_at=utc_now(),
        )
        result = normalizer.normalize_single(record)
        assert result.summary is not None
        assert result.summary.total_shares_traded == Decimal(0)
    
    def test_handles_tier_aliases(self, normalizer):
        """Various tier names are normalized to canonical values."""
        test_cases = [
            ("ADF OTC", "ADF_OTC"),
            ("adf otc", "ADF_OTC"),
            ("ADF-OTC", "ADF_OTC"),
            ("OTC Tier 1", "OTC_TIER_1"),
        ]
        for raw_tier, expected_tier in test_cases:
            record = RawWeeklyRecord(
                finra_record_id="123",
                raw_json={
                    "weekStartDate": "2025-01-06",
                    "issueSymbolIdentifier": "AAPL",
                    "tierIdentifier": raw_tier,
                    "totalShareQuantity": 100,
                    "dollarVolume": 1000.00,
                    "tradeCount": 5,
                },
                fetched_at=utc_now(),
            )
            result = normalizer.normalize_single(record)
            assert result.summary.tier.value == expected_tier
```

---

## 10. Worked Example: `liquidity_score_v1`

### 10.1 Business Logic

**Liquidity Score** measures how easily a security can be traded based on:

```
liquidity_score = log10(dollar_volume) * (1 - spread_impact) * consistency_factor
```

Where:
- `dollar_volume` = average weekly dollar volume over lookback period
- `spread_impact` = estimated bid-ask spread as % of price (derived from avg trade size)
- `consistency_factor` = % of weeks with trading activity

**Score Interpretation:**
| Score | Interpretation |
|-------|----------------|
| ≥ 8.0 | Highly liquid (institutional grade) |
| 6.0 - 7.9 | Moderately liquid (active trading) |
| 4.0 - 5.9 | Low liquidity (caution) |
| < 4.0 | Illiquid (high risk) |

### 10.2 Full Implementation

```python
# app/domains/otc/calculations/liquidity_score_v1.py

"""
Liquidity Score V1 Calculation.

Computes a liquidity score for each symbol based on:
- Average weekly dollar volume
- Trade frequency / consistency
- Estimated spread impact
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math

from app.domains.otc.contracts import (
    CalculationParams,
    CalculationResult,
    WeeklyMetricRow,
    CanonicalWeeklySummary,
)
from app.core.time import utc_now


@dataclass
class LiquidityScoreParams(CalculationParams):
    """Parameters for liquidity score calculation."""
    lookback_weeks: int = 12  # How many weeks to consider


class LiquidityScoreV1:
    """
    V1 Liquidity Score Calculation.
    
    Scoring methodology:
    1. Calculate average weekly dollar volume
    2. Estimate spread impact from avg trade size
    3. Measure trading consistency (% of weeks active)
    4. Combine into single score
    """
    
    name: str = "liquidity_score"
    version: str = "v1"
    output_columns: list[str] = [
        "avg_weekly_dollar_volume",
        "avg_trade_size",
        "spread_impact",
        "consistency_factor",
        "active_weeks",
        "total_weeks",
        "liquidity_score",
        "liquidity_grade",
    ]
    
    # Spread impact estimation constants
    SPREAD_COEFFICIENT = Decimal("0.001")  # Base spread as fraction of inverse trade size
    MAX_SPREAD_IMPACT = Decimal("0.5")     # Cap spread impact at 50%
    
    def compute(
        self,
        summaries: list[CanonicalWeeklySummary],
        params: LiquidityScoreParams,
    ) -> CalculationResult:
        """Compute liquidity scores for all symbols in date range."""
        computed_at = utc_now()
        
        # Determine lookback window
        end_date = params.end_date
        start_date = max(
            params.start_date,
            end_date - timedelta(weeks=params.lookback_weeks),
        )
        
        # Count total weeks in range
        total_weeks = ((end_date - start_date).days // 7) + 1
        
        # Aggregate by symbol
        symbol_data: dict[str, dict] = defaultdict(
            lambda: {
                "weeks": set(),
                "total_dollar": Decimal(0),
                "total_trades": 0,
                "tier": None,
            }
        )
        
        for s in summaries:
            if s.week_start_date < start_date or s.week_start_date > end_date:
                continue
            
            data = symbol_data[s.symbol]
            data["weeks"].add(s.week_start_date)
            data["total_dollar"] += s.total_dollar_volume
            data["total_trades"] += s.total_trades
            if data["tier"] is None:
                data["tier"] = s.tier
        
        rows = []
        for symbol, data in sorted(symbol_data.items()):
            active_weeks = len(data["weeks"])
            
            # Calculate metrics
            avg_weekly_dollar = (
                data["total_dollar"] / active_weeks
                if active_weeks > 0
                else Decimal(0)
            )
            
            avg_trade_size = (
                data["total_dollar"] / data["total_trades"]
                if data["total_trades"] > 0
                else Decimal(0)
            )
            
            # Estimate spread impact (inverse relationship to trade size)
            spread_impact = self._estimate_spread_impact(avg_trade_size)
            
            # Consistency factor (% of weeks with activity)
            consistency = Decimal(active_weeks) / Decimal(total_weeks)
            
            # Calculate final score
            score = self._calculate_score(
                avg_weekly_dollar, spread_impact, consistency
            )
            grade = self._score_to_grade(score)
            
            rows.append(WeeklyMetricRow(
                symbol=symbol,
                tier=data["tier"],
                week_start_date=end_date,  # Score is as-of this date
                calc_name=self.name,
                calc_version=self.version,
                value=score,
                metrics={
                    "avg_weekly_dollar_volume": str(avg_weekly_dollar.quantize(Decimal("0.01"))),
                    "avg_trade_size": str(avg_trade_size.quantize(Decimal("0.01"))),
                    "spread_impact": str(spread_impact.quantize(Decimal("0.0001"))),
                    "consistency_factor": str(consistency.quantize(Decimal("0.01"))),
                    "active_weeks": active_weeks,
                    "total_weeks": total_weeks,
                    "liquidity_score": str(score.quantize(Decimal("0.01"))),
                    "liquidity_grade": grade,
                },
                computed_at=computed_at,
            ))
        
        return CalculationResult(
            calc_name=self.name,
            calc_version=self.version,
            computed_at=computed_at,
            rows=rows,
            input_summary_count=len(summaries),
        )
    
    def _estimate_spread_impact(self, avg_trade_size: Decimal) -> Decimal:
        """
        Estimate bid-ask spread impact from average trade size.
        
        Smaller trades typically face higher spreads.
        """
        if avg_trade_size <= 0:
            return self.MAX_SPREAD_IMPACT
        
        # Inverse relationship: smaller trades = higher spread
        impact = self.SPREAD_COEFFICIENT * (Decimal(1000) / avg_trade_size)
        return min(impact, self.MAX_SPREAD_IMPACT)
    
    def _calculate_score(
        self,
        avg_weekly_dollar: Decimal,
        spread_impact: Decimal,
        consistency: Decimal,
    ) -> Decimal:
        """
        Calculate final liquidity score.
        
        score = log10(dollar_volume) * (1 - spread_impact) * consistency
        """
        if avg_weekly_dollar <= 0:
            return Decimal(0)
        
        log_volume = Decimal(str(math.log10(float(avg_weekly_dollar))))
        spread_factor = Decimal(1) - spread_impact
        
        score = log_volume * spread_factor * consistency
        return max(score, Decimal(0))  # Floor at 0
    
    def _score_to_grade(self, score: Decimal) -> str:
        """Convert numeric score to letter grade."""
        if score >= 8:
            return "A"
        elif score >= 6:
            return "B"
        elif score >= 4:
            return "C"
        else:
            return "D"
```

### 10.3 Registration

```python
# app/domains/otc/calculations/__init__.py

from app.domains.otc.registry import calculations
from app.domains.otc.calculations.liquidity_score_v1 import LiquidityScoreV1

calculations.register("liquidity_score", "v1", LiquidityScoreV1, is_default=True)
```

### 10.4 Golden Test Fixture

```json
// tests/domains/otc/fixtures/golden/liquidity_score_v1_input.json
[
  {
    "symbol": "AAPL",
    "tier": "ADF_OTC",
    "week_start_date": "2025-01-06",
    "total_shares_traded": 1000000,
    "total_dollar_volume": 150000000.00,
    "total_trades": 50000,
    "normalizer_version": "v1"
  },
  {
    "symbol": "AAPL",
    "tier": "ADF_OTC",
    "week_start_date": "2025-01-13",
    "total_shares_traded": 1200000,
    "total_dollar_volume": 180000000.00,
    "total_trades": 60000,
    "normalizer_version": "v1"
  },
  {
    "symbol": "PENNY",
    "tier": "OTC_PINK",
    "week_start_date": "2025-01-06",
    "total_shares_traded": 100000,
    "total_dollar_volume": 5000.00,
    "total_trades": 50,
    "normalizer_version": "v1"
  }
]
```

```json
// tests/domains/otc/fixtures/golden/liquidity_score_v1_expected.json
{
  "params": {
    "start_date": "2025-01-01",
    "end_date": "2025-01-20",
    "lookback_weeks": 12
  },
  "rows": [
    {
      "symbol": "AAPL",
      "week_start_date": "2025-01-20",
      "value": "7.92",
      "metrics": {
        "avg_weekly_dollar_volume": "165000000.00",
        "avg_trade_size": "3000.00",
        "spread_impact": "0.0003",
        "consistency_factor": "1.00",
        "active_weeks": 2,
        "total_weeks": 2,
        "liquidity_score": "7.92",
        "liquidity_grade": "B"
      }
    },
    {
      "symbol": "PENNY",
      "week_start_date": "2025-01-20",
      "value": "1.85",
      "metrics": {
        "avg_weekly_dollar_volume": "5000.00",
        "avg_trade_size": "100.00",
        "spread_impact": "0.0100",
        "consistency_factor": "0.50",
        "active_weeks": 1,
        "total_weeks": 2,
        "liquidity_score": "1.85",
        "liquidity_grade": "D"
      }
    }
  ]
}
```

### 10.5 Backfill Strategy

```python
# scripts/backfill_liquidity_scores.py

"""
Backfill liquidity_score_v1 for all historical data.

Usage:
    python scripts/backfill_liquidity_scores.py --start 2021-01-01 --end 2025-01-01
"""

import asyncio
from datetime import date, timedelta

from app.domains.otc.registry import resolve_calc
from app.domains.otc.contracts import CalculationParams


async def backfill_liquidity_scores(
    start_date: date,
    end_date: date,
    *,
    chunk_size_weeks: int = 12,
):
    """Backfill liquidity scores in chunks."""
    calc = resolve_calc("liquidity_score", "v1")
    
    current = start_date
    while current <= end_date:
        chunk_end = min(current + timedelta(weeks=chunk_size_weeks), end_date)
        
        await dispatcher.submit(
            pipeline="otc_compute_metrics",
            params={
                "calc": "liquidity_score",
                "version": "v1",
                "start_date": current.isoformat(),
                "end_date": chunk_end.isoformat(),
            },
            logical_key=f"otc:backfill:liquidity_score:v1:{current}:{chunk_end}",
            priority="low",
        )
        
        current = chunk_end + timedelta(days=1)
        
    print(f"Submitted backfill jobs from {start_date} to {end_date}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    
    asyncio.run(backfill_liquidity_scores(
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
    ))
```

---

## 11. Developer Workflow

### 11.1 Adding a New Calculation Version

**Step 1: Create the calculation file**

```bash
# Create new file
touch app/domains/otc/calculations/liquidity_score_v2.py
```

**Step 2: Implement the calculation**

```python
# app/domains/otc/calculations/liquidity_score_v2.py

"""
Liquidity Score V2 - Enhanced with volatility adjustment.
"""

from app.domains.otc.calculations.liquidity_score_v1 import LiquidityScoreV1


class LiquidityScoreV2(LiquidityScoreV1):
    """V2 adds volatility adjustment to spread impact."""
    
    version: str = "v2"
    
    def _estimate_spread_impact(self, avg_trade_size: Decimal) -> Decimal:
        # Enhanced logic...
        base_impact = super()._estimate_spread_impact(avg_trade_size)
        volatility_adjustment = self._calculate_volatility_adjustment()
        return min(base_impact * volatility_adjustment, self.MAX_SPREAD_IMPACT)
```

**Step 3: Register the new version**

```python
# app/domains/otc/calculations/__init__.py

from app.domains.otc.calculations.liquidity_score_v2 import LiquidityScoreV2

# Add registration (v1 remains default)
calculations.register("liquidity_score", "v2", LiquidityScoreV2)
```

**Step 4: Add golden test**

```python
# tests/domains/otc/test_calculations/test_liquidity_score_v2.py

class TestLiquidityScoreV2Golden:
    """Golden tests for V2 calculation."""
    
    @pytest.fixture
    def calc(self) -> LiquidityScoreV2:
        return LiquidityScoreV2()
    
    def test_golden_output(self, calc, input_data, expected_v2_output):
        # ... same pattern as v1
```

**Step 5: Run tests**

```bash
pytest tests/domains/otc/test_calculations/test_liquidity_score_v2.py -v
```

**Step 6: Update fixtures and promote to default (when ready)**

```python
# When v2 is validated and ready for production:
calculations.register("liquidity_score", "v2", LiquidityScoreV2, is_default=True)
```

### 11.2 Running Calculations

```python
# Via dispatcher (recommended)
await dispatcher.submit(
    pipeline="otc_compute_metrics",
    params={
        "calc": "liquidity_score",
        "version": "v2",  # Explicit version
        "start_date": "2025-01-01",
        "end_date": "2025-03-31",
    },
)

# Direct invocation (for testing)
from app.domains.otc.registry import resolve_calc

calc = resolve_calc("liquidity_score", "v2")
result = calc.compute(summaries, params)
```

### 11.3 Troubleshooting

| Issue | Solution |
|-------|----------|
| `PluginNotFoundError` | Check registration in `__init__.py`, ensure import |
| `PluginVersionNotFoundError` | Verify version string matches registration |
| Golden test failures | Regenerate fixtures with new version |
| Missing data in results | Check date range filters in calculation |

---

## 12. Summary

This architecture provides:

✅ **Correct FINRA API modeling** - weeklySummary (12mo) + weeklySummaryHistoric (4yr) with proper query rules  
✅ **Sync and async capture** - Paged download or job-based for large datasets  
✅ **Versioned components** - Connectors, normalizers, and calculations all versioned  
✅ **Bronze/Silver/Gold layers** - Raw → Canonical → Metrics progression  
✅ **Idempotent pipelines** - Rerunnable without duplication  
✅ **Golden tests** - Deterministic validation of calculation logic  
✅ **Registry pattern** - Runtime resolution with default versions  
✅ **Freshness rules** - Smart refresh based on data age
