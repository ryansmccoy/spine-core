"""Spine Core -- Reusable, domain-agnostic platform primitives.

Manifesto:
    Every spine project (feedspine, entityspine, capture-spine, market-spine)
    needs the same foundational capabilities: database connections, structured
    errors, idempotent processing, quality checks, manifest tracking, temporal
    primitives, and secrets management.  Without a shared core, each project
    reinvents these patterns -- with subtle incompatibilities that surface as
    production bugs.

    ``spine.core`` is the **zero-dependency-on-other-spines** foundation layer.
    All 36+ root modules use synchronous APIs and stdlib types so they compose
    cleanly into any async or sync application.

    - **Sync-only primitives:** Higher tiers wrap async drivers, core stays simple
    - **Schema ownership:** Core infrastructure tables defined once, shared by all
    - **Protocol-first:** Connection, Dialect, CacheBackend are protocols, not classes
    - **Import-guarded extras:** asyncpg, SQLAlchemy, Redis loaded lazily

Architecture::

    Layer 1 -- Type System & Errors
        errors.py          Structured error hierarchy (SpineError, TransientError)
        result.py          Result[T] envelope (Ok / Err / try_result)
        enums.py           Shared domain enums (RunStatus, EventType, etc.)
        protocols.py       Canonical protocols (Connection, Dialect, etc.)
        timestamps.py      ULID generation + UTC helpers (stdlib-only)

    Layer 2 -- Database & Storage
        storage.py         DB-agnostic storage protocol (sync-only)
        dialect.py         SQL dialect abstraction (5 backends)
        connection.py      Connection factory (create_connection)
        repository.py      BaseRepository with dialect-aware helpers
        repositories.py    Domain repositories (10 aggregates)
        database.py        Async PostgreSQL connection pool (asyncpg)
        adapters/          Database adapters (SQLite -> Oracle, 5 backends)
        schema/            SQL DDL files (core tables + per-backend)
        schema.py          DDL registry + create_core_tables()
        orm/               Optional SQLAlchemy 2.0 ORM layer
        migrations/        SQL migration runner (_migrations table)

    Layer 3 -- Operation Primitives
        execution.py       ExecutionContext for lineage tracking
        hashing.py         Deterministic record hashing (dedup)
        idempotency.py     Skip/force checks, delete+insert helpers
        manifest.py        WorkManifest for multi-stage workflows
        rejects.py         Reject sink for validation failures
        quality.py         Quality check framework + gates
        anomalies.py       Anomaly/error recording
        backfill.py        Backfill planning for gap-filling
        watermarks.py      Cursor-based incremental processing
        rolling.py         Rolling window time-series aggregates
        retention.py       Data purge by retention period

    Layer 4 -- Domain Models
        temporal.py          WeekEnding + date range utilities
        temporal_envelope.py 4-timestamp bi-temporal records
        finance/             Adjustment chains + correction taxonomy
        models/              Dataclass models for all schema tables
        taggable.py          Multi-dimensional tagging mixin
        versioned_content.py Immutable content version history
        assets.py            Dagster-inspired data artifact tracking

    Layer 5 -- Cross-Cutting Concerns
        logging.py         Structured logging (structlog / stdlib fallback)
        cache.py           CacheBackend with InMemory + Redis
        secrets.py         Multi-backend secret resolution
        feature_flags.py   Runtime feature toggling with env overrides
        settings.py        SpineBaseSettings base class
        health.py          Health check router + response models
        health_checks.py   Dependency health callables (Postgres, Redis, etc.)
        events/            EventBus protocol + InMemory / Redis backends
        transports/        MCP server scaffold for AI tooling

    Layer 6 -- Infrastructure Services
        scheduling/        Production cron scheduler (3 backends)
        config/            Centralized settings + DI container + profiles

Module Map (recommended reading order)
--------------------------------------
**Type System & Errors (start here)**
  errors            Structured error hierarchy with categories
  result            Result[T] monad for explicit success/failure
  enums             Shared domain enums across all spines
  protocols         Canonical protocols (Connection, Dialect, etc.)
  timestamps        ULID generation + UTC timestamp helpers

**Database & Storage**
  storage           DB-agnostic storage protocol (sync-only)
  dialect           SQL dialect abstraction (SQLite -> Oracle)
  connection        Connection factory from URL strings
  repository        BaseRepository with portable SQL helpers
  repositories      Domain-specific repositories (10 aggregates)
  database          Async PostgreSQL pool (requires asyncpg)
  schema            Core infrastructure DDL registry
  schema_loader     SQL file application utilities

**Operation Primitives**
  execution         ExecutionContext for lineage + tracing
  hashing           Deterministic content hashing for dedup
  idempotency       Skip/force checks for restartable operations
  manifest          WorkManifest for multi-stage tracking
  rejects           Reject sink with audit trail
  quality           Composable quality check framework
  anomalies         Anomaly/warning recording
  backfill          Backfill planning for gap-filling
  watermarks        Cursor-based incremental processing
  rolling           Rolling window time-series aggregates
  retention         Data purge by configurable retention period

**Domain Models**
  temporal          WeekEnding + date range primitives
  temporal_envelope 4-timestamp bi-temporal records
  taggable          Multi-dimensional tagging mixin
  versioned_content Immutable content version history
  assets            Dagster-inspired data artifact tracking

**Cross-Cutting Concerns**
  logging           Structured logging (structlog / stdlib fallback)
  cache             CacheBackend with InMemory + Redis
  secrets           Multi-backend secret resolution
  feature_flags     Runtime feature toggling with env overrides
  settings          SpineBaseSettings base class
  health            Health check router + response models
  health_checks     Dependency health callables (Postgres, Redis, etc.)

**Infrastructure Services**
  scheduling/       Production cron scheduler (3 backends)
  config/           Centralized settings + DI container + profiles

Tags:
    spine-core, foundation, platform-primitives, zero-dependency,
    sync-only, protocol-first, domain-agnostic

Doc-Types:
    package-overview, architecture-map, module-index
"""

