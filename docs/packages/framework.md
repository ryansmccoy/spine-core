# spine.framework

The application framework layer — operation definitions, registry, runner, alert routing, and source connectors.

## Key Modules

| Module | Purpose |
|--------|---------|
| `operations` | `Operation` ABC, `OperationResult`, `OperationStatus` |
| `registry` | `@register_operation`, `get_operation()`, `list_operations()` |
| `runner` | `OperationRunner.run()`, `run_all()` |
| `dispatcher` | Framework-level event dispatching |
| `alerts/` | Alert routing and channel management |
| `sources/` | Source connectors for external systems |
| `params` | Parameter validation and defaults |
| `logging/` | Framework-specific structured logging |

## Operation Lifecycle

```
1. Define    →  class MyOp(Operation): ...
2. Register  →  @register_operation
3. Discover  →  list_operations()
4. Execute   →  OperationRunner.run("my_op")
5. Track     →  Result → ledger, anomalies, quality gates
```

## API Reference

See the full auto-generated API docs at [API Reference — spine.framework](../api/framework.md).
