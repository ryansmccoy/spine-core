# Error Handling

spine-core uses a dual approach to error handling: the `Result[T]` type for expected failures and a typed exception hierarchy for unexpected failures.

## Result Pattern

The `Result[T]` type makes error handling explicit in function signatures:

```python
from spine.core.result import Ok, Err, Result

def fetch_price(ticker: str) -> Result[float]:
    if not ticker:
        return Err("Empty ticker")
    return Ok(150.25)

# Chaining
result = (
    fetch_price("AAPL")
    .map(lambda p: p * 100)         # Ok(15025.0)
    .flat_map(lambda v: Ok(round(v)))  # Ok(15025)
)

# Safe unwrapping
value = result.unwrap_or(0)  # 15025
```

### Collecting Results

Process a batch and separate successes from failures:

```python
from spine.core.result import collect_results

results = [fetch_price(t) for t in ["AAPL", "", "MSFT"]]
successes, failures = collect_results(results)
# successes = [150.25, 150.25], failures = [Err("Empty ticker")]
```

## SpineError Hierarchy

For exceptional conditions, spine-core provides typed exceptions:

```
SpineError
├── TransientError      # Retryable (network timeout, rate limit)
├── SourceError         # External system failure
├── ValidationError     # Data validation failure
├── ConfigError         # Configuration problem
└── PermanentError      # Non-retryable failure
```

### Error Categories

Each `SpineError` carries an `ErrorCategory` that enables automatic routing:

```python
from spine.core.errors import TransientError, SpineError

try:
    call_external_api()
except TransientError as e:
    if e.is_retryable:
        retry_later(e)
    else:
        send_to_dlq(e)
```

### Retry Semantics

| Error Type | Retryable? | Example |
|-----------|-----------|---------|
| `TransientError` | Yes | Network timeout, 503 response |
| `SourceError` | Sometimes | API rate limit (yes), API auth failure (no) |
| `ValidationError` | No | Missing required field |
| `ConfigError` | No | Invalid database URL |
| `PermanentError` | No | Business rule violation |

## Integration with Execution Layer

The error hierarchy integrates with the execution infrastructure:

- **RetryStrategy** checks `is_retryable` to decide whether to retry
- **CircuitBreaker** counts failures to trigger the breaker
- **DLQManager** captures non-retryable failures for later inspection
- **ExecutionLedger** records all errors for audit

```python
from spine.execution.retry import RetryStrategy, ExponentialBackoff

strategy = RetryStrategy(
    max_retries=3,
    backoff=ExponentialBackoff(base_seconds=1.0),
    retryable_exceptions=(TransientError,),
)

# TransientError → retried up to 3 times
# ValidationError → fails immediately
result = strategy.execute(risky_operation)
```

## Best Practices

1. **Use `Result[T]`** for expected failure modes (parsing, validation, lookups)
2. **Use `SpineError` subclasses** for exceptional conditions
3. **Never catch bare `Exception`** — always catch specific types
4. **Tag errors with categories** for automatic routing
5. **Include context** in error messages (what failed, what was expected)