# Dataclass models for all schema tables (always available)
import spine.core.models as models  # noqa: F401  — exposes spine.core.models.*
from spine.core.anomalies import (
    AnomalyCategory,
    AnomalyRecorder,
    Severity,
)

# Asset tracking (Dagster-inspired data artifact tracking)
from spine.core.assets import (
    AssetDefinition,
    AssetKey,
    AssetMaterialization,
    AssetObservation,
    AssetRegistry,
    FreshnessPolicy,
    MaterializationStatus,
    get_asset_registry,
    register_asset,
    reset_asset_registry,
)

# Backfill planning with checkpoint resume
from spine.core.backfill import BackfillPlan, BackfillReason, BackfillStatus

# Caching abstraction (NEW)
from spine.core.cache import (
    CacheBackend,
    InMemoryCache,
    RedisCache,
)

# Connection factory (NEW)
from spine.core.connection import ConnectionInfo, create_connection

# Database portability
from spine.core.dialect import (
    DB2Dialect,
    Dialect,
    MySQLDialect,
    OracleDialect,
    PostgreSQLDialect,
    SQLiteDialect,
    get_dialect,
    register_dialect,
)

# Shared enums (used by multiple spines)
from spine.core.enums import (
    CaseStatus,
    CaseType,
    DataQualitySeverity,
    DecisionType,
    EventStatus,
    EventType,
    ProvenanceKind,
    RunStatus,
    VendorNamespace,
)

# New modules
from spine.core.errors import (
    ConfigError,
    ErrorCategory,
    SourceError,
    SpineError,
    TransientError,
    ValidationError,
    is_retryable,
)
from spine.core.execution import ExecutionContext, new_batch_id, new_context

# Feature flags (NEW)
from spine.core.feature_flags import (
    ENV_PREFIX,
    FeatureFlags,
    FlagDefinition,
    FlagNotFoundError,
    FlagRegistry,
    FlagType,
    feature_flag,
)

# Financial primitives (adjustments, corrections)
from spine.core.finance import (
    AdjustmentChain,
    AdjustmentFactor,
    AdjustmentMethod,
    CorrectionReason,
    CorrectionRecord,
)
from spine.core.hashing import compute_hash, compute_record_hash
from spine.core.idempotency import IdempotencyHelper, IdempotencyLevel
from spine.core.logging import (
    STRUCTLOG_AVAILABLE,
    LogContext,
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    unbind_context,
)
from spine.core.manifest import ManifestRow, WorkManifest

