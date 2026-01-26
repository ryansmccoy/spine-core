# Error Handling

This document covers the structured error handling system added to Spine Core.

---

## Overview

Spine now has a **typed error hierarchy** that enables:
- Automatic retry decisions based on error category
- Consistent error serialization for logging/alerting
- Error chaining for root cause analysis
- Explicit success/failure handling with `Result[T]`

---

## Error Categories

Every `SpineError` has a `category` that classifies what went wrong:

```python
from spine.core.errors import ErrorCategory

class ErrorCategory(str, Enum):
    # Infrastructure (usually transient)
    NETWORK = "NETWORK"       # Connection, timeout, DNS
    DATABASE = "DATABASE"     # Connection pool, query timeout
    STORAGE = "STORAGE"       # Disk, S3, file system
    
    # Data errors
    SOURCE = "SOURCE"         # Upstream API, file not found
    PARSE = "PARSE"           # Format errors
    VALIDATION = "VALIDATION" # Schema, constraint violations
    
    # Configuration (never retryable)
    CONFIG = "CONFIG"         # Missing config, invalid settings
    AUTH = "AUTH"             # Authentication, authorization
    
    # Application errors
    PIPELINE = "PIPELINE"     # Pipeline execution failures
    ORCHESTRATION = "ORCHESTRATION"  # Workflow, scheduler
    
    # Internal
    INTERNAL = "INTERNAL"     # Bugs, unexpected state
    UNKNOWN = "UNKNOWN"       # Uncategorized
```

---

## Error Hierarchy

```
SpineError (base)
├── TransientError (retryable by default)
│   ├── NetworkError
│   ├── TimeoutError
│   ├── RateLimitError
│   └── DatabaseConnectionError
│
├── SourceError (not retryable by default)
│   ├── SourceNotFoundError
│   ├── SourceUnavailableError (retryable)
│   └── ParseError
│
├── ValidationError (never retryable)
│   ├── SchemaError
│   └── ConstraintError
│
├── ConfigError (never retryable)
│   ├── MissingConfigError
│   └── InvalidConfigError
│
├── AuthError (never retryable)
│   ├── AuthenticationError
│   └── AuthorizationError
│
├── PipelineError
│   ├── PipelineNotFoundError
│   └── BadParamsError
│
├── OrchestrationError
│   ├── WorkflowError
│   └── ScheduleError
│
├── StorageError
│
└── DatabaseError
    ├── QueryError
    └── IntegrityError
```

---

## Using Errors

### Raising Typed Errors

```python
from spine.core.errors import (
    SourceError,
    TransientError,
    RateLimitError,
    ValidationError,
)

# Simple error
raise SourceError("File not found: data.csv")

# With context (fluent API)
raise SourceError("API returned 500").with_context(
    source_name="finra_api",
    url="https://api.finra.org/data",
    http_status=500,
)

# With retry metadata
raise TransientError(
    "Connection timed out",
    retryable=True,
    retry_after=30,  # Wait 30 seconds
)

# Rate limiting (auto-sets retry_after)
raise RateLimitError(retry_after=60)

# Validation with field info
raise ValidationError(
    "Invalid date format",
    field="trade_date",
    value="2026-13-45",
    constraint="ISO 8601",
)
```

### Error Chaining

Preserve the original cause for debugging:

```python
try:
    response = requests.get(url, timeout=10)
except requests.Timeout as e:
    raise TransientError(
        "API request timed out",
        cause=e,  # Links to original exception
        retryable=True,
    )
```

### Checking Retry-ability

```python
from spine.core.errors import is_retryable, get_retry_after, categorize_error

try:
    fetch_data()
except Exception as e:
    if is_retryable(e):
        delay = get_retry_after(e) or 30
        schedule_retry(delay=delay)
    else:
        # Permanent failure
        category = categorize_error(e)
        log.error(f"[{category}] {e}")
        send_alert(e)
```

---

## Result[T] Pattern

For functions where you want to avoid exceptions entirely:

