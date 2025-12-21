# ARCHITECTURE

**System Design and Structure**

> **Auto-generated from code annotations**  
> **Last Updated**: February 2026  
> **Status**: Living Document

---

## Table of Contents

1. [Core Primitives](#core-primitives)
   - [AnomalyCategory](#anomalycategory)
   - [AnomalyRecorder](#anomalyrecorder)
   - [Connection](#connection)
   - [Err](#err)
   - [ErrorCategory](#errorcategory)
   - [ErrorContext](#errorcontext)
   - [ExecutionContext](#executioncontext)
   - [IdempotencyHelper](#idempotencyhelper)
   - [IdempotencyLevel](#idempotencylevel)
   - [LogicalKey](#logicalkey)
   - [ManifestRow](#manifestrow)
   - [Ok](#ok)
   - [QualityRunner](#qualityrunner)
   - [Reject](#reject)
   - [RejectSink](#rejectsink)
   - [RollingResult](#rollingresult)
   - [RollingWindow](#rollingwindow)
   - [Severity](#severity)
   - [SpineError](#spineerror)
   - [StorageBackend](#storagebackend)
   - [TransientError](#transienterror)
   - [WeekEnding](#weekending)
   - [WorkManifest](#workmanifest)
2. [Execution Engine](#execution-engine)
   - [WorkerLoop](#workerloop)
3. [Orchestration](#orchestration)
4. [Deployment](#deployment)
5. [Tooling](#tooling)
   - [ChangelogGenerator](#changeloggenerator)

---

## Core Primitives

:

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

*Source: [`__init__.py`](spine-core/src/spine/core/__init__.py#L1)*

:

    DatabaseAdapter (base.py)        Abstract base with connect/execute/query
        |-- SQLiteAdapter            stdlib sqlite3 (always available)
        |-- PostgreSQLAdapter        psycopg2 (optional)
        |-- DB2Adapter               ibm_db_dbi (optional)
        |-- MySQLAdapter             mysql.connector (optional)
        |-- OracleAdapter            oracledb (optional)

    AdapterRegistry (registry.py)    Singleton: DatabaseType -> adapter class
    DatabaseConfig (types.py)        Pydantic config for connection parameters
    DatabaseType (types.py)          Enum of supported backends

Modules
-------
base            Abstract DatabaseAdapter base class
types           DatabaseType enum + DatabaseConfig model
registry        AdapterRegistry singleton + get_adapter() factory
sqlite          SQLite adapter (stdlib, always available)
postgresql      PostgreSQL adapter (requires psycopg2)
db2             IBM DB2 adapter (requires ibm-db)
mysql           MySQL / MariaDB adapter (requires mysql-connector-python)
oracle          Oracle adapter (requires oracledb)
database        Backward-compatible re-export shim

*Source: [`__init__.py`](spine-core/src/spine/core/adapters/__init__.py#L1)*

:

    settings.py       SpineCoreSettings (Pydantic) + get_settings() cache
    components.py     Backend enums + validate_component_combination()
    container.py      SpineContainer (lazy DI) + get_container()
    factory.py        create_database_engine / scheduler / cache / worker
    loader.py         .env file discovery + cascading load
    profiles.py       TOML profile inheritance (~/.spine/profiles/)

*Source: [`__init__.py`](spine-core/src/spine/core/config/__init__.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Anomaly Recording Flow                    │
        └─────────────────────────────────────────────────────────────┘

        Record Anomaly:
        ┌────────────────────────────────────────────────────────────┐
        │ recorder = AnomalyRecorder(conn, domain="finra.otc")       │
        │                                                            │
        │ anomaly_id = recorder.record(                              │
        │     stage="ingest",                                        │
        │     partition_key={"week_ending": "2025-12-26"},           │
        │     severity=Severity.ERROR,                               │
        │     category=AnomalyCategory.QUALITY_GATE,                 │
        │     message="Null rate 35% exceeds threshold 25%",         │
        │     metadata={"null_rate": 0.35}                           │
        │ )                                                          │
        └────────────────────────────────────────────────────────────┘

        Resolve Later:
        ┌────────────────────────────────────────────────────────────┐
        │ recorder.resolve(anomaly_id, "Fixed in re-run abc123")     │
        └────────────────────────────────────────────────────────────┘

        Storage (core_anomalies):
        ┌────────────────────────────────────────────────────────────┐
        │ id       | severity | category      | message | resolved   │
        │ abc123   | ERROR    | QUALITY_GATE  | "..."   | NULL      │
        │ def456   | WARN     | DATA_QUALITY  | "..."   | 2025-12-27│
        └────────────────────────────────────────────────────────────┘
```

*Source: [`anomalies.py`](spine-core/src/spine/core/anomalies.py#L1)*

```
::

        AssetKey("sec", "filings", "10-K")
              │
              ├── AssetMaterialization (data was produced)
              │     execution_id → links to operation run
              │     partition → "CIK:0001318605"
              │     metadata → {"count": 42}
              │
              └── AssetObservation (data was checked)
                    metadata → {"row_count": 42, "freshness_lag_hours": 2.5}
```

*Source: [`assets.py`](spine-core/src/spine/core/assets.py#L1)*

```
::

        ┌───────────────────────────────────────────────────────────┐
        │                  Backfill Lifecycle                        │
        └───────────────────────────────────────────────────────────┘

        WatermarkStore.list_gaps()
              │
              ▼
        BackfillPlan.create(domain, source, partition_keys, reason)
              │  status: PLANNED
              ▼
        plan.start()         → status: RUNNING
              │
              ├── plan.mark_partition_done("AAPL")   progress: 33%
              ├── plan.mark_partition_done("MSFT")   progress: 66%
              └── plan.mark_partition_done("GOOG")   progress: 100%
                    │
                    ▼
        status: COMPLETED (or FAILED if errors)
```

*Source: [`backfill.py`](spine-core/src/spine/core/backfill.py#L1)*

```
::

        CacheBackend (Protocol)
        ├── InMemoryCache  — Tier 1 (single-process, bounded LRU)
        └── RedisCache     — Tier 2/3 (distributed, persistent)

        API: get(key) → value | None
             set(key, value, ttl_seconds=None)
             delete(key)
             exists(key) → bool
             clear()
```

*Source: [`cache.py`](spine-core/src/spine/core/cache.py#L1)*

```
::

        create_connection(url) → (conn, ConnectionInfo)
              │
              ├── "memory" / None     → sqlite3 :memory:
              ├── "sqlite:///..."     → sqlite3 file
              ├── "./path.db"         → sqlite3 file
              └── "postgresql://..."  → psycopg2 connection
```

*Source: [`connection.py`](spine-core/src/spine/core/connection.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Connection Pool                          │
        └─────────────────────────────────────────────────────────────┘

        Pool Management:
        ┌────────────────────────────────────────────────────────────┐
        │ pool = await create_pool(database_url, min_size=5)         │
        │                                                             │
        │ async with pool.acquire() as conn:                          │
        │     result = await conn.fetch("SELECT * FROM users")        │
        │                                                             │
        │ await close_pool(pool)                                      │
        └────────────────────────────────────────────────────────────┘

        Pool State:
        ┌────────────────────────────────────────────────────────────┐
        │  ┌─────────┬─────────┬─────────┬─────────┬─────────┐       │
        │  │  conn1  │  conn2  │  conn3  │   ...   │  connN  │       │
        │  │  (idle) │ (in-use)│  (idle) │         │  (idle) │       │
        │  └─────────┴─────────┴─────────┴─────────┴─────────┘       │
        │  min_size=5 ───────────────────────────► max_size=20       │
        └────────────────────────────────────────────────────────────┘
```

*Source: [`database.py`](spine-core/src/spine/core/database.py#L1)*

```
:

    ┌──────────────────────────────────────────────────────────────────┐
    │                     Dialect Abstraction Layer                     │
    └──────────────────────────────────────────────────────────────────┘

    Domain Code:
    ┌────────────────────────────────────────────────────────────────┐
    │  sql = f"INSERT INTO t (a,b) VALUES ({d.placeholders(2)})"    │
    │  sql += f" WHERE ts > {d.now()}"                               │
    │  conn.execute(sql, params)                                     │
    └────────────────────────────────────────────────────────────────┘
                              │
                              ▼
    ┌──────────┐ ┌──────────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
    │ SQLite   │ │ PostgreSQL   │ │  DB2   │ │ MySQL  │ │  Oracle  │
    │ ?, ?, ?  │ │ %s, %s, %s   │ │ ?, ?, ?│ │ %s,%s  │ │ :1, :2   │
    │ datetime │ │ NOW()        │ │CURRENT │ │ NOW()  │ │SYSTIMEST │
    └──────────┘ └──────────────┘ └────────┘ └────────┘ └──────────┘
```

*Source: [`dialect.py`](spine-core/src/spine/core/dialect.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────────┐
        │                       SpineError                                 │
        │  (category, retryable, retry_after, context, cause)             │
        ├─────────────────────────────────────────────────────────────────┤
        │                                                                  │
        │  TransientError    SourceError       ValidationError            │
        │  (retryable=True)  (SOURCE)          (VALIDATION)               │
        │       │                │                   │                     │
        │  NetworkError      ParseError        SchemaError                │
        │  TimeoutError      SourceNotFound    ConstraintError            │
        │  RateLimitError    SourceUnavailable                            │
        │                                                                  │
        │  ConfigError       AuthError         OperationError              │
        │  (CONFIG)          (AUTH)            (operation)                 │
        │       │                │                   │                     │
        │  MissingConfig     Authentication    BadParamsError             │
        │  InvalidConfig     Authorization     OperationNotFound           │
        │                                                                  │
        │  StorageError      DatabaseError     OrchestrationError         │
        │  (STORAGE)         (DATABASE)        (ORCHESTRATION)            │
        │                         │                   │                    │
        │                    QueryError        WorkflowError              │
        │                    IntegrityError    ScheduleError              │
        └─────────────────────────────────────────────────────────────────┘
```

*Source: [`errors.py`](spine-core/src/spine/core/errors.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────────┐
        │                     ExecutionContext                             │
        ├─────────────────────────────────────────────────────────────────┤
        │  execution_id: str       ← Unique ID for this execution         │
        │  batch_id: str | None    ← Shared ID for related executions     │
        │  parent_execution_id: str | None  ← ID of spawning operation     │
        │  started_at: datetime    ← When execution began                 │
        ├─────────────────────────────────────────────────────────────────┤
        │                                                                  │
        │  Root Context            Child Context            Batch Context  │
        │  ────────────            ─────────────            ─────────────  │
        │  new_context()           ctx.child()              ctx.with_batch │
        │       │                       │                        │         │
        │       ▼                       ▼                        ▼         │
        │  execution_id: A         execution_id: B         execution_id: A │
        │  parent: None            parent: A               batch_id: X     │
        │  batch_id: X             batch_id: X             parent: None    │
        │                                                                  │
        └─────────────────────────────────────────────────────────────────┘
```

*Source: [`execution.py`](spine-core/src/spine/core/execution.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────────┐
        │                    Feature Flag System                          │
        └─────────────────────────────────────────────────────────────────┘

        Registration:
        ┌────────────────────────────────────────────────────────────────┐
        │ FeatureFlags.register("enable_new_parser", default=False)      │
        │ FeatureFlags.register("max_batch_size", default=100, type=int) │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ stored in
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │                    FlagRegistry (thread-safe)                   │
        │  ┌──────────────────────────────────────────────────────────┐  │
        │  │ flags: dict[str, FlagDefinition]                         │  │
        │  │ overrides: dict[str, Any]                                │  │
        │  └──────────────────────────────────────────────────────────┘  │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ resolved via
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │                    Resolution Order                             │
        │  1. Runtime override (FeatureFlags.set())                      │
        │  2. Environment variable (SPINE_FF_<NAME>)                     │
        │  3. Default value from registration                            │
        └────────────────────────────────────────────────────────────────┘
```

*Source: [`feature_flags.py`](spine-core/src/spine/core/feature_flags.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Hashing Patterns                          │
        └─────────────────────────────────────────────────────────────┘

        Natural Key Hash (L2_INPUT dedup):
        ┌────────────────────────────────────────────────────────────┐
        │ hash = compute_hash(week, tier, symbol, mpid)              │
        │                                                            │
        │ Same (week, tier, symbol, mpid) → Same hash               │
        │ Different values → Different hash                         │
        └────────────────────────────────────────────────────────────┘

        Content Hash (change detection):
        ┌────────────────────────────────────────────────────────────┐
        │ hash = compute_hash(week, tier, symbol, mpid, shares)     │
        │                                                            │
        │ Same record + same data → Same hash                       │
        │ Same record + different data → Different hash (UPDATE!)   │
        └────────────────────────────────────────────────────────────┘
```

*Source: [`hashing.py`](spine-core/src/spine/core/hashing.py#L1)*

```
::

        create_health_router(service_name, version, checks)
              │
              ├── GET /health/live  → LivenessResponse (always alive)
              ├── GET /health/ready → HealthResponse (checks run)
              └── GET /health       → HealthResponse (same as ready)

        HealthCheck("postgres", check_fn, required=True, timeout_s=5)
              │
              └── CheckResult(status="healthy", latency_ms=2.3)
```

*Source: [`health.py`](spine-core/src/spine/core/health.py#L1)*

```
::

        ┌───────────────────────────────────────────────────────────┐
        │                Idempotency Level Progression              │
        └───────────────────────────────────────────────────────────┘

        L1_APPEND (Raw)        L2_INPUT (Dedup)       L3_STATE (Derived)
        ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
        │ INSERT all  │   →    │ Hash check  │   →    │ DELETE key  │
        │ No checks   │        │ Skip if     │        │ INSERT new  │
        │             │        │ exists      │        │             │
        └─────────────┘        └─────────────┘        └─────────────┘
              ↓                      ↓                      ↓
        audit_log            bronze_otc_raw         silver_otc_volume

        L3_STATE Pattern (most common):
        ┌─────────────────────────────────────────────────────────┐
        │ BEGIN TRANSACTION                                        │
        │   DELETE FROM silver_otc WHERE week='2025-12-26'        │
        │                           AND tier='NMS_TIER_1'         │
        │   INSERT INTO silver_otc (week, tier, volume) VALUES... │
        │ COMMIT                                                   │
        └─────────────────────────────────────────────────────────┘
```

*Source: [`idempotency.py`](spine-core/src/spine/core/idempotency.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Logging Architecture                      │
        └─────────────────────────────────────────────────────────────┘

        Configuration Flow:
        ┌────────────────────────────────────────────────────────────┐
        │ configure_logging(level="INFO", json_format=True,          │
        │                   service="capture-spine")                 │
        │                                                             │
        │     ↓                                                       │
        │ structlog configured with processor chain:                  │
        │   1. add_timestamp                                          │
        │   2. add_log_level                                          │
        │   3. add_service_metadata                                   │
        │   4. elasticsearch_compatible                               │
        │   5. JSONRenderer (or ConsoleRenderer for dev)              │
        └────────────────────────────────────────────────────────────┘

        Usage Flow:
        ┌────────────────────────────────────────────────────────────┐
        │ logger = get_logger(__name__)                              │
        │ logger.info("event_happened", key="value", count=42)       │
        │                                                             │
        │ Output (JSON format):                                       │
        │ {                                                           │
        │   "@timestamp": "2025-12-26T10:00:00Z",                    │
        │   "log.level": "info",                                     │
        │   "service.name": "capture-spine",                         │
        │   "event": "event_happened",                               │
        │   "key": "value",                                          │
        │   "count": 42                                              │
        │ }                                                           │
        └────────────────────────────────────────────────────────────┘
```

*Source: [`logging.py`](spine-core/src/spine/core/logging.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    WorkManifest Architecture                 │
        └─────────────────────────────────────────────────────────────┘

        Stage Progression:
        ┌─────────────────────────────────────────────────────────────┐
        │                                                              │
        │  PENDING → INGESTED → NORMALIZED → AGGREGATED → PUBLISHED   │
        │    [0]        [1]         [2]          [3]          [4]     │
        │                                                              │
        │  Each stage has a rank for comparison (is_at_least)          │
        └─────────────────────────────────────────────────────────────┘

        Storage (core_manifest):
        ┌────────────────────────────────────────────────────────────┐
        │ domain | partition_key           | stage      | rank | ... │
        │ otc    | {"week_ending":"12-26"} | PENDING    | 0    | ... │
        │ otc    | {"week_ending":"12-26"} | INGESTED   | 1    | ... │
        │ otc    | {"week_ending":"12-26"} | NORMALIZED | 2    | ... │
        └────────────────────────────────────────────────────────────┘

        One row PER STAGE per partition (not one row per partition).

        API:
        ┌────────────────────────────────────────────────────────────┐
        │ advance_to(key, stage)  → UPSERT row for stage             │
        │ is_at_least(key, stage) → Check if rank >= target          │
        │ get(key)                → List all stages for partition    │
        └────────────────────────────────────────────────────────────┘
```

*Source: [`manifest.py`](spine-core/src/spine/core/manifest.py#L1)*

```
::

        protocols.py (YOU ARE HERE)
        ├── Connection          — sync DB protocol (sqlite3, psycopg2, etc.)
        ├── AsyncConnection     — async DB protocol (asyncpg, aiosqlite, etc.)
        ├── StorageBackend      — sync storage with connection + transaction mgmt
        ├── DispatcherProtocol  — event/task dispatch contract
        ├── OperationProtocol    — data operation contract
        └── ExecutorProtocol    — task executor contract

    Consumers:
        anomalies.py, idempotency.py, manifest.py, quality.py, rejects.py,
        storage.py, adapters/database.py, framework/db.py,
        orchestration/tracked_runner.py
```

*Source: [`protocols.py`](spine-core/src/spine/core/protocols.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Quality Framework                         │
        └─────────────────────────────────────────────────────────────┘

        QualityCheck Definition:
        ┌────────────────────────────────────────────────────────────┐
        │ check = QualityCheck(                                      │
        │     name="market_share_sum",                               │
        │     category=QualityCategory.BUSINESS_RULE,                │
        │     check_fn=lambda ctx: QualityResult(...)                │
        │ )                                                          │
        └────────────────────────────────────────────────────────────┘

        QualityRunner Execution:
        ┌────────────────────────────────────────────────────────────┐
        │ runner = QualityRunner(conn, domain="otc", exec_id="...")  │
        │ runner.add(check1).add(check2)                             │
        │ results = runner.run_all(context, partition_key)           │
        │                                                            │
        │ if runner.has_failures():                                  │
        │     raise QualityGateError(runner.failures())              │
        └────────────────────────────────────────────────────────────┘

        Storage (core_quality table):
        ┌────────────────────────────────────────────────────────────┐
        │ domain | partition_key | check_name | status | message    │
        │ "otc"  | {...}         | "sum_100"  | "PASS" | "Sum OK"   │
        │ "otc"  | {...}         | "no_neg"   | "FAIL" | "Found -5" │
        └────────────────────────────────────────────────────────────┘
```

*Source: [`quality.py`](spine-core/src/spine/core/quality.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Reject Flow Architecture                  │
        └─────────────────────────────────────────────────────────────┘

        Capture:
        ┌───────────────────────────────────────────────────────────┐
        │ sink = RejectSink(conn, domain="otc", execution_id="abc") │
        │                                                            │
        │ sink.write(Reject(                                         │
        │     stage="NORMALIZE",                                     │
        │     reason_code="INVALID_SYMBOL",                          │
        │     reason_detail="Symbol 'BAD$YM' contains $",            │
        │     raw_data={"symbol": "BAD$YM", "volume": 1000}          │
        │ ), partition_key={"week_ending": "2025-12-26"})            │
        └───────────────────────────────────────────────────────────┘

        Storage (core_rejects):
        ┌───────────────────────────────────────────────────────────┐
        │ domain | partition_key | stage     | reason_code    | ... │
        │ otc    | {"week":...}  | NORMALIZE | INVALID_SYMBOL | ... │
        │ otc    | {"week":...}  | INGEST    | NULL_FIELD     | ... │
        └───────────────────────────────────────────────────────────┘

        Analysis (later):
        ┌───────────────────────────────────────────────────────────┐
        │ SELECT reason_code, COUNT(*) FROM core_rejects            │
        │ WHERE domain='otc' GROUP BY reason_code                   │
        │                                                            │
        │ reason_code      | count                                   │
        │ INVALID_SYMBOL   | 42                                      │
        │ NEGATIVE_VOLUME  | 7                                       │
        └───────────────────────────────────────────────────────────┘
```

*Source: [`rejects.py`](spine-core/src/spine/core/rejects.py#L1)*

```
:

    ┌───────────────────────────────────────────────────────────────────┐
    │  ops/runs.py,  ops/processing.py,  ops/alerts.py  ...            │
    │  (operation functions — business orchestration)                   │
    └──────────────────────────┬────────────────────────────────────────┘
                               │ uses
                               ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │  repositories.py                                                  │
    │                                                                   │
    │  ExecutionRepository    — core_executions + core_execution_events │
    │  ManifestRepository     — core_manifest                           │
    │  RejectRepository       — core_rejects                            │
    │  WorkItemRepository     — core_work_items                         │
    │  AnomalyRepository      — core_anomalies                         │
    │  AlertRepository        — core_alerts + channels + deliveries     │
    │  DeadLetterRepository   — core_dead_letters                       │
    │  QualityRepository      — core_quality                            │
    │  WorkflowRepository     — core_workflow_runs/steps/events         │
    │  SourceRepository       — core_sources + fetches + cache          │
    └──────────────────────────┬────────────────────────────────────────┘
                               │ inherits
                               ▼
    ┌───────────────────────────────────────────────────────────────────┐
    │  BaseRepository  (spine.core.repository)                          │
    │   .execute()  .query()  .insert()  .ph()  .commit()               │
    └───────────────────────────────────────────────────────────────────┘
```

*Source: [`repositories.py`](spine-core/src/spine/core/repositories.py#L1)*

```
:

    ┌────────────────────────────────────────────────────────────────────┐
    │                       BaseRepository                               │
    │                                                                    │
    │   conn: Connection        ← protocol from spine.core.protocols     │
    │   dialect: Dialect         ← from spine.core.dialect                │
    │                                                                    │
    │   execute(sql, params)     → cursor                                │
    │   query(sql, params)       → list[dict]                            │
    │   query_one(sql, params)   → dict | None                           │
    │   insert(table, data)      → cursor                                │
    │   insert_many(table, rows) → int                                   │
    └────────────────────────────────────────────────────────────────────┘
```

*Source: [`repository.py`](spine-core/src/spine/core/repository.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                     Result[T]                                │
        │                    (Type Alias)                              │
        ├─────────────────┬─────────────────┬─────────────────────────┤
        │     Ok[T]       │     Err[T]      │     Utilities           │
        │   (Success)     │   (Failure)     │                         │
        ├─────────────────┼─────────────────┼─────────────────────────┤
        │ • value: T      │ • error: Exc    │ • try_result()          │
        │ • map()         │ • map_err()     │ • collect_results()     │
        │ • flat_map()    │ • or_else()     │ • partition_results()   │
        │ • unwrap()      │ • unwrap_or()   │ • from_optional()       │
        └─────────────────┴─────────────────┴─────────────────────────┘
```

*Source: [`result.py`](spine-core/src/spine/core/result.py#L1)*

```
::

        ┌──────────────────────────────────────────────────────────┐
        │                Retention Pipeline                         │
        └──────────────────────────────────────────────────────────┘

        RetentionConfig                purge_all(conn, config)
        ┌────────────────┐                    │
        │ executions: 90 │     ┌──────────────┼──────────────┐
        │ rejects: 30    │     ▼              ▼              ▼
        │ quality: 90    │  purge_table()  purge_table()  purge_table()
        │ anomalies: 180 │     │              │              │
        │ work_items: 30 │     ▼              ▼              ▼
        └────────────────┘  PurgeResult    PurgeResult    PurgeResult
                                    \         │         /
                                     ▼        ▼        ▼
                                   RetentionReport
```

*Source: [`retention.py`](spine-core/src/spine/core/retention.py#L1)*

```
::

        ┌────────────────────────────────────────────────────────────┐
        │                    RollingWindow Pattern                    │
        └────────────────────────────────────────────────────────────┘

        Input: as_of=WeekEnding("2025-12-26"), size=6

        ┌─────┬─────┬─────┬─────┬─────┬─────┐
        │11/21│11/28│12/05│12/12│12/19│12/26│  ← window periods
        └─────┴─────┴─────┴─────┴─────┴─────┘
              │     │     │     │     │
              ▼     ▼     ▼     ▼     ▼
            fetch_fn(period) → value or None
              │     │     │     │     │
              └──────────┬──────────────┘
                         │
                    aggregate_fn([(period, value), ...])
                         │
                         ▼
                   RollingResult
                    • aggregates: {avg: 1000, max: 1500}
                    • periods_present: 5
                    • periods_total: 6
                    • is_complete: False
```

*Source: [`rolling.py`](spine-core/src/spine/core/rolling.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                  Core Infrastructure Schema                  │
        └─────────────────────────────────────────────────────────────┘

        Table Registry (CORE_TABLES):
        ┌────────────────────────────────────────────────────────────┐
        │ manifest         → core_manifest                           │
        │ rejects          → core_rejects                            │
        │ quality          → core_quality                            │
        │ anomalies        → core_anomalies                          │
        │ executions       → core_executions                         │
        │ execution_events → core_execution_events                   │
        │ dead_letters     → core_dead_letters                       │
        │ concurrency_locks→ core_concurrency_locks                  │
        └────────────────────────────────────────────────────────────┘

        Partitioning:
        ┌────────────────────────────────────────────────────────────┐
        │ All tables have 'domain' column for partitioning:          │
        │                                                             │
        │ SELECT * FROM core_manifest WHERE domain = 'otc'           │
        │ SELECT * FROM core_rejects  WHERE domain = 'equity'        │
        │                                                             │
        │ Domains: otc, equity, options, finra.*, etc.               │
        └────────────────────────────────────────────────────────────┘

        Key-Value Pattern:
        ┌────────────────────────────────────────────────────────────┐
        │ partition_key is JSON for flexible logical keys:           │
        │                                                             │
        │ {"week_ending": "2025-12-26", "tier": "NMS_TIER_1"}        │
        │ {"date": "2025-12-26", "symbol": "AAPL"}                   │
        │                                                             │
        │ Enables arbitrary key combinations per domain.              │
        └────────────────────────────────────────────────────────────┘
```

*Source: [`schema.py`](spine-core/src/spine/core/schema.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────────┐
        │                    Secrets Resolution                           │
        └─────────────────────────────────────────────────────────────────┘

        Configuration Reference:
        ┌────────────────────────────────────────────────────────────────┐
        │ database:                                                       │
        │   password: "secret:env:DB_PASSWORD"     # Environment var     │
        │   api_key: "secret:file:/run/secrets/key" # File-based secret │
        │   token: "secret:vault:db/creds/prod"    # HashiCorp Vault    │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ resolved by
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │                   SecretsResolver                               │
        │  ┌──────────────────────────────────────────────────────────┐  │
        │  │ backends: list[SecretBackend]                            │  │
        │  │   - EnvSecretBackend (SPINE_SECRET_*)                    │  │
        │  │   - FileSecretBackend (/run/secrets/)                    │  │
        │  │   - VaultSecretBackend (optional)                        │  │
        │  │   - AWSSecretBackend (optional)                          │  │
        │  └──────────────────────────────────────────────────────────┘  │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ returns
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │                    Resolved Secret Value                        │
        │  "actual_password_value"                                       │
        └────────────────────────────────────────────────────────────────┘
```

*Source: [`secrets.py`](spine-core/src/spine/core/secrets.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    Storage Protocol Stack                    │
        └─────────────────────────────────────────────────────────────┘

        Domain Code (SYNC):
        ┌────────────────────────────────────────────────────────────┐
        │ def process(conn: Connection):                             │
        │     conn.execute("INSERT INTO ...", (values,))             │
        │     conn.commit()                                          │
        └────────────────────────────────────────────────────────────┘
                              │
                              │ uses Protocol
                              ▼
        ┌────────────────────────────────────────────────────────────┐
        │              Connection Protocol (SYNC)                     │
        │  execute() | executemany() | fetchone() | fetchall() | ... │
        └────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
        ┌───────────▼────────┐  ┌──────▼──────────────┐
        │ Basic Tier:        │  │ Intermediate+:       │
        │ sqlite3.Connection │  │ SyncPgAdapter       │
        │ (native sync)      │  │ (wraps asyncpg)     │
        └────────────────────┘  └─────────────────────┘
```

*Source: [`storage.py`](spine-core/src/spine/core/storage.py#L1)*

```
::

        TagGroupSet
        ├── TagGroup("tickers", ["AAPL", "MSFT"])
        ├── TagGroup("sectors", ["Technology"])
        ├── TagGroup("event_types", ["earnings"])
        └── TagGroup("sentiment", ["positive"])

        Taggable Protocol → TaggableContent Mixin
              │
              └── Any content class can gain tagging via mixin
```

*Source: [`taggable.py`](spine-core/src/spine/core/taggable.py#L1)*

```
::

        ┌───────────────────────────────────────────────────────────┐
        │                    WeekEnding Value Object                 │
        └───────────────────────────────────────────────────────────┘

        Input Validation:
        ┌────────────────────────────────────────────────────────────┐
        │ WeekEnding("2025-12-26")  → ✅ OK (Friday)                │
        │ WeekEnding("2025-12-25")  → ❌ ValueError (Thursday)      │
        │ WeekEnding.from_any_date(date(2025, 12, 23)) → ✅ 12-26   │
        └────────────────────────────────────────────────────────────┘

        6-Week Backfill Pattern:
        ┌────────────────────────────────────────────────────────────┐
        │ week = WeekEnding("2025-12-26")                           │
        │ window = week.window(6)  # Last 6 weeks                   │
        │                                                            │
        │ for w in window:                                           │
        │     process_week(w)  # Each is validated Friday           │
        └────────────────────────────────────────────────────────────┘

        Timeline:
        ──┬──────┬──────┬──────┬──────┬──────┬──────┬──
          │ 11/21│ 11/28│ 12/05│ 12/12│ 12/19│ 12/26│
          │  Fri │  Fri │  Fri │  Fri │  Fri │  Fri │
          └──────┴──────┴──────┴──────┴──────┴──────┘
                      week.window(6) returns all 6
```

*Source: [`temporal.py`](spine-core/src/spine/core/temporal.py#L1)*

```
::

        ┌──────────────────────────────────────────────────────────┐
        │                  TemporalEnvelope                         │
        │  event_time     — When did the real-world event happen?   │
        │  publish_time   — When did the source make it available?  │
        │  ingest_time    — When did WE first capture it?           │
        │  effective_time — When should consumers treat it as valid?│
        │  payload        — The actual data                         │
        └──────────────────────────────────────────────────────────┘

        BiTemporalRecord (extends with):
        │  valid_from / valid_to    — Business time axis            │
        │  system_from / system_to  — System/bookkeeping axis       │
```

*Source: [`temporal_envelope.py`](spine-core/src/spine/core/temporal_envelope.py#L1)*

```
::

        VersionedContent
        ├── ContentVersion v1 (original, source=HUMAN)
        ├── ContentVersion v2 (LLM-expanded, source=LLM_EXPANDED)
        └── ContentVersion v3 (corrected, source=HUMAN_EDITED)

        current → v3 (latest version)
        history → [v1, v2, v3] (full audit trail)
```

*Source: [`versioned_content.py`](spine-core/src/spine/core/versioned_content.py#L1)*

```
::

        ┌──────────────────────────────────────────────────────────┐
        │                  WatermarkStore                           │
        └──────────────────────────────────────────────────────────┘

        advance("equity", "polygon", "AAPL", cursor)
              │
              ▼
        ┌──────────────────────────────────────────────────────────┐
        │ core_watermarks table (or in-memory dict)                │
        │ domain | source  | partition_key | high_water | updated  │
        │ equity | polygon | AAPL          | 2026-02-15 | ...      │
        └──────────────────────────────────────────────────────────┘

        list_gaps(expected=["AAPL","MSFT","GOOG"])
              │
              ▼
        WatermarkGap("MSFT") → BackfillPlan
```

*Source: [`watermarks.py`](spine-core/src/spine/core/watermarks.py#L1)*

```
:

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
```

*Source: [`__init__.py`](spine-core/src/spine/core/repositories/__init__.py#L1)*

### AnomalyCategory

```
::

        Category → Team Routing:
        ┌────────────────────────────────────────────────────┐
        │ QUALITY_GATE      → Data Quality Team              │
        │ NETWORK           → Infrastructure Team            │
        │ DATA_QUALITY      → Data Engineering Team          │
        │ STEP_FAILURE      → Operation Owners                │
        │ WORKFLOW_FAILURE  → Operation Owners                │
        │ CONFIGURATION     → DevOps Team                    │
        │ SOURCE_ERROR      → Data Source Owners             │
        │ TIMEOUT           → Infrastructure Team            │
        │ RESOURCE          → Infrastructure Team            │
        │ UNKNOWN           → On-Call for Triage             │
        └────────────────────────────────────────────────────┘

Attributes:
    QUALITY_GATE: Data quality threshold not met.
    NETWORK: Network/connectivity issues.
    DATA_QUALITY: Data validation failures.
    STEP_FAILURE: Individual step failures.
    WORKFLOW_FAILURE: Entire workflow failures.
    CONFIGURATION: Configuration errors.
    SOURCE_ERROR: Source data issues.
    TIMEOUT: Operation timeouts.
    RESOURCE: Resource exhaustion.
    UNKNOWN: Uncategorized anomalies.
```

*Source: [`AnomalyCategory`](spine-core/src/spine/core/anomalies.py#L176)*

### AnomalyRecorder

```
::

        ┌────────────────────────────────────────────────────────────┐
        │                    AnomalyRecorder                         │
        ├────────────────────────────────────────────────────────────┤
        │ Properties:                                                 │
        │   conn: Connection      # DB connection (sync)             │
        │   domain: str           # Domain name                       │
        │   table: str            # core_anomalies table              │
        ├────────────────────────────────────────────────────────────┤
        │ Methods:                                                    │
        │   record(...)  → str    # Record anomaly, return ID         │
        │   resolve(id, note?)    # Mark anomaly resolved             │
        │   list_unresolved(...)  # Query open anomalies             │
        └────────────────────────────────────────────────────────────┘

        Record Flow:
        ┌───────────┐     ┌─────────────────┐     ┌──────────────┐
        │ Operation  │────▶│ AnomalyRecorder │────▶│ core_anomalies│
        │ catches   │     │ .record()       │     │ table         │
        │ error     │     │                 │     │               │
        └───────────┘     └─────────────────┘     └──────────────┘

        Resolution Flow:
        ┌───────────┐     ┌─────────────────┐     ┌──────────────┐
        │ Operator  │────▶│ AnomalyRecorder │────▶│ resolved_at  │
        │ fixes     │     │ .resolve(id)    │     │ = now()      │
        │ issue     │     │                 │     │               │
        └───────────┘     └─────────────────┘     └──────────────┘
```

*Source: [`AnomalyRecorder`](spine-core/src/spine/core/anomalies.py#L241)*

### Connection

```
::

        Connection Protocol:
        ┌────────────────────────────────────────────────────────┐
        │ execute(sql, params)   → Execute single statement      │
        │ executemany(sql, list) → Execute for multiple params   │
        │ fetchone()             → Get one result row            │
        │ fetchall()             → Get all result rows           │
        │ commit()               → Commit transaction            │
        │ rollback()             → Rollback transaction          │
        └────────────────────────────────────────────────────────┘

        Implementations:
        ┌────────────────────────────────────────────────────────┐
        │ Basic Tier        → sqlite3.Connection (native sync)   │
        │ Intermediate Tier → SyncPgAdapter wrapping asyncpg     │
        │ Advanced Tier     → SyncPgAdapter wrapping asyncpg     │
        │ Full Tier         → SyncPgAdapter wrapping asyncpg     │
        └────────────────────────────────────────────────────────┘
```

*Source: [`Connection`](spine-core/src/spine/core/protocols.py#L84)*

### Err

```
::

        ┌─────────────────────────────────────────────────────────┐
        │                        Err[T]                            │
        ├─────────────────────────────────────────────────────────┤
        │  error: Exception                                        │
        ├─────────────────────────────────────────────────────────┤
        │  Inspection     │  Recovery      │  Transformation      │
        │  • is_ok()      │  • unwrap_or() │  • map_err()         │
        │  • is_err()     │  • or_else()   │  • map() → no-op     │
        │                 │                │  • flat_map() → no-op│
        │                 │                │  • inspect_err()     │
        └─────────────────────────────────────────────────────────┘
```

*Source: [`Err`](spine-core/src/spine/core/result.py#L299)*

### ErrorCategory

**Network**

```
::

        ┌──────────────────────────────────────────────────────────┐
        │                    ErrorCategory                          │
        ├──────────────────────────────────────────────────────────┤
        │  Infrastructure    │  Data           │  Application      │
        │  ───────────────   │  ────           │  ───────────      │
        │  NETWORK           │  SOURCE         │  operation         │
        │  DATABASE          │  PARSE          │  ORCHESTRATION    │
        │  STORAGE           │  VALIDATION     │                   │
        ├──────────────────────────────────────────────────────────┤
        │  Configuration     │  Internal                           │
        │  ─────────────     │  ────────                           │
        │  CONFIG            │  INTERNAL                           │
        │  AUTH              │  UNKNOWN                            │
        └──────────────────────────────────────────────────────────┘
```

*Source: [`ErrorCategory`](spine-core/src/spine/core/errors.py#L142)*

### ErrorContext

```
::

        ┌─────────────────────────────────────────────────────────┐
        │                    ErrorContext                          │
        ├─────────────────────────────────────────────────────────┤
        │  Execution        │  Source         │  Request          │
        │  ──────────       │  ──────         │  ───────          │
        │  workflow          │  source_name    │  url              │
        │  workflow         │  source_type    │  http_status      │
        │  step             │                 │                   │
        │  run_id           │                 │                   │
        │  execution_id     │                 │                   │
        ├─────────────────────────────────────────────────────────┤
        │  metadata: dict[str, Any]  (extensible)                 │
        └─────────────────────────────────────────────────────────┘
```

*Source: [`ErrorContext`](spine-core/src/spine/core/errors.py#L253)*

### ExecutionContext

```
::

        ┌────────────────────────────────────────────────────────────┐
        │                    ExecutionContext                         │
        ├────────────────────────────────────────────────────────────┤
        │  execution_id: str     ← UUID, auto-generated              │
        │  batch_id: str | None  ← Shared across batch operations    │
        │  parent_execution_id: str | None  ← Links to parent        │
        │  started_at: datetime  ← UTC timestamp                     │
        ├────────────────────────────────────────────────────────────┤
        │  child() -> ExecutionContext                               │
        │      Creates new context with:                              │
        │      - New execution_id                                     │
        │      - parent_execution_id = self.execution_id             │
        │      - Inherited batch_id                                   │
        ├────────────────────────────────────────────────────────────┤
        │  with_batch(batch_id) -> ExecutionContext                  │
        │      Creates copy with batch_id set                        │
        └────────────────────────────────────────────────────────────┘
```

*Source: [`ExecutionContext`](spine-core/src/spine/core/execution.py#L121)*

### IdempotencyHelper

```
```
    ┌──────────────────────────────────────────────────────────┐
    │                   IdempotencyHelper API                   │
    └──────────────────────────────────────────────────────────┘

    L2 Pattern (hash-based):
    ┌────────────────────────────────────────────────────────┐
    │ if helper.hash_exists("bronze_raw", "hash", h):       │
    │     continue  # Skip duplicate                         │
    │ conn.execute("INSERT INTO bronze_raw ...")            │
    └────────────────────────────────────────────────────────┘

    L3 Pattern (delete+insert):
    ┌────────────────────────────────────────────────────────┐
    │ key = {"week_ending": "2025-12-26", "tier": "NMS_T1"} │
    │ helper.delete_for_key("silver_volume", key)           │
    │ # ... insert new data ...                              │
    └────────────────────────────────────────────────────────┘

    Batch L2 Pattern:
    ┌────────────────────────────────────────────────────────┐
    │ existing = helper.get_existing_hashes("bronze", "h")  │
    │ for record in batch:                                   │
    │     if record.hash not in existing:                   │
    │         to_insert.append(record)                      │
    └────────────────────────────────────────────────────────┘
    ```
```

*Source: [`IdempotencyHelper`](spine-core/src/spine/core/idempotency.py#L156)*

### IdempotencyLevel

```
```
    ┌──────────────────────────────────────────────────────────┐
    │              Idempotency Level Characteristics           │
    ├──────────────────────────────────────────────────────────┤
    │ Level     │ Re-run Safety │ Infrastructure │ Use Case   │
    ├───────────┼───────────────┼────────────────┼────────────┤
    │ L1_APPEND │ None          │ None           │ Audit logs │
    │ L2_INPUT  │ Hash-based    │ Hash column    │ Bronze     │
    │ L3_STATE  │ Delete+insert │ Logical key    │ Silver/Gold│
    └──────────────────────────────────────────────────────────┘

    Progression Through Layers:
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ L1_RAW  │ ──► │L2_BRONZE│ ──► │L3_SILVER│
    │ (append)│     │ (hash)  │     │ (d+i)   │
    └─────────┘     └─────────┘     └─────────┘
    ```
```

*Source: [`IdempotencyLevel`](spine-core/src/spine/core/idempotency.py#L78)*

### LogicalKey

```
```
    ┌──────────────────────────────────────────────────────────┐
    │                    LogicalKey Usage                       │
    └──────────────────────────────────────────────────────────┘

    Construction:
    ┌────────────────────────────────────────────────────────┐
    │ key = LogicalKey(week_ending="2025-12-26",            │
    │                  tier="NMS_TIER_1")                    │
    └────────────────────────────────────────────────────────┘

    SQL Generation:
    ┌────────────────────────────────────────────────────────┐
    │ key.where_clause()  → "week_ending = ? AND tier = ?"  │
    │ key.values()        → ("2025-12-26", "NMS_TIER_1")    │
    └────────────────────────────────────────────────────────┘

    With IdempotencyHelper:
    ┌────────────────────────────────────────────────────────┐
    │ helper.delete_for_key("table", key.as_dict())         │
    └────────────────────────────────────────────────────────┘
    ```
```

*Source: [`LogicalKey`](spine-core/src/spine/core/idempotency.py#L286)*

### ManifestRow

```
::

        ManifestRow Structure:
        ┌────────────────────────────────────────────────────────┐
        │ stage: str           # e.g., "INGESTED"                │
        │ stage_rank: int      # e.g., 1 (for ordering)          │
        │ row_count: int|None  # e.g., 1000 rows processed       │
        │ metrics: dict        # e.g., {"null_rate": 0.05}       │
        │ execution_id: str    # Correlation to execution        │
        │ batch_id: str        # Correlation to batch            │
        │ updated_at: str      # ISO timestamp                   │
        └────────────────────────────────────────────────────────┘

Attributes:
    stage: Stage name (e.g., "INGESTED", "NORMALIZED").
    stage_rank: Integer rank for stage ordering (0-indexed).
    row_count: Number of rows processed at this stage, or None.
    metrics: Custom metrics dictionary (JSON-serialized in DB).
    execution_id: Execution ID that created/updated this row.
    batch_id: Batch ID within the execution.
    updated_at: ISO timestamp of last update.
```

*Source: [`ManifestRow`](spine-core/src/spine/core/manifest.py#L140)*

### Ok

```
::

        ┌─────────────────────────────────────────────────────────┐
        │                        Ok[T]                             │
        ├─────────────────────────────────────────────────────────┤
        │  value: T                                                │
        ├─────────────────────────────────────────────────────────┤
        │  Inspection     │  Extraction    │  Transformation      │
        │  • is_ok()      │  • unwrap()    │  • map()             │
        │  • is_err()     │  • unwrap_or() │  • flat_map()        │
        │                 │                │  • and_then()        │
        │                 │                │  • inspect()         │
        └─────────────────────────────────────────────────────────┘
```

*Source: [`Ok`](spine-core/src/spine/core/result.py#L140)*

### QualityRunner

```
```
    ┌──────────────────────────────────────────────────────────┐
    │                    QualityRunner Flow                     │
    └──────────────────────────────────────────────────────────┘

    1. Setup:
    ┌────────────────────────────────────────────────────────┐
    │ runner = QualityRunner(conn, domain="otc", exec_id="..")│
    │ runner.add(check1).add(check2).add(check3)             │
    └────────────────────────────────────────────────────────┘

    2. Execution:
    ┌────────────────────────────────────────────────────────┐
    │ results = runner.run_all(context, partition_key)       │
    │                                                        │
    │ For each check:                                        │
    │   result = check.check_fn(context)                     │
    │   INSERT INTO core_quality (...)                       │
    └────────────────────────────────────────────────────────┘

    3. Quality Gate:
    ┌────────────────────────────────────────────────────────┐
    │ if runner.has_failures():                              │
    │     raise QualityGateError(runner.failures())          │
    └────────────────────────────────────────────────────────┘
    ```
```

*Source: [`QualityRunner`](spine-core/src/spine/core/quality.py#L281)*

### Reject

```
::

        Reject Structure:
        ┌────────────────────────────────────────────────────────┐
        │ stage: str              # "NORMALIZE"                  │
        │ reason_code: str        # "INVALID_SYMBOL"             │
        │ reason_detail: str      # "Symbol 'BAD$YM' has $"      │
        │ raw_data: Any           # {"symbol": "BAD$YM"}         │
        │ source_locator: str     # "file://data/raw.csv"        │
        │ line_number: int        # 42                           │
        └────────────────────────────────────────────────────────┘

Attributes:
    stage: Where rejected (INGEST, NORMALIZE, AGGREGATE).
    reason_code: Machine-readable code (INVALID_SYMBOL, NEGATIVE_VOLUME).
    reason_detail: Human-readable explanation.
    raw_data: Original data for debugging (JSON-serialized).
    source_locator: File path or URL of source data.
    line_number: Line number in source file.
```

*Source: [`Reject`](spine-core/src/spine/core/rejects.py#L130)*

### RejectSink

```
::

        ┌────────────────────────────────────────────────────────────┐
        │                       RejectSink                           │
        ├────────────────────────────────────────────────────────────┤
        │ Properties:                                                 │
        │   conn: Connection       # DB connection (sync)            │
        │   domain: str            # Domain name                      │
        │   table: str             # core_rejects table               │
        │   execution_id: str      # Execution correlation           │
        │   batch_id: str          # Batch correlation               │
        │   _count: int            # Running count of rejects        │
        ├────────────────────────────────────────────────────────────┤
        │ Methods:                                                    │
        │   write(reject, key)     # Write single reject             │
        │   write_batch(rejects)   # Write multiple rejects          │
        │   count → int            # Property: total written         │
        └────────────────────────────────────────────────────────────┘

        Write Flow:
        ┌────────────┐     ┌────────────┐     ┌─────────────┐
        │ Validation │────▶│ RejectSink │────▶│ core_rejects│
        │ stage      │     │ .write()   │     │ table       │
        │ catches    │     │            │     │             │
        │ bad record │     │            │     │             │
        └────────────┘     └────────────┘     └─────────────┘
```

*Source: [`RejectSink`](spine-core/src/spine/core/rejects.py#L195)*

### RollingResult

```
```
    ┌──────────────────────────────────────────────────────────┐
    │                    RollingResult                          │
    ├──────────────────────────────────────────────────────────┤
    │  aggregates: dict[str, Any]                              │
    │      └─ Domain-specific computed values                  │
    │         {"avg_volume": 1234, "max_volume": 5678}         │
    │                                                          │
    │  periods_present: int                                    │
    │      └─ How many periods had data (e.g., 5)             │
    │                                                          │
    │  periods_total: int                                      │
    │      └─ Window size (e.g., 6)                           │
    │                                                          │
    │  is_complete: bool                                       │
    │      └─ True if periods_present == periods_total         │
    └──────────────────────────────────────────────────────────┘
    ```
```

*Source: [`RollingResult`](spine-core/src/spine/core/rolling.py#L89)*

### RollingWindow

```
```
    ┌──────────────────────────────────────────────────────────┐
    │                   RollingWindow[T]                        │
    └──────────────────────────────────────────────────────────┘

    Construction:
    ┌────────────────────────────────────────────────────────┐
    │ window = RollingWindow(                                │
    │     size=6,                                            │
    │     step_back=lambda w: w.previous()  # WeekEnding     │
    │ )                                                      │
    └────────────────────────────────────────────────────────┘

    Computation Flow:
    ┌────────────────────────────────────────────────────────┐
    │ as_of = WeekEnding("2025-12-26")                       │
    │                                                        │
    │ 1. get_window(as_of)                                   │
    │    → [11/21, 11/28, 12/05, 12/12, 12/19, 12/26]       │
    │                                                        │
    │ 2. fetch_fn(period) for each                          │
    │    → [(11/21, 100), (11/28, None), ...]               │
    │                                                        │
    │ 3. Filter to present values                            │
    │    → [(11/21, 100), (12/05, 150), ...]               │
    │                                                        │
    │ 4. aggregate_fn(present)                               │
    │    → {"avg": 125.0, "count": 5}                       │
    │                                                        │
    │ 5. Return RollingResult                                │
    │    → aggregates, periods_present=5, is_complete=False │
    └────────────────────────────────────────────────────────┘
    ```
```

*Source: [`RollingWindow`](spine-core/src/spine/core/rolling.py#L178)*

### Severity

```
::

        Severity → Alert Routing:
        ┌────────────────────────────────────────────────────┐
        │ DEBUG    → Log only, no alert                      │
        │ INFO     → Log only, metrics collection            │
        │ WARN     → Creates ticket, appears on dashboard    │
        │ ERROR    → Triggers alert, requires resolution     │
        │ CRITICAL → Pages on-call, immediate attention      │
        └────────────────────────────────────────────────────┘

Attributes:
    DEBUG: Diagnostic information for developers.
    INFO: Notable events that aren't problems.
    WARN: Warning conditions that may need attention.
    ERROR: Error conditions causing step/operation failures.
    CRITICAL: Severe errors requiring immediate attention.
```

*Source: [`Severity`](spine-core/src/spine/core/anomalies.py#L123)*

### SpineError

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                       SpineError                             │
        ├─────────────────────────────────────────────────────────────┤
        │  Class Attributes                                            │
        │  ────────────────                                            │
        │  default_category: ErrorCategory = INTERNAL                  │
        │  default_retryable: bool = False                             │
        ├─────────────────────────────────────────────────────────────┤
        │  Instance Attributes                                         │
        │  ───────────────────                                         │
        │  message: str                                                │
        │  category: ErrorCategory                                     │
        │  retryable: bool                                             │
        │  retry_after: int | None                                     │
        │  context: ErrorContext                                       │
        │  cause: Exception | None                                     │
        ├─────────────────────────────────────────────────────────────┤
        │  Methods                                                     │
        │  ───────                                                     │
        │  with_context(**kwargs) -> SpineError  # fluent context add  │
        │  to_dict() -> dict  # serialization for logging              │
        └─────────────────────────────────────────────────────────────┘
```

*Source: [`SpineError`](spine-core/src/spine/core/errors.py#L387)*

### StorageBackend

```
::

        StorageBackend Protocol:
        ┌────────────────────────────────────────────────────────┐
        │ transaction()     → Context manager yielding Connection│
        │ get_connection()  → Get raw Connection (caller manages)│
        └────────────────────────────────────────────────────────┘

        Transaction Flow:
        ┌─────────────────────────────────────────────────────────┐
        │ with backend.transaction() as conn:                    │
        │     conn.execute("UPDATE ...")  # Within transaction   │
        │     conn.execute("INSERT ...")  # Still in transaction │
        │ # Auto-commits on successful exit                      │
        │ # Auto-rollbacks on exception                          │
        └─────────────────────────────────────────────────────────┘
```

*Source: [`StorageBackend`](spine-core/src/spine/core/storage.py#L115)*

### TransientError

```
::

        ┌─────────────────────────────────────────────────────────────┐
        │                    TransientError                            │
        │             (default_retryable=True)                         │
        ├─────────────────────────────────────────────────────────────┤
        │                                                              │
        │  NetworkError      TimeoutError      RateLimitError          │
        │  (NETWORK)         (NETWORK)         (NETWORK,retry_after)   │
        │                                                              │
        │  DatabaseConnectionError                                     │
        │  (DATABASE)                                                  │
        │                                                              │
        └─────────────────────────────────────────────────────────────┘
```

*Source: [`TransientError`](spine-core/src/spine/core/errors.py#L598)*

### WeekEnding

```
```
    ┌───────────────────────────────────────────────────────────┐
    │                    WeekEnding Operations                   │
    └───────────────────────────────────────────────────────────┘

    Construction:
    ┌─────────────────────────────────────────────────────────┐
    │ WeekEnding("2025-12-26")          → OK (Friday)        │
    │ WeekEnding(date(2025, 12, 26))    → OK (Friday)        │
    │ WeekEnding("2025-12-25")          → ValueError!        │
    │ WeekEnding.from_any_date(12-23)   → 2025-12-26 (Fri)   │
    │ WeekEnding.today()                → Current week's Fri │
    └─────────────────────────────────────────────────────────┘

    Navigation:
    ┌─────────────────────────────────────────────────────────┐
    │ week.previous(1)   → Previous Friday                   │
    │ week.next(1)       → Next Friday                       │
    │ week.window(6)     → Last 6 Fridays (oldest first)     │
    │ WeekEnding.last_n(6)  → Last 6 weeks from today        │
    └─────────────────────────────────────────────────────────┘

    Iteration:
    ┌─────────────────────────────────────────────────────────┐
    │ WeekEnding.range(start, end)                           │
    │   → Generator of all Fridays from start to end         │
    └─────────────────────────────────────────────────────────┘
    ```
```

*Source: [`WeekEnding`](spine-core/src/spine/core/temporal.py#L72)*

### WorkManifest

```
::

        ┌────────────────────────────────────────────────────────────┐
        │                      WorkManifest                          │
        ├────────────────────────────────────────────────────────────┤
        │ Properties:                                                 │
        │   conn: Connection        # DB connection (sync)           │
        │   domain: str             # Domain name                     │
        │   table: str              # core_manifest table             │
        │   stages: list[str]       # Ordered stage names            │
        │   _stage_ranks: dict      # stage → rank mapping           │
        │   on_stage_change: Hook   # Optional event callback        │
        ├────────────────────────────────────────────────────────────┤
        │ Methods:                                                    │
        │   advance_to(key, stage)  # UPSERT stage row               │
        │   is_at_least(key, stage) # Check rank >= target           │
        │   get(key)                # List all stages for partition  │
        └────────────────────────────────────────────────────────────┘

        Stage Progression:
        ┌────────────────────────────────────────────────────────────┐
        │                                                             │
        │  PENDING ─▶ INGESTED ─▶ NORMALIZED ─▶ AGGREGATED           │
        │   rank=0    rank=1       rank=2        rank=3              │
        │                                                             │
        │  is_at_least("NORMALIZED") checks rank >= 2                │
        └────────────────────────────────────────────────────────────┘

        Database Storage:
        ┌─────────────────────────────────────────────────────────────┐
        │ domain | partition_key           | stage     | rank | ...  │
        │ otc    | {"week":"12-26"}        | PENDING   | 0    | ...  │
        │ otc    | {"week":"12-26"}        | INGESTED  | 1    | ...  │
        │ ...one row per stage per partition...                      │
        └─────────────────────────────────────────────────────────────┘
```

*Source: [`WorkManifest`](spine-core/src/spine/core/manifest.py#L223)*

---

## Execution Engine

```
.. code-block:: text

        tracked_execution() lifecycle:

        ┌─────────────────────────────────────────────┐
        │ 1. Check idempotency (skip if done)      │
        │ 2. Create execution in ledger             │
        │ 3. Acquire concurrency lock               │
        │ 4. Mark RUNNING                           │
        │ 5. ─── yield ctx ───  (user code runs)   │
        │ 6a. Mark COMPLETED (on success)           │
        │ 6b. Mark FAILED + DLQ (on exception)      │
        │ 7. Release lock (always)                  │
        └─────────────────────────────────────────────┘

    .. mermaid::

        sequenceDiagram
            participant C as Caller
            participant TE as tracked_execution
            participant L as ExecutionLedger
            participant G as ConcurrencyGuard
            participant D as DLQManager

            C->>TE: with tracked_execution(...)
            TE->>L: create_execution()
            TE->>G: acquire(lock_key)
            G-->>TE: lock acquired
            TE->>L: update_status(RUNNING)
            TE-->>C: yield ctx
            Note over C: User code runs
            alt Success
                C->>TE: exit (no exception)
                TE->>L: update_status(COMPLETED)
            else Failure
                C->>TE: raise Exception
                TE->>L: update_status(FAILED)
                TE->>D: add_to_dlq()
            end
            TE->>G: release(lock_key)

Example:
    >>> from spine.execution.context import TrackedExecution
    >>>
    >>> async with TrackedExecution(
    ...     ledger=ledger,
    ...     guard=guard,
    ...     dlq=dlq,
    ...     workflow="sec.filings",
    ...     params={"date": "2024-01-01"},
    ... ) as ctx:
    ...     result = await fetch_filings(ctx.params)
    ...     ctx.set_result(result)
```

*Source: [`context.py`](spine-core/src/spine/execution/context.py#L1)*

```
.. code-block:: text

        ExecutionLedger — Single Source of Truth
        ┌───────────────────────────────────────────────────────────┐
        │                                                           │
        │  EXECUTION CRUD            EVENT RECORDING                │
        │  ─────────────             ────────────────                │
        │  create_execution()        record_event()                 │
        │  get_execution()           get_events()                   │
        │  get_by_idempotency_key()                                 │
        │  update_status()           Status→Event mapping:          │
        │  increment_retry()         PENDING  → CREATED             │
        │  list_executions()         RUNNING  → STARTED             │
        │                            COMPLETED→ COMPLETED           │
        │                            FAILED   → FAILED              │
        │                            TIMED_OUT→ TIMED_OUT           │
        │                                                           │
        ├───────────────────────────────────────────────────────────┤
        │  Tables:                                                  │
        │  ┌──────────────────┐     ┌──────────────────────────┐   │
        │  │ core_executions  │────>│ core_execution_events    │   │
        │  │ (state machine)  │     │ (append-only event log)  │   │
        │  └──────────────────┘     └──────────────────────────┘   │
        └───────────────────────────────────────────────────────────┘

    .. mermaid::

        erDiagram
            core_executions {
                text id PK
                text workflow
                text params
                text status
                text lane
                text trigger_source
                text parent_execution_id
                text created_at
                text started_at
                text completed_at
                text result
                text error
                int retry_count
                text idempotency_key
            }
            core_execution_events {
                text id PK
                text execution_id FK
                text event_type
                text timestamp
                text data
            }
            core_executions ||--o{ core_execution_events : "emits"
Example:
    >>> from spine.execution.ledger import ExecutionLedger
    >>> from spine.execution.models import Execution, EventType
    >>>
    >>> ledger = ExecutionLedger(conn)
    >>> execution = Execution.create(workflow="finra.otc.ingest")
    >>> ledger.create_execution(execution)
    >>> ledger.record_event(execution.id, EventType.STARTED)
```

*Source: [`ledger.py`](spine-core/src/spine/execution/ledger.py#L1)*

```
::

        ┌─────────────────────────────────────────────────────────────────┐
        │                    Timeout Enforcement                          │
        └─────────────────────────────────────────────────────────────────┘

        Sync Operations:
        ┌────────────────────────────────────────────────────────────────┐
        │ with with_deadline(30.0):                                      │
        │     result = slow_operation()                                  │
        │ # Raises TimeoutExpired if > 30 seconds                        │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ uses
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │               ThreadPoolExecutor + Event                        │
        │  - Runs operation in separate thread                           │
        │  - Main thread waits with timeout                              │
        │  - On timeout, raises TimeoutExpired                           │
        └────────────────────────────────────────────────────────────────┘

        Async Operations:
        ┌────────────────────────────────────────────────────────────────┐
        │ async with with_deadline_async(30.0):                          │
        │     result = await slow_async_operation()                      │
        │ # Raises TimeoutExpired if > 30 seconds                        │
        └────────────────────────────────────────────────────────────────┘
                              │
                              │ uses
                              ▼
        ┌────────────────────────────────────────────────────────────────┐
        │               asyncio.timeout (Python 3.11+)                    │
        │  - Native async timeout support                                │
        │  - Cancels task on timeout                                     │
        └────────────────────────────────────────────────────────────────┘
```

*Source: [`timeout.py`](spine-core/src/spine/execution/timeout.py#L1)*

```
:

    ┌─────────────────┐
    │  WorkflowPackager│
    │                  │
    │  .package()  ────┼──► myworkflow.pyz
    │  .inspect()  ────┼──► PackageManifest
    │  .unpack()   ────┼──► directory tree
    └─────────────────┘

Key design constraints:

- **Operation steps** are stored by name (string).  The target
  environment must have the referenced operations installed.
- **Lambda steps** with *named* functions can be packaged by
  extracting their source via ``inspect.getsource()``.  Inline
  lambdas and closures are **not** portable — the packager
  emits a warning and skips them.
- **Choice / wait / map** steps are serialized via ``Step.to_dict()``
  and reconstructed on the other side.

Usage::

    from spine.orchestration import Workflow, Step
    from spine.execution.packaging import WorkflowPackager

    wf = Workflow(
        name="my.operation",
        steps=[
            Step.operation("ingest", "my.ingest"),
            Step.operation("transform", "my.transform"),
        ],
    )

    packager = WorkflowPackager()
    path = packager.package(wf, "my_operation.pyz")
    print(f"Created {path}  ({path.stat().st_size} bytes)")
```

*Source: [`__init__.py`](spine-core/src/spine/execution/packaging/__init__.py#L1)*

```
.. code-block:: text

        JobEngine — Central Facade
        ┌─────────────────────────────────────────────────────────────┐
        │                                                             │
        │  submit(spec)                                               │
        │    ├── validate spec (SpecValidator)                        │
        │    ├── check idempotency (Ledger)                           │
        │    ├── create execution record (Ledger)                     │
        │    ├── route to adapter (Router)                            │
        │    ├── adapter.submit(spec) → external_ref                  │
        │    ├── update execution metadata with external_ref          │
        │    └── return SubmitResult                                  │
        │                                                             │
        │  status(execution_id)                                       │
        │    ├── get execution from Ledger                             │
        │    ├── get external_ref from metadata                       │
        │    ├── adapter.status(ref) → JobStatus                      │
        │    └── map runtime state → ExecutionStatus                  │
        │                                                             │
        │  cancel(execution_id)                                       │
        │    ├── get execution from Ledger                             │
        │    ├── adapter.cancel(ref)                                  │
        │    └── update Ledger → CANCELLED                            │
        │                                                             │
        │  logs(execution_id)                                         │
        │    ├── get external_ref from metadata                       │
        │    └── adapter.logs(ref) → AsyncIterator[str]               │
        │                                                             │
        │  cleanup(execution_id)                                      │
        │    ├── adapter.cleanup(ref)                                 │
        │    └── record CLEANUP_COMPLETED event                       │
        │                                                             │
        └─────────────────────────────────────────────────────────────┘

    .. mermaid::

        sequenceDiagram
            participant C as Client
            participant E as JobEngine
            participant V as SpecValidator
            participant R as Router
            participant L as Ledger
            participant A as RuntimeAdapter

            C->>E: submit(spec)
            E->>V: validate_or_raise(spec, adapter)
            E->>L: check idempotency
            E->>L: create_execution()
            E->>R: route(spec) → adapter
            E->>A: submit(spec) → external_ref
            E->>L: update metadata (external_ref, runtime)
            E-->>C: SubmitResult

            C->>E: status(execution_id)
            E->>L: get_execution()
            E->>A: status(external_ref) → JobStatus
            E-->>C: JobStatus

            C->>E: cancel(execution_id)
            E->>A: cancel(external_ref)
            E->>L: update_status(CANCELLED)
            E-->>C: True/False

Example:
    >>> from spine.execution.runtimes.engine import JobEngine
    >>> from spine.execution.runtimes._base import StubRuntimeAdapter
    >>> from spine.execution.runtimes.router import RuntimeAdapterRouter
    >>> from spine.execution.runtimes.validator import SpecValidator
    >>> from spine.execution.ledger import ExecutionLedger
    >>>
    >>> router = RuntimeAdapterRouter()
    >>> router.register(StubRuntimeAdapter())
    >>> engine = JobEngine(
    ...     router=router,
    ...     ledger=ExecutionLedger(conn),
    ...     validator=SpecValidator(),
    ... )
    >>> result = await engine.submit(spec)
    >>> print(result.execution_id, result.external_ref)
```

*Source: [`engine.py`](spine-core/src/spine/execution/runtimes/engine.py#L1)*

```
:

    HotReloadAdapter  (implements RuntimeAdapter protocol)
        ├── _inner: RuntimeAdapter  (the real adapter)
        ├── _config_source: Callable → dict | str path
        ├── _last_config: dict       (snapshot for change detection)
        └── _on_reload: Callable     (optional reload hook)

    On each submit/status/cancel call the adapter checks whether
    the config has changed since the last check.  If so, it calls
    ``on_reload(new_config)`` and replaces the inner adapter.

Example::

    from spine.execution.runtimes.hot_reload import HotReloadAdapter
    from spine.execution.runtimes.local_process import LocalProcessAdapter

    def make_adapter(cfg):
        return LocalProcessAdapter(
            default_image=cfg.get("image", "spine:latest"),
        )

    hot = HotReloadAdapter(
        initial_config={"image": "spine:v1"},
        adapter_factory=make_adapter,
    )

    # Later, update the config:
    hot.update_config({"image": "spine:v2"})
    # Next operation uses the new adapter automatically
```

*Source: [`hot_reload.py`](spine-core/src/spine/execution/runtimes/hot_reload.py#L1)*

```
.. code-block:: text

        LocalProcessAdapter — Container-Free Execution
        ┌──────────────────────────────────────────────────────────────┐
        │                                                              │
        │  Translates ContainerJobSpec → asyncio.subprocess            │
        │                                                              │
        │  ContainerJobSpec field      │ Local process equivalent      │
        │  ────────────────────────────┼───────────────────────────────│
        │  image                       │ ignored (runs local binary)   │
        │  command + args              │ subprocess argv               │
        │  env                         │ os.environ overlay            │
        │  working_dir                 │ subprocess cwd                │
        │  timeout_seconds             │ asyncio wait timeout          │
        │  artifacts_dir               │ local directory               │
        │                              │                               │
        │  NOT supported locally:                                      │
        │  - GPU, volumes, sidecars, init containers                   │
        │  - Image pulling (no images)                                 │
        │  - Resource limits (CPU/memory caps)                         │
        │  - Network isolation                                         │
        │                                                              │
        └──────────────────────────────────────────────────────────────┘

    .. mermaid::

        flowchart LR
            SPEC[ContainerJobSpec] --> LPA[LocalProcessAdapter]
            LPA --> PROC[asyncio.subprocess]
            PROC --> STDOUT[stdout → logs]
            PROC --> RC[returncode → status]
            PROC --> ART[artifacts_dir → artifacts]

Use cases:
    - **Development**: Run operations locally without Docker installed
    - **CI without Docker**: GitHub Actions runners or restricted CI
    - **Quick testing**: Faster feedback loop (no image pull)
    - **Fallback**: Auto-fallback when Docker daemon is unavailable

Example:
    >>> from spine.execution.runtimes.local_process import LocalProcessAdapter
    >>> from spine.execution.runtimes import ContainerJobSpec
    >>>
    >>> adapter = LocalProcessAdapter()
    >>> spec = ContainerJobSpec(
    ...     name="local-task",
    ...     image="ignored",  # No image needed
    ...     command=["python", "-c", "print('hello from local')"],
    ...     timeout_seconds=30,
    ... )
    >>> ref = await adapter.submit(spec)
    >>> status = await adapter.status(ref)
    >>> assert status.state == "succeeded"
```

*Source: [`local_process.py`](spine-core/src/spine/execution/runtimes/local_process.py#L1)*

```
:

    BaseRuntimeAdapter
    ├── StubRuntimeAdapter    (existing — always succeeds/fails)
    ├── FailingAdapter        (always raises a specific JobError)
    ├── SlowAdapter           (configurable latency injection)
    ├── FlakeyAdapter         (probabilistic failures)
    ├── SequenceAdapter       (scripted state progression)
    └── LatencyAdapter        (wraps another adapter + adds delay)

    Usage with JobEngine:

        router = RuntimeAdapterRouter()
        router.register("flaky", FlakeyAdapter(success_rate=0.7))
        router.register("slow", SlowAdapter(submit_delay=5.0))

        engine = JobEngine(router=router)
        result = engine.submit(spec, runtime="flaky")

Example::

    from spine.execution.runtimes.mock_adapters import (
        FailingAdapter,
        SlowAdapter,
        FlakeyAdapter,
        SequenceAdapter,
    )

    # Always fail with OOM
    adapter = FailingAdapter(category=ErrorCategory.OOM)

    # Add 2-second delay to every submit
    adapter = SlowAdapter(submit_delay=2.0)

    # 70% success rate — flaky deployment
    adapter = FlakeyAdapter(success_rate=0.7, seed=42)

    # Scripted: pending → running → succeeded
    adapter = SequenceAdapter(states=["pending", "running", "succeeded"])

See Also:
    spine.execution.runtimes._base — BaseRuntimeAdapter and StubRuntimeAdapter
    spine.execution.runtimes._types — Protocol and type definitions
    spine.execution.runtimes.engine — JobEngine facade
```

*Source: [`mock_adapters.py`](spine-core/src/spine/execution/runtimes/mock_adapters.py#L1)*

```
.. code-block:: text

        RuntimeAdapterRouter — Adapter Registry + Router
        ┌──────────────────────────────────────────────────────────────┐
        │                                                              │
        │  Registry                                                    │
        │  ────────                                                    │
        │  register(adapter)       → stores by adapter.runtime_name    │
        │  unregister(name)        → removes adapter                   │
        │  get(name)               → exact lookup by name              │
        │  list_runtimes()         → all registered names              │
        │                                                              │
        │  Routing                                                     │
        │  ───────                                                     │
        │  route(spec)             → adapter for this spec             │
        │    ├── spec.runtime set? → exact match                       │
        │    └── spec.runtime None → capability-based selection        │
        │                                                              │
        │  Health                                                      │
        │  ──────                                                      │
        │  health_all()            → health of every registered adapter│
        │                                                              │
        │  Default                                                     │
        │  ───────                                                     │
        │  set_default(name)       → fallback when no spec.runtime set │
        │                                                              │
        └──────────────────────────────────────────────────────────────┘

    .. mermaid::

        flowchart TD
            SPEC[ContainerJobSpec] --> R{Router}
            R -->|spec.runtime='docker'| D[DockerAdapter]
            R -->|spec.runtime='k8s'| K[KubernetesAdapter]
            R -->|spec.runtime=None| DEF[Default adapter]
            R -->|not found| ERR[JobError NOT_FOUND]

Example:
    >>> from spine.execution.runtimes.router import RuntimeAdapterRouter
    >>> from spine.execution.runtimes._base import StubRuntimeAdapter
    >>>
    >>> router = RuntimeAdapterRouter()
    >>> router.register(StubRuntimeAdapter())
    >>> adapter = router.route(spec)  # uses spec.runtime or default
```

*Source: [`router.py`](spine-core/src/spine/execution/runtimes/router.py#L1)*

```
.. code-block:: text

        SpecValidator — Pre-Submit Gate
        ┌───────────────────────────────────────────────────────┐
        │                                                       │
        │  validate(spec, capabilities, constraints)            │
        │    ├── capability checks (boolean flags)              │
        │    │   ├── GPU required but not supported?            │
        │    │   ├── Volumes required but not supported?        │
        │    │   ├── Sidecars required but not supported?       │
        │    │   └── Init containers required but unsupported?  │
        │    ├── constraint checks (numeric limits)             │
        │    │   ├── delegates to constraints.validate_spec()   │
        │    │   └── timeout, env count, env bytes              │
        │    └── budget gate                                    │
        │        └── max_cost_usd checked against estimate      │
        │                                                       │
        │  validate_or_raise(spec, adapter)                     │
        │    ├── calls validate(spec, caps, constraints)        │
        │    └── raises JobError(VALIDATION) on any violation   │
        │                                                       │
        └───────────────────────────────────────────────────────┘

    .. mermaid::

        flowchart TD
            SPEC[ContainerJobSpec] --> V{SpecValidator}
            V -->|capability checks| CAP[RuntimeCapabilities]
            V -->|numeric checks| CON[RuntimeConstraints]
            V -->|budget gate| BG[max_cost_usd]
            CAP --> R[violations list]
            CON --> R
            BG --> R
            R -->|empty| OK[✓ Submit allowed]
            R -->|non-empty| ERR[✗ JobError VALIDATION]

Example:
    >>> from spine.execution.runtimes.validator import SpecValidator
    >>> from spine.execution.runtimes import ContainerJobSpec, RuntimeCapabilities
    >>>
    >>> validator = SpecValidator()
    >>> spec = ContainerJobSpec(
    ...     name="gpu-job", image="nvidia/cuda:12",
    ...     resources=ResourceRequirements(gpu=1),
    ... )
    >>> caps = RuntimeCapabilities(supports_gpu=False)
    >>> errors = validator.validate(spec, caps)
    >>> errors
    ['Spec requires GPU but runtime does not support it']
```

*Source: [`validator.py`](spine-core/src/spine/execution/runtimes/validator.py#L1)*

```
.. code-block:: text

        RuntimeAdapter (Protocol)
              │
              ▼
        BaseRuntimeAdapter (Abstract Base)
        ├── submit()  → logging + error wrapping → _do_submit()
        ├── status()  → _do_status()
        ├── cancel()  → logging + safe fallback   → _do_cancel()
        ├── logs()    → _do_logs()
        ├── cleanup() → logging + non-fatal       → _do_cleanup()
        └── health()  → latency timing            → _do_health()
              │
        ┌─────┴───────────────────────┐
        │                             │
        ▼                             ▼
    DockerAdapter              StubRuntimeAdapter
    (real containers)          (in-memory for tests)

    .. mermaid::

        classDiagram
            class BaseRuntimeAdapter {
                <<abstract>>
                +submit(spec) str
                +status(ref) JobStatus
                +cancel(ref) bool
                +logs(ref) AsyncIterator
                +cleanup(ref) None
                +health() RuntimeHealth
                #_do_submit(spec)* str
                #_do_status(ref)* JobStatus
                #_do_cancel(ref)* bool
                #_do_logs(ref)* AsyncIterator
                #_do_cleanup(ref)* None
                #_do_health()* RuntimeHealth
            }
            class DockerAdapter {
                +runtime_name = "docker"
            }
            class StubRuntimeAdapter {
                +runtime_name = "stub"
                +jobs: dict
                +fail_submit: bool
            }
            BaseRuntimeAdapter <|-- DockerAdapter
            BaseRuntimeAdapter <|-- StubRuntimeAdapter

Usage:
    # In tests:
    adapter = StubRuntimeAdapter()
    ref = await adapter.submit(spec)
    status = await adapter.status(ref)
    assert status.state == "succeeded"

    # Subclassing for real adapters:
    class DockerAdapter(BaseRuntimeAdapter):
        runtime_name = "docker"
        ...

See Also:
    _types.py — Protocol and type definitions
    docker.py — Docker adapter (MVP-1)
```

*Source: [`_base.py`](spine-core/src/spine/execution/runtimes/_base.py#L1)*

```
.. code-block:: text

        ┌─────────────────────────────────────────────────────────────┐
        │                    _types.py Module Map                     │
        ├─────────────────────────────────────────────────────────────┤
        │                                                             │
        │  ┌─────────────────┐    ┌──────────────────────────────┐   │
        │  │  ErrorCategory  │    │     ContainerJobSpec          │   │
        │  │  (Enum: 10 cats)│    │     name, image, command      │   │
        │  └────────┬────────┘    │     env, resources, volumes   │   │
        │           │             │     timeout, budget, labels    │   │
        │  ┌────────▼────────┐    │     + to_dict(), spec_hash()  │   │
        │  │    JobError     │    └──────────┬───────────────────┘   │
        │  │  (Exception +   │               │                       │
        │  │   dataclass)    │    ┌──────────▼──────────────────┐    │
        │  └─────────────────┘    │  redact_spec(spec) → dict   │    │
        │                         │  job_external_name() → str   │    │
        │  ┌─────────────────┐    └─────────────────────────────┘    │
        │  │ RuntimeAdapter  │                                        │
        │  │  (Protocol)     │    ┌─────────────────────────────┐    │
        │  │  7 async methods│    │  RuntimeCapabilities        │    │
        │  └─────────────────┘    │  (boolean feature flags)    │    │
        │                         ├─────────────────────────────┤    │
        │  ┌─────────────────┐    │  RuntimeConstraints         │    │
        │  │   JobStatus     │    │  (numeric limits)           │    │
        │  │   JobArtifact   │    │  + validate_spec() → []     │    │
        │  │   RuntimeHealth │    └─────────────────────────────┘    │
        │  └─────────────────┘                                       │
        └─────────────────────────────────────────────────────────────┘

    .. mermaid::

        graph LR
            CJS[ContainerJobSpec] -->|"submitted to"| RA[RuntimeAdapter]
            RA -->|"returns"| JS[JobStatus]
            RA -->|"raises"| JE[JobError]
            RA -->|"produces"| JA[JobArtifact]
            RA -->|"reports"| RH[RuntimeHealth]
            RC[RuntimeCapabilities] -->|"checked before"| RA
            RCO[RuntimeConstraints] -->|"validated against"| RA

See Also:
    execution.spec.WorkSpec — In-process work specification
    execution.executors.protocol.Executor — In-process async protocol
    execution.models.ExecutionStatus — Canonical status enum
    execution.models.EventType — Canonical event type enum
```

*Source: [`_types.py`](spine-core/src/spine/execution/runtimes/_types.py#L1)*

```
.. code-block:: text

        spine.execution.runtimes
        ├── __init__.py      ← Public API (this file)
        ├── _types.py        ← RuntimeAdapter protocol + all types
        ├── _base.py         ← BaseRuntimeAdapter + StubRuntimeAdapter
        ├── validator.py     ← SpecValidator (pre-submit gate)
        ├── router.py        ← RuntimeAdapterRouter (adapter registry)
        ├── engine.py        ← JobEngine (central facade)
        ├── local_process.py ← LocalProcessAdapter (no Docker needed)
        ├── docker.py        ← DockerAdapter (MVP-1)
        └── (future)         ← k8s.py, podman.py, ecs.py, ...

    RuntimeAdapter is the canonical protocol for *container-level* execution.
    It is distinct from the Executor protocol (execution.executors.protocol),
    which handles *in-process* async work scheduling.

    RuntimeAdapter operates on ContainerJobSpec (image + resources).
    Executor operates on WorkSpec (name + params).

    .. mermaid::

        graph TB
            subgraph runtimes["spine.execution.runtimes"]
                TYPES["_types.py<br/>Protocol + Types"]
                BASE["_base.py<br/>BaseRuntimeAdapter"]
                VALID["validator.py<br/>SpecValidator"]
                ROUTER["router.py<br/>Router"]
                ENGINE["engine.py<br/>JobEngine"]
                LOCAL["local_process.py<br/>LocalProcessAdapter"]
                DOCKER["docker.py<br/>DockerAdapter"]
                STUB["StubRuntimeAdapter"]
            end

            subgraph executors["spine.execution.executors"]
                EP["protocol.py<br/>Executor Protocol"]
                MEM["MemoryExecutor"]
                CEL["CeleryExecutor"]
            end

            TYPES --> BASE --> DOCKER & LOCAL & STUB
            TYPES --> VALID
            BASE --> ROUTER
            VALID & ROUTER --> ENGINE
            EP --> MEM & CEL

            style runtimes fill:#fce4ec,stroke:#c62828
            style executors fill:#e3f2fd,stroke:#1565c0

Modules:
    _types      - RuntimeAdapter protocol, ContainerJobSpec, RuntimeCapabilities,
                  RuntimeConstraints, JobError, JobArtifact, etc.
    _base       - BaseRuntimeAdapter with shared lifecycle logic
    validator   - SpecValidator (pre-submit capability/constraint checks)
    router      - RuntimeAdapterRouter (adapter registry and routing)
    engine      - JobEngine (central facade for job lifecycle)
    local_process - LocalProcessAdapter (subprocess-based, no Docker needed)
    docker      - Docker Engine adapter (MVP-1)
    stub        - StubRuntimeAdapter for testing

See Also:
    spine-workspace/prompts/04_project/spine-core/job-engine.prompt.md
    spine-core/docs/architecture/JOB_ENGINE_ARCHITECTURE.md
```

*Source: [`__init__.py`](spine-core/src/spine/execution/runtimes/__init__.py#L1)*

### WorkerLoop

1. ``_poll()`` fetches pending rows (``SELECT … FOR UPDATE SKIP LOCKED``
       on PG, advisory-lock-free on SQLite).
    2. Atomically transitions status ``pending → running`` and records
       a ``started`` event.
    3. Resolves the handler via :class:`HandlerRegistry`.
    4. Executes the handler in a thread pool.
    5. On completion, transitions status to ``completed`` or ``failed``
       and records the corresponding event.

Thread-safety:
    The worker uses a single SQLite connection with ``check_same_thread=False``.
    The thread pool handles concurrent execution; the poll loop is
    single-threaded to avoid double-dispatch.

*Source: [`WorkerLoop`](spine-core/src/spine/execution/worker.py#L131)*

---

## Orchestration

```
:

    WorkflowRunner ──▶ Runnable protocol
                           │
                    ContainerRunnable
                           │
                        JobEngine
                     ┌─────┴─────┐
                     Router   Ledger
                       │
                   Adapter(s)

The ``ContainerRunnable`` translates ``submit_operation_sync()`` calls
into ``ContainerJobSpec`` and delegates to ``JobEngine.submit()`` +
``JobEngine.status()`` with polling.  This keeps the orchestration
layer fully decoupled from container specifics.

Example::

    from spine.execution.runtimes.engine import JobEngine
    from spine.orchestration.container_runnable import ContainerRunnable
    from spine.orchestration import WorkflowRunner, Workflow, Step

    engine = JobEngine(router=router, ledger=ledger)
    runnable = ContainerRunnable(engine=engine)

    runner = WorkflowRunner(runnable=runnable)
    result = runner.execute(workflow, params={...})
```

*Source: [`container_runnable.py`](spine-core/src/spine/orchestration/container_runnable.py#L1)*

```
:

    lint_workflow(workflow)
    │
    ├── _check_empty_workflow
    ├── _check_missing_handlers
    ├── _check_choice_completeness
    ├── _check_unreachable_steps
    ├── _check_deep_chains
    ├── _check_operation_naming
    ├── _check_similar_names
    └── (custom rules via register_lint_rule)
    │
    ▼
    LintResult
    ├── diagnostics: list[LintDiagnostic]
    ├── passed → bool (no errors)
    ├── errors / warnings / infos
    └── summary() → str

Example::

    from spine.orchestration.linter import lint_workflow
    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="my.operation",
        steps=[
            Step.operation("ingest", "my.ingest"),
            Step.lambda_("validate", None),  # missing handler!
        ],
    )

    result = lint_workflow(workflow)
    if not result.passed:
        for d in result.errors:
            print(f"[{d.code}] {d.message}")

See Also:
    spine.orchestration.playground — interactive step-by-step execution
    spine.orchestration.templates — pre-built workflow patterns
```

*Source: [`linter.py`](spine-core/src/spine/orchestration/linter.py#L1)*

```
:

    WorkflowPlayground
    ├── load(workflow)       → sets up step queue
    ├── step()               → executes next step, returns StepSnapshot
    ├── step_back()          → rewinds to previous context snapshot
    ├── peek()               → shows next step without executing
    ├── run_to(step_name)    → executes up to a named step
    ├── run_all()            → executes remaining steps
    ├── set_param(k, v)      → modifies context params on the fly
    ├── context              → current WorkflowContext
    ├── history              → list of StepSnapshot objects
    └── reset()              → restarts from beginning

Example::

    from spine.orchestration.playground import WorkflowPlayground
    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="debug.workflow",
        steps=[
            Step.operation("fetch", "my.fetcher"),
            Step.lambda_("validate", validate_fn),
            Step.operation("store", "my.store"),
        ],
    )

    pg = WorkflowPlayground()
    pg.load(workflow, params={"date": "2026-01-15"})

    # Step through one at a time
    snap = pg.step()          # executes "fetch"
    print(snap.result)        # inspect output
    print(pg.context.outputs) # see accumulated outputs

    pg.set_param("override", True)  # modify params
    snap = pg.step()          # executes "validate" with modified params

    pg.step_back()            # rewind to before "validate"
    snap = pg.step()          # re-execute "validate"

    pg.run_all()              # run remaining steps
```

*Source: [`playground.py`](spine-core/src/spine/orchestration/playground.py#L1)*

```
:

    RecordingRunner (wraps WorkflowRunner)
    ├── execute(workflow, params)
    │   ├── before each step → snapshot params/context
    │   ├── execute step (delegate to inner runner)
    │   └── after each step → capture result + timing
    │       → StepRecording
    └── last_recording → WorkflowRecording
        ├── to_dict() / to_json()
        ├── from_dict() / from_json()
        └── replay(workflow) → ReplayResult
            ├── diffs: list[StepDiff]
            └── all_match → bool

    StepRecording (frozen)
    ├── step_name, step_type
    ├── params_snapshot (before)
    ├── outputs_snapshot (after)
    ├── result (StepResult)
    ├── duration_ms
    └── error (optional)

Example::

    from spine.orchestration.recorder import RecordingRunner
    from spine.orchestration import Workflow, Step, StepResult

    def validate(ctx, config):
        return StepResult.ok(output={"valid": True})

    workflow = Workflow(
        name="test.operation",
        steps=[
            Step.operation("fetch", "data.fetch"),
            Step.lambda_("validate", validate),
        ],
    )

    # Record
    recorder = RecordingRunner()
    result = recorder.execute(workflow, params={"date": "2026-01-15"})
    recording = recorder.last_recording

    # Save
    json_str = recording.to_json()

    # Replay later
    loaded = WorkflowRecording.from_json(json_str)
    replay_result = replay(loaded, workflow)
    assert replay_result.all_match

See Also:
    spine.orchestration.playground — interactive step-by-step execution
    spine.orchestration.linter — static workflow analysis
```

*Source: [`recorder.py`](spine-core/src/spine/orchestration/recorder.py#L1)*

```
:

    Workflow
    ├── .steps
    ├── .dependency_graph()
    └── .topological_order()
        │
        ▼
    visualize_mermaid(workflow)  → str (Mermaid graph TD)
    visualize_ascii(workflow)   → str (box drawing)
    visualize_summary(workflow) → dict (metadata)

    Mermaid step shapes:
    - operation  → [operation_name]  (rectangle)
    - LAMBDA    → (handler_name)   (rounded)
    - CHOICE    → {condition}      (diamond)
    - WAIT      → [[wait]]         (subroutine)
    - MAP       → [/fan-out/]      (parallelogram)

Example::

    from spine.orchestration.visualizer import visualize_mermaid, visualize_ascii
    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="etl.operation",
        steps=[
            Step.operation("extract", "data.extract"),
            Step.lambda_("transform", transform_fn),
            Step.operation("load", "data.load"),
        ],
    )

    print(visualize_mermaid(workflow))
    # graph TD
    #     extract["extract<br/>data.extract"]
    #     transform("transform")
    #     load["load<br/>data.load"]
    #     extract --> transform
    #     transform --> load

    print(visualize_ascii(workflow))
    # ┌─────────┐    ┌───────────┐    ┌──────┐
    # │ extract │───▶│ transform │───▶│ load │
    # └─────────┘    └───────────┘    └──────┘

See Also:
    spine.orchestration.linter — static workflow analysis
    spine.orchestration.playground — interactive execution
```

*Source: [`visualizer.py`](spine-core/src/spine/orchestration/visualizer.py#L1)*

---

## Deployment

```
:

    ┌──────────────────────────────────────────────────────────────┐
    │                   deploy-spine                                │
    ├──────────────┬──────────────┬─────────────┬──────────────────┤
    │  Deployment  │   Testbed    │   Job/Task  │   Workflow       │
    │  Targets     │   Runner     │   Executor  │   Runner         │
    ├──────────────┴──────────────┴─────────────┴──────────────────┤
    │              Container Manager (docker CLI subprocess)        │
    ├──────────────────────────────────────────────────────────────┤
    │   Compose Generator │ Log Collector │ Result Models          │
    └──────────────────────────────────────────────────────────────┘
```

*Source: [`__init__.py`](spine-core/src/spine/deploy/__init__.py#L1)*

---

## Tooling

```
:

    ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
    │  Docstrings │  │  Git History  │  │  Phase Map   │
    └──────┬──────┘  └──────┬───────┘  └──────┬───────┘
           │                │                  │
           ▼                ▼                  ▼
    ┌──────────────────────────────────────────────────┐
    │              ChangelogGenerator                   │
    │  scan() → parse() → merge() → render() → write() │
    └───┬──────────┬──────────┬──────────┬─────────────┘
        ▼          ▼          ▼          ▼
    CHANGELOG  REVIEW.md  api_index  diagrams/
```

*Source: [`generator.py`](spine-core/src/spine/tools/changelog/generator.py#L1)*

```
:

    ┌─────────────────────────────────────────────────┐
    │                  git_scan.py                     │
    ├─────────────────────┬───────────────────────────┤
    │  LiveGitScanner     │  FixtureGitScanner        │
    │  (subprocess calls) │  (reads fixture files)    │
    └─────────────────────┴───────────────────────────┘
                │                     │
                ▼                     ▼
         CommitNote[]           CommitNote[]

Usage::

    from spine.tools.changelog.git_scan import scan_git_history

    # Live git
    commits = scan_git_history(repo_dir=Path("."))

    # From fixtures
    commits = scan_git_history(fixture_dir=Path("tests/fixtures/changelog_repo"))
```

*Source: [`git_scan.py`](spine-core/src/spine/tools/changelog/git_scan.py#L1)*

### ChangelogGenerator

```
::

        ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
        │  Docstrings  │  │  Git History  │  │  Phase Map   │
        └──────┬──────┘  └──────┬───────┘  └──────┬───────┘
               │                │                  │
               ▼                ▼                  ▼
        ┌──────────────────────────────────────────────────┐
        │              ChangelogGenerator                   │
        │  scan() → parse() → merge() → render() → write() │
        └───┬──────────┬──────────┬──────────┬─────────────┘
            ▼          ▼          ▼          ▼
        CHANGELOG  REVIEW.md  api_index  diagrams/
```

*Source: [`ChangelogGenerator`](spine-core/src/spine/tools/changelog/generator.py#L59)*

---

*77 diagrams, 81 fragments across 5 packages*

*Generated by document-spine*