# Canonical protocol definitions
from spine.core.protocols import (
    AsyncConnection,
    Connection,
    DispatcherProtocol,
    ExecutorProtocol,
    OperationProtocol,
)
from spine.core.quality import (
    QualityCategory,
    QualityCheck,
    QualityResult,
    QualityRunner,
    QualityStatus,
)
from spine.core.rejects import Reject, RejectSink
from spine.core.repository import BaseRepository
from spine.core.result import Err, Ok, Result, try_result
from spine.core.rolling import RollingResult, RollingWindow
from spine.core.schema import CORE_DDL, CORE_TABLES, create_core_tables

# Secrets resolution (NEW)
from spine.core.secrets import (
    DictSecretBackend,
    EnvSecretBackend,
    FileSecretBackend,
    MissingSecretError,
    SecretBackend,
    SecretResolutionError,
    SecretsResolver,
    SecretValue,
    get_resolver,
    resolve_config_secrets,
    resolve_secret,
)

# Taggable content (stdlib-only domain mixin)
from spine.core.taggable import TaggableMixin, TagGroup, TagGroupSet
from spine.core.temporal import WeekEnding

# Temporal envelope & bi-temporal records
from spine.core.temporal_envelope import BiTemporalRecord, TemporalEnvelope

# Timestamp and ID utilities (stdlib-only)
from spine.core.timestamps import (
    from_iso8601,
    generate_ulid,
    to_iso8601,
    utc_now,
)

# Versioned content (stdlib-only domain models)
from spine.core.versioned_content import ContentVersion, VersionedContent

# Watermark tracking for incremental operations
from spine.core.watermarks import Watermark, WatermarkGap, WatermarkStore


