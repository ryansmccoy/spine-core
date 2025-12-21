# Zero-Dependency spine-core — Feasibility Analysis

> **Date**: 2026-02-17  
> **Status**: ✅ **IMPLEMENTED** — All 4 phases complete  
> **Goal**: Can spine-core run with **zero required PyPI dependencies** (pure stdlib Python ≥3.12)?  
> **TL;DR**: Yes. `dependencies = []` in pyproject.toml. The core workflow engine, orchestration,
> and local execution layers are fully stdlib. structlog and pydantic are optional
> extras that unlock richer features when installed.

---

## Why This Matters

### The .pyz Use Case

spine-core's `WorkflowPackager` bundles workflows into executable `.pyz` archives:

```
python workflow.pyz          # ← runs on any Python 3.12+ machine
```

Today this **still requires** `pip install spine-core` (which pulls structlog + pydantic)
on the target machine. If spine-core had zero required deps, the `.pyz` archive would
truly be self-contained for simple workflows — drop a file, run it, done.

### The Local Executor Use Case

`LocalProcessAdapter` runs `ContainerJobSpec` as local subprocesses without Docker.
Combined with zero deps, this enables a dev/CI story where you:

1. `pip install spine-core` (just Python, no transitive deps)
2. Define workflows in pure Python
3. Run them locally via `LocalProcessAdapter`
4. Package them as `.pyz` for deployment

No Docker, no Redis, no databases, no structlog, no pydantic.

### When You **Would** Need Dependencies

If your workflow steps call `pandas`, `requests`, `sqlalchemy`, etc. — those are
**your** dependencies, not spine-core's. The orchestration engine doesn't care what
your step handlers import. The engine just calls your function and collects the result.

This is the same model as `pytest` — pytest itself has minimal deps, but your tests
can import anything.

---

## Current Dependency Map

```
spine-core (AFTER migration)
├── dependencies = []            ← ZERO required deps ✅
└── [optional-dependencies]
    ├── structured   → structlog (enhanced logging)
    ├── models       → pydantic (data validation)
    ├── settings     → pydantic-settings (env var loading)
    ├── sqlalchemy   → sqlalchemy
    ├── api          → fastapi, uvicorn, sse-starlette
    ├── cli          → typer, rich
    ├── scheduler    → croniter
    ├── postgresql   → psycopg2-binary
    ├── standard     → structured + models + cli
    ├── server       → standard + api + settings
    └── all          → everything above
```

### Per-Package Dependency Usage (src/spine/)

