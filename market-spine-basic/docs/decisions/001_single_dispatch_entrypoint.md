# ADR 001: Single Dispatch Entrypoint

**Status**: Accepted  
**Date**: December 2025  
**Context**: Market Spine Basic architecture

## Decision

All pipeline execution MUST go through the Dispatcher. No other code path is supported.

```python
# The ONLY way to run a pipeline
dispatcher = get_dispatcher()
execution = dispatcher.submit("pipeline.name", params={...})
```

## Context

We need to run pipelines from multiple sources:
- CLI commands
- Scheduled jobs
- API requests
- Sub-pipeline calls

Without a single entry point, each source would need to:
- Generate execution IDs
- Set logging context
- Handle errors
- Track execution history

This leads to inconsistent behavior and bugs.

## Consequences

### Positive

1. **Consistent tracing** — Every execution has an `execution_id`
2. **Unified logging** — Context is always set
3. **Single audit point** — All executions go through one place
4. **Future-proof** — Easy to add queueing, rate limiting, retries

### Negative

1. **Indirection** — Can't just instantiate and run a pipeline
2. **Testing overhead** — Tests should use the dispatcher too

### Mitigation

For unit testing individual pipelines, use:

```python
# Direct instantiation is OK for unit tests
pipeline = MyPipeline(params={...})
result = pipeline.run()
```

But integration tests should use the dispatcher.

## Alternatives Considered

### Direct Pipeline Instantiation

```python
pipeline = get_pipeline("name")(params)
pipeline.run()
```

**Rejected**: No execution tracking, no logging context.

### Pipeline.execute() Class Method

```python
MyPipeline.execute(params)
```

**Rejected**: Still bypasses centralized dispatch.

## Implementation

The Dispatcher is responsible for:

1. Generating `execution_id`
2. Creating `Execution` record
3. Setting logging context via `set_context()`
4. Calling `Runner.run()`
5. Logging `execution.summary`
6. Clearing context via `clear_context()`

```python
class Dispatcher:
    def submit(self, pipeline: str, params: dict, ...) -> Execution:
        execution_id = str(uuid4())
        
        set_context(execution_id=execution_id, pipeline=pipeline)
        
        try:
            result = self._runner.run(pipeline, params)
        finally:
            clear_context()
        
        return execution
```

## Related

- [Execution Model](../architecture/02_execution_model.md)
