"""
Spine Core - Reusable platform primitives.

SYNC-ONLY: All primitives use synchronous APIs. Higher tiers provide sync
adapters that wrap async drivers (asyncpg, etc.).

SCHEMA OWNERSHIP: Core infrastructure tables (manifest, rejects, quality)
are defined in spine.core.schema and shared by all domains.

These modules are domain-agnostic and can be composed by any domain:
- errors: Structured error types with categories (NEW)
- result: Result[T] envelope for success/failure (NEW)
- adapters: Database adapters (SQLite, PostgreSQL) (NEW)
- schema: Core infrastructure tables (core_manifest, core_rejects, core_quality)
- temporal: WeekEnding, date ranges, bucket utilities
- execution: ExecutionContext for lineage tracking
- hashing: Deterministic record hashing
- manifest: WorkManifest for multi-stage workflows
- idempotency: Skip/force checks, delete+insert helpers
- rejects: Reject sink for validation failures
- quality: Quality check framework
- rolling: Rolling window utilities
- storage: DB-agnostic connection protocol (sync-only)
"""

from spine.core.execution import ExecutionContext, new_batch_id, new_context
from spine.core.hashing import compute_hash, compute_record_hash
from spine.core.idempotency import IdempotencyHelper, IdempotencyLevel
from spine.core.manifest import ManifestRow, WorkManifest
from spine.core.quality import (
    QualityCategory,
    QualityCheck,
    QualityResult,
    QualityRunner,
    QualityStatus,
)
from spine.core.rejects import Reject, RejectSink
from spine.core.rolling import RollingResult, RollingWindow
from spine.core.schema import CORE_DDL, CORE_TABLES, create_core_tables
from spine.core.temporal import WeekEnding

# New modules
from spine.core.errors import (
    SpineError,
    TransientError,
    SourceError,
    ValidationError,
    ConfigError,
    ErrorCategory,
    is_retryable,
)
from spine.core.result import Result, Ok, Err, try_result

__all__ = [
    # schema
    "CORE_TABLES",
    "CORE_DDL",
    "create_core_tables",
    # temporal
    "WeekEnding",
    # execution
    "ExecutionContext",
    "new_context",
    "new_batch_id",
    # hashing
    "compute_hash",
    "compute_record_hash",
    # manifest
    "WorkManifest",
    "ManifestRow",
    # idempotency
    "IdempotencyHelper",
    "IdempotencyLevel",
    # rejects
    "Reject",
    "RejectSink",
    # quality
    "QualityRunner",
    "QualityCheck",
    "QualityStatus",
    "QualityCategory",
    "QualityResult",
    # rolling
    "RollingWindow",
    "RollingResult",
    # errors (NEW)
    "SpineError",
    "TransientError",
    "SourceError",
    "ValidationError",
    "ConfigError",
    "ErrorCategory",
    "is_retryable",
    # result (NEW)
    "Result",
    "Ok",
    "Err",
    "try_result",
]