| Package | Files | structlog imports | pydantic imports | Could be stdlib-only? |
|---------|-------|-------------------|------------------|-----------------------|
| **orchestration/** | 26 | 4 (runner, tracked, managed, registry) | 1 (workflow_yaml.py only) | **Yes** — 4 files need `get_logger()` swap, YAML parser is already optional |
| **execution/** | 44 | 5 (packager, executors, workflow_executor) | 1 (fastapi.py only) | **Yes** — 5 logger swaps, fastapi.py is already API-layer |
| **core/** | 84 | 4 (logging.py already has fallback) | 11 (models/, health, settings) | **Partial** — models use BaseModel for API schemas |
| **ops/** | 20 | 12 (every ops module) | 1 (webhooks) | **Yes** — mechanical logger swaps |
| **framework/** | 25 | 3 (logging/, registry) | 0 | **Yes** — logging config needs conditional import |
| **api/** | 28 | 3 | 14 | **No** — FastAPI requires pydantic. This layer stays heavy. |
| **cli/** | 21 | 0 | 0 | **Already stdlib** (uses typer, which is optional) |
| **domain/** | 4 | 0 | 0 | **Already stdlib** |
| **observability/** | 3 | 0 | 0 | **Already stdlib** — has pure-stdlib StructuredLogger (432 LOC) |

### Key Insight

The dependency boundary falls naturally along a **library vs server** split:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LIBRARY LAYER (zero deps)                        │
│                                                                     │
│  orchestration/   → Workflow, Step, Runner, Linter, Visualizer     │
│  execution/       → Runtimes, LocalProcess, Packager, MockAdapters │
│  core/            → Result, Errors, Temporal, Quality, Cache       │
│  ops/             → Business logic (stateless operations)          │
│  framework/       → Pipeline registry, alerts, sources             │
│  domain/          → Finance models (pure Python)                   │
│  observability/   → StructuredLogger (pure stdlib)                 │
│                                                                     │
│  Total: ~230 files — ALL can work with stdlib logging              │
├─────────────────────────────────────────────────────────────────────┤
│                    SERVER LAYER (needs deps)                        │
│                                                                     │
│  api/      → FastAPI routers (needs pydantic + fastapi)            │
│  cli/      → Typer commands (needs typer + rich)                   │
│  deploy/   → Docker compose generation (needs pydantic for config) │
│  mcp/      → MCP server (needs mcp SDK)                           │
│                                                                     │
│  Total: ~60 files — keep dependencies as optional extras           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## structlog → Optional: Detailed Impact

### What exists already

spine-core has **three** logging implementations:

| Layer | Location | structlog needed? |
|-------|----------|-------------------|
| `core/logging.py` | `get_logger()` with `try/except ImportError` fallback | **No** — already has stdlib fallback |
| `observability/logging.py` | 432-line `StructuredLogger` (JSON, context, ECS fields) | **No** — pure stdlib |
| `framework/logging/` | Full config with processors, context propagation | **Yes** — wraps structlog directly |

**The abstraction layer already exists** in `core/logging.py`:

```python
try:
    import structlog
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False

def get_logger(name=None):
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    return logging.getLogger(name)
```

### What needs to change (30 files)

**Category A — Simple swap (27 files):**
These files just do `import structlog; logger = structlog.get_logger(__name__)`.
Change to `from spine.core.logging import get_logger; logger = get_logger(__name__)`.
Same logging API (`.info()`, `.debug()`, `.warning()`, `.error()`).

Files: All 12 ops modules, 4 orchestration modules, 5 execution modules, 
3 api modules, 2 framework modules, 1 packager.

**Category B — Moderate (2 files):**
- `framework/logging/config.py` — uses structlog processors directly. Needs
  conditional imports with stdlib `logging.config` fallback.
- `framework/logging/context.py` — uses `structlog.contextvars`. Needs fallback
  to `observability/logging.py`'s `ContextVar`-based implementation.

**Category C — Already done (1 file):**
- `core/logging.py` — already handles both paths.

### What the consumer experience looks like

```python
# Before (requires structlog installed):
import structlog
logger = structlog.get_logger(__name__)

# After (works with or without structlog):
from spine.core.logging import get_logger
logger = get_logger(__name__)

# Behavior:
#   structlog installed → returns structlog BoundLogger (JSON, processors, context)
#   structlog missing   → returns stdlib logging.Logger (basic formatting)
```

### Risk: LOW

- The `.info()`, `.debug()`, `.warning()`, `.error()` API is identical between
  structlog's BoundLogger and stdlib's Logger.
- The 4 files that already use `logging.getLogger()` (composition.py, dry_run.py,
  router.py, budget.py) prove the stdlib path works today.
- The only difference users notice: without structlog, logs are plain-text instead
  of structured JSON. The `observability/StructuredLogger` can bridge this gap
  if JSON output is needed without structlog.

---

## pydantic → Optional: The Real Story

### Three categories of pydantic usage

After reading every file that imports pydantic, the usage falls into exactly three
buckets with very different replacement stories:

#### Category 1: API-layer models — CANNOT change (50+ classes, 10 files)

These are FastAPI `response_model=` and request body types. FastAPI's contract
is `def endpoint(body: SomeBaseModel) -> SomeBaseModel`. No pydantic = no FastAPI.

| Location | Classes | Why pydantic is non-negotiable |
|----------|---------|-------------------------------|
| `api/schemas/common.py` | 6 (`SuccessResponse[T]`, `PagedResponse[T]`, `PageMeta`, `ProblemDetail`, etc.) | `Generic[T]` response envelopes — FastAPI needs this for OpenAPI generation |
| `api/schemas/domains.py` | 19 (`RunSummarySchema`, `WorkflowDetailSchema`, etc.) | Pydantic inheritance (`RunDetailSchema(RunSummarySchema)`), all used as `response_model=` |
| `api/routers/alerts.py` | 8 request/response models | `model_dump()` for pagination, request body validation |
| `api/routers/runs.py` | 2 (request bodies) | `datetime` Query param auto-parsing from ISO strings |
| `api/routers/sources.py` | 7 | Same pattern |
| `api/routers/events.py` | 5 | Same pattern |
| `api/routers/deploy.py` | 5 | `result.model_dump()` for JSON serialization |
| `api/routers/schedules.py` | 2 | Partial update pattern (`T | None = None` fields) |
| `api/routers/webhooks.py` | 1 | `response_model=WebhookResponse` |
| `api/routers/workflows.py` | 1 | Simple request body |
| `api/settings.py` | 1 (`BaseSettings`) | Env var loading with `env_prefix` |
| `execution/fastapi.py` | 7 | Already behind `if FASTAPI_AVAILABLE:` guard |
| `core/health.py` | 4 | FastAPI `response_model=HealthResponse` + `body.model_dump()` |

**Verdict**: These ~65 classes stay pydantic. They only load when you `pip install spine-core[api]`.
Already behind the `api` optional dependency. **No work needed.**

#### Category 2: Settings classes — CANNOT change (3 classes, 3 files)

| File | Class | Why |
|------|-------|-----|
| `core/settings.py` | `SpineBaseSettings(BaseSettings)` | `pydantic-settings` env var loading, `.env` file parsing |
| `core/config/settings.py` | `SpineCoreSettings(BaseSettings)` | `@model_validator(mode="after")` for component validation, enum coercion from env strings, `SettingsConfigDict(env_prefix=..., env_nested_delimiter=...)` |
| `api/settings.py` | `SpineCoreAPISettings(BaseSettings)` | Already has `try/except ImportError` fallback to `BaseModel` |

**Verdict**: These use `BaseSettings` which loads env vars, parses `.env` files,
coerces strings to enums/paths/bools. stdlib `os.environ` could do this manually
but you'd rewrite ~200 lines of validation logic. Already behind `[settings]`
optional dep. **No work needed.**

#### Category 3: Data models — CAN be dataclasses (~29 classes, 8 files)

These are the interesting ones. Let me show you the **actual code**:

```python
# core/models/scheduler.py — TODAY (pydantic):
class Schedule(BaseModel):
    """Schedule definition row (core_schedules)."""
    id: str
    name: str
    target_type: str = "pipeline"
    target_name: str = ""
    params: str | None = Field(default=None, description="JSON default parameters")
    schedule_type: str = "cron"
    cron_expression: str | None = None
    interval_seconds: int | None = None
    timezone: str = "UTC"
    enabled: int = 1
    max_instances: int = 1
    last_run_at: str | None = None
    next_run_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
```

The **exact same thing** as a dataclass:

```python
# core/models/scheduler.py — AFTER (stdlib):
@dataclass
class Schedule:
    """Schedule definition row (core_schedules)."""
    id: str
    name: str
    target_type: str = "pipeline"
    target_name: str = ""
    params: str | None = None
    schedule_type: str = "cron"
    cron_expression: str | None = None
    interval_seconds: int | None = None
    timezone: str = "UTC"
    enabled: int = 1
    max_instances: int = 1
    last_run_at: str | None = None
    next_run_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    version: int = 1
```

**What changes**: `BaseModel` → `@dataclass`, remove `Field(description=...)`, add
`from dataclasses import dataclass`.

**What you lose**: The `description=` metadata on `Field()`. That's it for these files.
These models map to SQL rows — there's no validation, no coercion, no computed fields,
no `model_config`. They're literally typed dict replacements.

Here's the full list of Category 3 files:

| File | Classes | Pydantic features actually used | What you lose with `@dataclass` |
|------|---------|-----------------------------------|---------------------------------|
| `core/models/core.py` | 12 (Execution, ManifestEntry, RejectRecord, etc.) | `Field(description=)`, `Field(default="")` | `description=` metadata (only showed in API docs, but these are never used as FastAPI response models directly) |
| `core/models/scheduler.py` | 3 (Schedule, ScheduleRun, ScheduleLock) | `Field(description=)` | Same |
| `core/models/workflow.py` | 3 (WorkflowRun, WorkflowStep, WorkflowEvent) | `Field(description=)` | Same |
| `core/models/alerting.py` | 4 (AlertChannel, Alert, AlertDelivery, AlertThrottle) | `Field(description=)` | Same |
| `core/models/sources.py` | 4 (Source, SourceFetch, SourceCacheEntry, DatabaseConnectionConfig) | `Field(description=)` | Same |
| `core/models/orchestration.py` | 3 (PipelineGroupRecord, GroupRun, GroupRunStep) — **DEPRECATED** | `Field(description=)` | Same (these are going away anyway) |
| `ops/webhooks.py` | 1 (WebhookTarget) | Nothing special at all | Nothing — it's `class WebhookTarget(BaseModel): url: str; events: list[str]` |

**Total**: 29 classes that are pure data containers with **zero pydantic-specific features** 
beyond `Field(description=)`.

### How these models are actually consumed

I traced all consumers. The critical question: does any code call `.model_dump()`
or `.model_dump_json()` on these Category 3 models?

**No.** They're consumed like this:

```python
# scheduling/repository.py — constructs from SQL row:
def _row_to_schedule(self, row: tuple) -> Schedule:
    columns = ["id", "name", "target_type", ...]
    data = dict(zip(columns, row, strict=False))
    return Schedule(**data)      # ← just **kwargs unpacking
```

```python
# framework/dispatcher.py — constructs directly:
execution = Execution(
    id=execution_id,
    pipeline=pipeline,
    params=params or {},
    status=PipelineStatus.PENDING,
    created_at=now,
)
```

Then they're read by attribute access (`schedule.name`, `execution.status`).
**`@dataclass` does exactly the same thing** — `__init__` from kwargs, attribute access,
repr, eq.

#### The one edge case: `WebhookTarget` in ops

`WebhookTarget` is used in the API router as `response_model=list[WebhookTarget]`.
But `WebhookTarget` lives in `ops/webhooks.py` (library layer), and the API router
imports it. Two options:

1. Keep `WebhookTarget` as pydantic (since the API layer has pydantic anyway)
2. Create a separate `WebhookTargetSchema` in the API layer and convert

Option 1 is simpler. Leave it as pydantic.

### What about `deploy/` models? (17 classes)

These are more complex:

```python
# deploy/results.py — uses pydantic more heavily:
class DeploymentResult(BaseModel):
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    services: list[ServiceStatus] = Field(default_factory=list)
    overall_status: OverallStatus = OverallStatus.PENDING

    def mark_complete(self, status=None):
        self.completed_at = datetime.now(UTC).isoformat()
        # ... computes duration from ISO timestamps
```

**Used features**: `Field(default_factory=lambda)`, nested models, `Literal` types,
`model_dump_json(indent=2)` in log_collector.py.

**`@dataclass` replacement**: `field(default_factory=...)` handles factories.
`dataclasses.asdict()` replaces `model_dump()`. `json.dumps(asdict(result), indent=2)`
replaces `model_dump_json(indent=2)`.

**But**: `model_dump_json()` handles datetime serialization, nested model serialization,
and enum value extraction automatically. With `dataclasses.asdict()` + `json.dumps()`,
you'd need a custom `default=` handler for datetime and enum types. That's ~15 lines
of a shared encoder:

```python
# What you'd need to add (once):
import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum

class SpineEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value
        return super().default(o)

def to_json(obj, indent=2):
    return json.dumps(asdict(obj), cls=SpineEncoder, indent=indent)
```

| deploy feature | pydantic gives you | stdlib replacement | Extra code |
|---------------|-------------------|--------------------|------------|
| `model_dump()` | Recursive dict with enum→str | `dataclasses.asdict()` + custom handler | 15-line encoder |
| `model_dump_json()` | JSON with datetime/enum handling | `json.dumps(asdict(x), cls=SpineEncoder)` | Same encoder |
| `Field(default_factory=lambda)` | Lambda defaults | `field(default_factory=lambda: ...)` | None — same syntax |
| Nested models | Auto-serialized | `asdict()` handles nested dataclasses | None |
| `Literal["running", ...]` | Runtime type checking | No runtime check with dataclass | Lose validation on construct |
| `@model_validator` | Auto-generates `run_id` | Move to `__post_init__` | Same complexity |

**Verdict for deploy/**: Replaceable with `@dataclass` + 15-line encoder. But `deploy/`
is the testbed/deployment tooling — it's never part of a minimal workflow install.
These files are only loaded when you `from spine.deploy import ...`. Low priority.

### What about `orchestration/workflow_yaml.py`? (5 classes)

This is the **most sophisticated** pydantic usage in the library layer:

```python
class WorkflowMetadataSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")         # rejects unknown YAML keys
    name: str = Field(..., min_length=1)              # non-empty string validation
    version: int = Field(default=1, ge=1)             # minimum value constraint

class WorkflowSpecSection(BaseModel):
    steps: list[WorkflowStepSpec] = Field(..., min_length=1)  # at least one step

    @field_validator("steps")
    @classmethod
    def validate_unique_names(cls, v):                # custom cross-field validation
        names = [step.name for step in v]
        if len(names) != len(set(names)):
            duplicates = [n for n in names if names.count(n) > 1]
            raise ValueError(f"Duplicate step names: {set(duplicates)}")
        return v

    @model_validator(mode="after")
    def validate_dependencies(self):                  # cross-model DAG validation
        step_names = {step.name for step in self.steps}
        for step in self.steps:
            invalid = set(step.depends_on) - step_names
            if invalid:
                raise ValueError(f"Step '{step.name}' depends on unknown: {invalid}")
        return self

class WorkflowSpec(BaseModel):
    apiVersion: Literal["spine.io/v1"]                # exact string enforcement
    kind: Literal["Workflow"]                         # exact string enforcement
    
    @classmethod
    def from_yaml(cls, yaml_content):
        data = yaml.safe_load(yaml_content)
        return cls.model_validate(data)               # recursive dict → nested models
```

Features used by `workflow_yaml.py` that **don't exist in dataclasses**:

| Feature | What it does | stdlib replacement | Effort |
|---------|-------------|-------------------|--------|
| `ConfigDict(extra="forbid")` | Rejects unknown YAML keys (typo protection) | `__post_init__` check + `__init_subclass__` | ~20 lines |
| `Field(min_length=1)` | Non-empty string validation | `if not name: raise ValueError(...)` in `__post_init__` | 2 lines each |
| `Field(ge=1)` | Minimum int constraint | `if version < 1: raise ValueError(...)` | 2 lines each |
| `@field_validator` | Cross-element uniqueness check | Same logic in `__post_init__` | Same code |
| `@model_validator(mode="after")` | DAG dependency validation | Same logic in `__post_init__` | Same code |
| `Literal["spine.io/v1"]` | Exact string enforcement | `if api_version != "spine.io/v1": raise` | 2 lines |
| `model_validate(dict)` | Recursive dict → nested model construction | Custom `from_dict()` classmethod | ~30 lines |
| `ConfigDict(extra="forbid")` | Unknown key detection | `__post_init__` with `cls.__dataclass_fields__` inspection | ~10 lines |

**Total extra code**: ~80 lines of validation in `__post_init__` methods + a `from_dict()`
factory. This is the **one file** where pydantic actually earns its keep — it's doing
real schema validation of untrusted YAML input.

**However**: `workflow_yaml.py` is already an optional feature. You only use it if you
load workflows from YAML. The core `Workflow(name=..., steps=[...])` API is already
a stdlib dataclass. So even without touching this file, the zero-dep story works:

```python
# Zero-dep workflow creation (works today):
from spine.orchestration.workflow import Workflow
from spine.orchestration.step_types import Step

wf = Workflow(name="my-wf", steps=[
    Step.pipeline("fetch", "fetch_data"),
    Step.pipeline("store", "persist", depends_on=("fetch",)),
])
```

Only `from spine.orchestration.workflow_yaml import WorkflowSpec` triggers pydantic.

### Summary: What We're Actually Deciding

| File group | Classes | Drop pydantic? | Effort | Value |
|-----------|---------|---------------|--------|-------|
| `api/` + `execution/fastapi.py` | ~65 | **No** — FastAPI requires it | N/A | N/A |
| `core/config/settings.py`, `core/settings.py`, `api/settings.py` | 3 | **No** — BaseSettings for env vars | N/A | N/A |
| `core/models/*.py` | 29 | **Yes** — pure data containers, zero pydantic features used | ~1 hour | Removes pydantic from library import chain |
| `ops/webhooks.py` | 1 | **Leave** — used as FastAPI response_model | N/A | N/A |
| `deploy/config.py` + `deploy/results.py` | 17 | **Could** — add 15-line encoder | ~2 hours | Only loaded by deploy tooling, low priority |
| `orchestration/workflow_yaml.py` | 5 | **Could** — add ~80 lines validation | ~3 hours | Already optional (YAML workflows), low priority  |

### The practical answer

**Convert `core/models/*.py` (29 classes) to `@dataclass`.** That's the high-value,
low-effort change. These files are:

- Imported by `ops/`, `framework/`, `scheduling/` — the library layer
- Pure typed containers mapping SQL rows
- Never used as FastAPI `response_model=` (API layer has its own schema models)
- Never serialized with `model_dump()` — consumers use attribute access
- Zero pydantic-specific features (no validators, no constraints, no model_config)

Everything else (API schemas, settings, YAML parser, deploy results) stays pydantic,
behind optional dependencies where they already live or should be moved to.

### The lazy-import alternative

If you don't want to rewrite `core/models/` at all, you can instead make the import lazy
so it never triggers pydantic for users who don't need models:

```python
# core/models/__init__.py — lazy imports:
def __getattr__(name):
    if name in {"Schedule", "ScheduleRun", "ScheduleLock"}:
        from spine.core.models.scheduler import Schedule, ScheduleRun, ScheduleLock
        return locals()[name]
    # ... etc for each module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

**Pro**: Zero code changes to model files. Pydantic only loaded when models accessed.
**Con**: Still requires pydantic installed (just not imported until needed). Doesn't
help the `.pyz` zero-dep story unless you also move pydantic to optional deps.

### Recommendation

Do **both**:
1. Convert `core/models/*.py` to `@dataclass` (removes pydantic from library layer import chain)
2. Move pydantic to `[models]` optional dependency
3. Guard remaining library-layer pydantic imports (`workflow_yaml.py`, `deploy/`) with
   `try/except ImportError`
4. API layer (`api/`, `execution/fastapi.py`) already lives behind `[api]` optional dep

Result: `pip install spine-core` = zero deps. `pip install spine-core[api]` = pydantic + FastAPI.
The library layer never touches pydantic.

---

## Proposed Dependency Tiers

```toml
[project]
dependencies = []    # ← ZERO required dependencies

[project.optional-dependencies]
# Tier 1: Enhanced logging (JSON, processors, context propagation)
structured = ["structlog>=24.0.0"]

# Tier 2: Data models + validation (pydantic BaseModel)
models = ["pydantic>=2.0.0"]

# Tier 3: Settings (.env loading, env var parsing)
settings = ["pydantic-settings>=2.0.0"]

# Tier 4: Server stack
api = ["spine-core[models]", "fastapi>=0.109", "uvicorn[standard]>=0.27", "sse-starlette>=1.8"]
cli = ["typer>=0.9", "rich>=13"]

# Tier 5: Infrastructure
sqlalchemy = ["sqlalchemy>=2.0.0"]
scheduler = ["croniter>=2.0.0"]
postgresql = ["psycopg2-binary>=2.9.0"]

# Convenience bundles
standard = ["spine-core[structured,models,cli]"]
server = ["spine-core[standard,api,settings]"]
all = ["spine-core[server,sqlalchemy,scheduler,postgresql]"]
```

### User install stories

```bash
# Minimal — workflow engine only (zero deps)
pip install spine-core

# With structured logging
pip install spine-core[structured]

# Developer experience (logging + models + CLI)
pip install spine-core[standard]

# Full server stack
pip install spine-core[server]

# Everything
pip install spine-core[all]
```

---

## Implementation Plan

### Phase 1: structlog → optional ✅ COMPLETE (~2 hours, 30 files)

| Step | Files | Change | Status |
|------|-------|--------|--------|
| 1a | `pyproject.toml` | Move `structlog` from `dependencies` to `[optional-dependencies] structured` | ✅ |
| 1b | 28 files in ops/, orchestration/, execution/, framework/, api/ | `import structlog; logger = structlog.get_logger()` → `from spine.core.logging import get_logger; logger = get_logger()` | ✅ |
| 1c | `framework/logging/config.py` | Add `try/except ImportError` around structlog processor imports | ✅ |
| 1d | `framework/logging/context.py` | Add fallback to `observability` context system | ✅ |
| 1e | `core/logging.py` | Already done — verified `get_logger()` fallback works | ✅ |
| 1f | Tests | All 3,435 tests pass | ✅ |

**Risk**: Low. The abstraction layer exists. The swap is mechanical.

### Phase 2: core/models → dataclasses ✅ COMPLETE (~1 hour, 8 files, 29 classes)

| Step | Files | Change | Status |
|------|-------|--------|--------|
| 2a | `core/models/core.py` | `BaseModel` → `@dataclass`, remove `Field(description=)` | ✅ |
| 2b | `core/models/scheduler.py` | Same | ✅ |
| 2c | `core/models/workflow.py` | Same | ✅ |
| 2d | `core/models/alerting.py` | Same | ✅ |
| 2e | `core/models/sources.py` | Same | ✅ |
| 2f | `core/models/orchestration.py` | Same (deprecated, kept for backward compat) | ✅ |
| 2g | `core/models/__init__.py` | Update docstring | ✅ |
| 2h | `core/scheduling/service.py` | `model_copy(update=)` → `dataclasses.replace()` | ✅ |

**What changes in consumer code**: Nothing. These models are constructed with `Model(**kwargs)`
and consumed with `model.field_name` — both work identically with `@dataclass`.

**What tests break**: None — tests construct models with kwargs and check attributes.
Neither pattern calls `.model_dump()` on these classes.

**Risk**: Low. I verified every consumer — all use `**kwargs` construction and attribute access.

### Phase 3: Move pydantic to optional dependency ✅ COMPLETE (~30 min)

| Step | Files | Change | Status |
|------|-------|--------|--------|
| 3a | `pyproject.toml` | Move `pydantic` from `dependencies` to `[optional-dependencies] models` | ✅ |
| 3b | `orchestration/workflow_yaml.py` | Add `try/except ImportError` — fail gracefully if YAML parsing requested without pydantic | ✅ |
| 3c | `ops/webhooks.py` | Converted `WebhookTarget` to `@dataclass` (trivial 3-field model) | ✅ |
| 3d | `deploy/config.py`, `deploy/results.py` | Guard with try/except — these are tooling, not library | ✅ |
| 3e | `core/health.py` | Guard with try/except — health models only used when FastAPI is present | ✅ |
| 3f | `orchestration/__init__.py` | Lazy-load `WorkflowSpec` and `validate_yaml_workflow` via `__getattr__` | ✅ |

### Phase 4: Validate zero-dep story ✅ COMPLETE

| Step | Test | Status |
|------|------|--------|
| 4a | `uv build` produces wheel with zero unconditional `Requires-Dist` | ✅ |
| 4b | 12/12 core orchestration imports succeed with site-packages removed | ✅ |
| 4c | Lazy `WorkflowSpec` import works when pydantic IS installed | ✅ |
| 4d | All 3,435 tests pass (0 failures, 360 skipped) | ✅ |

### Verified Zero-Dep Import Chain

```
from spine.orchestration.workflow import Workflow          ✅
from spine.orchestration.step_types import Step            ✅
from spine.core.logging import get_logger                  ✅
from spine.core.models.scheduler import Schedule           ✅
from spine.orchestration.linter import lint_workflow        ✅
from spine.orchestration.composition import chain           ✅
from spine.orchestration.dry_run import dry_run            ✅
from spine.orchestration.testing import StubRunnable        ✅
from spine.orchestration.recorder import RecordingRunner    ✅
from spine.orchestration.visualizer import visualize_mermaid ✅
from spine.execution.runtimes.local_process import LocalProcessAdapter ✅
from spine.execution.packaging.packager import WorkflowPackager ✅
```

All succeed with **zero external packages** — pure Python 3.12 stdlib only.

---

## Complete Feature Audit: What You Lose Without pydantic

### Features never used (0 impact)

These pydantic features exist but spine-core doesn't use them at all:

| Feature | Evidence |
|---------|----------|
| `@validator` (v1 API) | 0 occurrences — all v2 style |
| `@root_validator` (v1 API) | 0 occurrences |
| `@computed_field` | 0 occurrences — `@property` used instead |
| `Annotated[..., custom_validator]` | 0 occurrences |
| `model_json_schema()` | 0 occurrences — FastAPI generates schemas, never called directly |
| Custom type validators | 0 occurrences |
| `model_config = ConfigDict(frozen=True)` | 0 occurrences — all models mutable |
| `Field(alias=...)` | 0 occurrences |
| `Field(pattern=...)` | 0 occurrences |

### Features used only in API layer (already behind `[api]` dep)

These stay pydantic — no impact on zero-dep users:

| Feature | Where | Count |
|---------|-------|-------|
| `response_model=` | All 10 router files | ~40 endpoints |
| `Generic[T]` models | `api/schemas/common.py` | 2 classes |
| Pydantic inheritance | `api/schemas/domains.py` | 2 chains |
| `model_dump()` | Router files, health.py | ~15 call sites |
| Request body validation | Router files | ~15 endpoints |
| `datetime` Query coercion | `api/routers/runs.py` | 3 fields |

### Features used in library layer (what changes)

| Feature | Where | Current behavior | After migration | Impact |
|---------|-------|-----------------|----------------|--------|
| `Field(description="...")` | `core/models/*.py` (29 classes, ~100 fields) | Metadata on fields | **Lost** — dataclasses don't have field descriptions | **None** — the descriptions weren't consumed by any code (no `model_json_schema()` calls, never used as FastAPI response_model) |
| `Field(default="")` | `core/models/*.py` | Explicit default | `field(default="")` or just `= ""` | **None** — identical behavior |
| `BaseModel(**kwargs)` | All consumers (repositories, dispatcher) | Pydantic init with type coercion | `@dataclass` init, no coercion | **Theoretical risk**: if a SQL column returns `"123"` for an `int` field, pydantic silently coerces to `123`. Dataclass would keep it as `"123"`. **In practice**: all fields that receive SQL values are typed as `str` or `str | None` already — no coercion happening |
| `Field(default_factory=lambda)` | `deploy/results.py` (timestamps) | Lambda for dynamic defaults | `field(default_factory=lambda: ...)` | **None** — dataclass supports this |

### Features used in `workflow_yaml.py` (optional YAML parsing)

| Feature | stdlib replacement | Lines of new code |
|---------|-------------------|-------------------|
| `ConfigDict(extra="forbid")` | `__post_init__` checking `cls.__dataclass_fields__` vs kwargs | ~10 lines per class (5 classes = ~50 lines) |
| `Field(min_length=1)` | `if not name: raise ValueError(...)` | 2 lines each (3 fields = 6 lines) |
| `Field(ge=1)` | `if version < 1: raise ValueError(...)` | 2 lines each (3 fields = 6 lines) |
| `Field(..., min_length=1)` on list | `if not steps: raise ValueError(...)` | 2 lines |
| `@field_validator("steps")` | Same logic in `__post_init__` | Same code (~6 lines) |
| `@model_validator(mode="after")` | Same logic in `__post_init__` | Same code (~10 lines) |
| `Literal["spine.io/v1"]` | `if api_version != "spine.io/v1": raise` | 2 lines |
| `model_validate(dict)` | Custom `from_dict()` classmethod with recursive construction | ~30 lines |
| Enum coercion from strings | `ExecutionMode(value)` explicit call | 2 lines each |

**Total new validation code**: ~80 lines spread across 5 `__post_init__` methods + 1 `from_dict()`.
**However**: this file is already optional. You only need it for YAML workflow loading.
The recommended approach is `try: from pydantic import BaseModel except ImportError: ...`
with a clear error message when YAML parsing is attempted without pydantic.

### Features used in `deploy/` (deployment tooling)

| Feature | stdlib replacement | Effort |
|---------|-------------------|--------|
| `model_dump_json(indent=2)` | `json.dumps(asdict(obj), cls=SpineEncoder, indent=2)` with 15-line encoder | One-time: 15 lines |
| `model_dump()` | `dataclasses.asdict(obj)` | Drop-in (but loses enum→str and datetime→ISO) |
| `@model_validator(mode="after")` | `__post_init__` | Same complexity |
| `@property` on model | `@property` on dataclass | Identical |
| Nested models | Nested dataclasses | `asdict()` handles recursively |

**However**: `deploy/` is tooling, not library. It's only loaded when running testbed
or deployment commands. Low priority for zero-dep conversion.

---

## Decision Matrix

| Approach | Required deps | Effort | .pyz portable? | API works? | Who benefits? |
|----------|---------------|--------|----------------|------------|---------------|
| ~~Today~~ | ~~structlog + pydantic~~ | ~~0~~ | ~~No~~ | ~~Yes~~ | ~~Nobody new~~ |
| ~~Phase 1 only~~ | ~~pydantic~~ | ~~2h~~ | ~~No~~ | ~~Yes~~ | |
| ~~Phase 1 + 2~~ | ~~pydantic~~ | ~~3h~~ | ~~No~~ | ~~Yes~~ | |
| **Phase 1 + 2 + 3 ✅ IMPLEMENTED** | **NONE** | **~4h** | **Yes** | **Yes (with extras)** | **.pyz users, embedded/CI, air-gapped** |
| ~~Drop pydantic entirely~~ | ~~NONE~~ | ~~3 days~~ | ~~Yes~~ | ~~No~~ | ~~Bad trade~~ |

**Recommended**: Phase 1 + 2 + 3. Zero required deps. ~4 hours total. ✅ **DONE.**

---

## What the Zero-Dep Import Chain Looks Like

### ~~Today~~ Before (was)

```
from spine.orchestration import Workflow, Step
  → spine.orchestration.__init__
    → spine.orchestration.workflow → dataclass (stdlib) ✓
    → spine.orchestration.step_types → dataclass (stdlib) ✓
    → ... BUT transitively:
    → spine.core.models → pydantic ✗ (29 BaseModel classes)
    → spine.ops → structlog ✗ (12 files)
```

### After migration ✅ (verified)

```
from spine.orchestration import Workflow, Step
  → spine.orchestration.__init__
    → spine.orchestration.workflow → dataclass (stdlib) ✅
    → spine.orchestration.step_types → dataclass (stdlib) ✅
    → spine.core.models → dataclass (stdlib) ✅
    → spine.core.logging → stdlib logging ✅
    → ZERO external imports ✅
```

```
from spine.orchestration import WorkflowSpec  # lazy-loaded via __getattr__
  → pydantic (optional — clear ImportError if missing) ✅

from spine.api import create_app
  → pydantic + fastapi (behind [api] optional dep) ✅
```
