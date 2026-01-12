# Architecture Overview

## How It All Fits Together

This document explains how the new Spine components work together to provide a production-grade data platform.

---

## The Big Picture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            SPINE FRAMEWORK                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐          │
│  │   SOURCES   │────▶│    PIPELINES    │────▶│    CAPTURES      │          │
│  │  (Ingest)   │     │  (Transform)    │     │  (Store/Track)   │          │
│  └─────────────┘     └─────────────────┘     └──────────────────┘          │
│         │                    │                        │                     │
│         │                    │                        │                     │
│         ▼                    ▼                        ▼                     │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │                      ORCHESTRATION                          │           │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐        │           │
│  │  │ Step 1  │─▶│ Step 2  │─▶│ Step 3  │─▶│ Step N  │        │           │
│  │  │(Lambda) │  │(Pipeline│  │(Choice) │  │(Pipeline│        │           │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘        │           │
│  │         ▲           │                          │            │           │
│  │         └───────────┴──── Context Passing ─────┘            │           │
│  └─────────────────────────────────────────────────────────────┘           │
│                               │                                             │
│         ┌─────────────────────┼─────────────────────┐                      │
│         ▼                     ▼                     ▼                      │
│  ┌─────────────┐     ┌─────────────────┐     ┌──────────────┐             │
│  │   ALERTS    │     │   SCHEDULER     │     │   HISTORY    │             │
│  │ Slack/Email │     │   (APScheduler) │     │ (Audit Trail)│             │
│  └─────────────┘     └─────────────────┘     └──────────────┘             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. Sources (Data Ingestion)

**Problem**: Before, each pipeline had to implement its own file reading, API calling, or database querying logic.

**Solution**: The `Source` protocol provides a unified interface:

```python
from spine.framework.sources import FileSource, source_registry

# Register a source
source = FileSource(
    name="finra.otc.weekly",
    path="/data/finra/*.psv",
    domain="finra.otc_transparency",
)
source_registry.register(source)

# Use it anywhere
result = source_registry.get("finra.otc.weekly").fetch()
if result.success:
    process(result.data)
```

**Key Features**:
- Auto-detects file format (CSV, PSV, JSON, Parquet)
- Content hashing for change detection (skip unchanged files)
- Streaming support for large files
- Metadata tracking (fetch time, bytes, row count)

### 2. Error Handling

**Problem**: Exceptions were untyped—you couldn't tell if a failure was retryable or permanent.

**Solution**: Structured error hierarchy with categories:

```python
from spine.core.errors import TransientError, SourceError, is_retryable

try:
    fetch_data()
except Exception as e:
    if is_retryable(e):
        # Network timeout, rate limit—try again
        schedule_retry()
    else:
        # File not found, validation error—alert and move on
        send_alert(e)
```

**Error Categories**:
| Category | Retryable? | Examples |
|----------|------------|----------|
| `NETWORK` | Yes | Timeout, connection refused |
| `DATABASE` | Maybe | Pool exhausted vs. query error |
| `SOURCE` | No | File not found, 404 |
| `VALIDATION` | No | Schema mismatch, constraint violation |
| `CONFIG` | No | Missing required setting |

### 3. Result[T] Pattern

**Problem**: Using exceptions for control flow obscures success/failure paths.

**Solution**: Explicit `Result[T]` type (similar to Rust's Result):

```python
from spine.core.result import Result, Ok, Err, try_result

def fetch_user(id: str) -> Result[User]:
    try:
        user = db.get(id)
        return Ok(user)
    except NotFound:
        return Err(SourceNotFoundError(f"User {id} not found"))

# Pattern matching
result = fetch_user("123")
match result:
    case Ok(user):
        print(f"Found: {user.name}")
    case Err(error):
        print(f"Error: {error.message}")

# Or functional chaining
final = (
    fetch_user("123")
    .map(lambda u: u.name)
    .unwrap_or("Unknown")
)
```

### 4. Orchestration (Workflow v2)

**Problem**: PipelineGroups can only orchestrate registered pipelines—no inline logic, no data passing between steps.

**Solution**: Workflows with context passing:

```python
from spine.orchestration import Workflow, Step, StepResult

def validate_fn(ctx, config):
    count = ctx.get_output("ingest", "record_count", 0)
    if count < 100:
        return StepResult.fail("Too few records")
    return StepResult.ok(output={"validated": True})

workflow = Workflow(
    name="finra.weekly_refresh",
    steps=[
        Step.pipeline("ingest", "finra.otc.ingest_week"),
        Step.lambda_("validate", validate_fn),
        Step.choice("route",
            condition=lambda ctx: ctx.get_output("validate", "validated"),
            then_step="process",
            else_step="reject",
        ),
        Step.pipeline("process", "finra.otc.normalize"),
    ],
)
```

**Key Concepts**:
- **WorkflowContext**: Immutable context that flows step-to-step
- **StepResult**: Each step returns success/failure with output data
- **Steps** store their output in `context.outputs[step_name]`
- **Lambda steps**: Inline functions for validation, routing, notifications
- **Pipeline steps**: Wrap registered pipelines
- **Choice steps**: Conditional branching (Intermediate tier)

### 5. Alerting

**Problem**: No way to notify operators when pipelines fail.

**Solution**: Multi-channel alert framework:

```python
from spine.framework.alerts import SlackChannel, alert_registry, send_alert

# Configure channels (usually at startup)
slack = SlackChannel(
    name="ops-alerts",
    webhook_url="https://hooks.slack.com/...",
    min_severity=AlertSeverity.ERROR,
    domains=["finra.*"],  # Only FINRA alerts
)
alert_registry.register(slack)

# Send alerts (from anywhere)
send_alert(
    severity=AlertSeverity.ERROR,
    title="FINRA Ingestion Failed",
    message="Weekly OTC file could not be downloaded",
    source="finra.otc.ingest",
)
```

**Channels**:
- `SlackChannel`: Sends to Slack webhook
- `EmailChannel`: Sends via SMTP
- `WebhookChannel`: POST to any URL
- `ConsoleChannel`: Development/testing

### 6. Database Adapters

**Problem**: Intermediate tier uses PostgreSQL, but code shouldn't depend on specific drivers.

**Solution**: Adapter pattern with registry:

```python
from spine.core.adapters.database import get_adapter, DatabaseType

# SQLite (Basic tier)
adapter = get_adapter(DatabaseType.SQLITE, path="local.db")

# PostgreSQL (Intermediate tier)
adapter = get_adapter(
    DatabaseType.POSTGRESQL,
    host="localhost",
    database="spine",
    username="spine_user",
)

# Use uniformly
with adapter.transaction() as conn:
    conn.execute("SELECT * FROM captures WHERE domain = ?", (domain,))
```

---

## Data Flow Example

Here's a complete example showing how data flows through the system:

```
1. SCHEDULE TRIGGERS
   ┌─────────────────┐
   │ APScheduler     │ ──────▶ "Run finra.weekly_refresh"
   └─────────────────┘

2. WORKFLOW STARTS
   ┌─────────────────┐
   │ WorkflowRunner  │ ──────▶ Creates WorkflowContext(run_id=...)
   └─────────────────┘

3. STEP 1: INGEST (Pipeline Step)
   ┌─────────────────┐
   │ FileSource      │ ──────▶ Fetches /data/finra/*.psv
   │                 │         Returns SourceResult(data=[...], metadata={hash, size})
   └─────────────────┘
   
4. STEP 2: VALIDATE (Lambda Step)
   ┌─────────────────┐
   │ validate_fn     │ ──────▶ Checks row count from ctx.outputs["ingest"]
   │                 │         Returns StepResult.ok(validated=True)
   └─────────────────┘

5. STEP 3: ROUTE (Choice Step)
   ┌─────────────────┐
   │ Choice          │ ──────▶ ctx.outputs["validate"]["validated"] == True
   │                 │         Jump to "process" step
   └─────────────────┘

6. STEP 4: PROCESS (Pipeline Step)
   ┌─────────────────┐
   │ Dispatcher      │ ──────▶ Runs finra.otc.normalize pipeline
   │                 │         Captures output with lineage
   └─────────────────┘

7. WORKFLOW COMPLETES
   ┌─────────────────┐
   │ History         │ ──────▶ Writes to core_workflow_runs
   │                 │         Status=COMPLETED, duration_ms=...
   └─────────────────┘

8. (On failure) ALERT SENT
   ┌─────────────────┐
   │ AlertRegistry   │ ──────▶ Sends to all matching channels
   │                 │         Logs to core_alerts, core_alert_deliveries
   └─────────────────┘
```

---

## Tier Mapping

| Component | Basic | Intermediate | Advanced | Full |
|-----------|-------|--------------|----------|------|
| `Result[T]` | ✅ | ✅ | ✅ | ✅ |
| `SpineError` hierarchy | ✅ | ✅ | ✅ | ✅ |
| `FileSource` | ✅ | ✅ | ✅ | ✅ |
| `SQLiteAdapter` | ✅ | ✅ | ✅ | ✅ |
| `Workflow` (lambda/pipeline steps) | ✅ | ✅ | ✅ | ✅ |
| `WorkflowRunner` | ✅ | ✅ | ✅ | ✅ |
| SQL History Tables | ❌ | ✅ | ✅ | ✅ |
| `Choice` steps | ❌ | ✅ | ✅ | ✅ |
| `PostgreSQLAdapter` | ❌ | ✅ | ✅ | ✅ |
| Alerting (Slack/Email) | ❌ | ✅ | ✅ | ✅ |
| Scheduler Service | ❌ | ✅ | ✅ | ✅ |
| `HttpSource` | ❌ | ❌ | ✅ | ✅ |
| `Wait`/`Map` steps | ❌ | ❌ | ✅ | ✅ |
| Distributed Scheduling | ❌ | ❌ | ❌ | ✅ |
| ServiceNow/PagerDuty | ❌ | ❌ | ❌ | ✅ |

---

## Next Steps

For detailed documentation on each component:

1. [Error Handling](./02-ERROR-HANDLING.md) - Deep dive into SpineError and Result[T]
2. [Source Adapters](./03-SOURCE-ADAPTERS.md) - How to use and extend sources
3. [Alerting Framework](./04-ALERTING-FRAMEWORK.md) - Setting up notifications
4. [Orchestration v2](./05-ORCHESTRATION-V2.md) - Building workflows
5. [SQL Schema](./06-SQL-SCHEMA.md) - Database table reference
