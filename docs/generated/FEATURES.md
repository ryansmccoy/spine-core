# FEATURES

**What This Project Can Do**

*Auto-generated from code annotations on 2026-02-19*

---

## Table of Contents

1. [Core Primitives](#core-primitives)
2. [Execution Engine](#execution-engine)
3. [Orchestration](#orchestration)
4. [Observability](#observability)
5. [Tooling](#tooling)

---

## Core Primitives

### AnomalyRecorder

- **Severity classification:** DEBUG/INFO/WARN/ERROR/CRITICAL
    - **Category classification:** QUALITY_GATE, NETWORK, etc.
    - **Metadata storage:** Structured JSON for additional context
    - **Resolution tracking:** record() → resolve() workflow
    - **Execution correlation:** Link to operation execution IDs
    - **Query support:** list_unresolved() for investigation

*From [`AnomalyRecorder`](spine-core/src/spine/core/anomalies.py#L241)*

### Err

- **Short-circuit propagation:** map/flat_map pass Err through unchanged
    - **Error transformation:** map_err() to wrap/convert errors
    - **Recovery operations:** or_else() for fallback, unwrap_or() for default
    - **Side effects:** inspect_err() for logging without unwrapping
    - **Serialization:** to_dict() converts SpineError to structured dict

*From [`Err`](spine-core/src/spine/core/result.py#L299)*

### ExecutionContext

- **Auto-generated IDs:** execution_id is a UUID by default
    - **Child context creation:** child() for sub-operation calls
    - **Batch ID propagation:** batch_id inherited by children
    - **Timestamp tracking:** started_at for metrics/debugging

*From [`ExecutionContext`](spine-core/src/spine/core/execution.py#L121)*

### IdempotencyHelper

- hash_exists(): Single hash lookup for L2 dedup
    - get_existing_hashes(): Batch hash preload
    - delete_for_key(): L3 delete by logical key
    - Works with any Connection protocol (SQLite, PostgreSQL, etc.)

*From [`IdempotencyHelper`](spine-core/src/spine/core/idempotency.py#L156)*

### IdempotencyLevel

- L1_APPEND (1): Raw capture, always insert, external dedup
    - L2_INPUT (2): Hash-based dedup, same hash → skip
    - L3_STATE (3): Delete+insert, same key → same state
    - IntEnum for ordering and comparison

*From [`IdempotencyLevel`](spine-core/src/spine/core/idempotency.py#L78)*

### LogicalKey

- Keyword argument construction for clarity
    - where_clause(): SQL WHERE without keyword
    - values(): Parameter tuple for prepared statements
    - as_dict(): Dictionary form for other APIs
    - Readable __repr__ for debugging

*From [`LogicalKey`](spine-core/src/spine/core/idempotency.py#L286)*

- **Severity levels:** DEBUG, INFO, WARN, ERROR, CRITICAL
    - **Categories:** QUALITY_GATE, NETWORK, DATA_QUALITY, etc.
    - **Resolution tracking:** record() + resolve() workflow
    - **Metadata:** Structured JSON for additional context
    - **Lineage:** execution_id correlation

*From [`anomalies.py`](spine-core/src/spine/core/anomalies.py#L1)*

- **AssetKey:** Hierarchical tuple-based naming for namespace queries
    - **AssetMaterialization:** Records data production with execution lineage
    - **AssetObservation:** Records freshness checks without re-materializing
    - **Partition support:** Incremental materialization and staleness checks
    - **Frozen dataclasses:** Immutable, memory-efficient value objects

*From [`assets.py`](spine-core/src/spine/core/assets.py#L1)*

- **BackfillPlan:** Specification + mutable progress tracking
    - **BackfillStatus:** PLANNED → RUNNING → COMPLETED / FAILED / CANCELLED
    - **BackfillReason:** GAP, CORRECTION, QUALITY_FAILURE, SCHEMA_CHANGE, MANUAL
    - **Checkpoint resume:** Crash at hour 4 → resume from last checkpoint
    - **Progress tracking:** completed_keys, failed_keys, progress_pct

*From [`backfill.py`](spine-core/src/spine/core/backfill.py#L1)*

- **CacheBackend protocol:** get/set/delete/exists/clear with TTL
    - **InMemoryCache:** Bounded LRU cache with TTL expiration
    - **RedisCache:** Redis-backed distributed cache
    - **JSON values:** Keys are strings, values are JSON-serializable

*From [`cache.py`](spine-core/src/spine/core/cache.py#L1)*

- **Multi-backend:** SQLite (memory/file) and PostgreSQL
    - **URL normalization:** Handles sqlite:///, postgres://, postgresql://
    - **Schema initialization:** Optional init_schema=True
    - **ConnectionInfo:** Backend metadata (backend, persistent, url)
    - **Registry-based:** _BACKEND_REGISTRY for future backends

*From [`connection.py`](spine-core/src/spine/core/connection.py#L1)*

- Async connection pooling with asyncpg
    - URL normalization (SQLAlchemy dialect stripping)
    - SSL configuration support
    - Health check functionality
    - Graceful shutdown

*From [`database.py`](spine-core/src/spine/core/database.py#L1)*

- **SQLiteDialect:** ``?`` placeholders, ``datetime('now')``
    - **PostgreSQLDialect:** ``%s`` placeholders, ``NOW()``
    - **DB2Dialect:** ``?`` placeholders, ``CURRENT TIMESTAMP``
    - **MySQLDialect / OracleDialect:** Additional backends
    - **get_dialect():** Auto-detect dialect from connection object

*From [`dialect.py`](spine-core/src/spine/core/dialect.py#L1)*

- **VendorNamespace:** SEC, Bloomberg, FactSet, Reuters, OpenFIGI, etc.
    - **EventType:** M&A, bankruptcy, earnings, dividends, splits, etc.
    - **Jurisdiction / Market / InstrumentType:** Financial domain enums
    - **str Enum base:** All enums serialize to string naturally

*From [`enums.py`](spine-core/src/spine/core/enums.py#L1)*

- **ErrorCategory enum:** Standard categories for classification and routing
    - **ErrorContext dataclass:** Structured metadata (operation, source, URL, etc.)
    - **SpineError base class:** Common interface for all errors
    - **Transient errors:** Network, timeout, rate limit - usually retryable
    - **Source errors:** Upstream API/file errors - context-dependent retry
    - **Validation errors:** Schema/constraint violations - never retryable
    - **Config errors:** Missing/invalid settings - never retryable
    - **Auth errors:** Authentication/authorization - never retryable
    - **Operation/Orchestration errors:** Execution failures

*From [`errors.py`](spine-core/src/spine/core/errors.py#L1)*

- **Unique execution IDs:** UUID-based identifiers
    - **Parent-child linking:** child() method for sub-operations
    - **Batch correlation:** with_batch() and batch_id for grouping
    - **Timestamp tracking:** started_at for duration calculation
    - **Immutable design:** Methods return new contexts, don't mutate

*From [`execution.py`](spine-core/src/spine/core/execution.py#L1)*

- **compute_hash():** Generic hash from any values
    - **compute_record_hash():** OTC-specific record hash
    - **Configurable length:** Default 32 chars (128 bits)
    - **SHA-256 based:** Cryptographically sound

*From [`hashing.py`](spine-core/src/spine/core/hashing.py#L1)*

- **create_health_router():** One-liner K8s health endpoint setup
    - **HealthCheck:** Declarative dependency check definition
    - **CheckResult:** Per-dependency status with latency and error info
    - **HealthResponse:** Aggregated status with uptime and version
    - **SpineHealth:** Lightweight model for non-HTTP callers

*From [`health.py`](spine-core/src/spine/core/health.py#L1)*

- **check_postgres():** PostgreSQL connectivity via asyncpg
    - **check_redis():** Redis PING via aioredis
    - **check_ollama():** Ollama API /api/tags via httpx
    - **check_elasticsearch():** ES cluster health via httpx
    - **Composable:** Use functools.partial to bind URLs at startup

*From [`health_checks.py`](spine-core/src/spine/core/health_checks.py#L1)*

- Structured JSON output for Elasticsearch ingestion
    - Context propagation (workflow, run_id, request_id)
    - Service-level metadata
    - Elasticsearch-compatible field names (@timestamp, log.level)
    - Colored console output for development
    - Fallback to stdlib logging if structlog unavailable

*From [`logging.py`](spine-core/src/spine/core/logging.py#L1)*

- **Stage tracking:** Advance through stages with advance_to()
    - **Progress checks:** is_at_least() for idempotent stage gates
    - **Metrics storage:** row_count, custom metrics per stage
    - **Execution lineage:** execution_id, batch_id correlation
    - **Event hooks:** Optional on_stage_change for future event emission

*From [`manifest.py`](spine-core/src/spine/core/manifest.py#L1)*

- **Connection:** Sync DB protocol (execute, fetchone, fetchall, commit)
    - **AsyncConnection:** Async DB protocol for advanced tier adapters
    - **StorageBackend:** Connection lifecycle + transaction management
    - **DispatcherProtocol:** Event/task dispatch contract for decoupled messaging
    - **OperationProtocol:** Data operation contract for operation steps
    - **ExecutorProtocol:** Task executor contract for scheduled/queued work

*From [`protocols.py`](spine-core/src/spine/core/protocols.py#L1)*

- **QualityCheck:** Declarative check definition
    - **QualityRunner:** Execute checks and record results
    - **QualityStatus:** PASS/WARN/FAIL status enum
    - **QualityCategory:** INTEGRITY/COMPLETENESS/BUSINESS_RULE
    - **Quality gates:** has_failures(), failures() for gating

*From [`quality.py`](spine-core/src/spine/core/quality.py#L1)*

- **Reject dataclass:** Structured reject with stage, reason, raw data
    - **RejectSink:** Write single or batch rejects to core_rejects
    - **Lineage tracking:** execution_id, batch_id, source_locator
    - **Pattern analysis:** reason_code for aggregation
    - **Debugging:** raw_data preserved as JSON

*From [`rejects.py`](spine-core/src/spine/core/rejects.py#L1)*

- **14 repository classes:** One per domain table/aggregate
    - **Consistent API:** list() returns (list[dict], int) tuples
    - **Factory helpers:** _xxx_repo(ctx) pattern for ops modules
    - **Dialect portability:** All SQL via BaseRepository helpers

*From [`repositories.py`](spine-core/src/spine/core/repositories.py#L1)*

- **execute():** Raw SQL execution with params
    - **query() / query_one():** Return dicts for ergonomic access
    - **insert() / insert_many():** Typed INSERT with dict data
    - **ph():** Dialect placeholder shorthand (``self.ph(3)`` → ``?, ?, ?``)

*From [`repository.py`](spine-core/src/spine/core/repository.py#L1)*

- **Type-safe success/failure:** Ok[T] and Err[T] with pattern matching
    - **Functional combinators:** map, flat_map, or_else for chaining
    - **Safe value extraction:** unwrap_or, unwrap_or_else for defaults
    - **Batch collection:** collect_results, collect_all_errors, partition_results
    - **Conversion utilities:** from_optional, from_bool, try_result

*From [`result.py`](spine-core/src/spine/core/result.py#L1)*

- **purge_all():** Run purge on all purgeable tables with one call
    - **RetentionConfig:** Per-table retention period configuration
    - **RetentionReport:** Aggregated results with error tracking
    - **purge_table():** Low-level single-table purge with dialect support
    - **get_table_counts():** Pre/post purge monitoring

*From [`retention.py`](spine-core/src/spine/core/retention.py#L1)*

- **RollingWindow:** Generic rolling window computation
    - **RollingResult:** Structured result with completeness tracking
    - **compute_trend():** Trend direction from first/last N values
    - **Works with any temporal type:** WeekEnding, date, etc.

*From [`rolling.py`](spine-core/src/spine/core/rolling.py#L1)*

- **CORE_TABLES:** Dict mapping logical names to table names
    - **CORE_DDL:** Dict of CREATE TABLE statements
    - **Indexes:** Pre-defined for common query patterns
    - **create_tables():** Helper to create all tables

*From [`schema.py`](spine-core/src/spine/core/schema.py#L1)*

- **load_schema():** Apply a .sql file to a connection
    - **Multi-statement:** Splits by semicolons and executes sequentially
    - **Idempotent:** CREATE TABLE IF NOT EXISTS pattern

*From [`schema_loader.py`](spine-core/src/spine/core/schema_loader.py#L1)*

- **SpineBaseSettings:** Base class with host, port, debug, log_level, data_dir
    - **env_prefix:** Per-spine environment variable namespacing
    - **.env file support:** Automatic loading via pydantic-settings
    - **Extra ignore:** Unknown env vars don't cause startup failures

*From [`settings.py`](spine-core/src/spine/core/settings.py#L1)*

- **Connection protocol:** execute, executemany, fetchone, fetchall, commit
    - **StorageBackend protocol:** transaction(), get_connection()
    - **SyncPgAdapter pattern:** Example adapter for async drivers
    - **SQLHelper:** Cross-dialect SQL generation

*From [`storage.py`](spine-core/src/spine/core/storage.py#L1)*

- **TagGroup:** Named dimension with values (topics, tickers, etc.)
    - **TagGroupSet:** Collection of orthogonal tag dimensions
    - **Taggable:** Protocol for anything that can be tagged
    - **TaggableContent:** Mixin that adds tagging to any content class
    - **Similarity matching:** matches() for content-based discovery

*From [`taggable.py`](spine-core/src/spine/core/taggable.py#L1)*

- **TemporalEnvelope:** 4-timestamp wrapper for any payload
    - **BiTemporalRecord:** Full bi-temporal support (valid + system axes)
    - **effective_time default:** Falls back to event_time when unset
    - **Replay-safe:** ingest_time reflects re-ingest, not original capture
    - **stdlib-only:** No Pydantic dependency

*From [`temporal_envelope.py`](spine-core/src/spine/core/temporal_envelope.py#L1)*

- **ULID generation:** Time-sortable, 26-char, Crockford base32
    - **UTC utilities:** utc_now(), to_iso8601(), from_iso8601()
    - **stdlib-only:** No external dependencies
    - **Deterministic ordering:** ULIDs sort by creation time

*From [`timestamps.py`](spine-core/src/spine/core/timestamps.py#L1)*

- **VersionedContent:** Content with immutable version history
    - **ContentVersion:** Single snapshot with version number and source
    - **ContentType:** Enum (NEWS_HEADLINE, SEC_FILING, LLM_PROMPT, etc.)
    - **ContentSource:** Who created this version (HUMAN, LLM, SYSTEM)
    - **Content hashing:** SHA-256 fingerprint per version for dedup

*From [`versioned_content.py`](spine-core/src/spine/core/versioned_content.py#L1)*

- **Watermark dataclass:** Frozen high-water mark per (domain, source, key)
    - **WatermarkStore:** advance(), get(), list_gaps() with DB or memory backend
    - **Forward-only:** Monotonic advancement prevents duplicate processing
    - **Gap detection:** Compare expected vs actual partitions
    - **WatermarkGap:** Feeds into BackfillPlan for structured recovery

*From [`watermarks.py`](spine-core/src/spine/core/watermarks.py#L1)*

- Abstract ``connect()``, ``disconnect()``, ``execute()``, ``query()``
    - Property-based dialect and connection-state introspection
    - Context-manager protocol for connection lifecycle
    - Config-driven construction from ``DatabaseConfig``

*From [`base.py`](spine-core/src/spine/core/adapters/base.py#L1)*

- Connection pooling with configurable pool_size
    - SSL mode selection (prefer, require, disable)
    - Import-guarded: psycopg2 loaded at ``connect()`` time only
    - Compatible with TimescaleDB extensions

*From [`postgresql.py`](spine-core/src/spine/core/adapters/postgresql.py#L1)*

- ``AdapterRegistry`` singleton with pre-registered defaults
    - ``register()`` for custom / third-party adapters
    - ``get_adapter()`` factory: type + config → connected adapter

*From [`registry.py`](spine-core/src/spine/core/adapters/registry.py#L1)*

- In-memory and file-based databases
    - Read-only mode for safe query workloads
    - WAL mode enabled by default for concurrent reads
    - Context-manager connection lifecycle

*From [`sqlite.py`](spine-core/src/spine/core/adapters/sqlite.py#L1)*

- ``DatabaseType`` enum: SQLITE, POSTGRESQL, DB2, MYSQL, ORACLE
    - ``DatabaseConfig`` dataclass: union of all backend connection fields
    - Validation via ``validate()`` method with backend-specific rules

*From [`types.py`](spine-core/src/spine/core/adapters/types.py#L1)*

- ``create_database_engine()`` — SQLAlchemy engine from settings
    - ``create_scheduler_backend()`` — Thread / APScheduler / Celery
    - ``create_cache_client()`` — InMemory / Redis cache
    - ``create_worker_executor()`` — Thread / Process / Celery executor
    - ``create_event_bus()`` — InMemory / Redis event bus

*From [`factory.py`](spine-core/src/spine/core/config/factory.py#L1)*

### Ok

- **Type inspection:** is_ok(), is_err() for runtime checking
    - **Safe extraction:** unwrap(), unwrap_or(), unwrap_or_else()
    - **Value transformation:** map() for simple transforms
    - **Result chaining:** flat_map()/and_then() for fallible operations
    - **Side effects:** inspect() for logging/debugging without unwrapping
    - **Serialization:** to_dict() for JSON conversion

*From [`Ok`](spine-core/src/spine/core/result.py#L140)*

### QualityRunner

- **Fluent API:** runner.add(check1).add(check2)
    - **Batch execution:** run_all() executes all checks
    - **Persistence:** Results recorded to core_quality table
    - **Quality gates:** has_failures(), failures()
    - **Context flow:** execution_id, batch_id for lineage

*From [`QualityRunner`](spine-core/src/spine/core/quality.py#L281)*

### RejectSink

- **Single writes:** write() for one reject at a time
    - **Batch writes:** write_batch() for efficiency
    - **Count tracking:** count property for metrics
    - **Lineage:** execution_id, batch_id correlation
    - **JSON serialization:** raw_data stored as JSON

*From [`RejectSink`](spine-core/src/spine/core/rejects.py#L195)*

### RollingWindow

- **Generic over time type:** Works with WeekEnding, date, etc.
    - **Custom step_back:** Define how to move to previous period
    - **Completeness tracking:** Know how many periods had data
    - **Separation of concerns:** Fetch and aggregate are separate
    - **Composable:** Reuse window definition with different aggregations

*From [`RollingWindow`](spine-core/src/spine/core/rolling.py#L178)*

### SpineError

- **Category-based classification:** Routes to correct alerting channel
    - **Retry semantics:** Automatic retry decisions based on retryable flag
    - **Fluent context API:** Chain with_context() calls
    - **JSON serialization:** to_dict() for structured logging
    - **Error chaining:** cause attribute and __cause__ for tracebacks

*From [`SpineError`](spine-core/src/spine/core/errors.py#L387)*

### WeekEnding

- **Validation:** Non-Fridays raise ValueError with helpful message
    - **Multiple inputs:** Accepts str, date, or WeekEnding (idempotent)
    - **Factory methods:** from_any_date(), today(), last_n()
    - **Navigation:** previous(), next(), window()
    - **Iteration:** range() generates all Fridays between two dates
    - **Comparison:** Full ordering support (<, <=, >, >=)
    - **Immutable:** Frozen dataclass with slots

*From [`WeekEnding`](spine-core/src/spine/core/temporal.py#L72)*

### WorkManifest

- **UPSERT semantics:** advance_to() creates or updates stage row
    - **Rank comparison:** is_at_least() uses stage ordering
    - **Metrics storage:** row_count, custom JSON metrics per stage
    - **Execution lineage:** execution_id, batch_id correlation
    - **Event hooks:** Optional on_stage_change for future use

*From [`WorkManifest`](spine-core/src/spine/core/manifest.py#L223)*

## Execution Engine

### CeleryExecutor

- Distributed execution across workers
- Priority queues (realtime, high, normal, low, slow)
- Lane-based routing (gpu, cpu, io-bound)
- Retries with exponential backoff
- Result backend for status/results
- Monitoring via Flower

Requires:
- pip install celery[redis]
- Redis/RabbitMQ broker running
- Celery workers running

Example:
    >>> from celery import Celery
    >>>
    >>> app = Celery('spine', broker='redis://localhost:6379/0')
    >>> executor = CeleryExecutor(app)
    >>> ref = await executor.submit(task_spec("send_email", {"to": "user@example.com"}))
    >>> # ref is the Celery task_id

Worker setup (separate process):
    >>> # In your Celery app module, register the spine executor task:
    >>> @app.task(name="spine.execute.task")
    >>> def execute_task(name: str, params: dict, **kwargs):
    ...     handler = registry.get("task", name)
    ...     return handler(params)

*From [`CeleryExecutor`](spine-core/src/spine/execution/executors/celery.py#L56)*

### LocalExecutor

- Async/non-blocking submission
- Configurable worker count
- Cancellation support (for pending work)

Example:
    >>> def process_data(params):
    ...     return {"processed": len(params["data"])}
    >>>
    >>> executor = LocalExecutor(max_workers=4)
    >>> executor.register_handler("task", "process", process_data)
    >>> ref = await executor.submit(task_spec("process", {"data": [1,2,3]}))

*From [`LocalExecutor`](spine-core/src/spine/execution/executors/local.py#L39)*

## Orchestration

### TrackedWorkflowRunner

- Progress tracking in core_manifest (one row per stage)
- Error recording in core_anomalies
- Idempotency via manifest checks (skip if already completed)
- Automatic retry from last successful stage

This extends the basic WorkflowRunner with persistence.

*From [`TrackedWorkflowRunner`](spine-core/src/spine/orchestration/tracked_runner.py#L83)*

## Observability

- JSON formatted output (machine-readable)
- Correlation IDs for request tracing
- Context propagation (request_id, user_id, etc.)
- Standard fields (timestamp, level, logger, message)
- Exception formatting with stack traces
- Performance timing helpers

Example:
    >>> from spine.observability.logging import get_logger, configure_logging
    >>>
    >>> configure_logging(level="INFO", json_output=True)
    >>> logger = get_logger("my.module")
    >>>
    >>> logger.info("Processing started", operation="sec.filings", records=100)
    >>> # Output: {"timestamp": "2024-01-01T00:00:00Z", "level": "INFO", ...}

*From [`logging.py`](spine-core/src/spine/observability/logging.py#L1)*

## Tooling

### ChangelogGenerator

- 4-stage operation: Scan → Parse → Merge → Render
    - Keep-a-Changelog format with auto-categorization
    - Commit review document mirroring REWRITE_COMMIT_REVIEW.md format
    - API module index grouped by Doc-Type, Tier, Stability
    - Mermaid diagram extraction from docstrings and sidecars
    - Fixture-based testing mode (no git dependency)

*From [`ChangelogGenerator`](spine-core/src/spine/tools/changelog/generator.py#L59)*

### DocHeader

- Controlled vocabularies for Stability, Tier, Doc-Types
    - Frozen dataclass — immutable after parsing
    - Preserves raw text for downstream rendering
    - AST-based extraction without importing target modules

*From [`DocHeader`](spine-core/src/spine/tools/changelog/model.py#L118)*

---

*275 features documented across 5 packages*