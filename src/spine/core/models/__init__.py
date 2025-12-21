"""Dataclass models for all spine-core schema tables.

Manifesto:
    Every SQL table in ``spine.core.schema/`` needs a typed Python
    representation for the ops layer, API responses, and cross-project
    data contracts.  Without shared models, each consumer invents its
    own dict shapes -- leading to silent key mismatches and missing fields.

    All models use :func:`dataclasses.dataclass` (stdlib, zero external
    dependencies).  Field names match SQL column names exactly so
    ``Model(**row._asdict())`` works directly from query results.

Modules
-------
core
    Tables from ``00_core.sql`` -- executions, manifest, rejects, quality,
    anomalies, work items, dead letters, concurrency locks, calc deps,
    expected schedules, data readiness.
workflow
    Tables from ``02_workflow_history.sql`` -- workflow runs, steps, events.
scheduler
    Tables from ``03_scheduler.sql`` -- schedules, schedule runs, locks.
alerting
    Tables from ``04_alerting.sql`` -- alert channels, alerts, deliveries, throttle.
sources
    Tables from ``05_sources.sql`` -- sources, fetches, cache, DB connections.

Tags:
    spine-core, models, dataclasses, stdlib, schema-mapping,
    zero-dependency, data-contracts

Doc-Types:
    package-overview, module-index
"""

# 00_core.sql models
# 04_alerting.sql models
from spine.core.models.alerting import (
    Alert,
    AlertChannel,
    AlertDelivery,
    AlertThrottle,
)
from spine.core.models.core import (
    AnomalyRecord,
    CalcDependency,
    ConcurrencyLock,
    DataReadiness,
    DeadLetter,
    Execution,
    ExecutionEvent,
    ExpectedSchedule,
    ManifestEntry,
    MigrationRecord,
    QualityRecord,
    RejectRecord,
    WorkItem,
)

# 03_scheduler.sql models
from spine.core.models.scheduler import (
    Schedule,
    ScheduleLock,
    ScheduleRun,
)

# 05_sources.sql models
from spine.core.models.sources import (
    DatabaseConnectionConfig,
    Source,
    SourceCacheEntry,
    SourceFetch,
)

# 02_workflow_history.sql models
from spine.core.models.workflow import (
    WorkflowEvent,
    WorkflowRun,
    WorkflowStep,
)

__all__ = [
    # core (00)
    "MigrationRecord",
    "Execution",
    "ExecutionEvent",
    "ManifestEntry",
    "RejectRecord",
    "QualityRecord",
    "AnomalyRecord",
    "WorkItem",
    "DeadLetter",
    "ConcurrencyLock",
    "CalcDependency",
    "ExpectedSchedule",
    "DataReadiness",
    # workflow (02)
    "WorkflowRun",
    "WorkflowStep",
    "WorkflowEvent",
    # scheduler (03)
    "Schedule",
    "ScheduleRun",
    "ScheduleLock",
    # alerting (04)
    "AlertChannel",
    "Alert",
    "AlertDelivery",
    "AlertThrottle",
    # sources (05)
    "Source",
    "SourceFetch",
    "SourceCacheEntry",
    "DatabaseConnectionConfig",
]
