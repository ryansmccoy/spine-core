"""ORM table package — re-exports all table classes for backward compatibility.

Import from ``spine.core.orm.tables`` exactly as before::

    from spine.core.orm.tables import ExecutionTable, AlertTable

Tags:
    spine-core, orm, sqlalchemy, tables

Doc-Types:
    api-reference
"""

from spine.core.orm.tables.core import (  # noqa: F401
    AnomalyTable,
    CalcDependencyTable,
    ConcurrencyLockTable,
    DataReadinessTable,
    DeadLetterTable,
    ExecutionEventTable,
    ExecutionTable,
    ExpectedScheduleTable,
    ManifestTable,
    MigrationTable,
    QualityTable,
    RejectTable,
    WorkItemTable,
)
from spine.core.orm.tables.workflow import (  # noqa: F401
    WorkflowEventTable,
    WorkflowRunTable,
    WorkflowStepTable,
)
from spine.core.orm.tables.scheduling import (  # noqa: F401
    ScheduleLockTable,
    ScheduleRunTable,
    ScheduleTable,
)
from spine.core.orm.tables.alerts import (  # noqa: F401
    AlertChannelTable,
    AlertDeliveryTable,
    AlertTable,
    AlertThrottleTable,
)
from spine.core.orm.tables.sources import (  # noqa: F401
    DatabaseConnectionTable,
    SourceCacheTable,
    SourceFetchTable,
    SourceTable,
)

__all__ = [
    # core
    "MigrationTable",
    "ExecutionTable",
    "ExecutionEventTable",
    "ManifestTable",
    "RejectTable",
    "QualityTable",
    "AnomalyTable",
    "WorkItemTable",
    "DeadLetterTable",
    "ConcurrencyLockTable",
    "CalcDependencyTable",
    "ExpectedScheduleTable",
    "DataReadinessTable",
    # workflow
    "WorkflowRunTable",
    "WorkflowStepTable",
    "WorkflowEventTable",
    # scheduling
    "ScheduleTable",
    "ScheduleRunTable",
    "ScheduleLockTable",
    # alerting
    "AlertChannelTable",
    "AlertTable",
    "AlertDeliveryTable",
    "AlertThrottleTable",
    # sources
    "SourceTable",
    "SourceFetchTable",
    "SourceCacheTable",
    "DatabaseConnectionTable",
]
