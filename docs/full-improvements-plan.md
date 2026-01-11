# Market Spine Full - Improvement Plan

This document outlines planned improvements to the market-spine-full codebase, ensuring all changes align with the existing architecture and patterns.

## Current Architecture Summary

```
src/market_spine/
├── api/                    # FastAPI application layer
│   ├── main.py            # App factory with lifespan
│   ├── routes/            # Route modules (health, executions, otc, dlq)
│   └── middleware/        # Request middleware (NEW)
├── backends/               # Execution backends (Celery, Local, Stubs)
├── core/                   # Core utilities and models
│   ├── settings.py        # Pydantic settings
│   ├── database.py        # Connection pool management
│   ├── models.py          # Domain dataclasses
│   └── time.py            # Time utilities (NEW)
├── execution/              # Execution system
│   ├── ledger.py          # Execution tracking
│   ├── dispatcher.py      # Single entrypoint
│   ├── dlq.py             # Dead letter queue
│   └── concurrency.py     # Lock management
├── observability/          # Logging, metrics, tracing
├── pipelines/              # Pipeline definitions and runner
├── repositories/           # Database access layer
└── services/               # Business logic (connectors, normalizer, etc.)
```

## Planned Improvements

### 1. Time Utilities Module (CREATED)

**File:** `src/market_spine/core/time.py`

**Purpose:** Replace deprecated `datetime.utcnow()` calls with timezone-aware utilities.

**Contents:**
- `utc_now()` - Returns timezone-aware UTC datetime
- `utc_now_naive()` - Returns naive UTC datetime for DB compatibility
- `ago(days, hours, minutes, seconds)` - Calculate past datetime
- `from_now(days, hours, minutes, seconds)` - Calculate future datetime
- `parse_iso()`, `format_iso()` - ISO datetime handling

**Pattern Alignment:**
- Follows existing `core/` module pattern (settings, database, models)
- Pure functions, no side effects
- Will be exported via `core/__init__.py`

---

### 2. Rate Limiting Middleware (CREATED)

**File:** `src/market_spine/api/middleware/rate_limit.py`

**Purpose:** Protect API endpoints from abuse using token bucket algorithm.

**Contents:**
- `RateLimiter` class - Token bucket implementation
- `RateLimitMiddleware` - FastAPI middleware wrapper
- Configurable: `max_tokens`, `refill_rate`, `exclude_paths`
- Returns standard rate limit headers (X-RateLimit-*)

**Pattern Alignment:**
- Located in `api/middleware/` following FastAPI conventions
- Uses `observability.logging.get_logger` for logging
- Excludes `/health` and `/metrics` paths by default
- Returns JSON responses consistent with other error handlers

---

### 3. Request Context Middleware (CREATED)

**File:** `src/market_spine/api/middleware/request_context.py`

**Purpose:** Establish request correlation IDs for distributed tracing.

**Contents:**
- `request_id_var` - ContextVar for request-scoped ID
- `get_request_id()` - Access current request ID from anywhere
- `RequestContextMiddleware` - Extracts/generates correlation IDs

**Pattern Alignment:**
- Integrates with existing `observability/` structured logging
- Uses X-Request-ID/X-Correlation-ID headers (industry standard)
- Adds request_id to all log entries for correlation

---

### 4. Circuit Breaker Pattern (PLANNED)

**File:** `src/market_spine/services/circuit_breaker.py`

**Purpose:** Prevent cascade failures when external services are down.

**Contents:**
- `CircuitBreaker` class with states: CLOSED, OPEN, HALF_OPEN
- Configurable failure threshold, recovery timeout
- Decorator `@circuit_breaker` for wrapping service calls
- Metrics integration for monitoring circuit state

**Pattern Alignment:**
- Located in `services/` alongside connectors it protects
- Uses `observability/metrics` for Prometheus counters
- Follows tenacity-style retry patterns already in use

---

### 5. Redis Health Check (PLANNED)

**File:** Update `src/market_spine/api/routes/health.py`

**Purpose:** Add Redis connectivity to readiness checks.