### Basic Usage

```python
from spine.core.result import Result, Ok, Err

def fetch_user(user_id: str) -> Result[User]:
    try:
        user = db.get_user(user_id)
        if user is None:
            return Err(SourceNotFoundError(f"User {user_id} not found"))
        return Ok(user)
    except DatabaseError as e:
        return Err(e)

# Pattern matching (Python 3.10+)
result = fetch_user("123")
match result:
    case Ok(user):
        print(f"Found: {user.name}")
    case Err(error):
        print(f"Error: {error.message}")
```

### Unwrapping

```python
# Get value or raise
user = result.unwrap()  # Raises if Err

# Get value with default
user = result.unwrap_or(default_user)

# Get value with fallback function
user = result.unwrap_or_else(lambda e: create_default_user())
```

### Functional Chaining

```python
# Transform successful value
name_result: Result[str] = result.map(lambda u: u.name)

# Chain to another Result-returning function
profile_result: Result[Profile] = result.flat_map(fetch_profile)

# Handle both paths
final_name = (
    fetch_user("123")
    .map(lambda u: u.name)
    .map(lambda n: n.upper())
    .unwrap_or("UNKNOWN")
)
```

### Collecting Results

```python
from spine.core.result import collect_results, partition_results

# Fetch multiple users
results = [fetch_user(id) for id in user_ids]

# Stop at first error
all_users = collect_results(results)  # Result[list[User]]

# Or get all values and all errors
users, errors = partition_results(results)
if errors:
    log.warning(f"{len(errors)} users not found")
process(users)
```

### Converting to/from Optional

```python
from spine.core.result import from_optional

# Optional to Result
cache_value = cache.get("key")
result = from_optional(
    cache_value,
    error=SourceNotFoundError("Cache miss"),
)
```

---

## Serialization

All errors serialize to dictionaries for logging:

```python
error = SourceError("API failed").with_context(
    source_name="finra_api",
    http_status=500,
)

error.to_dict()
# {
#     "error_type": "SourceError",
#     "message": "API failed",
#     "category": "SOURCE",
#     "retryable": False,
#     "context": {
#         "source_name": "finra_api",
#         "http_status": 500
#     }
# }
```

---

## Integration with Logging

```python
import structlog

log = structlog.get_logger()

try:
    process_data()
except SpineError as e:
    log.error(
        "processing_failed",
        **e.to_dict(),
    )
    # Logs structured JSON with all error context
```

---

## Best Practices

### 1. Use Specific Error Types

```python
# ❌ Generic
raise Exception("Something went wrong")

# ✅ Specific
raise SourceNotFoundError("FINRA file missing for 2026-01-10")
```

### 2. Add Context

```python
# ❌ No context
raise ParseError("Invalid JSON")

# ✅ With context
raise ParseError("Invalid JSON at line 42").with_context(
    source_name="trades.json",
    path="/data/trades.json",
)
```

### 3. Use Result for Expected Failures

```python
# ❌ Using exceptions for control flow
try:
    user = fetch_user(id)
except UserNotFound:
    user = create_default()

# ✅ Using Result
user = fetch_user(id).unwrap_or_else(lambda _: create_default())
```

### 4. Chain Causes

```python
# ❌ Swallowing the original error
except requests.HTTPError:
    raise SourceError("API call failed")

# ✅ Preserving the chain
except requests.HTTPError as e:
    raise SourceError("API call failed", cause=e)
```

---

## Summary

| Feature | Purpose |
|---------|---------|
| `SpineError` | Base exception with category, retryable flag |
| `TransientError` | Temporary failures (network, rate limits) |
| `SourceError` | Data source failures |
| `ValidationError` | Data validation failures |
| `ConfigError` | Configuration problems |
| `Result[T]` | Explicit success/failure without exceptions |
| `is_retryable()` | Check if error should be retried |
| `categorize_error()` | Get category of any exception |
| `.with_context()` | Add metadata to error |
| `.to_dict()` | Serialize for logging |
