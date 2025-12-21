# Protocols

spine-core uses Python `Protocol` classes to define interfaces without requiring inheritance. This enables duck typing with static type checking.

## Core Protocols

### Connection

The `Connection` protocol defines the sync database interface used throughout spine-core:

```python
from spine.core.protocols import Connection
```

**Key points:**

- Runtime-checkable via `@runtime_checkable`
- Any object with these methods satisfies the protocol
- Used by `BaseRepository`, `Dialect`, and all ops modules

### Usage Example

```python
import sqlite3
from spine.core.protocols import Connection

# sqlite3.Connection satisfies the protocol
conn: Connection = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
conn.commit()
```

## Result Protocol

The `Result[T]` type acts as a protocol for success/failure handling:

```python
from spine.core.result import Ok, Err, Result

def divide(a: float, b: float) -> Result[float]:
    if b == 0:
        return Err("Division by zero")
    return Ok(a / b)

# Pattern matching
result = divide(10, 3)
if result.is_ok():
    print(f"Value: {result.unwrap()}")
else:
    print(f"Error: {result.error}")
```

## Executor Protocol

The `Executor` protocol in `spine.execution.executors` defines how work gets executed:

- `MemoryExecutor` — In-process, synchronous
- `LocalExecutor` — Thread pool
- `AsyncLocalExecutor` — asyncio-based
- `ProcessExecutor` — Multi-process
- `CeleryExecutor` — Distributed via Celery
- `StubExecutor` — Testing double

## Design Philosophy

spine-core prefers protocols over abstract base classes because:

1. **No inheritance required** — Any matching object works
2. **Gradual typing** — Works with or without type checkers
3. **Testability** — Easy to create test doubles
4. **Interop** — Third-party objects can satisfy spine protocols
