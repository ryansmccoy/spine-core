# Error Model and Anomalies

> Canonical patterns for error handling and anomaly recording in spine-core. Reference this when handling failures.

## Error Model

### API Error Response

All API errors follow a consistent structure:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable error description",
    "details": {
      "field": "limit",
      "constraint": "must be positive integer"
    }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `NOT_FOUND` | 404 | Resource doesn't exist |
| `CONFLICT` | 409 | Resource already exists |
| `RATE_LIMITED` | 429 | Too many requests |
| `UPSTREAM_ERROR` | 502 | External API failed |
| `INTERNAL_ERROR` | 500 | Unexpected server error |

### Implementation

```python
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class ApiError(Exception):
    """Structured API error."""
    code: str
    message: str
    details: dict[str, Any] | None = None
    http_status: int = 400
    
    def to_response(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


# Usage in FastAPI
from fastapi import HTTPException
from fastapi.responses import JSONResponse

@app.exception_handler(ApiError)
async def api_error_handler(request, exc: ApiError):
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_response(),
    )
```

---

## Anomalies

Anomalies are **recorded issues** that don't necessarily fail the operation but should be tracked.

### Anomaly Structure

```python
@dataclass
class Anomaly:
    """Recorded issue during processing."""
    category: str          # Classification (e.g., "data_quality")
    message: str           # Human-readable description
    severity: str          # "warning" or "error"
    context: dict | None   # Additional context
    recorded_at: str       # ISO timestamp
```

### Anomaly Categories

| Category | Description | Example |
|----------|-------------|---------|
| `api_error` | External API returned error | "Rate limit exceeded" |
| `rate_limit` | Rate limiting triggered | "429 from Alpha Vantage" |
| `network_error` | Network/connection issue | "Connection timeout" |
| `parse_error` | Response parsing failed | "Invalid JSON" |
| `data_quality` | Data validation issue | "Missing close price" |
| `schema_mismatch` | Unexpected schema | "New field in response" |

### Recording Anomalies

```python
from dataclasses import dataclass, field
from datetime import datetime, UTC


@dataclass
class FetchResult:
    """Result with optional anomalies."""
    data: list[dict]
    anomalies: list[dict] = field(default_factory=list)
    success: bool = True


def record_anomaly(
    result: FetchResult,
    category: str,
    message: str,
    severity: str = "warning",
    context: dict | None = None,
) -> None:
    result.anomalies.append({
        "category": category,
        "message": message,
        "severity": severity,
        "context": context,
        "recorded_at": datetime.now(UTC).isoformat(),
    })
    
    if severity == "error":
        result.success = False
```

---

## Error vs Anomaly

### When to Raise Error

- Request validation fails
- Required resource not found
- Authentication/authorization fails
- Unrecoverable system failure

### When to Record Anomaly

- Partial data returned (some symbols failed)
- Data quality issues (missing fields, outliers)
- Rate limiting (but retries succeeded)
- Schema drift detected

### Example: Mixed Success

```python
def fetch_batch(symbols: list[str]) -> FetchResult:
    result = FetchResult(data=[], anomalies=[])
    
    for symbol in symbols:
        try:
            data = fetch_symbol(symbol)
            result.data.extend(data)
        except RateLimitError as e:
            record_anomaly(
                result,
                category="rate_limit",
                message=f"Rate limited for {symbol}",
                severity="warning",
                context={"symbol": symbol, "retry_after": e.retry_after},
            )
        except ApiError as e:
            record_anomaly(
                result,
                category="api_error",
                message=f"Failed to fetch {symbol}: {e}",
                severity="error",
                context={"symbol": symbol, "error": str(e)},
            )
    
    # Success if at least some data
    result.success = len(result.data) > 0
    return result
```

---

## Persistence

### Anomaly Table

```sql
CREATE TABLE anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_id TEXT NOT NULL,
    category TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL,
    context TEXT,  -- JSON
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (capture_id) REFERENCES captures(capture_id)
);

CREATE INDEX idx_anomalies_capture ON anomalies(capture_id);
CREATE INDEX idx_anomalies_category ON anomalies(category);
```

### Recording to Database

```python
def persist_anomalies(
    conn,
    capture_id: str,
    anomalies: list[dict],
) -> None:
    if not anomalies:
        return
    
    cursor = conn.cursor()
    for a in anomalies:
        cursor.execute("""
            INSERT INTO anomalies 
            (capture_id, category, message, severity, context, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            capture_id,
            a["category"],
            a["message"],
            a["severity"],
            json.dumps(a.get("context")),
            a["recorded_at"],
        ))
    conn.commit()
```

---

## Retry Strategies

### Exponential Backoff

```python
MAX_RETRIES = 3
BACKOFF_BASE = 1.0  # seconds

def fetch_with_retry(fetch_fn, params: dict) -> FetchResult:
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            return fetch_fn(params)
        except RateLimitError as e:
            delay = BACKOFF_BASE * (2 ** attempt)
            time.sleep(delay)
            last_error = e
        except ApiError:
            raise  # Don't retry client errors
    
    # All retries exhausted
    result = FetchResult(data=[], success=False)
    record_anomaly(
        result,
        category="rate_limit",
        message=f"Max retries ({MAX_RETRIES}) exceeded",
        severity="error",
    )
    return result
```

### Circuit Breaker (Advanced)

```python
@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    reset_timeout: float = 60.0
    
    _failures: int = 0
    _last_failure: float = 0.0
    _state: str = "closed"  # closed, open, half-open
    
    def call(self, fn, *args, **kwargs):
        if self._state == "open":
            if time.time() - self._last_failure > self.reset_timeout:
                self._state = "half-open"
            else:
                raise CircuitOpenError()
        
        try:
            result = fn(*args, **kwargs)
            self._failures = 0
            self._state = "closed"
            return result
        except Exception as e:
            self._failures += 1
            self._last_failure = time.time()
            
            if self._failures >= self.failure_threshold:
                self._state = "open"
            
            raise
```

---

## Logging Best Practices

### Structured Logging

```python
import logging
import json

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        return json.dumps(log_data)


# Usage
logger.info("Fetch completed", extra={
    "symbol": "AAPL",
    "rows": 100,
    "anomalies": 0,
})
```

### What to Log

| Level | When |
|-------|------|
| DEBUG | Detailed execution flow |
| INFO | Normal operations (fetch, insert) |
| WARNING | Anomalies, retries |
| ERROR | Failures requiring attention |
| CRITICAL | System-level failures |

---

## Guardrails for LLMs

When implementing error handling:

1. ✅ Use structured error responses (code + message)
2. ✅ Record anomalies for non-fatal issues
3. ✅ Include context in error/anomaly records
4. ✅ Implement retry with exponential backoff
5. ✅ Log at appropriate levels
6. ❌ Don't swallow exceptions silently
7. ❌ Don't expose internal stack traces in API responses
8. ❌ Don't retry on client errors (4xx except 429)
9. ❌ Don't lose anomaly data (persist to database)

---

## Checklist

Before submitting changes:

- [ ] Errors have consistent structure
- [ ] Anomalies are recorded, not lost
- [ ] Retries use exponential backoff
- [ ] Rate limit handling implemented
- [ ] Errors logged with context
- [ ] HTTP status codes are correct
- [ ] No stack traces in production responses
