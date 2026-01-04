# OTC Domain Plugin Architecture

> **Version:** 1.0.0  
> **Status:** Design Proposal  
> **Last Updated:** 2026-01-02

---

## Table of Contents

1. [OTC Domain Goals & Extension Contract](#1-otc-domain-goals--extension-contract)
2. [Folder Structure](#2-folder-structure)
3. [Plugin Interfaces](#3-plugin-interfaces)
4. [Registry & Wiring](#4-registry--wiring)
5. [Versioning Strategy](#5-versioning-strategy)
6. [Idempotency Rules & DB Constraints](#6-idempotency-rules--db-constraints)
7. [Fixture Layout & Golden Tests](#7-fixture-layout--golden-tests)
8. [Example: liquidity_score_v1](#8-example-liquidity_score_v1)
9. [Guardrails & Organization Rules](#9-guardrails--organization-rules)

---

## 1. OTC Domain Goals & Extension Contract

### 1.1 Design Principles

| Principle | Description |
|-----------|-------------|
| **Separation of Concerns** | Connectors fetch, Normalizers transform, Calculations compute. No cross-layer coupling. |
| **Backend Agnostic** | Plugins never import orchestration frameworks (Celery, Prefect, Dagster). |
| **Idempotent by Design** | Every operation is safely rerunnable without duplicating data. |
| **Versioned & Reproducible** | Any historical output can be reproduced by specifying explicit versions. |
| **Testable in Isolation** | Each plugin is unit-testable without database or network. |

### 1.2 What It Means to Extend

#### Adding a New Connector

A connector fetches raw OTC trade data from an external source (API, file, message queue).

**Developer must:**
1. Create `app/domains/otc/connectors/{source_name}.py`
2. Implement `ConnectorProtocol` with `capture()` method
3. Define a Pydantic params model for configuration
4. Register in `app/domains/otc/registry.py`
5. Add unit tests in `app/domains/otc/tests/connectors/`
6. Add fixtures in `app/domains/otc/fixtures/connectors/`

**Connector responsibilities:**
- Fetch raw data from external source
- Return `CaptureBatch` with `RawTradeRecord` objects
- Generate deterministic `record_hash` for deduplication

**Connector must NOT:**
- Write to any database table
- Transform data into canonical schema
- Import orchestration frameworks

#### Adding a New Normalizer Version

A normalizer transforms raw records into canonical `otc_trades` schema.

**Developer must:**
1. Create `app/domains/otc/normalizers/trades_v{N}.py`
2. Implement `NormalizerProtocol` with `normalize()` method
3. Declare `input_schema_version` compatibility
4. Register in `app/domains/otc/registry.py`
5. Add golden tests in `app/domains/otc/tests/normalizers/`
6. Add fixtures with expected outputs

**Normalizer responsibilities:**
- Transform `RawTradeRecord` → `CanonicalTrade`
- Generate stable `trade_id` for identity
- Classify records as `accepted` or `rejected` (with reason)

**Normalizer must NOT:**
- Fetch data from external sources
- Write directly to database
- Depend on other normalizer versions at runtime

#### Adding a New Calculation

A calculation derives metrics from canonical trade data.

**Developer must:**
1. Create `app/domains/otc/calculations/{calc_name}_v{N}.py`
2. Implement `CalculationProtocol` with `compute()` method
3. Define input query shape and output schema
4. Register in `app/domains/otc/registry.py`
5. Add golden tests with deterministic fixtures
6. Document formula and assumptions

**Calculation responsibilities:**
- Read from canonical schema only
- Produce deterministic, reproducible output
- Include `calc_name` and `calc_version` in output metadata

**Calculation must NOT:**
- Call connectors or fetch external data
- Modify source data
- Produce non-deterministic results

### 1.3 Two-Minute Extension Guide

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     ADDING A NEW CONNECTOR                               │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. app/domains/otc/connectors/my_source.py    # Implement connector     │
│ 2. app/domains/otc/registry.py                # Register it             │
│ 3. app/domains/otc/fixtures/connectors/       # Add test fixtures       │
│ 4. app/domains/otc/tests/connectors/          # Add unit tests          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                   ADDING A NEW NORMALIZER VERSION                        │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. app/domains/otc/normalizers/trades_v2.py   # Implement normalizer    │
│ 2. app/domains/otc/registry.py                # Register it             │
│ 3. app/domains/otc/fixtures/normalizers/      # Add golden fixtures     │
│ 4. app/domains/otc/tests/normalizers/         # Add golden tests        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      ADDING A NEW CALCULATION                            │
├─────────────────────────────────────────────────────────────────────────┤
│ 1. app/domains/otc/calculations/my_calc_v1.py # Implement calc          │
│ 2. app/domains/otc/registry.py                # Register it             │
│ 3. app/domains/otc/fixtures/calculations/     # Add expected outputs    │
│ 4. app/domains/otc/tests/calculations/        # Add golden tests        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Folder Structure

### 2.1 Authoritative Directory Tree

```
app/
└── domains/
    └── otc/
        ├── __init__.py
        ├── contracts.py              # Pydantic models + Protocol definitions
        ├── registry.py               # Plugin registries + resolution
        ├── exceptions.py             # Domain-specific exceptions
        │
        ├── connectors/
        │   ├── __init__.py
        │   ├── base.py               # Base connector utilities
        │   ├── ats_a.py              # ATS_A venue connector
        │   ├── ats_b.py              # ATS_B venue connector
        │   └── file_import.py        # CSV/JSON file connector
        │
        ├── normalizers/
        │   ├── __init__.py
        │   ├── base.py               # Base normalizer utilities
        │   ├── trades_v1.py          # Original normalizer
        │   └── trades_v2.py          # Updated normalizer (new fields)
        │
        ├── calculations/
        │   ├── __init__.py
        │   ├── base.py               # Base calculation utilities
        │   ├── daily_volume_v1.py    # Daily volume aggregation
        │   ├── vwap_v1.py            # Volume-weighted average price
        │   └── liquidity_score_v1.py # Liquidity scoring
        │
        ├── pipelines/
        │   ├── __init__.py
        │   ├── ingest.py             # otc_ingest pipeline
        │   ├── normalize.py          # otc_normalize pipeline
        │   └── compute.py            # otc_compute pipeline
        │
        ├── repositories/
        │   ├── __init__.py
        │   ├── raw_trades.py         # Bronze layer repository
        │   ├── trades.py             # Silver layer repository
        │   └── metrics.py            # Gold layer repository
        │
        ├── fixtures/
        │   ├── __init__.py
        │   ├── connectors/
        │   │   ├── ats_a_sample.json
        │   │   └── ats_b_sample.json
        │   ├── normalizers/
        │   │   ├── raw_input_v1.json
        │   │   ├── expected_output_v1.json
        │   │   └── expected_output_v2.json
        │   └── calculations/
        │       ├── trades_input.json
        │       ├── daily_volume_expected.json
        │       ├── vwap_expected.json
        │       └── liquidity_score_expected.json
        │
        └── tests/
            ├── __init__.py
            ├── conftest.py           # Shared fixtures
            ├── connectors/
            │   ├── __init__.py
            │   ├── test_ats_a.py
            │   └── test_ats_b.py
            ├── normalizers/
            │   ├── __init__.py
            │   ├── test_trades_v1.py
            │   └── test_trades_v2.py
            ├── calculations/
            │   ├── __init__.py
            │   ├── test_daily_volume.py
            │   ├── test_vwap.py
            │   └── test_liquidity_score.py
            └── pipelines/
                ├── __init__.py
                └── test_pipeline_integration.py
```

### 2.2 Layer Mapping

| Layer | Tables | Domain Folder | Purpose |
|-------|--------|---------------|---------|
| **Bronze** | `otc_trades_raw` | `connectors/`, `repositories/raw_trades.py` | Append-only raw capture |
| **Silver** | `otc_trades` | `normalizers/`, `repositories/trades.py` | Canonical, deduplicated |
| **Gold** | `otc_metrics_daily` | `calculations/`, `repositories/metrics.py` | Derived analytics |

### 2.3 Integration Points

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         EXECUTION FLOW                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   dispatcher.submit(pipeline="otc_ingest", ...)                         │
│         │                                                                │
│         ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  Execution Ledger (executions, execution_events, dead_letters)  │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│         │                                                                │
│         ▼                                                                │
│   run_pipeline(execution_id)                                            │
│         │                                                                │
│         ▼                                                                │
│   runtime.runner                                                         │
│         │                                                                │
│         ▼                                                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │  domains/otc/pipelines/{ingest,normalize,compute}.py            │   │
│   │      │                                                           │   │
│   │      ├── registry.resolve_connector(name)                        │   │
│   │      ├── registry.resolve_normalizer(version)                    │   │
│   │      └── registry.resolve_calc(name, version)                    │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Plugin Interfaces

All interfaces are defined in `app/domains/otc/contracts.py`.

### 3.1 Core Data Models

```python
# app/domains/otc/contracts.py

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Protocol, TypeVar, Generic, Any
from uuid import UUID
import hashlib

from pydantic import BaseModel, Field, computed_field


# =============================================================================
# ENUMS
# =============================================================================

class TradeDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"


class NormalizationStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# =============================================================================
# RAW LAYER (BRONZE)
# =============================================================================

class RawTradeRecord(BaseModel):
    """Individual raw trade record from a connector."""
    
    source: str = Field(..., description="Connector source identifier (e.g., 'ats_a')")
    raw_payload: dict[str, Any] = Field(..., description="Original payload as received")
    captured_at: datetime = Field(..., description="Timestamp when record was captured")
    
    @computed_field
    @property
    def record_hash(self) -> str:
        """
        Deterministic hash for deduplication.
        
        Rule: hash(source + sorted(raw_payload as canonical JSON))
        """
        import json
        canonical = json.dumps(self.raw_payload, sort_keys=True, default=str)
        content = f"{self.source}:{canonical}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]


class CaptureBatch(BaseModel):
    """Output of a connector capture operation."""
    
    batch_id: UUID = Field(..., description="Unique batch identifier")
    connector_name: str = Field(..., description="Name of the connector")
    connector_version: str = Field(..., description="Version of the connector")
    source: str = Field(..., description="Data source identifier")
    captured_at: datetime = Field(..., description="Batch capture timestamp")
    records: list[RawTradeRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    @property
    def record_count(self) -> int:
        return len(self.records)


# =============================================================================
# CANONICAL LAYER (SILVER)
# =============================================================================

class CanonicalTrade(BaseModel):
    """Normalized trade in canonical schema."""
    
    trade_id: str = Field(..., description="Stable unique trade identifier")
    source: str = Field(..., description="Original data source")
    record_hash: str = Field(..., description="Hash of source raw record")
    schema_version: str = Field(..., description="Normalizer version used")
    
    # Trade fields
    symbol: str = Field(..., min_length=1, max_length=20)
    trade_date: date
    trade_time: datetime
    direction: TradeDirection
    quantity: Decimal = Field(..., gt=0)
    price: Decimal = Field(..., gt=0)
    notional: Decimal = Field(..., gt=0)
    venue: str = Field(..., description="Execution venue")
    
    # Audit
    normalized_at: datetime


class NormalizationResult(BaseModel):
    """Output of a normalizer operation."""
    
    normalizer_name: str
    normalizer_version: str
    input_record_hash: str
    status: NormalizationStatus
    trade: CanonicalTrade | None = None
    rejection_reason: str | None = None


class NormalizationBatch(BaseModel):
    """Batch result from normalizer."""
    
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


# =============================================================================
# METRICS LAYER (GOLD)
# =============================================================================

class MetricRow(BaseModel):
    """Single metric output row."""
    
    symbol: str
    metric_date: date
    calc_name: str
    calc_version: str
    value: Decimal
    metadata: dict[str, Any] = Field(default_factory=dict)
    computed_at: datetime


class CalculationResult(BaseModel):
    """Output of a calculation operation."""
    
    calc_name: str
    calc_version: str
    computed_at: datetime
    rows: list[MetricRow] = Field(default_factory=list)
    input_trade_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 3.2 Connector Protocol

```python
# app/domains/otc/contracts.py (continued)

from typing import Protocol, TypeVar, Generic

TParams = TypeVar("TParams", bound=BaseModel)


class ConnectorParams(BaseModel):
    """Base class for connector parameters."""
    
    symbols: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None


class ConnectorProtocol(Protocol[TParams]):
    """
    Protocol for OTC data connectors.
    
    Connectors are responsible for:
    - Fetching raw data from external sources
    - Producing CaptureBatch with RawTradeRecord objects
    - Generating deterministic record_hash for deduplication
    
    Connectors must NOT:
    - Write to any database table
    - Transform data into canonical schema
    - Import orchestration frameworks
    """
    
    @property
    def name(self) -> str:
        """Unique connector identifier."""
        ...
    
    @property
    def version(self) -> str:
        """Connector version (semver recommended)."""
        ...
    
    @property
    def source(self) -> str:
        """Data source identifier for record attribution."""
        ...
    
    def capture(self, params: TParams) -> CaptureBatch:
        """
        Capture raw trade data.
        
        Args:
            params: Connector-specific parameters
            
        Returns:
            CaptureBatch containing RawTradeRecord objects
            
        Raises:
            ConnectorError: On fetch failure (retryable)
            ConnectorConfigError: On invalid configuration (non-retryable)
        """
        ...
```

**Example Connector Implementation:**

```python
# app/domains/otc/connectors/ats_a.py

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field

from app.domains.otc.contracts import (
    ConnectorProtocol,
    ConnectorParams,
    CaptureBatch,
    RawTradeRecord,
)
from app.domains.otc.exceptions import ConnectorError
from app.core.time import utc_now


class ATSAParams(ConnectorParams):
    """Parameters for ATS_A connector."""
    
    api_key: str = Field(..., description="API authentication key")
    batch_size: int = Field(default=1000, ge=1, le=10000)


class ATSAConnector:
    """Connector for ATS_A trading venue."""
    
    name: str = "ats_a"
    version: str = "1.0.0"
    source: str = "ats_a"
    
    def __init__(self, client=None):
        """
        Args:
            client: Optional HTTP client for dependency injection in tests.
        """
        self._client = client
    
    def capture(self, params: ATSAParams) -> CaptureBatch:
        """Fetch trades from ATS_A API."""
        captured_at = utc_now()
        
        try:
            # In real implementation, call external API
            raw_trades = self._fetch_from_api(params)
        except Exception as e:
            raise ConnectorError(f"ATS_A fetch failed: {e}") from e
        
        records = [
            RawTradeRecord(
                source=self.source,
                raw_payload=trade,
                captured_at=captured_at,
            )
            for trade in raw_trades
        ]
        
        return CaptureBatch(
            batch_id=uuid4(),
            connector_name=self.name,
            connector_version=self.version,
            source=self.source,
            captured_at=captured_at,
            records=records,
            metadata={
                "symbols": params.symbols,
                "start_date": str(params.start_date),
                "end_date": str(params.end_date),
            },
        )
    
    def _fetch_from_api(self, params: ATSAParams) -> list[dict]:
        """Internal: Fetch from ATS_A API."""
        # Implementation would use self._client or httpx
        ...
```

### 3.3 Normalizer Protocol

```python
# app/domains/otc/contracts.py (continued)

class NormalizerProtocol(Protocol):
    """
    Protocol for OTC trade normalizers.
    
    Normalizers are responsible for:
    - Transforming RawTradeRecord → CanonicalTrade
    - Generating stable trade_id for identity
    - Classifying records as accepted or rejected
    
    Normalizers must NOT:
    - Fetch data from external sources
    - Write directly to database
    - Depend on other normalizer versions at runtime
    """
    
    @property
    def name(self) -> str:
        """Normalizer identifier (e.g., 'trades')."""
        ...
    
    @property
    def version(self) -> str:
        """Normalizer version (e.g., 'v1', 'v2')."""
        ...
    
    @property
    def input_schema_version(self) -> str:
        """
        Expected raw payload schema version.
        Used for compatibility checking.
        """
        ...
    
    def normalize(self, record: RawTradeRecord) -> NormalizationResult:
        """
        Normalize a single raw record.
        
        Args:
            record: Raw trade record to normalize
            
        Returns:
            NormalizationResult with status and optional trade/rejection_reason
            
        Error Handling:
        - Missing required fields → REJECTED with reason
        - Invalid data types → REJECTED with reason
        - Parsing exceptions → REJECTED with reason
        - System errors → Raise exception (fails batch)
        """
        ...
    
    def normalize_batch(self, records: list[RawTradeRecord]) -> NormalizationBatch:
        """
        Normalize a batch of raw records.
        
        Default implementation calls normalize() for each record.
        Override for batch optimizations.
        """
        ...
```

**Example Normalizer Implementation:**

```python
# app/domains/otc/normalizers/trades_v1.py

from datetime import datetime, date
from decimal import Decimal, InvalidOperation

from app.domains.otc.contracts import (
    NormalizerProtocol,
    RawTradeRecord,
    NormalizationResult,
    NormalizationBatch,
    NormalizationStatus,
    CanonicalTrade,
    TradeDirection,
)
from app.core.time import utc_now


class TradesNormalizerV1:
    """V1 normalizer for OTC trades."""
    
    name: str = "trades"
    version: str = "v1"
    input_schema_version: str = "raw_v1"
    
    def normalize(self, record: RawTradeRecord) -> NormalizationResult:
        """Normalize a single raw trade record."""
        payload = record.raw_payload
        
        # Validate required fields
        required = ["symbol", "trade_date", "side", "qty", "price", "venue"]
        missing = [f for f in required if f not in payload]
        if missing:
            return NormalizationResult(
                normalizer_name=self.name,
                normalizer_version=self.version,
                input_record_hash=record.record_hash,
                status=NormalizationStatus.REJECTED,
                rejection_reason=f"Missing required fields: {missing}",
            )
        
        try:
            # Parse and validate
            symbol = str(payload["symbol"]).upper().strip()
            trade_date = self._parse_date(payload["trade_date"])
            trade_time = self._parse_datetime(payload.get("trade_time", payload["trade_date"]))
            direction = self._parse_direction(payload["side"])
            quantity = Decimal(str(payload["qty"]))
            price = Decimal(str(payload["price"]))
            venue = str(payload["venue"]).upper().strip()
            
            if quantity <= 0 or price <= 0:
                return self._reject(record, "Quantity and price must be positive")
            
            # Generate stable trade_id
            trade_id = self._generate_trade_id(record, symbol, trade_date, venue)
            
            trade = CanonicalTrade(
                trade_id=trade_id,
                source=record.source,
                record_hash=record.record_hash,
                schema_version=self.version,
                symbol=symbol,
                trade_date=trade_date,
                trade_time=trade_time,
                direction=direction,
                quantity=quantity,
                price=price,
                notional=quantity * price,
                venue=venue,
                normalized_at=utc_now(),
            )
            
            return NormalizationResult(
                normalizer_name=self.name,
                normalizer_version=self.version,
                input_record_hash=record.record_hash,
                status=NormalizationStatus.ACCEPTED,
                trade=trade,
            )
            
        except (ValueError, InvalidOperation, KeyError) as e:
            return self._reject(record, f"Parsing error: {e}")
    
    def normalize_batch(self, records: list[RawTradeRecord]) -> NormalizationBatch:
        """Normalize a batch of records."""
        results = [self.normalize(r) for r in records]
        return NormalizationBatch(
            normalizer_name=self.name,
            normalizer_version=self.version,
            processed_at=utc_now(),
            results=results,
        )
    
    def _reject(self, record: RawTradeRecord, reason: str) -> NormalizationResult:
        return NormalizationResult(
            normalizer_name=self.name,
            normalizer_version=self.version,
            input_record_hash=record.record_hash,
            status=NormalizationStatus.REJECTED,
            rejection_reason=reason,
        )
    
    def _generate_trade_id(
        self,
        record: RawTradeRecord,
        symbol: str,
        trade_date: date,
        venue: str,
    ) -> str:
        """Generate stable trade ID from record attributes."""
        # Combine source + record_hash for global uniqueness
        return f"{record.source}:{record.record_hash[:16]}"
    
    def _parse_date(self, value) -> date:
        if isinstance(value, date):
            return value
        return datetime.fromisoformat(str(value)).date()
    
    def _parse_datetime(self, value) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
    
    def _parse_direction(self, value: str) -> TradeDirection:
        v = str(value).lower().strip()
        if v in ("buy", "b", "bid"):
            return TradeDirection.BUY
        if v in ("sell", "s", "ask", "offer"):
            return TradeDirection.SELL
        raise ValueError(f"Unknown direction: {value}")
```

### 3.4 Calculation Protocol

```python
# app/domains/otc/contracts.py (continued)

class CalculationParams(BaseModel):
    """Base parameters for calculations."""
    
    symbols: list[str] | None = None
    start_date: date
    end_date: date


class CalculationProtocol(Protocol[TParams]):
    """
    Protocol for OTC metric calculations.
    
    Calculations are responsible for:
    - Reading from canonical schema only
    - Producing deterministic, reproducible output
    - Including calc metadata in output rows
    
    Calculations must NOT:
    - Call connectors or fetch external data
    - Modify source data
    - Produce non-deterministic results (no random, no wall-clock time in formulas)
    """
    
    @property
    def name(self) -> str:
        """Calculation identifier (e.g., 'daily_volume')."""
        ...
    
    @property
    def version(self) -> str:
        """Calculation version (e.g., 'v1')."""
        ...
    
    @property
    def output_columns(self) -> list[str]:
        """List of output metric columns produced."""
        ...
    
    def compute(
        self,
        trades: list[CanonicalTrade],
        params: TParams,
    ) -> CalculationResult:
        """
        Compute metrics from canonical trades.
        
        Args:
            trades: Canonical trades to process
            params: Calculation-specific parameters
            
        Returns:
            CalculationResult with MetricRow objects
            
        Requirements:
        - Must be deterministic given same inputs
        - Must include calc_name and calc_version in output
        - Must handle empty input gracefully
        """
        ...
```

**Example Calculation Implementation:**

```python
# app/domains/otc/calculations/daily_volume_v1.py

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.domains.otc.contracts import (
    CalculationProtocol,
    CalculationParams,
    CalculationResult,
    MetricRow,
    CanonicalTrade,
)
from app.core.time import utc_now


class DailyVolumeParams(CalculationParams):
    """Parameters for daily volume calculation."""
    pass  # Uses base params only


class DailyVolumeV1:
    """V1 daily volume aggregation calculation."""
    
    name: str = "daily_volume"
    version: str = "v1"
    output_columns: list[str] = ["total_quantity", "total_notional", "trade_count"]
    
    def compute(
        self,
        trades: list[CanonicalTrade],
        params: DailyVolumeParams,
    ) -> CalculationResult:
        """Compute daily volume metrics by symbol."""
        computed_at = utc_now()
        
        # Aggregate by (symbol, date)
        agg: dict[tuple[str, date], dict] = defaultdict(
            lambda: {"quantity": Decimal(0), "notional": Decimal(0), "count": 0}
        )
        
        for trade in trades:
            key = (trade.symbol, trade.trade_date)
            agg[key]["quantity"] += trade.quantity
            agg[key]["notional"] += trade.notional
            agg[key]["count"] += 1
        
        rows = []
        for (symbol, metric_date), values in sorted(agg.items()):
            rows.append(MetricRow(
                symbol=symbol,
                metric_date=metric_date,
                calc_name=self.name,
                calc_version=self.version,
                value=values["notional"],  # Primary value is notional
                metadata={
                    "total_quantity": str(values["quantity"]),
                    "total_notional": str(values["notional"]),
                    "trade_count": values["count"],
                },
                computed_at=computed_at,
            ))
        
        return CalculationResult(
            calc_name=self.name,
            calc_version=self.version,
            computed_at=computed_at,
            rows=rows,
            input_trade_count=len(trades),
        )
```

---

## 4. Registry & Wiring

### 4.1 Registry Location and Structure

The registry lives at `app/domains/otc/registry.py` and provides:
- Plugin registration at import time
- Resolution by name/version
- Configuration-based default version selection
- Fail-fast behavior for missing plugins

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
    """Registry entry for a plugin."""
    name: str
    version: str
    factory: Callable[[], T]
    metadata: dict[str, Any] = field(default_factory=dict)


class PluginRegistry(Generic[T]):
    """Generic plugin registry with name/version resolution."""
    
    def __init__(self, plugin_type: str):
        self._plugin_type = plugin_type
        self._entries: dict[str, dict[str, PluginEntry[T]]] = {}
        self._defaults: dict[str, str] = {}
    
    def register(
        self,
        name: str,
        version: str,
        factory: Callable[[], T],
        *,
        metadata: dict[str, Any] | None = None,
        is_default: bool = False,
    ) -> None:
        """
        Register a plugin.
        
        Args:
            name: Plugin name (e.g., 'ats_a', 'trades', 'daily_volume')
            version: Plugin version (e.g., 'v1', '1.0.0')
            factory: Callable that returns plugin instance
            metadata: Optional metadata
            is_default: If True, set as default version for this name
        """
        if name not in self._entries:
            self._entries[name] = {}
        
        self._entries[name][version] = PluginEntry(
            name=name,
            version=version,
            factory=factory,
            metadata=metadata or {},
        )
        
        if is_default or name not in self._defaults:
            self._defaults[name] = version
    
    def set_default(self, name: str, version: str) -> None:
        """Set default version for a plugin name."""
        if name not in self._entries:
            raise PluginNotFoundError(self._plugin_type, name)
        if version not in self._entries[name]:
            raise PluginVersionNotFoundError(self._plugin_type, name, version)
        self._defaults[name] = version
    
    def resolve(self, name: str, version: str | None = None) -> T:
        """
        Resolve and instantiate a plugin.
        
        Args:
            name: Plugin name
            version: Optional version (uses default if None)
            
        Returns:
            Instantiated plugin
            
        Raises:
            PluginNotFoundError: If plugin name not registered
            PluginVersionNotFoundError: If version not found
        """
        if name not in self._entries:
            raise PluginNotFoundError(self._plugin_type, name)
        
        versions = self._entries[name]
        target_version = version or self._defaults.get(name)
        
        if target_version is None or target_version not in versions:
            available = list(versions.keys())
            raise PluginVersionNotFoundError(
                self._plugin_type, name, target_version, available
            )
        
        return versions[target_version].factory()
    
    def list_plugins(self) -> dict[str, list[str]]:
        """List all registered plugins and their versions."""
        return {name: list(versions.keys()) for name, versions in self._entries.items()}
    
    def get_default_version(self, name: str) -> str | None:
        """Get default version for a plugin name."""
        return self._defaults.get(name)


# =============================================================================
# GLOBAL REGISTRIES
# =============================================================================

connectors: PluginRegistry[ConnectorProtocol] = PluginRegistry("connector")
normalizers: PluginRegistry[NormalizerProtocol] = PluginRegistry("normalizer")
calculations: PluginRegistry[CalculationProtocol] = PluginRegistry("calculation")


# =============================================================================
# RESOLUTION FUNCTIONS
# =============================================================================

def resolve_connector(name: str) -> ConnectorProtocol:
    """
    Resolve a connector by name.
    
    Args:
        name: Connector name (e.g., 'ats_a')
        
    Returns:
        Instantiated connector
    """
    return connectors.resolve(name)


def resolve_normalizer(version: str | None = None) -> NormalizerProtocol:
    """
    Resolve a normalizer by version.
    
    Args:
        version: Normalizer version (e.g., 'v1', 'v2'). Uses default if None.
        
    Returns:
        Instantiated normalizer
    """
    return normalizers.resolve("trades", version)


def resolve_calc(name: str, version: str | None = None) -> CalculationProtocol:
    """
    Resolve a calculation by name and version.
    
    Args:
        name: Calculation name (e.g., 'daily_volume')
        version: Calculation version. Uses default if None.
        
    Returns:
        Instantiated calculation
    """
    return calculations.resolve(name, version)
```

### 4.2 Plugin Registration

Plugins are registered at module import time using decorators or explicit calls:

```python
# app/domains/otc/connectors/__init__.py

from app.domains.otc.registry import connectors
from app.domains.otc.connectors.ats_a import ATSAConnector
from app.domains.otc.connectors.ats_b import ATSBConnector
from app.domains.otc.connectors.file_import import FileImportConnector


# Register connectors
connectors.register("ats_a", "1.0.0", ATSAConnector, is_default=True)
connectors.register("ats_b", "1.0.0", ATSBConnector, is_default=True)
connectors.register("file_import", "1.0.0", FileImportConnector, is_default=True)
```

```python
# app/domains/otc/normalizers/__init__.py

from app.domains.otc.registry import normalizers
from app.domains.otc.normalizers.trades_v1 import TradesNormalizerV1
from app.domains.otc.normalizers.trades_v2 import TradesNormalizerV2


# Register normalizers (v1 is default initially)
normalizers.register("trades", "v1", TradesNormalizerV1, is_default=True)
normalizers.register("trades", "v2", TradesNormalizerV2)
```

```python
# app/domains/otc/calculations/__init__.py

from app.domains.otc.registry import calculations
from app.domains.otc.calculations.daily_volume_v1 import DailyVolumeV1
from app.domains.otc.calculations.vwap_v1 import VWAPV1
from app.domains.otc.calculations.liquidity_score_v1 import LiquidityScoreV1


# Register calculations
calculations.register("daily_volume", "v1", DailyVolumeV1, is_default=True)
calculations.register("vwap", "v1", VWAPV1, is_default=True)
calculations.register("liquidity_score", "v1", LiquidityScoreV1, is_default=True)
```

### 4.3 Configuration-Based Defaults

Default versions can be overridden via settings:

```python
# app/core/settings.py

from pydantic_settings import BaseSettings


class OTCSettings(BaseSettings):
    """OTC domain configuration."""
    
    # Default plugin versions
    normalizer_version: str = "v1"
    calc_daily_volume_version: str = "v1"
    calc_vwap_version: str = "v1"
    calc_liquidity_score_version: str = "v1"
    
    class Config:
        env_prefix = "OTC_"


# Apply settings to registry at startup
def configure_otc_defaults(settings: OTCSettings) -> None:
    from app.domains.otc.registry import normalizers, calculations
    
    normalizers.set_default("trades", settings.normalizer_version)
    calculations.set_default("daily_volume", settings.calc_daily_volume_version)
    calculations.set_default("vwap", settings.calc_vwap_version)
    calculations.set_default("liquidity_score", settings.calc_liquidity_score_version)
```

### 4.4 Per-Execution Override

Execution parameters can specify version overrides:

```python
# Example: dispatcher.submit with version override

await dispatcher.submit(
    pipeline="otc_normalize",
    params={
        "batch_id": "abc-123",
        "normalizer_version": "v2",  # Override default
    },
    logical_key="otc_normalize:batch:abc-123",
)

await dispatcher.submit(
    pipeline="otc_compute",
    params={
        "calc": "daily_volume",
        "version": "v1",  # Explicit version
        "symbols": ["AAPL", "MSFT"],
        "start_date": "2026-01-01",
        "end_date": "2026-01-15",
    },
    logical_key="otc_compute:daily_volume:2026-01-01",
)
```

### 4.5 Pipeline Resolution Example

```python
# app/domains/otc/pipelines/normalize.py

from app.domains.otc.registry import resolve_normalizer
from app.domains.otc.repositories.raw_trades import RawTradesRepository
from app.domains.otc.repositories.trades import TradesRepository


async def run_normalize_pipeline(
    execution_id: str,
    params: dict,
    *,
    raw_repo: RawTradesRepository,
    trades_repo: TradesRepository,
) -> dict:
    """
    OTC normalization pipeline.
    
    Resolves normalizer from registry, processes raw records, writes canonical trades.
    """
    batch_id = params["batch_id"]
    version = params.get("normalizer_version")  # None = use default
    
    # Resolve normalizer (fail-fast if not found)
    normalizer = resolve_normalizer(version)
    
    # Fetch raw records
    raw_records = await raw_repo.get_batch(batch_id)
    
    # Normalize
    result = normalizer.normalize_batch(raw_records)
    
    # Persist accepted trades (repository handles upsert)
    accepted_trades = [r.trade for r in result.results if r.trade]
    await trades_repo.upsert_batch(accepted_trades)
    
    return {
        "batch_id": batch_id,
        "normalizer": f"{normalizer.name}:{normalizer.version}",
        "accepted": result.accepted_count,
        "rejected": result.rejected_count,
    }
```

### 4.6 Fail-Fast Behavior

```python
# app/domains/otc/exceptions.py

class OTCDomainError(Exception):
    """Base exception for OTC domain."""
    pass


class PluginNotFoundError(OTCDomainError):
    """Raised when a plugin is not registered."""
    
    def __init__(self, plugin_type: str, name: str):
        self.plugin_type = plugin_type
        self.name = name
        super().__init__(
            f"{plugin_type.capitalize()} '{name}' is not registered. "
            f"Check that the plugin module is imported."
        )


class PluginVersionNotFoundError(OTCDomainError):
    """Raised when a plugin version is not found."""
    
    def __init__(
        self,
        plugin_type: str,
        name: str,
        version: str | None,
        available: list[str] | None = None,
    ):
        self.plugin_type = plugin_type
        self.name = name
        self.version = version
        self.available = available or []
        
        msg = f"{plugin_type.capitalize()} '{name}' version '{version}' not found."
        if self.available:
            msg += f" Available versions: {self.available}"
        super().__init__(msg)


class ConnectorError(OTCDomainError):
    """Raised on connector fetch failure (retryable)."""
    pass


class ConnectorConfigError(OTCDomainError):
    """Raised on connector configuration error (non-retryable)."""
    pass
```

---

## 5. Versioning Strategy

### 5.1 Version Representation

| Component | Version Format | Storage Column | Example |
|-----------|----------------|----------------|---------|
| Connector | `X.Y.Z` (semver) | `batch.connector_version` | `1.0.0` |
| Normalizer | `vN` | `otc_trades.schema_version` | `v1`, `v2` |
| Calculation | `vN` | `otc_metrics_daily.calc_version` | `v1` |

### 5.2 Side-by-Side Normalizer Versions

To introduce `trades_v2.py` alongside `trades_v1.py`:

**Step 1: Create new normalizer**

```python
# app/domains/otc/normalizers/trades_v2.py

from app.domains.otc.contracts import (
    NormalizerProtocol,
    RawTradeRecord,
    NormalizationResult,
    CanonicalTrade,
)


class TradesNormalizerV2:
    """
    V2 normalizer with enhanced parsing:
    - Supports new raw schema fields (settlement_date, counterparty)
    - Improved direction parsing
    - Stricter validation
    """
    
    name: str = "trades"
    version: str = "v2"
    input_schema_version: str = "raw_v2"
    
    def normalize(self, record: RawTradeRecord) -> NormalizationResult:
        # V2 implementation with new fields
        ...
```

**Step 2: Register new version**

```python
# app/domains/otc/normalizers/__init__.py

normalizers.register("trades", "v2", TradesNormalizerV2)

# To make v2 the default:
# normalizers.register("trades", "v2", TradesNormalizerV2, is_default=True)
```

**Step 3: Run side-by-side**

Both versions can run simultaneously. The `schema_version` column tracks which normalizer produced each trade:

```sql
SELECT schema_version, COUNT(*) 
FROM otc_trades 
GROUP BY schema_version;

-- Result:
-- v1 | 4500
-- v2 | 1200
```

### 5.3 Backfilling Silver from Bronze with V2

To re-normalize historical raw records with V2:

```python
# Backfill execution
await dispatcher.submit(
    pipeline="otc_normalize_backfill",
    params={
        "source": "ats_a",
        "start_date": "2025-12-01",
        "end_date": "2025-12-31",
        "normalizer_version": "v2",  # Force v2
    },
    logical_key="otc_backfill:ats_a:2025-12-01:v2",
)
```

**Backfill pipeline behavior:**
1. Fetch raw records from `otc_trades_raw` for date range
2. Normalize with specified version
3. Upsert to `otc_trades` (updates existing trade_id or inserts new)
4. Track `schema_version` = "v2" on all affected rows

```python
# app/domains/otc/pipelines/normalize_backfill.py

async def run_normalize_backfill_pipeline(
    execution_id: str,
    params: dict,
    *,
    raw_repo: RawTradesRepository,
    trades_repo: TradesRepository,
) -> dict:
    """Backfill normalization with specific version."""
    version = params["normalizer_version"]
    normalizer = resolve_normalizer(version)
    
    # Fetch raw records for date range
    raw_records = await raw_repo.get_by_date_range(
        source=params["source"],
        start_date=params["start_date"],
        end_date=params["end_date"],
    )
    
    result = normalizer.normalize_batch(raw_records)
    
    # Upsert with new schema_version
    accepted = [r.trade for r in result.results if r.trade]
    await trades_repo.upsert_batch(accepted)  # trade_id is stable, so updates in place
    
    return {
        "normalizer": f"{normalizer.name}:{normalizer.version}",
        "processed": len(raw_records),
        "accepted": result.accepted_count,
    }
```

### 5.4 Side-by-Side Calculation Versions

Calculations can have multiple versions producing **separate metric rows**:

```sql
-- Daily volume computed with v1 and v2 exist side-by-side
SELECT symbol, metric_date, calc_name, calc_version, value
FROM otc_metrics_daily
WHERE symbol = 'AAPL' AND metric_date = '2026-01-01';

-- Result:
-- AAPL | 2026-01-01 | daily_volume | v1 | 1500000.00
-- AAPL | 2026-01-01 | daily_volume | v2 | 1485000.00  (different formula)
```

**Key insight:** Changing the uniqueness constraint to include `calc_version` allows historical data to remain untouched while new versions are computed.

### 5.5 Reproducing Historical Outputs

To reproduce outputs with specific versions:

```python
# Reproduce metrics with explicit versions
await dispatcher.submit(
    pipeline="otc_compute",
    params={
        "calc": "daily_volume",
        "version": "v1",  # Explicit version
        "symbols": ["AAPL"],
        "start_date": "2025-12-01",
        "end_date": "2025-12-15",
        "force_recompute": True,
    },
    logical_key="otc_compute:daily_volume:AAPL:2025-12-01:v1",
)
```

### 5.6 Database Schema for Versions

```sql
-- Bronze: otc_trades_raw
CREATE TABLE otc_trades_raw (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    source VARCHAR(50) NOT NULL,
    record_hash VARCHAR(64) NOT NULL,
    raw_payload JSONB NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    connector_name VARCHAR(100),
    connector_version VARCHAR(20),
    
    UNIQUE (source, record_hash)  -- Dedup per source
);

-- Silver: otc_trades  
CREATE TABLE otc_trades (
    id BIGSERIAL PRIMARY KEY,
    trade_id VARCHAR(100) NOT NULL UNIQUE,  -- Stable identity
    source VARCHAR(50) NOT NULL,
    record_hash VARCHAR(64) NOT NULL,
    schema_version VARCHAR(10) NOT NULL,    -- Normalizer version
    
    symbol VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    trade_time TIMESTAMPTZ NOT NULL,
    direction VARCHAR(10) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    price NUMERIC(20,8) NOT NULL,
    notional NUMERIC(30,8) NOT NULL,
    venue VARCHAR(50) NOT NULL,
    
    normalized_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_otc_trades_symbol_date ON otc_trades(symbol, trade_date);
CREATE INDEX idx_otc_trades_schema_version ON otc_trades(schema_version);

-- Gold: otc_metrics_daily
CREATE TABLE otc_metrics_daily (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    metric_date DATE NOT NULL,
    calc_name VARCHAR(100) NOT NULL,
    calc_version VARCHAR(20) NOT NULL,
    value NUMERIC(30,8) NOT NULL,
    metadata JSONB DEFAULT '{}',
    
    computed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE (symbol, metric_date, calc_name, calc_version)
);

CREATE INDEX idx_otc_metrics_symbol_date ON otc_metrics_daily(symbol, metric_date);
CREATE INDEX idx_otc_metrics_calc ON otc_metrics_daily(calc_name, calc_version);
```

### 5.7 API Queries: Latest vs Specific Version

```python
# app/api/routes/otc_metrics.py

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/otc/metrics", tags=["otc"])


@router.get("/daily-volume")
async def get_daily_volume(
    symbol: str,
    start_date: date,
    end_date: date,
    version: str | None = Query(None, description="Calc version (default: latest)"),
):
    """
    Get daily volume metrics.
    
    If version is None, returns the latest version for each date.
    """
    if version:
        # Specific version
        return await metrics_repo.get_by_calc(
            symbol=symbol,
            calc_name="daily_volume",
            calc_version=version,
            start_date=start_date,
            end_date=end_date,
        )
    else:
        # Latest version per date (subquery for max version)
        return await metrics_repo.get_latest_by_calc(
            symbol=symbol,
            calc_name="daily_volume",
            start_date=start_date,
            end_date=end_date,
        )
```

```sql
-- Query for latest version per (symbol, date, calc_name)
SELECT DISTINCT ON (symbol, metric_date)
    symbol, metric_date, calc_name, calc_version, value, metadata
FROM otc_metrics_daily
WHERE symbol = 'AAPL'
  AND calc_name = 'daily_volume'
  AND metric_date BETWEEN '2026-01-01' AND '2026-01-15'
ORDER BY symbol, metric_date, calc_version DESC;
```

---

## 6. Idempotency Rules & DB Constraints

### 6.1 Guiding Principles

| Principle | Description |
|-----------|-------------|
| **Rerunnable** | Any pipeline stage can be safely rerun without data corruption |
| **No Duplicates** | Constraints prevent duplicate records at every layer |
| **Upsert Semantics** | Updates replace existing data with same identity key |
| **Partial Failure Safety** | Failures leave data in consistent state |

### 6.2 Bronze Layer: `otc_trades_raw`

**Deduplication Strategy:** Unique on `(source, record_hash)`

```sql
CREATE TABLE otc_trades_raw (
    id BIGSERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    source VARCHAR(50) NOT NULL,
    record_hash VARCHAR(64) NOT NULL,
    raw_payload JSONB NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    connector_name VARCHAR(100),
    connector_version VARCHAR(20),
    
    -- Primary dedupe constraint
    CONSTRAINT uq_raw_source_hash UNIQUE (source, record_hash)
);

CREATE INDEX idx_raw_batch_id ON otc_trades_raw(batch_id);
CREATE INDEX idx_raw_captured_at ON otc_trades_raw(captured_at);
```

**Append-only rules:**
- Inserts use `ON CONFLICT (source, record_hash) DO NOTHING`
- No updates to raw records (immutable audit trail)
- Connector produces deterministic `record_hash` from payload

```python
# app/domains/otc/repositories/raw_trades.py

class RawTradesRepository:
    async def insert_batch(self, records: list[RawTradeRecord], batch_id: UUID) -> int:
        """
        Insert raw records, skipping duplicates.
        
        Returns:
            Number of records actually inserted (excludes duplicates)
        """
        query = """
            INSERT INTO otc_trades_raw 
                (batch_id, source, record_hash, raw_payload, captured_at,
                 connector_name, connector_version)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (source, record_hash) DO NOTHING
        """
        inserted = 0
        for record in records:
            result = await self._conn.execute(
                query,
                batch_id,
                record.source,
                record.record_hash,
                record.raw_payload,
                record.captured_at,
                record.connector_name,
                record.connector_version,
            )
            if result == "INSERT 0 1":
                inserted += 1
        return inserted
```

**Idempotency test:**
```python
# Rerunning capture with same data inserts zero new records
batch1 = connector.capture(params)
inserted1 = await raw_repo.insert_batch(batch1.records, batch1.batch_id)

batch2 = connector.capture(params)  # Same data, new batch_id
inserted2 = await raw_repo.insert_batch(batch2.records, batch2.batch_id)

assert inserted2 == 0  # All duplicates, nothing inserted
```

### 6.3 Silver Layer: `otc_trades`

**Deduplication Strategy:** Unique on `trade_id` (stable identity derived from source + record_hash)

```sql
CREATE TABLE otc_trades (
    id BIGSERIAL PRIMARY KEY,
    trade_id VARCHAR(100) NOT NULL,
    source VARCHAR(50) NOT NULL,
    record_hash VARCHAR(64) NOT NULL,
    schema_version VARCHAR(10) NOT NULL,
    
    symbol VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    trade_time TIMESTAMPTZ NOT NULL,
    direction VARCHAR(10) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    price NUMERIC(20,8) NOT NULL,
    notional NUMERIC(30,8) NOT NULL,
    venue VARCHAR(50) NOT NULL,
    
    normalized_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Primary identity constraint
    CONSTRAINT uq_trades_trade_id UNIQUE (trade_id)
);
```

**Upsert semantics:**
- `trade_id` is stable: derived from `source:record_hash[:16]`
- Re-normalization updates existing row (changes `schema_version`, `updated_at`)
- Different normalizer versions can update the same trade

```python
# app/domains/otc/repositories/trades.py

class TradesRepository:
    async def upsert_batch(self, trades: list[CanonicalTrade]) -> tuple[int, int]:
        """
        Upsert canonical trades.
        
        Returns:
            (inserted_count, updated_count)
        """
        query = """
            INSERT INTO otc_trades 
                (trade_id, source, record_hash, schema_version,
                 symbol, trade_date, trade_time, direction,
                 quantity, price, notional, venue, normalized_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            ON CONFLICT (trade_id) DO UPDATE SET
                schema_version = EXCLUDED.schema_version,
                symbol = EXCLUDED.symbol,
                trade_date = EXCLUDED.trade_date,
                trade_time = EXCLUDED.trade_time,
                direction = EXCLUDED.direction,
                quantity = EXCLUDED.quantity,
                price = EXCLUDED.price,
                notional = EXCLUDED.notional,
                venue = EXCLUDED.venue,
                normalized_at = EXCLUDED.normalized_at,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted
        """
        inserted = updated = 0
        for trade in trades:
            result = await self._conn.fetchrow(query, *trade_values(trade))
            if result["inserted"]:
                inserted += 1
            else:
                updated += 1
        return inserted, updated
```

**Idempotency test:**
```python
# Rerunning normalization updates in place
result1 = normalizer_v1.normalize_batch(raw_records)
await trades_repo.upsert_batch([r.trade for r in result1.results if r.trade])

result2 = normalizer_v2.normalize_batch(raw_records)  # Same records, v2
await trades_repo.upsert_batch([r.trade for r in result2.results if r.trade])

# trade_id unchanged, schema_version updated to v2
trade = await trades_repo.get_by_trade_id("ats_a:abc123def456")
assert trade.schema_version == "v2"
```

### 6.4 Gold Layer: `otc_metrics_daily`

**Deduplication Strategy:** Unique on `(symbol, metric_date, calc_name, calc_version)`

```sql
CREATE TABLE otc_metrics_daily (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    metric_date DATE NOT NULL,
    calc_name VARCHAR(100) NOT NULL,
    calc_version VARCHAR(20) NOT NULL,
    value NUMERIC(30,8) NOT NULL,
    metadata JSONB DEFAULT '{}',
    
    computed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Composite uniqueness: one value per (symbol, date, calc, version)
    CONSTRAINT uq_metrics_identity UNIQUE (symbol, metric_date, calc_name, calc_version)
);
```

**Upsert semantics:**
- Recalculation replaces existing metric with same identity
- Different versions coexist (both v1 and v2 can have rows for same symbol/date)
- `computed_at` tracks when calculation ran

```python
# app/domains/otc/repositories/metrics.py

class MetricsRepository:
    async def upsert_batch(self, rows: list[MetricRow]) -> tuple[int, int]:
        """
        Upsert metric rows.
        
        Returns:
            (inserted_count, updated_count)
        """
        query = """
            INSERT INTO otc_metrics_daily 
                (symbol, metric_date, calc_name, calc_version, value, metadata, computed_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (symbol, metric_date, calc_name, calc_version) DO UPDATE SET
                value = EXCLUDED.value,
                metadata = EXCLUDED.metadata,
                computed_at = EXCLUDED.computed_at,
                updated_at = NOW()
            RETURNING (xmax = 0) AS inserted
        """
        inserted = updated = 0
        for row in rows:
            result = await self._conn.fetchrow(
                query,
                row.symbol, row.metric_date, row.calc_name,
                row.calc_version, row.value, row.metadata, row.computed_at,
            )
            if result["inserted"]:
                inserted += 1
            else:
                updated += 1
        return inserted, updated
```

**Idempotency test:**
```python
# Rerunning calculation replaces existing metrics
result1 = daily_volume_v1.compute(trades, params)
await metrics_repo.upsert_batch(result1.rows)

result2 = daily_volume_v1.compute(trades, params)  # Same inputs
await metrics_repo.upsert_batch(result2.rows)

# Count unchanged (upsert in place)
count = await metrics_repo.count_by_calc("daily_volume", "v1")
assert count == len(result1.rows)
```

### 6.5 Partial Failure Handling

**Strategy:** Use transactions per batch with savepoints for recoverability.

```python
# app/domains/otc/pipelines/normalize.py

async def run_normalize_pipeline(
    execution_id: str,
    params: dict,
    *,
    conn_pool: AsyncConnectionPool,
) -> dict:
    """
    Normalize pipeline with transaction safety.
    
    On failure:
    - No partial writes to otc_trades
    - Raw records remain in otc_trades_raw
    - Execution marked failed, DLQ entry created
    """
    async with conn_pool.connection() as conn:
        async with conn.transaction():
            raw_repo = RawTradesRepository(conn)
            trades_repo = TradesRepository(conn)
            
            # Fetch and normalize
            raw_records = await raw_repo.get_batch(params["batch_id"])
            normalizer = resolve_normalizer(params.get("normalizer_version"))
            result = normalizer.normalize_batch(raw_records)
            
            # Write trades (all or nothing within transaction)
            accepted = [r.trade for r in result.results if r.trade]
            inserted, updated = await trades_repo.upsert_batch(accepted)
            
            return {
                "batch_id": params["batch_id"],
                "inserted": inserted,
                "updated": updated,
                "rejected": result.rejected_count,
            }
    # Transaction commits on exit, rolls back on exception
```

### 6.6 Constraint Summary Table

| Layer | Table | Uniqueness Constraint | On Duplicate |
|-------|-------|----------------------|--------------|
| Bronze | `otc_trades_raw` | `(source, record_hash)` | `DO NOTHING` |
| Silver | `otc_trades` | `(trade_id)` | `DO UPDATE` |
| Gold | `otc_metrics_daily` | `(symbol, metric_date, calc_name, calc_version)` | `DO UPDATE` |

---

## 7. Fixture Layout & Golden Tests

### 7.1 Fixture Directory Structure

```
app/domains/otc/fixtures/
├── __init__.py
├── loader.py                       # Fixture loading utilities
│
├── connectors/
│   ├── ats_a_sample.json           # Sample ATS_A API response
│   ├── ats_b_sample.json           # Sample ATS_B API response
│   └── file_import_sample.csv      # Sample CSV import
│
├── normalizers/
│   ├── raw_trades_v1.json          # Raw input for v1 normalizer
│   ├── raw_trades_v2.json          # Raw input for v2 normalizer
│   ├── expected_trades_v1.json     # Expected output from v1
│   ├── expected_trades_v2.json     # Expected output from v2
│   └── rejection_cases.json        # Records that should be rejected
│
├── calculations/
│   ├── trades_input.json           # Canonical trades for calc tests
│   ├── daily_volume_expected.json  # Expected daily_volume output
│   ├── vwap_expected.json          # Expected VWAP output
│   └── liquidity_score_expected.json
│
└── scenarios/
    ├── end_to_end_ingest.json      # Full ingest scenario
    └── backfill_renormalize.json   # Backfill scenario
```

### 7.2 Fixture Naming Conventions

| Pattern | Purpose | Example |
|---------|---------|---------|
| `{source}_sample.json` | Connector mock responses | `ats_a_sample.json` |
| `raw_{type}_v{N}.json` | Raw input for normalizer | `raw_trades_v1.json` |
| `expected_{type}_v{N}.json` | Expected normalizer output | `expected_trades_v1.json` |
| `{calc_name}_expected.json` | Expected calculation output | `daily_volume_expected.json` |
| `trades_input.json` | Canonical trades for calc tests | `trades_input.json` |

### 7.3 Fixture Format

**Raw records fixture (JSON):**

```json
{
  "description": "Sample raw trades for v1 normalizer testing",
  "source": "ats_a",
  "records": [
    {
      "raw_payload": {
        "symbol": "AAPL",
        "trade_date": "2026-01-02",
        "trade_time": "2026-01-02T10:30:00Z",
        "side": "buy",
        "qty": "100",
        "price": "185.50",
        "venue": "ATS_A"
      }
    },
    {
      "raw_payload": {
        "symbol": "MSFT",
        "trade_date": "2026-01-02",
        "trade_time": "2026-01-02T11:15:00Z",
        "side": "sell",
        "qty": "50",
        "price": "425.25",
        "venue": "ATS_A"
      }
    }
  ]
}
```

**Expected output fixture (JSON):**

```json
{
  "description": "Expected canonical trades from v1 normalizer",
  "normalizer_version": "v1",
  "trades": [
    {
      "symbol": "AAPL",
      "trade_date": "2026-01-02",
      "direction": "buy",
      "quantity": "100",
      "price": "185.50",
      "notional": "18550.00",
      "venue": "ATS_A"
    },
    {
      "symbol": "MSFT",
      "trade_date": "2026-01-02",
      "direction": "sell",
      "quantity": "50",
      "price": "425.25",
      "notional": "21262.50",
      "venue": "ATS_A"
    }
  ],
  "rejected": []
}
```

**Calculation expected output:**

```json
{
  "description": "Expected daily_volume v1 output",
  "calc_name": "daily_volume",
  "calc_version": "v1",
  "metrics": [
    {
      "symbol": "AAPL",
      "metric_date": "2026-01-02",
      "value": "18550.00",
      "metadata": {
        "total_quantity": "100",
        "total_notional": "18550.00",
        "trade_count": 1
      }
    },
    {
      "symbol": "MSFT",
      "metric_date": "2026-01-02",
      "value": "21262.50",
      "metadata": {
        "total_quantity": "50",
        "total_notional": "21262.50",
        "trade_count": 1
      }
    }
  ]
}
```

### 7.4 Fixture Loader

```python
# app/domains/otc/fixtures/loader.py

import json
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal
from typing import Any

from app.domains.otc.contracts import RawTradeRecord, CanonicalTrade, MetricRow


FIXTURES_DIR = Path(__file__).parent


def load_json(path: str) -> dict[str, Any]:
    """Load JSON fixture file."""
    with open(FIXTURES_DIR / path) as f:
        return json.load(f)


def load_raw_records(path: str) -> list[RawTradeRecord]:
    """Load raw trade records from fixture."""
    data = load_json(path)
    source = data["source"]
    captured_at = datetime.fromisoformat("2026-01-02T12:00:00+00:00")
    
    return [
        RawTradeRecord(
            source=source,
            raw_payload=r["raw_payload"],
            captured_at=captured_at,
        )
        for r in data["records"]
    ]


def load_expected_trades(path: str) -> list[dict]:
    """Load expected canonical trades from fixture."""
    data = load_json(path)
    return data["trades"]


def load_expected_metrics(path: str) -> list[dict]:
    """Load expected metrics from fixture."""
    data = load_json(path)
    return data["metrics"]


def assert_trades_match(actual: list[CanonicalTrade], expected: list[dict]) -> None:
    """Assert actual trades match expected fixture data."""
    assert len(actual) == len(expected), f"Count mismatch: {len(actual)} vs {len(expected)}"
    
    for a, e in zip(sorted(actual, key=lambda t: t.symbol), 
                    sorted(expected, key=lambda t: t["symbol"])):
        assert a.symbol == e["symbol"]
        assert str(a.trade_date) == e["trade_date"]
        assert a.direction.value == e["direction"]
        assert a.quantity == Decimal(e["quantity"])
        assert a.price == Decimal(e["price"])
        assert a.notional == Decimal(e["notional"])
        assert a.venue == e["venue"]


def assert_metrics_match(actual: list[MetricRow], expected: list[dict]) -> None:
    """Assert actual metrics match expected fixture data."""
    assert len(actual) == len(expected)
    
    for a, e in zip(sorted(actual, key=lambda m: (m.symbol, str(m.metric_date))),
                    sorted(expected, key=lambda m: (m["symbol"], m["metric_date"]))):
        assert a.symbol == e["symbol"]
        assert str(a.metric_date) == e["metric_date"]
        assert a.value == Decimal(e["value"])
        # Check metadata keys
        for key in e.get("metadata", {}):
            assert str(a.metadata.get(key)) == str(e["metadata"][key])
```

### 7.5 Test Types

#### Connector Tests (Deterministic)

Test that connectors produce consistent output given mocked external data.

```python
# app/domains/otc/tests/connectors/test_ats_a.py

import pytest
from unittest.mock import Mock
from uuid import uuid4

from app.domains.otc.connectors.ats_a import ATSAConnector, ATSAParams
from app.domains.otc.fixtures.loader import load_json


class TestATSAConnector:
    @pytest.fixture
    def mock_client(self):
        """Mock HTTP client with fixture data."""
        client = Mock()
        data = load_json("connectors/ats_a_sample.json")
        client.get.return_value = Mock(json=lambda: data["api_response"])
        return client
    
    @pytest.fixture
    def connector(self, mock_client):
        return ATSAConnector(client=mock_client)
    
    def test_capture_returns_batch(self, connector):
        params = ATSAParams(
            api_key="test-key",
            symbols=["AAPL"],
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
        )
        
        batch = connector.capture(params)
        
        assert batch.connector_name == "ats_a"
        assert batch.connector_version == "1.0.0"
        assert len(batch.records) > 0
    
    def test_record_hash_deterministic(self, connector):
        """Same payload produces same hash."""
        params = ATSAParams(api_key="test-key")
        
        batch1 = connector.capture(params)
        batch2 = connector.capture(params)
        
        # Same raw data → same hashes
        hashes1 = {r.record_hash for r in batch1.records}
        hashes2 = {r.record_hash for r in batch2.records}
        assert hashes1 == hashes2
```

#### Normalizer Golden Tests

Test that normalizers produce expected output from fixture input.

```python
# app/domains/otc/tests/normalizers/test_trades_v1.py

import pytest

from app.domains.otc.normalizers.trades_v1 import TradesNormalizerV1
from app.domains.otc.contracts import NormalizationStatus
from app.domains.otc.fixtures.loader import (
    load_raw_records,
    load_expected_trades,
    assert_trades_match,
)


class TestTradesNormalizerV1:
    @pytest.fixture
    def normalizer(self):
        return TradesNormalizerV1()
    
    def test_normalize_batch_golden(self, normalizer):
        """Golden test: raw input → expected canonical output."""
        raw_records = load_raw_records("normalizers/raw_trades_v1.json")
        expected = load_expected_trades("normalizers/expected_trades_v1.json")
        
        result = normalizer.normalize_batch(raw_records)
        
        accepted = [r.trade for r in result.results if r.trade]
        assert_trades_match(accepted, expected)
    
    def test_rejection_cases(self, normalizer):
        """Test that invalid records are properly rejected."""
        raw_records = load_raw_records("normalizers/rejection_cases.json")
        
        result = normalizer.normalize_batch(raw_records)
        
        # All should be rejected
        assert result.accepted_count == 0
        assert result.rejected_count == len(raw_records)
        
        # Each has a rejection reason
        for r in result.results:
            assert r.status == NormalizationStatus.REJECTED
            assert r.rejection_reason is not None
    
    def test_trade_id_stability(self, normalizer):
        """Same raw record always produces same trade_id."""
        raw_records = load_raw_records("normalizers/raw_trades_v1.json")
        
        result1 = normalizer.normalize_batch(raw_records)
        result2 = normalizer.normalize_batch(raw_records)
        
        ids1 = {r.trade.trade_id for r in result1.results if r.trade}
        ids2 = {r.trade.trade_id for r in result2.results if r.trade}
        assert ids1 == ids2
```

#### Calculation Golden Tests

Test that calculations produce expected metrics from canonical input.

```python
# app/domains/otc/tests/calculations/test_daily_volume.py

import pytest
from datetime import date

from app.domains.otc.calculations.daily_volume_v1 import DailyVolumeV1, DailyVolumeParams
from app.domains.otc.fixtures.loader import (
    load_json,
    load_expected_metrics,
    assert_metrics_match,
)
from app.domains.otc.contracts import CanonicalTrade


def load_trades_input() -> list[CanonicalTrade]:
    """Load canonical trades from fixture."""
    data = load_json("calculations/trades_input.json")
    return [CanonicalTrade(**t) for t in data["trades"]]


class TestDailyVolumeV1:
    @pytest.fixture
    def calc(self):
        return DailyVolumeV1()
    
    @pytest.fixture
    def trades(self):
        return load_trades_input()
    
    def test_compute_golden(self, calc, trades):
        """Golden test: canonical trades → expected metrics."""
        expected = load_expected_metrics("calculations/daily_volume_expected.json")
        
        params = DailyVolumeParams(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 15),
        )
        result = calc.compute(trades, params)
        
        assert_metrics_match(result.rows, expected)
    
    def test_deterministic(self, calc, trades):
        """Same inputs produce identical outputs."""
        params = DailyVolumeParams(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 15),
        )
        
        result1 = calc.compute(trades, params)
        result2 = calc.compute(trades, params)
        
        # Values match exactly
        for r1, r2 in zip(result1.rows, result2.rows):
            assert r1.symbol == r2.symbol
            assert r1.metric_date == r2.metric_date
            assert r1.value == r2.value
    
    def test_empty_input(self, calc):
        """Handles empty trade list gracefully."""
        params = DailyVolumeParams(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 15),
        )
        
        result = calc.compute([], params)
        
        assert result.rows == []
        assert result.input_trade_count == 0
```

#### Contract Tests (Interface Invariants)

Test that all registered plugins satisfy interface contracts.

```python
# app/domains/otc/tests/test_contracts.py

import pytest
from datetime import date

from app.domains.otc.registry import connectors, normalizers, calculations
from app.domains.otc.contracts import (
    ConnectorProtocol,
    NormalizerProtocol,
    CalculationProtocol,
    RawTradeRecord,
    CanonicalTrade,
)


class TestConnectorContracts:
    @pytest.mark.parametrize("name", ["ats_a", "ats_b", "file_import"])
    def test_has_required_attributes(self, name):
        """All connectors have required attributes."""
        connector = connectors.resolve(name)
        
        assert hasattr(connector, "name")
        assert hasattr(connector, "version")
        assert hasattr(connector, "source")
        assert hasattr(connector, "capture")
        assert callable(connector.capture)


class TestNormalizerContracts:
    @pytest.mark.parametrize("version", ["v1", "v2"])
    def test_has_required_attributes(self, version):
        """All normalizers have required attributes."""
        normalizer = normalizers.resolve("trades", version)
        
        assert hasattr(normalizer, "name")
        assert hasattr(normalizer, "version")
        assert hasattr(normalizer, "input_schema_version")
        assert hasattr(normalizer, "normalize")
        assert hasattr(normalizer, "normalize_batch")


class TestCalculationContracts:
    @pytest.mark.parametrize("name", ["daily_volume", "vwap", "liquidity_score"])
    def test_has_required_attributes(self, name):
        """All calculations have required attributes."""
        calc = calculations.resolve(name)
        
        assert hasattr(calc, "name")
        assert hasattr(calc, "version")
        assert hasattr(calc, "output_columns")
        assert hasattr(calc, "compute")
        assert callable(calc.compute)
```

### 7.6 Handling Time and Randomness

**Rule:** Fixtures and tests must be deterministic. Use these patterns:

```python
# Freeze time in tests
from freezegun import freeze_time

@freeze_time("2026-01-02T12:00:00Z")
def test_normalized_at_timestamp(normalizer):
    raw = load_raw_records("normalizers/raw_trades_v1.json")
    result = normalizer.normalize_batch(raw)
    
    for r in result.results:
        if r.trade:
            assert r.trade.normalized_at.isoformat() == "2026-01-02T12:00:00+00:00"


# Inject time function for production code
class TradesNormalizerV1:
    def __init__(self, now_fn=None):
        self._now = now_fn or utc_now
    
    def normalize(self, record):
        trade = CanonicalTrade(
            ...,
            normalized_at=self._now(),  # Injected
        )


# In tests:
def test_with_fixed_time():
    fixed_time = datetime(2026, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    normalizer = TradesNormalizerV1(now_fn=lambda: fixed_time)
    ...
```

### 7.7 Golden Test Flow Example

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     GOLDEN TEST FLOW: NORMALIZER                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   1. Load fixture                                                        │
│      └── raw_records = load_raw_records("normalizers/raw_trades_v1.json")│
│                                                                          │
│   2. Run normalizer                                                      │
│      └── result = normalizer.normalize_batch(raw_records)                │
│                                                                          │
│   3. Load expected output                                                │
│      └── expected = load_expected_trades("normalizers/expected_v1.json") │
│                                                                          │
│   4. Assert match                                                        │
│      └── assert_trades_match(result.accepted, expected)                  │
│                                                                          │
│   ✓ If expected output changes (schema evolution):                       │
│     - Update expected fixture                                            │
│     - PR review catches unintended changes                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Example Extension: liquidity_score_v1

This section provides a complete, implementation-ready example of adding a new calculation plugin.

### 8.1 Calculation Contract

**Name:** `liquidity_score`  
**Version:** `v1`

**Inputs:**
- Canonical trades for a symbol/date range
- Parameters: `symbols`, `start_date`, `end_date`

**Output Columns:**
| Column | Type | Description |
|--------|------|-------------|
| `liquidity_score` | Decimal | Primary score (0-100) |
| `trade_count` | int | Number of trades in period |
| `avg_trade_size` | Decimal | Average notional per trade |
| `spread_proxy` | Decimal | Proxy for bid-ask spread |

**Formula (simplified but plausible):**

```
liquidity_score = normalize(
    w1 * log(trade_count + 1) +
    w2 * log(total_notional + 1) +
    w3 * (1 / (spread_proxy + 0.001))
)

where:
  w1 = 0.4 (trade frequency weight)
  w2 = 0.4 (volume weight)  
  w3 = 0.2 (spread tightness weight)
  
  spread_proxy = stddev(price) / mean(price)
  
  normalize() scales result to 0-100 range
```

### 8.2 Implementation

```python
# app/domains/otc/calculations/liquidity_score_v1.py

"""
Liquidity Score v1 Calculation

Computes a daily liquidity score (0-100) for each symbol based on:
- Trade frequency
- Total notional volume
- Price stability (inverse spread proxy)

Higher scores indicate more liquid instruments.
"""

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from statistics import mean, stdev
import math

from app.domains.otc.contracts import (
    CalculationProtocol,
    CalculationParams,
    CalculationResult,
    MetricRow,
    CanonicalTrade,
)
from app.core.time import utc_now


# =============================================================================
# PARAMETERS
# =============================================================================

class LiquidityScoreParams(CalculationParams):
    """Parameters for liquidity score calculation."""
    
    # Weight configuration (can be overridden)
    weight_frequency: Decimal = Decimal("0.4")
    weight_volume: Decimal = Decimal("0.4")
    weight_spread: Decimal = Decimal("0.2")


# =============================================================================
# CALCULATION
# =============================================================================

class LiquidityScoreV1:
    """
    V1 Liquidity Score calculation.
    
    Produces a normalized score (0-100) indicating instrument liquidity.
    """
    
    name: str = "liquidity_score"
    version: str = "v1"
    output_columns: list[str] = [
        "liquidity_score",
        "trade_count", 
        "avg_trade_size",
        "spread_proxy",
    ]
    
    # Normalization bounds (derived from historical analysis)
    MAX_LOG_COUNT = Decimal("7")      # ~1100 trades
    MAX_LOG_NOTIONAL = Decimal("18")  # ~$65M
    MAX_SPREAD_FACTOR = Decimal("100")
    
    def compute(
        self,
        trades: list[CanonicalTrade],
        params: LiquidityScoreParams,
    ) -> CalculationResult:
        """Compute liquidity scores by symbol and date."""
        computed_at = utc_now()
        
        if not trades:
            return CalculationResult(
                calc_name=self.name,
                calc_version=self.version,
                computed_at=computed_at,
                rows=[],
                input_trade_count=0,
            )
        
        # Group trades by (symbol, date)
        grouped: dict[tuple[str, date], list[CanonicalTrade]] = defaultdict(list)
        for trade in trades:
            key = (trade.symbol, trade.trade_date)
            grouped[key].append(trade)
        
        rows = []
        for (symbol, metric_date), day_trades in sorted(grouped.items()):
            score_data = self._compute_score(day_trades, params)
            
            rows.append(MetricRow(
                symbol=symbol,
                metric_date=metric_date,
                calc_name=self.name,
                calc_version=self.version,
                value=score_data["liquidity_score"],
                metadata={
                    "trade_count": score_data["trade_count"],
                    "total_notional": str(score_data["total_notional"]),
                    "avg_trade_size": str(score_data["avg_trade_size"]),
                    "spread_proxy": str(score_data["spread_proxy"]),
                    "weights": {
                        "frequency": str(params.weight_frequency),
                        "volume": str(params.weight_volume),
                        "spread": str(params.weight_spread),
                    },
                },
                computed_at=computed_at,
            ))
        
        return CalculationResult(
            calc_name=self.name,
            calc_version=self.version,
            computed_at=computed_at,
            rows=rows,
            input_trade_count=len(trades),
        )
    
    def _compute_score(
        self,
        trades: list[CanonicalTrade],
        params: LiquidityScoreParams,
    ) -> dict:
        """Compute score components for a single symbol-day."""
        trade_count = len(trades)
        prices = [float(t.price) for t in trades]
        notionals = [t.notional for t in trades]
        
        total_notional = sum(notionals, Decimal(0))
        avg_trade_size = total_notional / trade_count if trade_count else Decimal(0)
        
        # Spread proxy: coefficient of variation of prices
        if len(prices) >= 2:
            spread_proxy = Decimal(str(stdev(prices) / mean(prices))) if mean(prices) > 0 else Decimal(0)
        else:
            spread_proxy = Decimal("0.01")  # Default for single trade
        
        # Component scores (normalized 0-1)
        freq_score = self._log_normalize(
            Decimal(trade_count), 
            self.MAX_LOG_COUNT
        )
        vol_score = self._log_normalize(
            total_notional, 
            self.MAX_LOG_NOTIONAL
        )
        
        # Spread: lower is better, so invert
        spread_factor = Decimal(1) / (spread_proxy + Decimal("0.001"))
        spread_score = min(spread_factor / self.MAX_SPREAD_FACTOR, Decimal(1))
        
        # Weighted combination
        raw_score = (
            params.weight_frequency * freq_score +
            params.weight_volume * vol_score +
            params.weight_spread * spread_score
        )
        
        # Scale to 0-100
        liquidity_score = min(raw_score * Decimal(100), Decimal(100)).quantize(Decimal("0.01"))
        
        return {
            "liquidity_score": liquidity_score,
            "trade_count": trade_count,
            "total_notional": total_notional,
            "avg_trade_size": avg_trade_size.quantize(Decimal("0.01")),
            "spread_proxy": spread_proxy.quantize(Decimal("0.0001")),
        }
    
    def _log_normalize(self, value: Decimal, max_log: Decimal) -> Decimal:
        """Normalize using log scale, capped at 1.0."""
        if value <= 0:
            return Decimal(0)
        log_val = Decimal(str(math.log(float(value) + 1)))
        return min(log_val / max_log, Decimal(1))
```

### 8.3 Registration

```python
# app/domains/otc/calculations/__init__.py

from app.domains.otc.registry import calculations
from app.domains.otc.calculations.daily_volume_v1 import DailyVolumeV1
from app.domains.otc.calculations.vwap_v1 import VWAPV1
from app.domains.otc.calculations.liquidity_score_v1 import LiquidityScoreV1


# Register calculations
calculations.register("daily_volume", "v1", DailyVolumeV1, is_default=True)
calculations.register("vwap", "v1", VWAPV1, is_default=True)
calculations.register("liquidity_score", "v1", LiquidityScoreV1, is_default=True)
```

### 8.4 Fixture: Expected Output

```json
// app/domains/otc/fixtures/calculations/liquidity_score_expected.json
{
  "description": "Expected liquidity_score v1 output",
  "calc_name": "liquidity_score",
  "calc_version": "v1",
  "input_description": "10 AAPL trades, 5 MSFT trades on 2026-01-02",
  "metrics": [
    {
      "symbol": "AAPL",
      "metric_date": "2026-01-02",
      "value": "62.45",
      "metadata": {
        "trade_count": 10,
        "avg_trade_size": "18550.00",
        "spread_proxy": "0.0023"
      }
    },
    {
      "symbol": "MSFT",
      "metric_date": "2026-01-02", 
      "value": "48.32",
      "metadata": {
        "trade_count": 5,
        "avg_trade_size": "21262.50",
        "spread_proxy": "0.0045"
      }
    }
  ]
}
```

### 8.5 Tests

```python
# app/domains/otc/tests/calculations/test_liquidity_score.py

import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

from app.domains.otc.calculations.liquidity_score_v1 import (
    LiquidityScoreV1,
    LiquidityScoreParams,
)
from app.domains.otc.contracts import CanonicalTrade, TradeDirection
from app.domains.otc.fixtures.loader import (
    load_json,
    load_expected_metrics,
    assert_metrics_match,
)


def make_trade(
    symbol: str,
    trade_date: date,
    price: Decimal,
    quantity: Decimal,
) -> CanonicalTrade:
    """Helper to create test trades."""
    return CanonicalTrade(
        trade_id=f"test:{symbol}:{trade_date}:{price}",
        source="test",
        record_hash="testhash",
        schema_version="v1",
        symbol=symbol,
        trade_date=trade_date,
        trade_time=datetime(trade_date.year, trade_date.month, trade_date.day, 12, 0, tzinfo=timezone.utc),
        direction=TradeDirection.BUY,
        quantity=quantity,
        price=price,
        notional=quantity * price,
        venue="TEST",
        normalized_at=datetime.now(timezone.utc),
    )


class TestLiquidityScoreV1:
    @pytest.fixture
    def calc(self):
        return LiquidityScoreV1()
    
    @pytest.fixture
    def params(self):
        return LiquidityScoreParams(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 15),
        )
    
    def test_compute_basic(self, calc, params):
        """Basic computation produces valid scores."""
        trades = [
            make_trade("AAPL", date(2026, 1, 2), Decimal("185.50"), Decimal("100")),
            make_trade("AAPL", date(2026, 1, 2), Decimal("186.00"), Decimal("150")),
            make_trade("AAPL", date(2026, 1, 2), Decimal("185.75"), Decimal("200")),
        ]
        
        result = calc.compute(trades, params)
        
        assert len(result.rows) == 1
        row = result.rows[0]
        assert row.symbol == "AAPL"
        assert row.metric_date == date(2026, 1, 2)
        assert Decimal(0) <= row.value <= Decimal(100)
        assert row.metadata["trade_count"] == 3
    
    def test_golden_output(self, calc, params):
        """Golden test: matches expected fixture output."""
        # Load canonical trades input
        data = load_json("calculations/trades_input.json")
        trades = [CanonicalTrade(**t) for t in data["trades"]]
        
        # Load expected output
        expected = load_expected_metrics("calculations/liquidity_score_expected.json")
        
        result = calc.compute(trades, params)
        assert_metrics_match(result.rows, expected)
    
    def test_deterministic(self, calc, params):
        """Same inputs produce identical scores."""
        trades = [
            make_trade("AAPL", date(2026, 1, 2), Decimal("185.50"), Decimal("100")),
            make_trade("AAPL", date(2026, 1, 2), Decimal("186.00"), Decimal("150")),
        ]
        
        result1 = calc.compute(trades, params)
        result2 = calc.compute(trades, params)
        
        assert result1.rows[0].value == result2.rows[0].value
    
    def test_empty_trades(self, calc, params):
        """Empty input returns empty result."""
        result = calc.compute([], params)
        
        assert result.rows == []
        assert result.input_trade_count == 0
    
    def test_single_trade(self, calc, params):
        """Single trade produces valid score (uses default spread)."""
        trades = [
            make_trade("AAPL", date(2026, 1, 2), Decimal("185.50"), Decimal("100")),
        ]
        
        result = calc.compute(trades, params)
        
        assert len(result.rows) == 1
        assert result.rows[0].value > Decimal(0)
        assert result.rows[0].metadata["trade_count"] == 1
    
    def test_score_increases_with_activity(self, calc, params):
        """More trades and volume should increase score."""
        low_activity = [
            make_trade("AAPL", date(2026, 1, 2), Decimal("185"), Decimal("10")),
        ]
        high_activity = [
            make_trade("AAPL", date(2026, 1, 2), Decimal("185"), Decimal("1000")),
            make_trade("AAPL", date(2026, 1, 2), Decimal("185.10"), Decimal("1000")),
            make_trade("AAPL", date(2026, 1, 2), Decimal("185.05"), Decimal("1000")),
        ]
        
        low_result = calc.compute(low_activity, params)
        high_result = calc.compute(high_activity, params)
        
        assert high_result.rows[0].value > low_result.rows[0].value
    
    def test_custom_weights(self, calc):
        """Custom weight parameters are applied."""
        trades = [
            make_trade("AAPL", date(2026, 1, 2), Decimal("185.50"), Decimal("100")),
            make_trade("AAPL", date(2026, 1, 2), Decimal("186.00"), Decimal("150")),
        ]
        
        default_params = LiquidityScoreParams(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 15),
        )
        custom_params = LiquidityScoreParams(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 15),
            weight_frequency=Decimal("0.8"),
            weight_volume=Decimal("0.1"),
            weight_spread=Decimal("0.1"),
        )
        
        default_result = calc.compute(trades, default_params)
        custom_result = calc.compute(trades, custom_params)
        
        # Scores differ due to weight change
        assert default_result.rows[0].value != custom_result.rows[0].value
        # Weights recorded in metadata
        assert custom_result.rows[0].metadata["weights"]["frequency"] == "0.8"
```

### 8.6 Pipeline Invocation

```python
# Invoke via dispatcher
await dispatcher.submit(
    pipeline="otc_compute",
    params={
        "calc": "liquidity_score",
        "version": "v1",
        "symbols": ["AAPL", "MSFT", "GOOGL"],
        "start_date": "2026-01-01",
        "end_date": "2026-01-15",
    },
    logical_key="otc_compute:liquidity_score:2026-01-01:2026-01-15",
)
```

**Pipeline implementation:**

```python
# app/domains/otc/pipelines/compute.py

from app.domains.otc.registry import resolve_calc
from app.domains.otc.repositories.trades import TradesRepository
from app.domains.otc.repositories.metrics import MetricsRepository


async def run_compute_pipeline(
    execution_id: str,
    params: dict,
    *,
    trades_repo: TradesRepository,
    metrics_repo: MetricsRepository,
) -> dict:
    """
    OTC compute pipeline.
    
    Resolves calculation from registry, computes metrics, persists results.
    """
    calc_name = params["calc"]
    version = params.get("version")  # None = use default
    
    # Resolve calculation (fail-fast if not found)
    calc = resolve_calc(calc_name, version)
    
    # Build params model
    param_class = get_param_class(calc_name)  # Registry lookup
    calc_params = param_class(
        symbols=params.get("symbols"),
        start_date=params["start_date"],
        end_date=params["end_date"],
        **params.get("calc_options", {}),
    )
    
    # Fetch canonical trades
    trades = await trades_repo.get_by_date_range(
        symbols=calc_params.symbols,
        start_date=calc_params.start_date,
        end_date=calc_params.end_date,
    )
    
    # Compute
    result = calc.compute(trades, calc_params)
    
    # Persist (upsert handles idempotency)
    inserted, updated = await metrics_repo.upsert_batch(result.rows)
    
    return {
        "calc": f"{calc.name}:{calc.version}",
        "input_trades": result.input_trade_count,
        "output_rows": len(result.rows),
        "inserted": inserted,
        "updated": updated,
    }
```

### 8.7 API Endpoint (Optional)

```python
# app/api/routes/otc_metrics.py

@router.get("/liquidity-score")
async def get_liquidity_score(
    symbol: str,
    start_date: date,
    end_date: date,
    version: str | None = Query(None),
):
    """Get liquidity scores for a symbol."""
    return await metrics_repo.get_by_calc(
        symbol=symbol,
        calc_name="liquidity_score",
        calc_version=version,  # None = latest
        start_date=start_date,
        end_date=end_date,
    )
```

---

## 9. Guardrails & Organization Rules

### 9.1 "Never Do This" Rules

These rules are **non-negotiable** and must be enforced via code review and CI checks.

| ❌ NEVER | ✅ INSTEAD |
|----------|-----------|
| Connector writing to `otc_trades` (Silver) | Connector returns `CaptureBatch`, pipeline writes to Bronze |
| Calculation calling a connector | Calculation receives pre-fetched `list[CanonicalTrade]` |
| Normalizer fetching from network/API | Normalizer receives `RawTradeRecord`, transforms in-memory |
| Plugin importing `celery`, `prefect`, `dagster` | Only `orchestration/backends/` may import frameworks |
| Pipeline using `datetime.now()` in business logic | Use `core.time.utc_now()` and pass as parameter |
| Plugin writing directly to DB | Return result objects, let pipeline/repository handle persistence |
| Calculation depending on wall-clock time | Accept `computed_at` as parameter or from `utc_now()` at start |
| Mixing Silver and Gold writes in same transaction | Separate pipeline stages with distinct transactions |

### 9.2 Layer Boundary Rules

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         DEPENDENCY DIRECTION                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   contracts.py  ◄───────  ALL plugins depend on contracts               │
│        │                                                                 │
│        ▼                                                                 │
│   connectors/   ──────►  May NOT import normalizers/ or calculations/   │
│                                                                          │
│   normalizers/  ──────►  May NOT import connectors/ or calculations/    │
│                                                                          │
│   calculations/ ──────►  May NOT import connectors/ or normalizers/     │
│                                                                          │
│   pipelines/    ──────►  MAY import from all of the above               │
│                          MAY import from repositories/                   │
│                          May NOT import from orchestration/backends/     │
│                                                                          │
│   repositories/ ──────►  MAY import from contracts.py only              │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Import Restrictions (Enforced)

```python
# Forbidden imports by module path

FORBIDDEN_IMPORTS = {
    # Connectors cannot import
    "domains/otc/connectors/*": [
        "celery",
        "prefect", 
        "dagster",
        "domains/otc/normalizers",
        "domains/otc/calculations",
        "domains/otc/repositories",  # No direct DB access
    ],
    
    # Normalizers cannot import
    "domains/otc/normalizers/*": [
        "celery",
        "prefect",
        "dagster",
        "httpx",
        "requests",
        "aiohttp",  # No network calls
        "domains/otc/connectors",
        "domains/otc/calculations",
    ],
    
    # Calculations cannot import
    "domains/otc/calculations/*": [
        "celery",
        "prefect",
        "dagster",
        "httpx",
        "requests",
        "aiohttp",
        "domains/otc/connectors",
        "domains/otc/normalizers",
    ],
    
    # Pipelines cannot import orchestration backends directly
    "domains/otc/pipelines/*": [
        "celery",
        "prefect",
        "dagster",
    ],
}
```

### 9.4 CI Enforcement

#### Ruff Rule Configuration

```toml
# pyproject.toml

[tool.ruff]
select = ["E", "F", "I", "B", "C4", "UP"]

[tool.ruff.per-file-ignores]
# Additional custom checks via pre-commit

[tool.ruff.isort]
known-first-party = ["app"]
force-single-line = true
```

#### Custom Import Checker

```python
# scripts/check_imports.py
"""
CI script to enforce plugin layer boundaries.

Run: python scripts/check_imports.py app/domains/otc/

Exit code 0 = pass, 1 = violations found
"""

import ast
import sys
from pathlib import Path

FORBIDDEN = {
    "connectors": ["celery", "prefect", "dagster", "normalizers", "calculations"],
    "normalizers": ["celery", "prefect", "dagster", "httpx", "requests", "connectors", "calculations"],
    "calculations": ["celery", "prefect", "dagster", "httpx", "requests", "connectors", "normalizers"],
    "pipelines": ["celery", "prefect", "dagster"],
}


def check_file(path: Path) -> list[str]:
    """Check a single file for forbidden imports."""
    violations = []
    
    # Determine which forbidden set applies
    layer = None
    for layer_name in FORBIDDEN:
        if f"/{layer_name}/" in str(path):
            layer = layer_name
            break
    
    if not layer:
        return []
    
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in FORBIDDEN[layer]:
                    if forbidden in alias.name:
                        violations.append(
                            f"{path}:{node.lineno}: {layer} imports forbidden '{alias.name}'"
                        )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for forbidden in FORBIDDEN[layer]:
                    if forbidden in node.module:
                        violations.append(
                            f"{path}:{node.lineno}: {layer} imports forbidden '{node.module}'"
                        )
    
    return violations


def main(root: str) -> int:
    root_path = Path(root)
    all_violations = []
    
    for py_file in root_path.rglob("*.py"):
        violations = check_file(py_file)
        all_violations.extend(violations)
    
    if all_violations:
        print("❌ Import violations found:\n")
        for v in all_violations:
            print(f"  {v}")
        return 1
    
    print("✅ All import checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "app/domains/otc"))
```

#### Pre-commit Hook

```yaml
# .pre-commit-config.yaml

repos:
  - repo: local
    hooks:
      - id: check-otc-imports
        name: Check OTC Plugin Imports
        entry: python scripts/check_imports.py app/domains/otc/
        language: python
        pass_filenames: false
        always_run: true
        
      - id: check-no-utcnow
        name: Check No datetime.utcnow()
        entry: grep -r "datetime.utcnow\(\)" --include="*.py" app/
        language: system
        pass_filenames: false
        always_run: true
        # This hook FAILS if utcnow() is found (exit 0 from grep)
```

### 9.5 Testing Requirements

| Plugin Type | Required Tests | Coverage Target |
|-------------|----------------|-----------------|
| Connector | Mock client test, hash determinism test | 90% |
| Normalizer | Golden test, rejection test, trade_id stability | 95% |
| Calculation | Golden test, determinism test, empty input test | 95% |
| Pipeline | Integration test with test DB | 80% |

### 9.6 Documentation Requirements

Every new plugin must include:

1. **Module docstring** explaining purpose and constraints
2. **Contract compliance** section in docstring
3. **Version notes** explaining changes from previous versions
4. **Example usage** in docstring or separate doc

```python
# Example: Required docstring structure

"""
Daily Volume V1 Calculation

Computes daily trading volume aggregates per symbol.

Contract Compliance:
- ✅ Deterministic: Same inputs always produce same outputs
- ✅ No side effects: Does not modify input trades
- ✅ No network calls: All data passed as parameters
- ✅ Version-tracked: Output includes calc_name and calc_version

Version Notes:
- v1 (2026-01-02): Initial implementation
  - Aggregates by symbol and date
  - Outputs total_quantity, total_notional, trade_count

Example:
    calc = DailyVolumeV1()
    result = calc.compute(trades, DailyVolumeParams(...))
"""
```

### 9.7 Review Checklist

When reviewing PRs that add or modify OTC plugins:

```markdown
## Plugin Review Checklist

### General
- [ ] Module docstring present with contract compliance section
- [ ] No forbidden imports (run `python scripts/check_imports.py`)
- [ ] Uses `core.time.utc_now()` instead of `datetime.utcnow()`
- [ ] Returns result objects (does not write to DB directly)

### Connector
- [ ] Implements `ConnectorProtocol`
- [ ] `capture()` returns `CaptureBatch`
- [ ] `record_hash` is deterministic
- [ ] No writes to Bronze/Silver tables
- [ ] Registered in `connectors/__init__.py`

### Normalizer
- [ ] Implements `NormalizerProtocol`
- [ ] `normalize()` returns `NormalizationResult`
- [ ] `trade_id` generation is stable/deterministic
- [ ] Proper rejection vs exception handling
- [ ] No network calls
- [ ] Registered in `normalizers/__init__.py`

### Calculation
- [ ] Implements `CalculationProtocol`
- [ ] `compute()` is deterministic
- [ ] Handles empty input gracefully
- [ ] Output includes `calc_name` and `calc_version`
- [ ] No calls to connectors or normalizers
- [ ] Registered in `calculations/__init__.py`

### Tests
- [ ] Golden test with fixture
- [ ] Determinism test (run twice, compare)
- [ ] Edge case tests (empty input, single record)
- [ ] Contract compliance test
```

---

## Appendix A: Quick Reference

### A.1 File Locations

| Artifact | Path |
|----------|------|
| Contracts & Models | `app/domains/otc/contracts.py` |
| Plugin Registry | `app/domains/otc/registry.py` |
| Exceptions | `app/domains/otc/exceptions.py` |
| Connectors | `app/domains/otc/connectors/{name}.py` |
| Normalizers | `app/domains/otc/normalizers/trades_v{N}.py` |
| Calculations | `app/domains/otc/calculations/{name}_v{N}.py` |
| Pipelines | `app/domains/otc/pipelines/{stage}.py` |
| Repositories | `app/domains/otc/repositories/{layer}.py` |
| Fixtures | `app/domains/otc/fixtures/{type}/` |
| Tests | `app/domains/otc/tests/{type}/` |

### A.2 Resolution Functions

```python
from app.domains.otc.registry import (
    resolve_connector,   # resolve_connector("ats_a") -> ATSAConnector
    resolve_normalizer,  # resolve_normalizer("v2") -> TradesNormalizerV2
    resolve_calc,        # resolve_calc("daily_volume", "v1") -> DailyVolumeV1
)
```

### A.3 Common Patterns

```python
# Pattern: Connector capture
batch = connector.capture(params)
await raw_repo.insert_batch(batch.records, batch.batch_id)

# Pattern: Normalize batch
result = normalizer.normalize_batch(raw_records)
accepted = [r.trade for r in result.results if r.trade]
await trades_repo.upsert_batch(accepted)

# Pattern: Compute metrics
result = calc.compute(trades, params)
await metrics_repo.upsert_batch(result.rows)
```

---

*End of Document*