# Database utilities (optional - requires asyncpg)
# Import lazily to avoid import errors when asyncpg not installed
def __getattr__(name):
    """Lazy import for optional modules.

    Optional dependencies (asyncpg, pydantic-settings, mcp, sqlalchemy) are
    imported lazily.  If the dependency is missing the ``ImportError`` is
    converted to ``AttributeError`` so that ``from spine.core import *``
    gracefully skips unavailable symbols instead of crashing.
    """
    # --- ORM (optional, requires sqlalchemy) ---
    if name == "orm":
        try:
            from spine.core import orm as _orm_mod

            return _orm_mod
        except ImportError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} "
                "(requires sqlalchemy — pip install spine-core[sqlalchemy])"
            ) from None
    if name == "SpineBase":
        try:
            from spine.core.orm.base import SpineBase

            return SpineBase
        except ImportError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} "
                "(requires sqlalchemy — pip install spine-core[sqlalchemy])"
            ) from None
    if name == "TimestampMixin":
        try:
            from spine.core.orm.base import TimestampMixin

            return TimestampMixin
        except ImportError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} "
                "(requires sqlalchemy — pip install spine-core[sqlalchemy])"
            ) from None
    if name in ("create_spine_engine", "SpineSession", "spine_session_factory", "SAConnectionBridge"):
        try:
            from spine.core.orm import session as _sess_mod

            return getattr(_sess_mod, name)
        except ImportError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} "
                "(requires sqlalchemy — pip install spine-core[sqlalchemy])"
            ) from None
    if name in ("create_pool", "close_pool", "pool_health_check", "normalize_database_url"):
        try:
            from spine.core import database

            return getattr(database, name)
        except ImportError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} (requires asyncpg — pip install spine-core[postgres])"
            ) from None
    if name == "SpineBaseSettings":
        try:
            from spine.core.settings import SpineBaseSettings

            return SpineBaseSettings
        except ImportError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} "
                "(requires pydantic-settings — pip install spine-core[settings])"
            ) from None
    if name in ("SpineHealth", "HealthResponse", "CheckResult", "LivenessResponse", "HealthCheck", "create_health_router"):
        try:
            from spine.core import health as _health_mod

            return getattr(_health_mod, name)
        except ImportError:
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    if name in ("check_postgres", "check_redis", "check_http", "check_elasticsearch", "check_qdrant", "check_ollama"):
        try:
            from spine.core import health_checks as _hc_mod

            return getattr(_hc_mod, name)
        except ImportError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} "
                "(requires httpx/asyncpg/redis — install appropriate extras)"
            ) from None
    if name in ("create_spine_mcp", "run_spine_mcp"):
        try:
            from spine.core.transports import mcp as _mcp_mod

            return getattr(_mcp_mod, name)
        except ImportError:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r} (requires mcp SDK — pip install spine-core[mcp])"
            ) from None
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # protocols (canonical definitions)
    "Connection",
    "AsyncConnection",
    "DispatcherProtocol",
    "OperationProtocol",
    "ExecutorProtocol",
    # schema
    "CORE_TABLES",
    "CORE_DDL",
    "create_core_tables",
    # connection factory (NEW)
    "create_connection",
    "ConnectionInfo",
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
    # anomalies (NEW)
    "AnomalyRecorder",
    "Severity",
    "AnomalyCategory",
    # cache (NEW)
    "CacheBackend",
    "InMemoryCache",
    "RedisCache",
    # dialect / database portability (NEW)
    "Dialect",
    "SQLiteDialect",
    "PostgreSQLDialect",
    "MySQLDialect",
    "DB2Dialect",
    "OracleDialect",
    "get_dialect",
    "register_dialect",
    "BaseRepository",
    # logging (NEW)
    "configure_logging",
    # timestamps (NEW)
    "generate_ulid",
    "utc_now",
    "to_iso8601",
    "from_iso8601",
    # taggable (SRP refactor)
    "TaggableMixin",
    "TagGroup",
    "TagGroupSet",
    # versioned content (SRP refactor)
    "ContentVersion",
    "VersionedContent",
    # finance primitives
    "AdjustmentChain",
    "AdjustmentFactor",
    "AdjustmentMethod",
    "CorrectionReason",
    "CorrectionRecord",
    # backfill (NEW)
    "BackfillPlan",
    "BackfillReason",
    "BackfillStatus",
    # temporal envelope (NEW)
    "BiTemporalRecord",
    "TemporalEnvelope",
    # watermarks (NEW)
    "Watermark",
    "WatermarkGap",
    "WatermarkStore",
    # feature flags (NEW)
    "FeatureFlags",
    "FlagDefinition",
    "FlagType",
    "FlagRegistry",
    "FlagNotFoundError",
    "feature_flag",
    "ENV_PREFIX",
    # secrets (NEW)
    "SecretBackend",
    "EnvSecretBackend",
    "FileSecretBackend",
    "DictSecretBackend",
    "SecretsResolver",
    "SecretValue",
    "MissingSecretError",
    "SecretResolutionError",
    "resolve_secret",
    "resolve_config_secrets",
    "get_resolver",
    # asset tracking
    "AssetKey",
    "AssetMaterialization",
    "AssetObservation",
    "AssetDefinition",
    "AssetRegistry",
    "FreshnessPolicy",
    "MaterializationStatus",
    "get_asset_registry",
    "register_asset",
    "reset_asset_registry",
    # shared enums (NEW)
    "VendorNamespace",
    "EventType",
    "EventStatus",
    "RunStatus",
    "DataQualitySeverity",
    "CaseType",
    "CaseStatus",
    "DecisionType",
    "ProvenanceKind",
    "get_logger",
    "bind_context",
    "unbind_context",
    "clear_context",
    "LogContext",
    "STRUCTLOG_AVAILABLE",
    # models package (always available — stdlib dataclasses)
    "models",
    # ---------- optional (available via explicit import, not ``import *``) ----------
    # "orm", "SpineBase", "TimestampMixin",  # sqlalchemy ORM layer
    # "create_spine_engine", "SpineSession", "spine_session_factory", "SAConnectionBridge",  # ORM session
    # "create_pool", "close_pool", "pool_health_check", "normalize_database_url",  # asyncpg
    # "SpineBaseSettings",  # pydantic-settings
    # "SpineHealth", "HealthResponse", "CheckResult", "LivenessResponse",  # health models
    # "HealthCheck", "create_health_router",  # health router factory (requires fastapi)
    # "check_postgres", "check_redis", "check_http",  # health_checks (requires httpx/asyncpg/redis)
    # "check_elasticsearch", "check_qdrant", "check_ollama",
    # "create_spine_mcp", "run_spine_mcp",  # mcp SDK
]
