# Quick Start Guide

Get up and running with the new Spine features in 5 minutes.

---

## What's New?

This release adds production-grade infrastructure to Spine:

| Feature | What It Does |
|---------|--------------|
| **Structured Errors** | Typed exceptions with retry metadata |
| **Result[T]** | Explicit success/failure handling |
| **Source Adapters** | Unified data ingestion (file, API, DB) |
| **Orchestration v2** | Workflows with context passing |
| **Alerting** | Slack, Email, webhook notifications |
| **SQL History** | Track all workflow executions |
| **REST APIs** | Manage everything via API |

---

## 1. Structured Errors (2 minutes)

Before: Generic exceptions everywhere
After: Typed errors with retry decisions built in

```python
from spine.core.errors import SourceError, TransientError, is_retryable

try:
    data = fetch_data()
except Exception as e:
    if is_retryable(e):
        # Network timeout, rate limit - retry later
        schedule_retry(delay=30)
    else:
        # Permanent failure - alert and move on
        send_alert(e)
```

---

## 2. File Source (2 minutes)

Before: Manual CSV parsing in every pipeline
After: Unified source with change detection

```python
from spine.framework.sources.file import FileSource

# Auto-detects PSV format from extension
source = FileSource(name="finra", path="/data/finra.psv")
result = source.fetch()

if result.success:
    for row in result.data:
        print(row["symbol"], row["volume"])
    
    # Check hash to skip unchanged files next time
    print(f"Content hash: {result.metadata.content_hash}")
```

---

## 3. Workflows (3 minutes)

Before: PipelineGroups with no data passing
After: Steps that share context

```python
from spine.orchestration import Workflow, Step, StepResult, WorkflowRunner

# Lambda step for validation
def validate(ctx, config):
    count = ctx.get_output("ingest", "row_count", 0)
    if count < 100:
        return StepResult.fail("Too few records")
    return StepResult.ok(output={"validated": True})

# Define workflow
workflow = Workflow(
    name="my.workflow",
    steps=[
        Step.pipeline("ingest", "my.ingest_pipeline"),
        Step.lambda_("validate", validate),
        Step.pipeline("process", "my.process_pipeline"),
    ],
)

# Run it
runner = WorkflowRunner()
result = runner.execute(workflow, params={"date": "2026-01-11"})

print(f"Status: {result.status}")
print(f"Completed: {result.completed_steps}")
```

---

## 4. Alerting (2 minutes)

Before: No way to notify on failures
After: Multi-channel alerts

```python
from spine.framework.alerts import SlackChannel, alert_registry, send_alert, AlertSeverity

# At startup: configure channels
alert_registry.register(SlackChannel(
    name="ops",
    webhook_url="https://hooks.slack.com/...",
    min_severity=AlertSeverity.ERROR,
))

# Anywhere: send alerts
send_alert(
    severity=AlertSeverity.ERROR,
    title="Pipeline Failed",
    message="FINRA ingestion timed out",
    source="finra.ingest",
)
```

---

## 5. Result[T] Pattern (1 minute)

Before: Exceptions for expected failures
After: Explicit success/failure

```python
from spine.core.result import Result, Ok, Err

def fetch_user(id: str) -> Result[User]:
    user = db.get(id)
    if user is None:
        return Err(SourceNotFoundError(f"User {id} not found"))
    return Ok(user)

# Pattern matching
result = fetch_user("123")
match result:
    case Ok(user):
        print(user.name)
    case Err(error):
        print(f"Error: {error.message}")

# Or functional style
name = fetch_user("123").map(lambda u: u.name).unwrap_or("Unknown")
```

---

## Migration Checklist

### For Intermediate Tier

1. **Run SQL migrations**
   ```bash
   sqlite3 data.db < schema/02_workflow_history.sql
   sqlite3 data.db < schema/03_scheduler.sql
   sqlite3 data.db < schema/04_alerting.sql
   sqlite3 data.db < schema/05_sources.sql
   ```

2. **Register API routes** (in `main.py`)
   ```python
   from market_spine.api.routes import workflows, schedules, alerts, sources
   
   app.include_router(workflows.router)
   app.include_router(schedules.router)
   app.include_router(alerts.router)
   app.include_router(sources.router)
   ```

3. **Configure alert channels** (via API or startup code)
   ```python
   # startup.py
   from spine.framework.alerts import SlackChannel, alert_registry
   
   alert_registry.register(SlackChannel(
       name="production",
       webhook_url=os.environ["SLACK_WEBHOOK"],
   ))
   ```

---

## File Map

| What You Need | Where To Find It |
|---------------|------------------|
| Error types | `spine/core/errors.py` |
| Result[T] | `spine/core/result.py` |
| FileSource | `spine/framework/sources/file.py` |
| Source protocol | `spine/framework/sources/protocol.py` |
| AlertChannel | `spine/framework/alerts/protocol.py` |
| Workflow | `spine/orchestration/workflow.py` |
| WorkflowContext | `spine/orchestration/workflow_context.py` |
| WorkflowRunner | `spine/orchestration/workflow_runner.py` |
| Step types | `spine/orchestration/step_types.py` |
| StepResult | `spine/orchestration/step_result.py` |
| SQL schema | `spine/core/schema/02-05_*.sql` |
| API routes | `market_spine/api/routes/*.py` |
| TypeScript types | `trading-desktop/src/api/operationsTypes.ts` |

---

## Next Steps

- [01-ARCHITECTURE-OVERVIEW.md](./01-ARCHITECTURE-OVERVIEW.md) - See how components fit together
- [02-ERROR-HANDLING.md](./02-ERROR-HANDLING.md) - Deep dive on errors and Result[T]
- [03-SOURCE-ADAPTERS.md](./03-SOURCE-ADAPTERS.md) - All about data sources
- [04-ALERTING-FRAMEWORK.md](./04-ALERTING-FRAMEWORK.md) - Setting up notifications
- [05-ORCHESTRATION-V2.md](./05-ORCHESTRATION-V2.md) - Building workflows
