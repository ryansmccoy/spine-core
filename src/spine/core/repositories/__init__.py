"""Repositories for spine-core domain tables.

Each repository class extends :class:`BaseRepository` and provides
typed, dialect-aware CRUD for a specific domain aggregate.  Operations
in ``spine.ops`` should use these repositories instead of
inline raw SQL.

Architecture::

    ┌────────────────────────────────────────────────────────────────┐
    │  ops/runs.py,  ops/processing.py,  ops/alerts.py  ...         │
    │  (operation functions — business orchestration)                │
    └────────────────────────────┬───────────────────────────────────┘
                                 │ uses
                                 ▼
    ┌────────────────────────────────────────────────────────────────┐
    │  spine.core.repositories  (this package)                      │
    │                                                               │
    │  execution.py   — ExecutionRepository                         │
    │  processing.py  — ManifestRepository, RejectRepository,       │
    │                   WorkItemRepository                          │
    │  alerts.py      — AlertRepository, AnomalyRepository          │
    │  system.py      — DeadLetterRepository, QualityRepository,    │
    │                   LockRepository, WorkflowRunRepository       │
    │  sources.py     — SourceRepository                            │
    │  scheduling.py  — ScheduleOpsRepository,                      │
    │                   CalcDependencyRepository,                   │
    │                   ExpectedScheduleRepository,                 │
    │                   DataReadinessRepository                     │
    │  _helpers.py    — PageSlice, _build_where                     │
    └────────────────────────────────────────────────────────────────┘

Backward Compatibility:
    All classes are re-exported here so existing imports like
    ``from spine.core.repositories import AlertRepository`` continue
    to work unchanged.

Tags:
    repository, sql, domain, refactoring, spine-core,
    data-access, crud, dialect-aware

Doc-Types:
    - API Reference
    - Architecture Documentation
    - Repository Pattern Guide
"""

from spine.core.repositories._helpers import PageSlice, _build_where
from spine.core.repositories.alerts import AlertRepository, AnomalyRepository
from spine.core.repositories.execution import ExecutionRepository
from spine.core.repositories.processing import (
    ManifestRepository,
    RejectRepository,
    WorkItemRepository,
)
from spine.core.repositories.scheduling import (
    CalcDependencyRepository,
    DataReadinessRepository,
    ExpectedScheduleRepository,
    ScheduleOpsRepository,
)
from spine.core.repositories.sources import SourceRepository
from spine.core.repositories.system import (
    DeadLetterRepository,
    LockRepository,
    QualityRepository,
    WorkflowRunRepository,
)

__all__ = [
    "PageSlice",
    "_build_where",
    "ExecutionRepository",
    "ManifestRepository",
    "RejectRepository",
    "WorkItemRepository",
    "AnomalyRepository",
    "AlertRepository",
    "DeadLetterRepository",
    "QualityRepository",
    "LockRepository",
    "WorkflowRunRepository",
    "SourceRepository",
    "ScheduleOpsRepository",
    "CalcDependencyRepository",
    "ExpectedScheduleRepository",
    "DataReadinessRepository",
]