**Changes:**
- Add `_check_redis()` helper function
- Include Redis status in `/health/ready` response
- Report DEGRADED if Redis is down but DB is up

**Pattern Alignment:**
- Extends existing health check pattern
- Consistent response structure with database checks

---

### 6. Pipeline Timeout Enforcement (PLANNED)

**File:** Update `src/market_spine/pipelines/runner.py`

**Purpose:** Kill pipelines that exceed configured timeout.

**Changes:**
- Add `timeout_seconds` to pipeline definitions
- Wrap handler execution with signal-based timeout
- Record timeout as failure reason in execution ledger

**Pattern Alignment:**
- Uses existing `execution/ledger.py` for status updates
- Configurable per-pipeline via registry

---

## Integration Points

### Update `core/__init__.py`

```python
# Add time utilities export
from market_spine.core.time import utc_now, utc_now_naive, ago, from_now

__all__ = [
    # ... existing exports ...
    "utc_now",
    "utc_now_naive",
    "ago",
    "from_now",
]
```

### Update `api/main.py`

```python
# Add middleware imports
from market_spine.api.middleware import (
    RateLimitMiddleware,
    RequestContextMiddleware,
)

def create_app() -> FastAPI:
    # ... existing code ...
    
    # Add new middleware (order matters - context first)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(RateLimitMiddleware, max_tokens=100, refill_rate=10)
    
    # ... rest of app setup ...
```

### Replace `datetime.utcnow()` Calls

Files requiring updates:
- `core/models.py` (2 occurrences)
- `execution/ledger.py` (1 occurrence)
- `execution/dlq.py` (3 occurrences)
- `execution/concurrency.py` (3 occurrences)
- `repositories/otc.py` (4 occurrences)
- `repositories/execution.py` (4 occurrences)
- `services/connector.py` (6 occurrences)
- `services/normalizer.py` (1 occurrence)
- `pipelines/otc.py` (1 occurrence)
- `api/routes/health.py` (3 occurrences)

**Migration pattern:**
```python
# Before
from datetime import datetime
created_at = datetime.utcnow()

# After
from market_spine.core.time import utc_now_naive
created_at = utc_now_naive()
```

---

## File Summary

| File | Status | Description |
|------|--------|-------------|
| `core/time.py` | ✅ CREATED | Timezone-aware datetime utilities |
| `core/__init__.py` | ✅ UPDATED | Export time utilities |
| `api/middleware/__init__.py` | ✅ CREATED | Middleware package exports |
| `api/middleware/rate_limit.py` | ✅ CREATED | Token bucket rate limiter |
| `api/middleware/request_context.py` | ✅ CREATED | Request correlation IDs |
| `api/main.py` | ✅ UPDATED | Integrate new middleware |
| `tests/test_time.py` | ✅ CREATED | 12 tests for time utilities |
| `tests/test_middleware.py` | ✅ CREATED | 7 tests for rate limiting |
| `services/circuit_breaker.py` | 📋 PLANNED | External service protection |
| `api/routes/health.py` | 📋 UPDATE | Add Redis health check |
| `pipelines/runner.py` | 📋 UPDATE | Pipeline timeout enforcement |

**Test Results:** 66 tests passing (up from 47)

---

## Testing Strategy

Each new component requires tests:

| Component | Test File | Test Cases |
|-----------|-----------|------------|
| Time utilities | `tests/test_time.py` | utc_now returns aware datetime, ago/from_now math |
| Rate limiter | `tests/test_rate_limit.py` | Token refill, limit exceeded, exclude paths |
| Request context | `tests/test_request_context.py` | ID generation, header extraction |
| Circuit breaker | `tests/test_circuit_breaker.py` | State transitions, recovery |

---

## Invariant Preservation

All changes must maintain existing invariants:

1. **Single Execution Entrypoint** - Only `Dispatcher` creates executions ✅
2. **Single Processing Point** - Only `run_pipeline()` calls handlers ✅
3. **API-Backend Separation** - API never calls `run_pipeline` directly ✅
4. **Consistent Backend Interface** - All backends have same `submit()` signature ✅

The new middleware and utilities are cross-cutting concerns that don't affect these core architectural invariants.
