# spine.execution

The execution infrastructure layer — dispatching, retrying, circuit breaking, rate limiting, and tracking work.

## Key Modules

| Module | Purpose |
|--------|---------|
| `dispatcher` | `Dispatcher` — routes work specs to handlers |
| `spec` | `WorkSpec`, `task_spec()`, `operation_spec()`, `workflow_spec()` |
| `runs` | `RunRecord`, `RunStatus`, `RunSummary` |
| `retry` | `RetryStrategy`, `ExponentialBackoff`, `LinearBackoff` |
| `circuit_breaker` | `CircuitBreaker`, `CircuitBreakerRegistry` |
| `rate_limit` | `TokenBucketLimiter`, `SlidingWindowLimiter`, `KeyedRateLimiter` |
| `batch` | `BatchBuilder`, `BatchExecutor`, `BatchResult` |
| `concurrency` | `ConcurrencyGuard` — prevent overlapping runs |
| `dlq` | `DLQManager` — dead-letter queue for failures |
| `ledger` | `ExecutionLedger` — append-only audit log |
| `health` | `ExecutionHealthChecker`, `HealthReport` |
| `handlers` | `HandlerRegistry`, `@register_task` |
| `timeout` | `TimeoutExecutor`, `@with_timeout` decorator |

## API Reference

See the full auto-generated API docs at [API Reference — spine.execution](../api/execution.md).
