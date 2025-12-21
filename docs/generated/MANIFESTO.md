# MANIFESTO

**Core Principles and Philosophy**

> **Auto-generated from code annotations**  
> **Last Updated**: February 2026  
> **Status**: Living Document

---

## Table of Contents

1. [Core Primitives](#core-primitives)
2. [Framework & Configuration](#framework--configuration)
3. [Execution Engine](#execution-engine)
4. [Orchestration](#orchestration)
5. [API Layer](#api-layer)
6. [Tooling](#tooling)

---

## Core Primitives

### AnomalyCategory

Categories answer "what type of problem?" while severity answers
    "how bad is it?". Together they enable smart routing and analysis.
    The UNKNOWN category is a catch-all for edge cases that should
    be investigated and properly categorized.

*Source: [`AnomalyCategory`](spine-core/src/spine/core/anomalies.py#L176)*

### AnomalyRecorder

Production operations encounter many issues that aren't fatal:
    quality warnings, transient network errors, data format anomalies.
    These need to be recorded for audit, classified for routing, and
    tracked to resolution. AnomalyRecorder is the single entry point
    for all such issues in the Spine ecosystem.

    Key principles:
    - **Immutability:** Anomalies are NEVER deleted (audit trail)
    - **Classification:** Severity + Category enable smart routing
    - **Resolution:** Mark resolved, don't delete
    - **Correlation:** execution_id links to operation runs

*Source: [`AnomalyRecorder`](spine-core/src/spine/core/anomalies.py#L241)*

### AsyncConnection

While domain code stays sync (via Connection), infrastructure and
    API layers often need native async. AsyncConnection provides that
    contract without forcing sync adapters on inherently async code.

*Source: [`AsyncConnection`](spine-core/src/spine/core/protocols.py#L164)*

### Connection

Domain code should never deal with async complexity. By defining
    a sync protocol, we:
    - Keep domain logic simple and testable
    - Enable portability across deployment tiers
    - Push async wrapping to infrastructure

    The same domain code runs on SQLite (Basic tier) and PostgreSQL
    (Intermediate/Advanced/Full tiers) without modification.

*Source: [`Connection`](spine-core/src/spine/core/protocols.py#L84)*

### Err

- **Error as a value:** Errors are first-class values, not control flow
    - **Propagation without throwing:** Err flows through map chains unchanged
    - **Rich context:** Prefer SpineError with category, retryable, context
    - **Recovery points:** or_else() provides structured error recovery

*Source: [`Err`](spine-core/src/spine/core/result.py#L299)*

### ErrorCategory

- **Routing by category:** Alerts go to right team (infra vs app)
    - **Retry heuristics:** Category suggests default retry behavior
    - **Consistent classification:** Same categories across all spine projects
    - **String enum:** Category values are human-readable strings

*Source: [`ErrorCategory`](spine-core/src/spine/core/errors.py#L142)*

### ErrorContext

- **Structured over ad-hoc:** Typed fields for common metadata
    - **Extensible:** metadata dict for custom fields
    - **Serialization-ready:** to_dict() for logging/JSON
    - **Optional fields:** Only set what's relevant

*Source: [`ErrorContext`](spine-core/src/spine/core/errors.py#L253)*

### ExecutionContext

- **Identity:** Every execution has a unique execution_id
    - **Lineage:** Parent-child relationships via parent_execution_id
    - **Batch correlation:** Related executions share batch_id
    - **Timestamp:** started_at enables duration calculation
    - **Copy semantics:** Methods return new contexts, preserving immutability

*Source: [`ExecutionContext`](spine-core/src/spine/core/execution.py#L121)*

### IdempotencyHelper

The delete+insert pattern is deceptively simple but easy to get wrong:
    - Delete must use exact logical key (not partial matches)
    - Delete and insert must be in same transaction
    - Key columns must match between delete and insert

    IdempotencyHelper encapsulates these patterns with a clean API:
    - hash_exists(): L2 pattern - check before insert
    - delete_for_key(): L3 pattern - delete by logical key
    - get_existing_hashes(): Batch L2 - preload for bulk checks

*Source: [`IdempotencyHelper`](spine-core/src/spine/core/idempotency.py#L156)*

### IdempotencyLevel

Not all operations need the same idempotency guarantees. Raw capture
    operations (L1) can append freely because downstream layers handle dedup.
    Bronze layers (L2) use hash-based dedup to avoid re-processing identical
    source data. Silver/Gold layers (L3) use delete+insert to ensure re-runs
    produce exactly the same final state.

    Explicitly declaring idempotency level:
    - Documents operation behavior for operators
    - Enables framework-level safety checks
    - Guides monitoring and alerting (L1 re-run: normal, L3 re-run: investigate)

*Source: [`IdempotencyLevel`](spine-core/src/spine/core/idempotency.py#L78)*

### LogicalKey

Financial data has natural keys: (week_ending, tier), (accession_number),
    (cik, form_type, filed_date). These keys are meaningful to the business
    and stable across systems. LogicalKey:
    - Makes natural keys first-class citizens
    - Provides WHERE clause generation
    - Enables key-based operations (delete, lookup)
    - Documents what makes a record unique

*Source: [`LogicalKey`](spine-core/src/spine/core/idempotency.py#L286)*

### ManifestRow

Each stage in a operation needs to track:
    - **What:** stage name and rank for ordering
    - **When:** updated_at timestamp
    - **How much:** row_count for volume tracking
    - **Metrics:** custom JSON metrics per stage
    - **Lineage:** execution_id, batch_id for tracing

    ManifestRow is an immutable snapshot of this information,
    returned by WorkManifest.get() for each stage.

*Source: [`ManifestRow`](spine-core/src/spine/core/manifest.py#L140)*

Financial operations encounter many issues that aren't fatal:
    - Quality threshold warnings
    - Transient network errors
    - Data format anomalies
    - Step execution failures

    These need to be:
    - **Recorded:** Persistent audit trail in core_anomalies table
    - **Classified:** Severity and category for routing
    - **Resolvable:** Mark anomalies as resolved when addressed
    - **Queryable:** Find open issues for investigation

    Anomalies are NEVER deleted - they form a permanent audit trail.

*Source: [`anomalies.py`](spine-core/src/spine/core/anomalies.py#L1)*

spine-core processes SEC filings, financial data, and portfolio metrics.
    Without asset tracking, you can answer "did the operation run?" but not
    "is the 10-K data for AAPL fresh?" or "what produced this filing record?"

    - **Data as first-class citizen:** Track artifacts alongside executions
    - **Composable keys:** Hierarchical naming (("sec", "filings", "10-K"))
    - **Materialization vs Observation:** Production vs freshness monitoring
    - **Partition-aware:** Incremental materialization by CIK, date, sector

*Source: [`assets.py`](spine-core/src/spine/core/assets.py#L1)*

Financial data has strict completeness requirements. If an SEC EDGAR
    crawl misses Q3 filings for 200 companies, downstream models,
    compliance reports, and client queries break. Backfill plans capture
    *what* is missing, *why*, and *how far* recovery has progressed:

    - **Structured recovery:** BackfillPlan captures partition_keys, reason, progress
    - **Crash safety:** Checkpoint-based resume for multi-hour backfills
    - **Audit trail:** Reason enum (GAP, CORRECTION, SCHEMA_CHANGE, QUALITY_FAILURE)
    - **Progress visibility:** completed_keys, failed_keys, progress_pct

*Source: [`backfill.py`](spine-core/src/spine/core/backfill.py#L1)*

Caching is a cross-cutting concern that every spine needs. Without
    a shared abstraction, each project implements its own cache with
    inconsistent APIs, no TTL support, and no backend portability.

    - **Protocol-based:** CacheBackend defines the contract
    - **Tier-aware:** InMemoryCache for dev, RedisCache for production
    - **TTL support:** Time-based expiration for all backends
    - **Zero config:** InMemoryCache works out of the box

*Source: [`cache.py`](spine-core/src/spine/core/cache.py#L1)*

Every module that needs a database connection should use
    ``create_connection()`` rather than importing backend-specific
    classes directly. This ensures:

    - **Single entry point:** One function for all backends
    - **URL-driven:** Backend selected by URL scheme, not code changes
    - **Extensible:** New backends added to _BACKEND_REGISTRY
    - **Schema init:** Optional create_tables() on connection

*Source: [`connection.py`](spine-core/src/spine/core/connection.py#L1)*

Database connections are expensive (TCP handshake, auth, TLS).
    A connection pool maintains warm connections ready for use.
    This module provides:

    - **Pooling:** Efficient connection reuse across requests
    - **Normalization:** URL format handling for asyncpg compatibility
    - **Lifecycle:** Clean pool creation and shutdown
    - **Monitoring:** Connection pool health checks

    Every spine that needs PostgreSQL should use spine.core.database.

*Source: [`database.py`](spine-core/src/spine/core/database.py#L1)*

Domain code must be portable across SQLite, PostgreSQL, DB2, MySQL,
    and Oracle. Without a dialect layer, SQL fragments are littered with
    backend-specific syntax that breaks when switching tiers.

    - **One interface:** Dialect protocol for all SQL generation
    - **Zero coupling:** Domain code never imports database drivers
    - **Auto-detection:** get_dialect(conn) chooses the right dialect
    - **Testable:** SQLiteDialect for tests, PostgreSQLDialect for prod

*Source: [`dialect.py`](spine-core/src/spine/core/dialect.py#L1)*

Domain enums (vendor namespaces, event types, jurisdictions) are
    shared vocabulary across the ecosystem. Without a canonical home,
    each spine defines its own copies, leading to drift and breakage.
    This module is the single source of truth for cross-spine enums.

*Source: [`enums.py`](spine-core/src/spine/core/enums.py#L1)*

- **Typed Error Hierarchy:** Different error types for different domains
    - **Explicit Retry Semantics:** Each error knows if it's retryable
    - **Rich Context:** Errors carry metadata for logging and alerting
    - **Error Chaining:** Preserve original exceptions while adding context

*Source: [`errors.py`](spine-core/src/spine/core/errors.py#L1)*

- **Every execution gets an ID:** Unique identifier for tracing
    - **Parent-child linking:** Sub-operations link to their parent
    - **Batch correlation:** Related executions share batch_id
    - **Immutable context:** Context is copied, not mutated

*Source: [`execution.py`](spine-core/src/spine/core/execution.py#L1)*

Feature flags are essential for production deployments:
    - **Safe rollouts:** Enable features for subset of users/environments
    - **Kill switches:** Disable problematic features without redeployment
    - **Environment-aware:** Different flags for dev/staging/production
    - **Zero dependencies:** No external service required for basic usage

    Spine's approach is deliberately simple:
    - In-memory registry with optional persistence
    - Environment variable overrides (SPINE_FF_<FLAG_NAME>=true/false)
    - Type-safe flag definitions via dataclass
    - Thread-safe operations for concurrent access

*Source: [`feature_flags.py`](spine-core/src/spine/core/feature_flags.py#L1)*

Data operations need stable identifiers that survive re-processing:
    - **Natural key hash:** Identify records by business key
    - **Content hash:** Detect when record data has changed
    - **Deterministic:** Same inputs always produce same hash
    - **Collision-resistant:** Different inputs produce different hashes

    compute_hash() provides the foundation - a simple, deterministic SHA-256
    based hash that works with any combination of values.

*Source: [`hashing.py`](spine-core/src/spine/core/hashing.py#L1)*

Every Spine service must expose K8s-style health endpoints for
    container orchestration, load balancers, and monitoring. Without
    standardized health checks, each service invents its own format,
    breaking monitoring dashboards and alerting rules.

    - **Liveness:** "Is the process alive?" (always yes if responding)
    - **Readiness:** "Can I serve traffic?" (all required deps healthy)
    - **Health summary:** Aggregated status with per-check details

*Source: [`health.py`](spine-core/src/spine/core/health.py#L1)*

Health checks are the bridge between infrastructure dependencies
    and the health router. Each check is a pure async function that
    probes a single dependency — easy to test, easy to compose.

*Source: [`health_checks.py`](spine-core/src/spine/core/health_checks.py#L1)*

Financial data operations must be re-runnable without creating duplicates.
    When a operation fails halfway through a 6-week backfill, operators need to
    re-run it safely. Without idempotency, re-runs create:
    - Duplicate records (inflate volumes)
    - Conflicting versions (which is correct?)
    - Failed constraints (unique violations)

    spine-core defines three idempotency levels:

    **L1_APPEND:** Raw capture layer. Always insert, let downstream dedup.
        Use case: Audit logs, event streams, raw API responses

    **L2_INPUT:** Hash-based dedup. Same input hash → skip insert.
        Use case: Bronze layer where source data has no natural key

    **L3_STATE:** Delete + insert. Same logical key → delete old, insert new.
        Use case: Aggregations, derived tables, any table with natural keys

*Source: [`idempotency.py`](spine-core/src/spine/core/idempotency.py#L1)*

Observability is critical for financial data operations. This module
    provides structured logging that:

    - **Standardizes:** Same log format across all spines
    - **Structures:** JSON output for log aggregation (ELK, etc.)
    - **Correlates:** execution_id, batch_id propagation
    - **Flexes:** Console output for development, JSON for production

    Every spine should use spine.core.logging for consistency.

*Source: [`logging.py`](spine-core/src/spine/core/logging.py#L1)*

Financial data operations have multiple stages: ingest, normalize,
    aggregate, publish. Each stage must be tracked to support:

    - **Idempotent restarts:** Know where to resume after failure
    - **Progress monitoring:** Dashboard visibility into operation state
    - **Metrics collection:** Row counts, timing, quality metrics per stage
    - **Audit trail:** When stages completed, by which execution

    WorkManifest is the single source of truth for "where is this
    work item in the operation?" It uses a current-state table design
    (one row per stage per partition) optimized for fast lookups.

*Source: [`manifest.py`](spine-core/src/spine/core/manifest.py#L1)*

Protocols define contracts without inheritance. They enable:
    - **Decoupling:** Modules depend on shape, not implementation
    - **Testability:** Any object matching the protocol works
    - **Portability:** Same domain code on SQLite, PostgreSQL, async drivers

    Before this module existed, Connection(Protocol) was duplicated in 9 files
    (~400 LOC of pure duplication). Now there is ONE definition, ONE docstring,
    ONE place to evolve the contract.

*Source: [`protocols.py`](spine-core/src/spine/core/protocols.py#L1)*

Data quality is critical for financial operations. Bad data leads to bad
    decisions. The quality framework provides:

    - **Declarative checks:** Define what to check, not how to check it
    - **Audit trail:** All checks recorded with results and context
    - **Quality gates:** Stop processing if critical checks fail
    - **Composable:** Add/remove checks without code changes

    Checks are non-blocking by default: they record issues but don't stop
    processing. Use has_failures() for explicit quality gates.

*Source: [`quality.py`](spine-core/src/spine/core/quality.py#L1)*

Financial data operations encounter invalid records:
    - Invalid symbols (BAD$YM)
    - Negative volumes
    - Missing required fields
    - Format mismatches

    These records must be:
    - **Captured:** Don't lose the data, store for investigation
    - **Classified:** Stage + reason_code for pattern analysis
    - **Traceable:** Lineage via execution_id, source_locator
    - **Debuggable:** Raw data preserved for reproduction

    Rejects are NEVER deleted - they form an audit trail of
    data quality issues for compliance and debugging.

*Source: [`rejects.py`](spine-core/src/spine/core/rejects.py#L1)*

Raw SQL scattered across ops modules is unmaintainable, untestable,
    and dialect-dependent. Repositories centralize data access:

    - **Typed methods:** create(), list(), update() with clear signatures
    - **Dialect-aware:** SQL generated via Dialect, not hardcoded
    - **Testable:** Mock at repository boundary, not SQL strings
    - **Auditable:** One place per table for all SQL operations

*Source: [`repositories.py`](spine-core/src/spine/core/repositories.py#L1)*

Repositories need a consistent set of DB helpers. Without a base class,
    each repository reimplements execute(), query(), insert() with subtle
    differences. BaseRepository provides:

    - **Dialect-aware:** SQL generation via Dialect protocol
    - **Standard API:** execute, query, query_one, insert, insert_many
    - **Connection pairing:** Each repo instance gets a connection at construction
    - **Portable:** Works with SQLite, PostgreSQL, or any Dialect implementation

*Source: [`repository.py`](spine-core/src/spine/core/repository.py#L1)*

- **Explicit over Implicit:** No hidden exceptions that callers might miss
    - **Fail-fast discovery:** Type checker catches unhandled error paths
    - **Functional composition:** Chain operations with map/flat_map without
      nested try/except blocks
    - **Batch-friendly:** Collect results from many operations, handle errors
      at the end using collect_results() or partition_results()

*Source: [`result.py`](spine-core/src/spine/core/result.py#L1)*

Core infrastructure tables (executions, rejects, quality, anomalies)
    grow unbounded without active retention management. Financial compliance
    requires minimum retention periods, but keeping data forever increases
    storage costs and slows queries. This module provides:

    - **Configurable retention:** Per-table retention periods (days)
    - **Safe purging:** Only deletes records past retention window
    - **Audit-aware:** Respects compliance minimums (e.g., 180 days for anomalies)
    - **Reporting:** RetentionReport with per-table results and errors

*Source: [`retention.py`](spine-core/src/spine/core/retention.py#L1)*

Financial analysis requires window functions: "What's the average volume
    over the last 6 weeks?" "Is the trend up or down?" "Did we have data for
    all periods?"

    RollingWindow encapsulates this pattern:
    - **Generic over time:** Works with WeekEnding, date, month, etc.
    - **Completeness tracking:** Know if window has gaps
    - **Separation of concerns:** Fetch data, aggregate separately
    - **Trend detection:** Built-in UP/DOWN/FLAT classification

*Source: [`rolling.py`](spine-core/src/spine/core/rolling.py#L1)*

Financial data workflows share common infrastructure needs:
    - **Manifest:** Track workflow stage progression
    - **Rejects:** Store validation failures for audit
    - **Quality:** Record quality check results
    - **Anomalies:** Log errors and warnings
    - **Executions:** Workflow execution ledger

    Rather than each domain creating its own tables, we share
    infrastructure tables partitioned by domain name. This:
    - Reduces schema proliferation
    - Enables cross-domain queries (all rejects, all anomalies)
    - Simplifies maintenance and migrations

*Source: [`schema.py`](spine-core/src/spine/core/schema.py#L1)*

Schema loading is the bridge between SQL files and database state.
    This module handles simple apply-once schemas for development and
    testing. Production deployments should use tracked migrations.

*Source: [`schema_loader.py`](spine-core/src/spine/core/schema_loader.py#L1)*

Hardcoded secrets are a security anti-pattern:
    - **Source control exposure:** Secrets in code get committed
    - **Environment coupling:** Different credentials per environment
    - **Rotation pain:** Changing secrets requires code changes

    Spine's secrets resolver provides:
    - **Pluggable backends:** Env vars, files, Vault, AWS, etc.
    - **Unified interface:** `resolve_secret(key)` works everywhere
    - **Layered resolution:** Try multiple backends in order
    - **Reference syntax:** `secret:env:DB_PASSWORD` for explicit backend

*Source: [`secrets.py`](spine-core/src/spine/core/secrets.py#L1)*

Configuration should be explicit, validated, and environment-driven.
    Without a shared base, each spine reinvents settings with inconsistent
    field names, missing validation, and no .env support.

    - **Pydantic validation:** Type-checked at startup, not runtime
    - **Environment-driven:** Reads from env vars and .env files
    - **Hierarchical:** Each spine adds its own prefix (GENAI_, SEARCH_, etc.)
    - **Sensible defaults:** Works out of the box for development

*Source: [`settings.py`](spine-core/src/spine/core/settings.py#L1)*

Spine domains must be portable across deployment tiers:
    - Basic: SQLite for single-machine development
    - Intermediate: PostgreSQL for production
    - Advanced/Full: Async PostgreSQL with connection pooling

    This module provides a SYNCHRONOUS protocol that all tiers implement.
    Higher tiers wrap their async drivers (asyncpg) in sync adapters.

    Key principles:
    - **Sync-only:** Domain code never sees async/await
    - **Protocol-based:** Duck typing via Protocol classes
    - **Tier-agnostic:** Same domain code on any tier

*Source: [`storage.py`](spine-core/src/spine/core/storage.py#L1)*

Content in the spine ecosystem needs multi-dimensional classification
    for discovery, filtering, and similarity matching. Without a shared
    tagging model, each project invents its own taxonomy with incompatible
    structures. TagGroupSet provides:

    - **Orthogonal dimensions:** Independent tag groups (topics, sectors, etc.)
    - **Faceted search:** Multiple independent filters on any axis
    - **Hierarchical taxonomies:** topic > subtopic nesting support
    - **Similarity matching:** Compare tagsets for content similarity

*Source: [`taggable.py`](spine-core/src/spine/core/taggable.py#L1)*

Financial data operations operate on institutional time cycles. FINRA publishes
    OTC transparency data every Friday. Market calendars follow weekly patterns.
    Using arbitrary dates leads to bugs: "Did we process 2025-12-25 (Thursday)?"

    WeekEnding solves this by making week boundaries explicit and validated:
    - Construction from non-Friday dates FAILS (explicit is better than implicit)
    - Use from_any_date() when you have an arbitrary date
    - All week comparisons, ranges, and iterations work correctly

*Source: [`temporal.py`](spine-core/src/spine/core/temporal.py#L1)*

In financial data, a single observation (e.g. Apple's Q3 EPS) may be
    *announced* (event_time), *published* by a vendor (publish_time),
    *ingested* by our operation (ingest_time), and *effective* for a
    reporting period (effective_time). Conflating these causes:

    - **Look-ahead bias:** Backtests use data before it was known
    - **Stale-data masking:** Corrections missed because timestamps overlap
    - **Source-vendor confusion:** Bloomberg vs FactSet timing differences

    TemporalEnvelope makes this distinction first-class, enabling replay,
    backfill, and PIT queries without per-project ad-hoc conventions.

*Source: [`temporal_envelope.py`](spine-core/src/spine/core/temporal_envelope.py#L1)*

Every spine needs unique IDs and UTC timestamps. Without a shared
    module, each project reinvents these with subtle differences
    (timezone handling, ID format, precision). This module provides:

    - **generate_ulid():** Time-sortable unique IDs (26-char, base32)
    - **utc_now():** Timezone-aware UTC datetime
    - **to_iso8601() / from_iso8601():** Safe serialization round-trip

*Source: [`timestamps.py`](spine-core/src/spine/core/timestamps.py#L1)*

Content evolves — headlines get corrected, prompts get refined,
    filing sections get restated. Without version history, the original
    context is lost, making audit trails impossible and debugging blind.

    - **Immutable history:** Every version is preserved, never overwritten
    - **Event sourcing:** Derive current state from version sequence
    - **Content-agnostic:** Works with any content type via ContentType enum
    - **Source tracking:** Who/what created each version (human, LLM, system)

*Source: [`versioned_content.py`](spine-core/src/spine/core/versioned_content.py#L1)*

Financial data sources publish continuously — SEC EDGAR, Polygon,
    Bloomberg. Without watermarks, a restart forces a full re-crawl,
    wasting API credits, time, and rate-limit headroom.

    Watermarks record the last-processed position per (domain, source,
    partition) tuple. On restart the operation reads its watermark and
    resumes from there. Key principles:

    - **Forward-only advancement:** Prevents accidental backward movement
    - **Gap detection:** ``list_gaps()`` flags missing partitions for audit
    - **Persistence-agnostic:** Database or in-memory (tests)
    - **Partition-aware:** Per-source, per-partition tracking

*Source: [`watermarks.py`](spine-core/src/spine/core/watermarks.py#L1)*

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

*Source: [`__init__.py`](spine-core/src/spine/core/__init__.py#L1)*

All database adapters share common lifecycle (connect/disconnect),
    query execution, and dialect management.  The abstract base class
    defines the interface contract so consumers never depend on a
    specific database vendor.

*Source: [`base.py`](spine-core/src/spine/core/adapters/base.py#L1)*

Enterprise and mainframe environments run DB2.  This adapter wraps
    ``ibm_db_dbi`` with the ``DatabaseAdapter`` interface so spine
    operations run identically on DB2 as on SQLite or PostgreSQL.

Uses ``ibm_db_dbi`` — the DB-API 2.0 interface from the ``ibm-db``
package.  DB2 uses **qmark** (``?``) placeholder style natively.

Install the driver::

    pip install ibm-db
    # or:  pip install spine-core[db2]

This adapter is import-guarded: if ``ibm_db`` is not installed a clear
:class:`~spine.core.errors.ConfigError` is raised at ``connect()`` time
rather than at import time.

*Source: [`db2.py`](spine-core/src/spine/core/adapters/db2.py#L1)*

Web-scale and cloud-native deployments often use MySQL or MariaDB.
    This adapter wraps ``mysql.connector`` with the ``DatabaseAdapter``
    interface so spine operations run identically across backends.

Uses ``mysql.connector`` from the ``mysql-connector-python`` package.
MySQL uses **format** (``%s``) placeholder style.

Install the driver::

    pip install mysql-connector-python
    # or:  pip install spine-core[mysql]

This adapter is import-guarded: if ``mysql.connector`` is not installed
a clear :class:`~spine.core.errors.ConfigError` is raised at
``connect()`` time.

*Source: [`mysql.py`](spine-core/src/spine/core/adapters/mysql.py#L1)*

Financial institutions and large enterprises often mandate Oracle.
    This adapter wraps ``oracledb`` (python-oracledb) with the
    ``DatabaseAdapter`` interface for seamless backend portability.

Uses ``oracledb`` (python-oracledb) — the modern Oracle DB driver that
supersedes ``cx_Oracle``.  Oracle uses **numeric** (``:1``, ``:2``)
placeholder style.

Install the driver::

    pip install oracledb
    # or:  pip install spine-core[oracle]

This adapter is import-guarded: if ``oracledb`` is not installed a
clear :class:`~spine.core.errors.ConfigError` is raised at
``connect()`` time.

*Source: [`oracle.py`](spine-core/src/spine/core/adapters/oracle.py#L1)*

PostgreSQL is the production-grade backend for multi-user, high-throughput
    spine deployments.  The adapter wraps ``psycopg2`` with connection pooling
    and SSL support while conforming to the ``DatabaseAdapter`` interface.

*Source: [`postgresql.py`](spine-core/src/spine/core/adapters/postgresql.py#L1)*

Consumers should never hard-code adapter class names.  The registry
    maps ``DatabaseType`` strings to adapter classes and the ``get_adapter()``
    factory creates a configured instance from a config dict or URL.

*Source: [`registry.py`](spine-core/src/spine/core/adapters/registry.py#L1)*

SQLite is the zero-dependency default for development, testing, and
    basic-tier production.  The adapter wraps stdlib ``sqlite3`` with the
    same ``DatabaseAdapter`` interface as PostgreSQL or DB2.

*Source: [`sqlite.py`](spine-core/src/spine/core/adapters/sqlite.py#L1)*

Centralise the enumeration of supported database backends and the
    connection parameter model so every adapter, factory, and registry
    speaks the same vocabulary.

*Source: [`types.py`](spine-core/src/spine/core/adapters/types.py#L1)*

Financial data operations must run identically on SQLite (dev), PostgreSQL
    (production), and sometimes DB2/Oracle (enterprise).  Without a common
    adapter interface, every operation embeds backend-specific SQL and connection
    logic -- making migrations between databases a multi-week project instead
    of a config change.

    Each adapter is **import-guarded**: the database driver is only required at
    ``connect()`` time, not at import time.  Install the corresponding extra::

        pip install spine-core[postgresql]   # psycopg2-binary
        pip install spine-core[db2]          # ibm-db
        pip install spine-core[mysql]        # mysql-connector-python
        pip install spine-core[oracle]       # oracledb

*Source: [`__init__.py`](spine-core/src/spine/core/adapters/__init__.py#L1)*

Each pluggable dimension (database, cache, scheduler, metrics, tracing,
    worker, events) has a finite set of supported backends.  Enumerating
    them as typed enums prevents typo-driven misconfigurations, and
    ``validate_component_combination()`` catches incompatible selections
    (e.g. Celery Beat requires Redis) before anything starts.

Each enum represents a pluggable backend dimension.  The
:func:`validate_component_combination` function checks that a set of
chosen backends is consistent (e.g. Celery-beat requires Redis).

*Source: [`components.py`](spine-core/src/spine/core/config/components.py#L1)*

Application code should declare *what* it needs (engine, scheduler, cache)
    without knowing *how* to construct those components.  ``SpineContainer``
    creates each component on first access using the factory layer, then
    caches it for the lifetime of the container.

:class:`SpineContainer` holds references to the major backend
components (database engine, scheduler, cache, worker executor) and
creates them on first access using the factory functions.

*Source: [`container.py`](spine-core/src/spine/core/config/container.py#L1)*

Each factory uses lazy imports so that optional heavy dependencies
    (``sqlalchemy``, ``redis``, ``celery``, …) are only loaded when the
    corresponding backend is actually selected.  This keeps
    ``import spine.core`` fast and dependency-free.

*Source: [`factory.py`](spine-core/src/spine/core/config/factory.py#L1)*

Configuration cascading must be predictable and debuggable.  This
    module implements a strict load order with no hidden magic: earlier
    values are overridden by later files, and real environment variables
    always win.

Implements the cascading load order::

    .env.base  →  .env.{tier}  →  .env.local  →  .env  →  real env vars

All parsing is pure-Python (no ``python-dotenv`` dependency).
Earlier values are overridden by later files, and real environment
variables always win.

*Source: [`loader.py`](spine-core/src/spine/core/config/loader.py#L1)*

Different environments (dev, staging, prod) need different settings,
    but copy-pasting full config files causes drift.  Profiles support
    single-key inheritance so a ``staging`` profile only overrides the
    fields that differ from ``production``.

Profiles live in ``~/.spine/profiles/`` (user scope) or
``<project>/.spine/profiles/`` (project scope).  Project-scoped
profiles take precedence over user-scoped ones.

*Source: [`profiles.py`](spine-core/src/spine/core/config/profiles.py#L1)*

One validated, cached settings object replaces the ad-hoc per-module
    settings classes that each parsed the same environment variables
    differently.  ``SpineCoreSettings`` cooperates with the env-file
    loader and TOML profiles to resolve values in a single place.

:class:`SpineCoreSettings` replaces the ad-hoc per-module settings
classes with a single, validated, cached source of truth.  It
cooperates with the :mod:`~spine.core.config.loader` (env-file
cascade) and :mod:`~spine.core.config.profiles` (TOML profiles) to
resolve values.

*Source: [`settings.py`](spine-core/src/spine/core/config/settings.py#L1)*

spine-core supports 3 deployment tiers (minimal/standard/full) with
    pluggable backends for database, cache, scheduler, metrics, and workers.
    Without centralized config, each module creates its own settings class
    and the same environment variable gets parsed 5 different ways.

    This package provides a **single validated source of truth** with:

    * **Component enums** -- ``DatabaseBackend``, ``SchedulerBackend``, etc.
    * **Environment-file loader** -- cascading ``.env`` discovery & parsing
    * **TOML profiles** -- inheritable configuration profiles
    * **Settings** -- validated ``SpineCoreSettings`` (Pydantic, cached)
    * **Factory functions** -- create engines, schedulers, cache clients
    * **DI container** -- :class:`SpineContainer` with lazy component init

Quick start::

    from spine.core.config import get_settings, SpineContainer

    settings = get_settings()
    print(settings.database_backend)   # DatabaseBackend.SQLITE
    print(settings.infer_tier())       # "minimal"

    with SpineContainer() as c:
        engine = c.engine

*Source: [`__init__.py`](spine-core/src/spine/core/config/__init__.py#L1)*

Single-process deployments and test suites need a zero-dependency event
    bus that delivers events immediately without external infrastructure.

Uses asyncio queues for single-node deployments. Events are processed
immediately and not persisted.

*Source: [`memory.py`](spine-core/src/spine/core/events/memory.py#L1)*

Multi-node deployments need events to cross process boundaries.
    Redis Pub/Sub provides fire-and-forget delivery with minimal latency
    and no schema overhead.

Uses Redis Pub/Sub for multi-node deployments. Events are delivered
asynchronously and not persisted (use Redis Streams for persistence).

Requires: ``pip install redis`` or ``spine-core[redis]``

*Source: [`redis.py`](spine-core/src/spine/core/events/redis.py#L1)*

Operation modules (ops, scheduling, execution) need to notify each other
    when things happen -- run completed, quality check failed, schedule fired.
    Without a shared event bus, modules either import each other directly
    (creating circular dependencies) or silently lose events.

    The ``EventBus`` protocol with pluggable backends (in-memory, Redis)
    decouples producers from consumers.  In-memory works for single-process
    deployments; Redis Pub/Sub enables multi-node event delivery.

Usage::

    from spine.core.events import Event, get_event_bus

    bus = get_event_bus()

    # Publish
    event = Event(
        event_type="run.completed",
        source="operation-runner",
        payload={"run_id": "abc-123", "status": "success"},
    )
    await bus.publish(event)

    # Subscribe (supports wildcards: "run.*")
    async def handler(event: Event):
        print(f"Run {event.payload['run_id']} completed!")
    sub_id = await bus.subscribe("run.*", handler)

Modules
-------
memory      InMemoryEventBus -- asyncio queues, single-node
redis       RedisEventBus -- Redis Pub/Sub, multi-node

*Source: [`__init__.py`](spine-core/src/spine/core/events/__init__.py#L1)*

When Apple executed a 4-for-1 stock split in August 2020, every
    historical price, EPS, and dividend figure had to be divided by 4
    to remain comparable with post-split figures.  Without composable
    adjustment factors as first-class objects, every project invents
    its own split math and gets it wrong for edge cases.

Provides composable adjustment factors that convert raw per-share
metrics (price, EPS, dividends) between different adjustment bases.
Common use-cases: stock splits, reverse splits, spin-offs, rights
issues, and special dividends.

    Real-world complexity:
    - **Multiple events**: TSLA had a 5-for-1 (2020) then a 3-for-1
      (2022).  The composite factor is 15, and ``adjust_as_of()``
      must apply only the factors effective up to a given date.
    - **Different metrics**: Splits affect price and EPS, but revenue
      and market cap are unaffected.  The caller decides which fields
      to adjust — this module supplies the math.
    - **Vendor reconciliation**: Bloomberg and FactSet may disagree
      on the exact adjustment factor for a spin-off.  Keeping factors
      as first-class objects (with provenance via ``metadata``) lets
      you audit the discrepancy.

Why This Matters — General Operations:
    Any time-series with unit changes over time (currency redenomination,
    sensor recalibration, API version migration) benefits from composable
    factor chains.  The ``adjust_as_of()`` pattern generalises to "apply
    only the corrections relevant up to this point in time".

Key Concepts:
    AdjustmentMethod: Why an adjustment was applied (SPLIT, DIVIDEND, etc.)
    AdjustmentFactor: A single (date, factor, method) triple.
    AdjustmentChain: An ordered sequence of factors with composite
        multiplication and inversion.

Related Modules:
    - :mod:`spine.core.finance.corrections` — records *why* a value
      changed (restatement, data error) — complementary to adjustments
      which handle *structural* changes (splits, dividends)
    - :mod:`spine.core.temporal_envelope` — ensures adjusted values
      carry correct temporal context

Example:
    >>> from datetime import date
    >>> from spine.core.finance.adjustments import (
    ...     AdjustmentChain, AdjustmentFactor, AdjustmentMethod,
    ... )
    >>> chain = AdjustmentChain(factors=[
    ...     AdjustmentFactor(
    ...         effective_date=date(2025, 6, 15),
    ...         factor=2.0,
    ...         method=AdjustmentMethod.SPLIT,
    ...         description="2-for-1 stock split",
    ...     ),
    ...     AdjustmentFactor(
    ...         effective_date=date(2025, 9, 1),
    ...         factor=4.0,
    ...         method=AdjustmentMethod.SPLIT,
    ...         description="4-for-1 stock split",
    ...     ),
    ... ])
    >>> chain.composite_factor
    8.0
    >>> chain.adjust(100.0)  # pre-split price → post-split
    800.0
    >>> chain.unadjust(800.0)  # post-split → pre-split
    100.0

STDLIB ONLY — no Pydantic.

*Source: [`adjustments.py`](spine-core/src/spine/core/finance/adjustments.py#L1)*

Financial data changes after publication more often than people
    expect.  SEC-mandated restatements (10-K/A filings), vendor
    correction notices from Bloomberg or FactSet, late-arriving actuals
    that replace preliminary estimates, and methodology changes all
    produce corrections that must be tracked with an auditable trail.

When an observation (price, EPS, ratio, etc.) changes after initial
publication, a CorrectionRecord captures **why** it changed, what the
old and new values were, and who/what made the correction.

    Real-world examples:
    - **EPS restatement**: Apple files a 10-K/A that revises diluted
      EPS from $1.52 to $1.46.  Without a CorrectionRecord, consumers
      have no idea the number changed, or why.
    - **Vendor disagreement**: Bloomberg and Zacks report different
      "actual" EPS values for the same quarter (see the feedspine
      estimates-vs-actuals design doc).  When one vendor later corrects
      their figure, the CorrectionRecord captures which vendor, when,
      and the delta.
    - **Late reporting**: A preliminary revenue estimate of $0 gets
      replaced by the actual figure of $1.5M once the quarterly
      report is filed.  ``pct_change`` returns ``None`` for the zero-
      original case, preventing division-by-zero surprises.

Why This Matters — General Operations:
    Any system where published values are later revised — reference
    data, configuration snapshots, telemetry — benefits from an
    auditable correction trail.  The pattern is: never silently
    overwrite; always capture old value, new value, reason, and
    who/what triggered the change.

Key Concepts:
    CorrectionReason: Enumeration of reasons an observation may be
        corrected (RESTATEMENT, DATA_ERROR, METHODOLOGY_CHANGE, etc.).
    CorrectionRecord: Immutable record pairing old/new values with a
        reason, timestamps, and optional provenance.

Related Modules:
    - :mod:`spine.core.finance.adjustments` — handles *structural*
      changes (splits, dividends) to per-share metrics; complementary
      to corrections which handle *value* changes
    - :mod:`spine.core.temporal_envelope` — BiTemporalRecord supersede()
      workflow uses corrections to close old versions and open new ones
    - :mod:`spine.core.backfill` — CORRECTION-reason backfills are
      triggered when corrections require re-processing downstream data

Example:
    >>> from spine.core.finance.corrections import (
    ...     CorrectionReason, CorrectionRecord,
    ... )
    >>> rec = CorrectionRecord.create(
    ...     entity_key="AAPL",
    ...     field_name="eps_diluted",
    ...     original_value=1.52,
    ...     corrected_value=1.46,
    ...     reason=CorrectionReason.RESTATEMENT,
    ...     corrected_by="sec_filing_parser",
    ...     source_ref="10-K/A filed 2025-03-15",
    ... )
    >>> rec.delta
    -0.06000...
    >>> rec.pct_change  # (1.46 - 1.52) / 1.52
    -0.0394...

STDLIB ONLY — no Pydantic.

*Source: [`corrections.py`](spine-core/src/spine/core/finance/corrections.py#L1)*

Financial data operations have unique correctness requirements that
    general-purpose tools miss.  Adjustments (splits, dividends) alter
    the meaning of per-share metrics across time.  Corrections (restatements,
    vendor fixes) change published values after the fact.  Without shared,
    auditable primitives, every project invents its own split math and
    silently overwrites corrected values.

    These patterns originate from real problems in the estimates-vs-actuals
    operation where different sources (Bloomberg, FactSet, Zacks) report
    *different* values for the same metric, and corrections arrive days
    or weeks after initial publication.

Modules:
    adjustments: Factor-based adjustment math (splits, dividends, etc.)
    corrections: Why-an-observation-changed taxonomy with audit trail

Related Modules:
    - :mod:`spine.core.temporal_envelope` — wraps financial observations
      with 4-timestamp semantics for PIT-correct queries
    - :mod:`spine.core.watermarks` — tracks how far each data source
      has been ingested
    - :mod:`spine.core.backfill` -- structured recovery when gaps or
      corrections are detected

STDLIB ONLY -- no Pydantic.

*Source: [`__init__.py`](spine-core/src/spine/core/finance/__init__.py#L1)*

Numbered .sql files are the single source of truth for schema.
    The runner applies them in filename order, records each in the
    ``_migrations`` table, and skips already-applied files so the
    operation is fully idempotent.

Reads ``.sql`` files from the schema directory, tracks applied migrations
in the ``_migrations`` table, and applies pending ones in filename order.

*Source: [`runner.py`](spine-core/src/spine/core/migrations/runner.py#L1)*

Database schemas must evolve safely across deployments.  Manual DDL
    execution is error-prone and unrepeatable.  The migration runner
    applies numbered .sql files idempotently, tracking what has already
    been applied in the ``_migrations`` table.

Applies SQL migration files from ``core/schema/`` in filename order,
tracking which have already been applied in the ``_migrations`` table.

Modules
-------
runner    MigrationRunner class with apply_pending() / status()

*Source: [`__init__.py`](spine-core/src/spine/core/migrations/__init__.py#L1)*

Alert channels, alerts, deliveries, and throttle state need typed
    representations so the alerting ops layer and API can work with
    structured objects instead of raw SQL rows.

Models for alert channel configuration and delivery tracking:
channels, alerts, delivery logs, and throttle state.

*Source: [`alerting.py`](spine-core/src/spine/core/models/alerting.py#L1)*

The fundamental spine-core tables (executions, manifest, rejects,
    quality, anomalies, work items, dead letters, locks, dependencies,
    schedules, data readiness) each need a typed dataclass so the ops
    and API layers work with structured objects instead of raw dicts.

Models for the fundamental spine-core tables: executions, manifest,
rejects, quality, anomalies, work items, dead letters, concurrency
locks, calculation dependencies, expected schedules, and data readiness.

*Source: [`core.py`](spine-core/src/spine/core/models/core.py#L1)*

Schedule definitions, execution history, and distributed locks
    need typed dataclass representations so the scheduling service
    and API can work with structured objects.

Models for cron-based operation scheduling: schedule definitions,
execution history, and distributed locks.

*Source: [`scheduler.py`](spine-core/src/spine/core/models/scheduler.py#L1)*

Data source registry, fetch history, caching, and DB connection
    config need typed dataclass representations for the ops layer
    and API to work with structured objects.

Models for data source tracking: source registry, fetch history,
caching, and database connection configuration.

*Source: [`sources.py`](spine-core/src/spine/core/models/sources.py#L1)*

Workflow runs, steps, and lifecycle events need typed dataclass
    representations so the orchestration engine and API can track
    execution progress as structured objects.

Models for workflow execution history: runs, steps, and lifecycle events.

*Source: [`workflow.py`](spine-core/src/spine/core/models/workflow.py#L1)*

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

*Source: [`__init__.py`](spine-core/src/spine/core/models/__init__.py#L1)*

Every ORM table needs a common declarative base with consistent
    type mappings (str→Text, bool→Integer for SQLite compat, etc.)
    and timestamp mixins.  Defining these once prevents subtle column
    type mismatches across 30+ table classes.

Uses SQLAlchemy 2.0 ``DeclarativeBase`` with a ``type_annotation_map``
that maps Python built-in types to portable SA column types.

*Source: [`base.py`](spine-core/src/spine/core/orm/base.py#L1)*

ORM and raw-SQL code must share a single abstraction so ops modules
    work identically whether the caller uses a raw ``sqlite3.Connection``
    or a ``Session``.  ``SAConnectionBridge`` wraps a SA Session to
    satisfy the ``spine.core.protocols.Connection`` protocol.

This module provides:

* ``create_spine_engine``  -- Create a SA engine from a URL or config dict.
* ``SpineSession``         -- A pre-configured ``sessionmaker`` subclass.
* ``SAConnectionBridge``   -- Wraps a SA ``Session`` to satisfy the
  ``spine.core.protocols.Connection`` protocol, enabling ORM and raw-SQL
  code to share a single abstraction.

*Source: [`session.py`](spine-core/src/spine/core/orm/session.py#L1)*

Every ``CREATE TABLE`` in ``spine.core.schema/*.sql`` has a corresponding
    ``Mapped`` class here so the ORM and raw-SQL layers share the same
    schema.  This is the single authoritative Python-side representation
    of spine-core's database structure.

Every ``CREATE TABLE`` in ``spine.core.schema/*.sql`` has a corresponding
``Mapped`` class here.  Column types are aligned with the SQL DDL:

* ``*_at`` columns -> ``DateTime``
* ``*_json`` / ``params`` / ``spec`` / ``data`` / ``outputs`` / ``metrics`` /
  ``payload`` / ``tags`` -> ``JSON``
* ``is_*`` / ``enabled`` / ``error_retryable`` -> ``Boolean``
  (stored as ``Integer`` on SQLite via ``type_annotation_map``)
* ``ForeignKey`` declared where the SQL DDL has ``FOREIGN KEY``

*Source: [`tables.py`](spine-core/src/spine/core/orm/tables.py#L1)*

The raw ``Connection`` protocol is sufficient for simple queries, but
    complex joins, eager loading, and unit-of-work patterns benefit from
    a full ORM.  This package provides SQLAlchemy 2.0 declarative models
    that mirror every ``spine.core.schema/*.sql`` table.

    Strictly **optional** -- all core primitives continue to work with
    raw SQL.  Install with ``pip install spine-core[sqlalchemy]``.

Modules
-------
base        SpineBase (declarative base) + TimestampMixin
session     Engine factory, SpineSession, SAConnectionBridge
tables      All 30 mapped table classes (MigrationTable, ExecutionTable, ...)

*Source: [`__init__.py`](spine-core/src/spine/core/orm/__init__.py#L1)*

For deployments needing database-backed job persistence, misfire
    policies, or advanced APScheduler features, this backend wraps
    APScheduler 3.x ``BackgroundScheduler`` behind the ``SchedulerBackend``
    protocol.

Wraps APScheduler 3.x ``BackgroundScheduler`` to provide the
``SchedulerBackend`` protocol for production deployments that need
richer job-store features (database-backed job persistence, misfire
handling, etc.).

Requires the ``[apscheduler]`` extra::

    pip install spine-core[apscheduler]

*Source: [`apscheduler_backend.py`](spine-core/src/spine/core/scheduling/apscheduler_backend.py#L1)*

Deployments already using Celery as a task broker can drive scheduler
    ticks from Celery Beat instead of a local thread.  This backend
    registers a periodic Celery task but does NOT start Beat itself --
    you must run ``celery -A <app> beat`` separately.

Wraps Celery Beat periodic task scheduling to provide the
``SchedulerBackend`` protocol.  This is intended for deployments that
already use Celery as a task broker and want the scheduler tick to be
driven by Celery Beat rather than a local thread or APScheduler.

Requires a Celery application instance and the ``celery`` package::

    pip install celery

.. warning::

    This backend is **experimental**.

*Source: [`celery_backend.py`](spine-core/src/spine/core/scheduling/celery_backend.py#L1)*

Cron schedules depend on accurate time.  If the system clock drifts,
    schedules fire late (or early), distributed locks expire incorrectly,
    and audit logs become unreliable.  Active health monitoring catches
    drift before it causes silent data gaps.

This module provides health monitoring for the scheduler system,
including time drift detection and NTP synchronization checks.

*Source: [`health.py`](spine-core/src/spine/core/scheduling/health.py#L1)*

Multiple scheduler instances must never execute the same schedule
    simultaneously.  The lock manager provides atomic acquire/release
    with TTL-based auto-expiry so crashed instances don't cause permanent
    deadlocks.  INSERT-or-fail semantics give O(1) conflict detection.

This module provides atomic lock acquire/release for schedules, enabling
safe distributed scheduler deployments.

*Source: [`lock_manager.py`](spine-core/src/spine/core/scheduling/lock_manager.py#L1)*

Backends control WHEN ticks happen; the service controls WHAT happens.
    This separation lets you swap timing implementations (thread, APScheduler,
    Celery Beat) without changing any schedule evaluation logic.

*Source: [`protocol.py`](spine-core/src/spine/core/scheduling/protocol.py#L1)*

Schedule persistence and next-run computation are pure data operations
    that belong in a repository, not in the service layer.  Separating
    them enables testing with in-memory connections and keeps the service
    focused on orchestration.

This module provides the data access layer for schedules, plus cron
expression evaluation using croniter.

*Source: [`repository.py`](spine-core/src/spine/core/scheduling/repository.py#L1)*

The SchedulerService is the central coordinator that combines backend
    (timing), repository (data), lock manager (safety), and dispatcher
    (execution) into a unified scheduling system.  The beat-as-poller
    pattern decouples timing from schedule evaluation for testability.

The SchedulerService is the central coordinator for schedule execution.
It combines backend (timing), repository (data), lock manager (safety),
and dispatcher (execution) into a unified scheduling system.

*Source: [`service.py`](spine-core/src/spine/core/scheduling/service.py#L1)*

The default backend uses only stdlib ``threading`` so spine-core
    scheduling works out of the box with zero extra dependencies.
    A daemon thread ticks at a configurable interval, invoking the
    scheduler service's async callback via ``asyncio.run()``.

This is the DEFAULT backend for spine-core scheduling. It uses Python's
stdlib threading module and has no external dependencies.

*Source: [`thread_backend.py`](spine-core/src/spine/core/scheduling/thread_backend.py#L1)*

```
Cron-based scheduling in distributed deployments requires more than
    ``time.sleep()`` in a loop.  It needs lock-guarded execution (so two
    instances don't fire the same schedule), misfire detection (so delayed
    ticks don't silently skip), and health monitoring (so time drift is
    caught before it causes silent data gaps).  The scheduling package
    provides all three with pluggable timing backends.

┌──────────────────────────────────────────────────────────────────────────────┐
│  SPINE SCHEDULER - Production-Grade Cron Scheduling                          │
│                                                                               │
│  A full-featured scheduling system with:                                      │
│  - Pluggable timing backends (Thread, APScheduler, Celery Beat)              │
│  - Cron and interval schedule types                                          │
│  - Distributed locks for multi-instance deployments                          │
│  - Misfire detection and grace periods                                       │
│  - Health monitoring and time drift detection                                │
│                                                                               │
│  Quick Start:                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │   from spine.core.scheduling import (                                │   │
│  │       SchedulerService,                                              │   │
│  │       ThreadSchedulerBackend,                                        │   │
│  │       ScheduleRepository,                                            │   │
│  │       LockManager,                                                   │   │
│  │   )                                                                  │   │
│  │                                                                      │   │
│  │   # Create scheduler                                                 │   │
│  │   backend = ThreadSchedulerBackend()                                 │   │
│  │   repo = ScheduleRepository(conn)                                    │   │
│  │   locks = LockManager(conn)                                          │   │
│  │   service = SchedulerService(backend, repo, locks, dispatcher)       │   │
│  │                                                                      │   │
│  │   # Start scheduling                                                 │   │
│  │   service.start()                                                    │   │
│  │                                                                      │   │
│  │   # Create a schedule                                                │   │
│  │   repo.create(ScheduleCreate(                                        │   │
│  │       name="daily-report",                                           │   │
│  │       target_type="workflow",                                        │   │
│  │       target_name="generate-report",                                 │   │
│  │       cron_expression="0 8 * * *",                                   │   │
│  │   ))                                                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
│  Architecture:                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                                                                     │    │
│  │   ┌──────────────┐    tick()    ┌──────────────────────────────┐  │    │
│  │   │  Backend     │ ───────────► │   SchedulerService           │  │    │
│  │   │ (timing)     │              │                              │  │    │
│  │   └──────────────┘              │  ┌──────────┐ ┌───────────┐  │  │    │
│  │                                 │  │ Repo     │ │ LockMgr   │  │  │    │
│  │   Backends:                     │  │ (data)   │ │ (safety)  │  │  │    │
│  │   • Thread (default)            │  └──────────┘ └───────────┘  │  │    │
│  │   • APScheduler                 │              │               │  │    │
│  │   • Celery Beat                 │              ▼               │  │    │
│  │                                 │       ┌──────────────┐       │  │    │
│  │                                 │       │  Dispatcher  │       │  │    │
│  │                                 │       │ (execution)  │       │  │    │
│  │                                 │       └──────────────┘       │  │    │
│  │                                 └──────────────────────────────┘  │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                               │
│  Dependencies:                                                                │
│  - croniter: Cron expression parsing (pip install croniter)                 │
│  - apscheduler: APScheduler backend (optional)                              │
│  - celery: Celery Beat backend (optional)                                   │
│                                                                               │
│  Tables (from 03_scheduler.sql):                                              │
│  - core_schedules: Schedule definitions                                      │
│  - core_schedule_runs: Execution history                                     │
│  - core_schedule_locks: Distributed locks                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

*Source: [`__init__.py`](spine-core/src/spine/core/scheduling/__init__.py#L1)*

Each spine only needs three things: a lifespan, some tools, and a
    ``run()`` call.  This module eliminates the repeated boilerplate
    across genai-spine, search-spine, and knowledge-spine MCP servers
    by providing ``create_spine_mcp()`` and ``run_spine_mcp()``.

Eliminates the repeated boilerplate across genai-spine, search-spine,
and knowledge-spine MCP servers.  Each spine only needs to:

1. Define a lifespan that yields its ``AppContext``
2. Register tools/resources/prompts on the returned ``FastMCP`` instance
3. Call ``run()`` from its console script entry point

Requires the ``mcp`` optional extra::

    pip install spine-core[mcp]

*Source: [`mcp.py`](spine-core/src/spine/core/transports/mcp.py#L1)*

Every spine service needs to be callable by AI agents via the Model
    Context Protocol.  Without a shared scaffold, each service re-implements
    the same stdio/HTTP framing, error mapping, and lifecycle boilerplate.

Provides ``create_spine_mcp()`` -- a factory that creates a ready-to-run
Model Context Protocol server for any spine service.  Each spine registers
its domain-specific tools; the transport layer handles stdio/HTTP framing,
error mapping, and lifecycle.

Modules
-------
mcp     create_spine_mcp() + run_spine_mcp() factory functions

*Source: [`__init__.py`](spine-core/src/spine/core/transports/__init__.py#L1)*

### Ok

- **Value presence guaranteed:** Unlike Optional, Ok always has a value
    - **Transformation without unwrapping:** Use map/flat_map to stay in Result
    - **Explicit success:** The type tells you the operation succeeded
    - **Immutability:** Frozen dataclass prevents accidental mutation

*Source: [`Ok`](spine-core/src/spine/core/result.py#L140)*

### QualityCategory

Quality checks fall into categories:
    - **INTEGRITY:** Data structure correctness (types, constraints)
    - **COMPLETENESS:** Data coverage and availability
    - **BUSINESS_RULE:** Domain-specific validation rules

    Categories enable:
    - Routing failures to appropriate teams
    - Different alert thresholds by category
    - Quality dashboards by check type

*Source: [`QualityCategory`](spine-core/src/spine/core/quality.py#L155)*

### QualityCheck

Quality checks should be:
    - **Named:** For identification in reports and alerts
    - **Categorized:** For routing and dashboards
    - **Pure functions:** Context in → Result out
    - **Reusable:** Same check for different partitions

*Source: [`QualityCheck`](spine-core/src/spine/core/quality.py#L237)*

### QualityResult

Quality results must be actionable:
    - **status:** Did the check pass, warn, or fail?
    - **message:** Human-readable explanation
    - **actual_value:** What was found (for debugging)
    - **expected_value:** What was expected (for comparison)

    This enables both automated gating and human investigation.

*Source: [`QualityResult`](spine-core/src/spine/core/quality.py#L185)*

### QualityRunner

Quality execution should be:
    - **Recorded:** All results persisted for audit trail
    - **Chainable:** Add checks fluently with add()
    - **Non-blocking:** Runs all checks, reports at end
    - **Gate-ready:** has_failures() enables quality gates

    Results are stored in core_quality table, partitioned by domain.
    Each check run creates one row with full context.

*Source: [`QualityRunner`](spine-core/src/spine/core/quality.py#L281)*

### QualityStatus

Three-state quality results enable nuanced handling:
    - **PASS:** Check succeeded, data is valid
    - **WARN:** Check found issues but not critical
    - **FAIL:** Check failed, data quality is compromised

    WARN allows for soft thresholds: "null rate is 15%, above 10% target
    but below 25% hard limit". This enables alerting without blocking.

*Source: [`QualityStatus`](spine-core/src/spine/core/quality.py#L128)*

### Reject

Every reject should answer:
    - **Where?** stage (INGEST, NORMALIZE, AGGREGATE)
    - **Why?** reason_code + reason_detail
    - **What?** raw_data for reproduction
    - **Source?** source_locator + line_number for tracing

    The reason_code enables aggregation ("how many INVALID_SYMBOL?")
    while reason_detail provides the specific explanation.

*Source: [`Reject`](spine-core/src/spine/core/rejects.py#L130)*

### RejectSink

RejectSink is the single entry point for recording validation
    failures. It ensures:
    - **Consistent schema:** All rejects in one shared table
    - **Domain partitioning:** Filter by domain for analysis
    - **Lineage tracking:** execution_id, batch_id for correlation
    - **Count tracking:** Easy access to rejection metrics

    Use one RejectSink per stage to track rejects by source.

*Source: [`RejectSink`](spine-core/src/spine/core/rejects.py#L195)*

### RollingResult

A 6-week average with only 3 weeks of data is unreliable. RollingResult
    makes this explicit:
    - **periods_present:** How many periods actually had data
    - **periods_total:** Window size (how many should have data)
    - **is_complete:** Quick check if window is full

    This enables data quality checks in downstream analysis:
    "Only report averages where is_complete=True"

*Source: [`RollingResult`](spine-core/src/spine/core/rolling.py#L89)*

### RollingWindow

Financial time-series analysis needs rolling calculations:
    - "6-week rolling average volume"
    - "52-week high/low"
    - "30-day moving average"

    RollingWindow provides a composable pattern:
    1. **Define window:** size and how to step back
    2. **Fetch data:** per-period retrieval (may return None for gaps)
    3. **Aggregate:** combine available data into result
    4. **Check completeness:** is_complete tells you if all periods had data

    This separation of concerns enables:
    - Different fetch strategies (DB, cache, API)
    - Custom aggregations (avg, sum, percentiles, trend)
    - Reusable window definitions

*Source: [`RollingWindow`](spine-core/src/spine/core/rolling.py#L178)*

### Severity

Not all anomalies are created equal. A CRITICAL issue that breaks
    production needs immediate attention, while INFO is just notable.
    Severity enables:
    - **Alert routing:** CRITICAL pages on-call, WARN creates tickets
    - **Dashboard filtering:** Focus on what matters
    - **Trend analysis:** Track severity distribution over time

*Source: [`Severity`](spine-core/src/spine/core/anomalies.py#L123)*

### SpineError

- **Single base class:** All spine errors inherit from SpineError
    - **Explicit retry semantics:** Every error knows if it's retryable
    - **Rich context:** Errors carry metadata for observability
    - **Error chaining:** Preserve original exceptions as cause
    - **Fluent API:** with_context() for adding metadata after creation

*Source: [`SpineError`](spine-core/src/spine/core/errors.py#L387)*

### StorageBackend

StorageBackend abstracts away connection management:
    - Connection pooling (handled by tier infrastructure)
    - Transaction boundaries (via context manager)
    - Resource cleanup (automatic on context exit)

    Domains use StorageBackend without knowing about pools or drivers.

*Source: [`StorageBackend`](spine-core/src/spine/core/storage.py#L115)*

### TransientError

- **Transient = retryable:** Default retryable=True
    - **Network category:** Default category is NETWORK
    - **Retry guidance:** Use retry_after to suggest delay
    - **Infrastructure focus:** For infrastructure/external service issues

*Source: [`TransientError`](spine-core/src/spine/core/errors.py#L598)*

### WeekEnding

FINRA publishes OTC transparency data every Friday. Market data operations
    process weekly windows. Using arbitrary dates leads to subtle bugs:
    - "2025-12-25" (Christmas, Thursday) - Wrong week boundary
    - Off-by-one errors in date arithmetic
    - Inconsistent week_ending formats across tables

    WeekEnding solves this by making Fridays a type, not a convention:
    - **Validation at construction:** Non-Fridays raise ValueError immediately
    - **Explicit conversion:** from_any_date() for arbitrary dates
    - **Range operations:** window(), range(), last_n() are always correct
    - **Comparison:** WeekEnding objects compare correctly

*Source: [`WeekEnding`](spine-core/src/spine/core/temporal.py#L72)*

### WorkManifest

Knowing "where is this work in the operation?" is critical for:
    - **Idempotent restarts:** Resume from the last completed stage
    - **Progress dashboards:** Show operation status at a glance
    - **Debugging:** Correlate issues with specific stages
    - **Metrics:** Track row counts and timing per stage

    WorkManifest is the single source of truth. It supports:
    - UPSERT semantics (advance_to creates or updates)
    - Rank-based comparison (is_at_least for stage gates)
    - Multi-stage queries (get all stages for a partition)

*Source: [`WorkManifest`](spine-core/src/spine/core/manifest.py#L223)*

## Framework & Configuration

Operations must validate inputs before executing.  This module
    provides declarative parameter schemas so validation is
    consistent and self-documenting.

*Source: [`params.py`](spine-core/src/spine/framework/params.py#L1)*

A central registry lets code discover operations at runtime
    (by name, tag, or domain) without import-time coupling.

*Source: [`registry.py`](spine-core/src/spine/framework/registry.py#L1)*

The runner executes operations with consistent lifecycle hooks
    (start → execute → record result) so ops code never manages
    its own timing, error capture, or result storage.

*Source: [`runner.py`](spine-core/src/spine/framework/runner.py#L1)*

Routing alerts to the right channel (Slack, email, console)
    should be configured once and honoured everywhere.  The
    registry stores channel bindings so alert producers don't
    pick delivery targets.

*Source: [`registry.py`](spine-core/src/spine/framework/alerts/registry.py#L1)*

Developers need to see alerts in their terminal without
    configuring Slack or email.  The console channel provides
    that zero-config default.

*Source: [`console.py`](spine-core/src/spine/framework/alerts/channels/console.py#L1)*

Most teams use Slack for ops notifications.  This channel
    posts structured alerts via incoming webhooks so on-call
    engineers get actionable context without leaving chat.

*Source: [`slack.py`](spine-core/src/spine/framework/alerts/channels/slack.py#L1)*

Any HTTP endpoint should be a valid alert target.  The
    generic webhook channel POSTs JSON to a user-defined URL
    so custom integrations (PagerDuty, Teams, etc.) work
    without dedicated channel code.

*Source: [`webhook.py`](spine-core/src/spine/framework/alerts/channels/webhook.py#L1)*

Each channel module implements a single delivery target.
    New channels are added as modules here and registered in
    the alert registry.

*Source: [`__init__.py`](spine-core/src/spine/framework/alerts/channels/__init__.py#L1)*

## Execution Engine

Many spine operations need to fan-out hundreds of I/O calls (SEC EDGAR
downloads, LLM API calls, DB queries) and collect results.  Using
``asyncio.gather`` with a semaphore gives true concurrency without
the thread-pool overhead of :class:`~spine.execution.batch.BatchExecutor`.

ARCHITECTURE
────────────
::

    AsyncBatchExecutor
      ├── .add(name, coroutine, params)  ─ enqueue work item
      ├── .run_all()                     ─ asyncio.gather + semaphore
      └── AsyncBatchResult               ─ succeeded / failed / items

    vs BatchExecutor (threads)       vs AsyncBatchExecutor (asyncio)
    ─────────────────────────       ────────────────────────────────
    ThreadPoolExecutor               asyncio.gather + Semaphore
    sync handlers                    async handlers (coroutines)
    OS-thread per item               single event loop

Related modules:
    batch.py       — sync/thread-pool version
    context.py     — ExecutionContext for lineage tracking

Example::

    batch = AsyncBatchExecutor(max_concurrency=20)
    batch.add("dl_1", download_filing, {"url": url1})
    batch.add("dl_2", download_filing, {"url": url2})
    result = await batch.run_all()
    print(result.succeeded, result.failed)  # 2 0

*Source: [`async_batch.py`](spine-core/src/spine/execution/async_batch.py#L1)*

Production workloads often need to run many operations in a single
batch (e.g. ingest all NMS tiers, refresh all SEC filings for a week).
BatchExecutor wraps a ThreadPoolExecutor with progress tracking,
aggregate results, and integration with the ExecutionLedger,
ConcurrencyGuard, and DLQManager.

ARCHITECTURE
────────────
::

    BatchExecutor
      ├── .add(operation, params)   ─ enqueue a BatchItem
      ├── .run_all()               ─ ThreadPool fan-out
      └── BatchResult              ─ successful / failed / items

    BatchBuilder (fluent API)
      ├── .add() / .add_many()     ─ accumulate items
      └── .build()                 ─ returns configured BatchExecutor

    Dependencies:
      ExecutionLedger    ─ persists each item run
      ConcurrencyGuard   ─ prevents duplicate runs
      DLQManager         ─ captures failures

Related modules:
    async_batch.py — asyncio version (no threads)
    ledger.py      — execution persistence
    concurrency.py — DB-level locking

Example::

    batch = BatchExecutor(ledger, guard, dlq, max_parallel=4)
    batch.add("sec.filings", {"date": "2024-01-01"})
    batch.add("market.prices", {"symbol": "AAPL"})
    results = batch.run_all()
    print(f"Completed: {results.successful}/{results.total}")

*Source: [`batch.py`](spine-core/src/spine/execution/batch.py#L1)*

When an external service (EDGAR, LLM API, database) starts failing,
retrying every request wastes time and load.  The circuit breaker
“trips” after N consecutive failures, rejecting requests instantly
for a recovery period, then tests with a single probe request.

ARCHITECTURE
────────────
::

    State machine:
      CLOSED  ──(N failures)──▶  OPEN  ──(timeout)──▶  HALF_OPEN
        ▲                                                  │
        └───────(success)────────────────────────────┘

    CircuitBreaker
      ├── .allow_request()     ─ check state before calling
      ├── .record_success()    ─ reset failure count
      ├── .record_failure()    ─ increment, maybe trip
      └── .stats               ─ CircuitStats snapshot

    CircuitBreakerRegistry
      ├── .get_or_create(name) ─ shared breaker per service
      └── get_circuit_breaker  ─ module-level convenience

BEST PRACTICES
──────────────
- Use one breaker per downstream service, not per operation.
- Set ``recovery_timeout`` to match the service’s typical recovery.
- Combine with ``RetryStrategy`` for transient failures *within*
  the closed state, and circuit breaker for sustained outages.

Related modules:
    retry.py       — per-call retry with backoff
    rate_limit.py  — throttle request rate
    timeout.py     — enforce deadlines

Example::

    breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=30.0)
    if breaker.allow_request():
        try:
            result = call_external_service()
            breaker.record_success()
        except Exception:
            breaker.record_failure()
            raise
    else:
        raise CircuitOpenError("Service unavailable")

*Source: [`circuit_breaker.py`](spine-core/src/spine/execution/circuit_breaker.py#L1)*

If two workers pick up the same operation+params (e.g. both try to
ingest ``finra.otc:2025-01-09``), the second run wastes resources and
can corrupt data.  ConcurrencyGuard uses database-level advisory
locking with automatic expiry so that even if a process crashes, the
lock self-heals.

ARCHITECTURE
────────────
::

    ConcurrencyGuard(conn)
      ├── .acquire(key, execution_id)  ─ try-lock with timeout
      ├── .release(key)                ─ explicit unlock
      ├── .is_locked(key)              ─ check without acquiring
      ├── .cleanup_expired()           ─ reap stale locks
      └── .list_active()               ─ list all held locks

    Lock key convention: “operation_name:partition_key”
      e.g. "finra.otc.ingest:2025-01-09"

BEST PRACTICES
──────────────
- Always release in a ``finally`` (or use BatchExecutor which
  handles this automatically).
- Set ``lock_timeout`` to slightly longer than the longest expected run.

Related modules:
    ledger.py  — persists the lock records
    batch.py   — uses ConcurrencyGuard internally

Example::

    guard = ConcurrencyGuard(conn)
    key = "finra.otc.ingest:2025-01-09"
    if guard.acquire(key, execution_id="exec-123"):
        try:
            run_operation()
        finally:
            guard.release(key)

*Source: [`concurrency.py`](spine-core/src/spine/execution/concurrency.py#L1)*

Every execution needs a consistent view of its parameters,
    credentials, and accumulated state.  ExecutionContext is the
    single immutable token passed through the call chain so
    downstream code never depends on ambient globals.

*Source: [`context.py`](spine-core/src/spine/execution/context.py#L1)*

Every work item (task, operation, workflow, step) needs the same
lifecycle: submit → track → query → cancel/retry.  Rather than
scattering this logic across callers, ``EventDispatcher`` is the
**single public API** for all execution, regardless of work type,
runtime backend, or persistence layer.

ARCHITECTURE
────────────
::

    EventDispatcher
      ├── .submit_task(name, params)      ─ fire-and-forget
      ├── .submit_operation(name, params)  ─ tracked operation run
      ├── .submit_operation_sync(...)      ─ blocking (Runnable protocol)
      ├── .submit(work_spec)              ─ generic submission
      ├── .get_run(run_id)                ─ query status
      ├── .list_runs(status=, kind=)      ─ filtered listing
      └── .cancel(run_id)                 ─ request cancellation

    Dependencies:
      Executor         ─ dispatches work to runtime
      HandlerRegistry  ─ resolves handler by name
      RunRecord        ─ persisted execution state

BEST PRACTICES
──────────────
- Create ONE dispatcher per application; pass it as a dependency.
- Use ``submit_operation_sync`` when the caller needs to block.
- The dispatcher is also the ``Runnable`` used by WorkflowRunner,
  so operation steps inside workflows get full RunRecord tracking.

Related modules:
    spec.py     — WorkSpec (what to run)
    runs.py     — RunRecord (execution state)
    registry.py — HandlerRegistry (name → handler)
    runnable.py — Runnable protocol (blocking interface)

*Source: [`dispatcher.py`](spine-core/src/spine/execution/dispatcher.py#L1)*

Operation failures should not disappear silently.  The DLQ captures
every failed execution with its full context (params, error, stack
trace) so operators can inspect, retry, or resolve failures without
re-running entire batches.

ARCHITECTURE
────────────
::

    DLQManager(conn)
      ├── .add_to_dlq(execution_id, operation, params, error)
      ├── .retry(dlq_id)           ─ re-queue for execution
      ├── .resolve(dlq_id, by)     ─ mark as handled
      ├── .list_pending()          ─ unresolved entries
      ├── .purge_old(days)         ─ cleanup resolved entries
      └── .stats()                 ─ counts by status/operation

    DeadLetter (models.py)     ─ row-level data model

BEST PRACTICES
──────────────
- Set ``max_retries`` to prevent infinite retry loops.
- Use ``purge_old()`` in a scheduled job to prevent unbounded growth.
- BatchExecutor automatically routes failures to the DLQ.

Related modules:
    models.py  — DeadLetter dataclass
    batch.py   — auto-routes failures to DLQ
    ledger.py  — execution storage

Example::

    dlq = DLQManager(conn, max_retries=3)
    entry = dlq.add_to_dlq(
        execution_id="exec-123",
        operation="finra.otc.ingest",
        params={"week_ending": "2025-01-09"},
        error="Connection timeout",
    )
    dlq.retry(entry.id)  # re-queue

*Source: [`dlq.py`](spine-core/src/spine/execution/dlq.py#L1)*

Mutable status fields only show *current* state.  Events capture the
complete lifecycle (“who changed what, when, why”) enabling
debugging, observability dashboards, and deterministic replay.

ARCHITECTURE
────────────
::

    RunEvent
      ├── run_id      ─ which run
      ├── event_type  ─ submitted / started / completed / failed / ...
      ├── timestamp   ─ when
      └── data        ─ arbitrary payload (params, error, metrics)

    Events are append-only; never update or delete.

Related modules:
    runs.py       — RunRecord (mutable current state)
    dispatcher.py — emits events on submission/completion

*Source: [`events.py`](spine-core/src/spine/execution/events.py#L1)*

All work types (tasks, operations, workflows, steps) share the same
lifecycle.  A single ``/runs`` endpoint avoids endpoint sprawl and
keeps the API surface small.  No separate ``/tasks``, ``/operations``,
``/executions`` routes.

ARCHITECTURE
────────────
::

    create_runs_router(dispatcher) → APIRouter
      POST   /runs          ─ submit new work
      GET    /runs           ─ list runs (filter by status/kind)
      GET    /runs/{run_id}  ─ get run details
      POST   /runs/{run_id}/cancel  ─ request cancellation
      GET    /runs/summary   ─ aggregate stats

    Depends on:
      EventDispatcher ─ all operations delegate here
      FastAPI         ─ optional dependency (graceful fallback)

Related modules:
    dispatcher.py — EventDispatcher (business logic)
    spec.py       — WorkSpec (request body model)
    runs.py       — RunRecord (response model)

*Source: [`fastapi.py`](spine-core/src/spine/execution/fastapi.py#L1)*

New users and integration tests need concrete handlers to exercise
the execution stack.  These register into the global
:class:`~spine.execution.registry.HandlerRegistry` on import,
so the WorkerLoop can resolve them by name immediately.

ARCHITECTURE
────────────
::

    Handlers (auto-registered on import):
      task:echo          ─ echo params unchanged
      task:sleep         ─ sleep for N seconds
      task:add           ─ add a + b
      task:fail          ─ always raises (DLQ / retry testing)
      task:transform     ─ apply a transform function
      operation:etl_stub  ─ simulates extract → transform → load

Usage::

    import spine.execution.handlers   # registers into global registry
    from spine.execution.worker import WorkerLoop
    WorkerLoop(db_path="spine.db").start()

Related modules:
    registry.py — HandlerRegistry these register into
    worker.py   — WorkerLoop that resolves handlers by name

*Source: [`handlers.py`](spine-core/src/spine/execution/handlers.py#L1)*

Execution infrastructure must self-report health so operators
    can detect capacity, queue depth, or executor failures before
    they cascade into user-visible outages.

*Source: [`health.py`](spine-core/src/spine/execution/health.py#L1)*

Every execution must have an auditable history of who ran what,
    when, and with what outcome.  The ledger is the single source
    of truth for execution lineage and powers replay, debugging,
    and compliance reporting.

*Source: [`ledger.py`](spine-core/src/spine/execution/ledger.py#L1)*

Execution state must be representable as plain data so it can
    be serialized, stored, and compared across executor backends
    without coupling to any one runtime.

*Source: [`models.py`](spine-core/src/spine/execution/models.py#L1)*

External APIs (SEC EDGAR, LLM endpoints) enforce rate limits.
Exceeding them causes bans or 429 errors.  In-process rate limiters
let spine throttle outgoing calls *before* hitting the limit.

ARCHITECTURE
────────────
::

    RateLimiter (ABC)
      ├── TokenBucketLimiter     ─ steady rate + burst capacity
      ├── SlidingWindowLimiter   ─ exact count in rolling window
      ├── KeyedRateLimiter       ─ per-key limits (e.g. per-CIK)
      └── CompositeRateLimiter   ─ combine multiple strategies

    All limiters are thread-safe (internal Lock).

BEST PRACTICES
──────────────
- Use ``TokenBucketLimiter`` for steady throughput with burst.
- Use ``SlidingWindowLimiter`` for strict per-window caps.
- Use ``KeyedRateLimiter`` when limits vary by entity (per-CIK,
  per-API-key).
- Combine with ``CircuitBreaker`` for full resilience.

Related modules:
    circuit_breaker.py — fail-fast on sustained failures
    retry.py           — backoff on transient failures
    timeout.py         — enforce deadlines

Example::

    limiter = TokenBucketLimiter(rate=10, capacity=20)
    if limiter.acquire():
        make_api_call()
    else:
        raise RateLimitExceeded("Too many requests")

*Source: [`rate_limit.py`](spine-core/src/spine/execution/rate_limit.py#L1)*

The EventDispatcher needs to resolve ``"task:send_email"`` to a
callable handler.  The registry decouples registration (at import
time or startup) from resolution (at dispatch time), and supports
both a global singleton and injectable instances for testing.

ARCHITECTURE
────────────
::

    HandlerRegistry
      ├── .register(kind, name, handler)  ─ store handler
      ├── .get(kind, name)                ─ lookup by key
      ├── .list_handlers()                ─ all registered keys
      └── .has(kind, name)                ─ existence check

    Convenience decorators (use global registry):
      register_task(name)        → registers as "task:{name}"
      register_operation(name)    → registers as "operation:{name}"
      register_workflow(name)    → registers as "workflow:{name}"
      register_step(name)        → registers as "step:{name}"

    get_default_registry()     ─ module-level singleton
    reset_default_registry()   ─ clear for testing

BEST PRACTICES
──────────────
- Use ``register_task`` / ``register_operation`` decorators for
  production code; pass explicit ``HandlerRegistry`` in tests.
- Call ``reset_default_registry()`` in test fixtures.

Related modules:
    dispatcher.py — EventDispatcher uses the registry
    handlers.py   — built-in example handlers
    spec.py       — WorkSpec references handler by name

*Source: [`registry.py`](spine-core/src/spine/execution/registry.py#L1)*

The :class:`ExecutionLedger` handles basic CRUD (create, update,
get-by-id).  The repository adds higher-level analytic queries
(stats over time, stale-execution detection, bulk cleanup) used
by health checks, dashboards, and scheduled maintenance jobs.

ARCHITECTURE
────────────
::

    ExecutionRepository(conn)
      ├── .get_execution_stats(hours)       ─ counts + durations
      ├── .get_stale_executions(minutes)    ─ stuck “running” rows
      ├── .get_operation_stats(operation)     ─ per-operation analytics
      ├── .cleanup_old(days)                ─ purge completed records
      └── .get_execution_timeline(hours)    ─ time-series for charts

Related modules:
    ledger.py  — basic CRUD (create / update / get)
    health.py  — uses repository for health scoring
    dlq.py     — dead-letter queue (failed executions)

Example::

    repo = ExecutionRepository(conn)
    stats = repo.get_execution_stats(hours=24)
    print(stats["status_counts"])  # {'completed': 50, 'failed': 5}
    stale = repo.get_stale_executions(older_than_minutes=60)

*Source: [`repository.py`](spine-core/src/spine/execution/repository.py#L1)*

Transient failures (network blips, 429 rate-limits, brief outages)
often resolve if you wait and try again.  Retry strategies calculate
the delay between attempts, with jitter to avoid thundering-herd.

ARCHITECTURE
────────────
::

    RetryStrategy (ABC)
      ├── ExponentialBackoff  ─ 2^n * base_delay (most common)
      ├── LinearBackoff       ─ n * base_delay
      ├── ConstantBackoff     ─ fixed delay
      └── NoRetry             ─ immediate fail (testing)

    RetryContext
      ├── .attempt            ─ current attempt number
      ├── .last_error         ─ most recent exception
      └── .total_delay        ─ cumulative wait time

    with_retry(fn, strategy)   ─ decorator / wrapper

BEST PRACTICES
──────────────
- Use ``ExponentialBackoff`` for API calls (EDGAR, LLM).
- Set ``max_delay`` to cap the wait (e.g. 60s).
- Enable ``jitter=True`` (default) to avoid thundering herd.
- Combine with ``CircuitBreaker`` for sustained outages.

Related modules:
    circuit_breaker.py — fail-fast after sustained failures
    rate_limit.py      — throttle before hitting limits
    timeout.py         — enforce deadlines

Example::

    strategy = ExponentialBackoff(max_retries=5, base_delay=1.0)
    result = with_retry(call_api, strategy=strategy)

*Source: [`retry.py`](spine-core/src/spine/execution/retry.py#L1)*

Any object that can "run" should expose a single interface.
    The Runnable protocol unifies tasks, workflows, and dispatchers
    so runners and executors accept them interchangeably.

*Source: [`runnable.py`](spine-core/src/spine/execution/runnable.py#L1)*

Run tracking must be executor-agnostic.  Whether a run executes
    locally, in Celery, or in a container, the same RunRecord
    captures its lifecycle so dashboards and alerting work
    unchanged across backends.

*Source: [`runs.py`](spine-core/src/spine/execution/runs.py#L1)*

A single WorkSpec schema means any executor can accept any
    work request without format translation.  This eliminates
    per-executor request models and keeps submission uniform.

*Source: [`spec.py`](spine-core/src/spine/execution/spec.py#L1)*

Celery tasks should be thin wrappers that delegate to handler
    functions.  This keeps business logic testable without a broker
    and lets the same handler run in any executor.

*Source: [`tasks.py`](spine-core/src/spine/execution/tasks.py#L1)*

Operations without timeouts are a reliability anti-pattern:
    - **Resource exhaustion:** Long-running tasks block workers
    - **Cascading failures:** Slow dependencies hang callers
    - **Poor user experience:** Users don't get timely feedback

    Spine's timeout enforcement is simple and composable:
    - Context manager: `with with_deadline(seconds):`
    - Decorator: `@timeout(seconds)`
    - Async support: Works with both sync and async code
    - Nested deadlines: Inner deadline wins if shorter

*Source: [`timeout.py`](spine-core/src/spine/execution/timeout.py#L1)*

The worker is the process-level loop that polls for work and
    delegates to handlers.  Keeping it thin and configurable means
    operators can tune concurrency without changing business logic.

*Source: [`worker.py`](spine-core/src/spine/execution/worker.py#L1)*

When a ``WorkSpec(kind="workflow")`` is submitted, the execution
layer needs to hand off to the orchestration layer.  This module
registers a handler that looks up the workflow, creates a
``WorkflowRunner`` **with the dispatcher as its Runnable**, so
operation steps inside the workflow also get full ``RunRecord``
tracking.

ARCHITECTURE
────────────
::

    EventDispatcher.submit(workflow_spec("ingest.daily"))
      │
      ▼
    _make_workflow_handler(dispatcher)
      │
      ├── get_workflow(name)           ─ from workflow_registry
      ├── WorkflowRunner(runnable=dispatcher)
      └── runner.execute(workflow, params)
            │
            └── operation steps → dispatcher.submit_operation_sync()
                 (full RunRecord tracking preserved)

    register_workflow_executor(registry) ─ wire into HandlerRegistry

Related modules:
    dispatcher.py              — the calling dispatcher
    orchestration.workflow_runner — WorkflowRunner
    orchestration.workflow_registry — get_workflow(name)

Registration::

    from spine.execution.workflow_executor import register_workflow_executor
    register_workflow_executor(registry)

*Source: [`workflow_executor.py`](spine-core/src/spine/execution/workflow_executor.py#L1)*

Operations, tasks, and workflows all need the same lifecycle: submit,
track, retry-on-failure, and report.  Rather than each project
reimplementing this, ``spine.execution`` provides a single contract
(``WorkSpec → EventDispatcher → RunRecord``) that works across
every runtime (threads, processes, Celery, containers).

ARCHITECTURE
────────────
::

    WorkSpec (what to run)
      │
      ▼
    EventDispatcher (submit / query / cancel)
      ├── HandlerRegistry ─ name → handler lookup
      ├── Executor        ─ runtime adapter (how it runs)
      │     ├─ MemoryExecutor    (in-process, testing)
      │     ├─ LocalExecutor     (ThreadPool)
      │     ├─ AsyncLocalExecutor (asyncio semaphore)
      │     ├─ ProcessExecutor   (ProcessPool, GIL escape)
      │     ├─ CeleryExecutor    (distributed, experimental)
      │     └─ StubExecutor      (no-op, dry-run)
      ├── RunRecord       ─ execution state + timestamps
      └── RunEvent        ─ immutable event-sourced history
      │
      ▼
    Resilience layer
      ├── RetryStrategy     ─ exponential / linear / constant backoff
      ├── CircuitBreaker    ─ fail-fast on downstream failures
      ├── RateLimiter       ─ token-bucket / sliding-window
      ├── ConcurrencyGuard  ─ DB-level lock (no duplicate runs)
      └── DeadlineContext   ─ per-step and per-workflow timeouts
      │
      ▼
    Infrastructure
      ├── ExecutionLedger   ─ persistent execution storage
      ├── DLQManager        ─ dead-letter queue for failed work
      ├── ExecutionRepository ─ analytics + maintenance queries
      ├── BatchExecutor     ─ coordinated multi-operation runs
      ├── AsyncBatchExecutor ─ asyncio fan-out / fan-in
      └── WorkerLoop        ─ polling loop for background work

    Sub-packages
      ├── executors/        ─ Executor protocol + 6 implementations
      ├── runtimes/         ─ container-level RuntimeAdapter + JobEngine
      └── packaging/        ─ PEP 441 zip-app bundler

MODULE MAP (recommended reading order)
──────────────────────────────────────
Contracts & Models
  1. spec.py              ─ WorkSpec + factory helpers
  2. runs.py              ─ RunRecord, RunStatus, state-machine
  3. events.py            ─ RunEvent (event-sourced history)
  4. models.py            ─ Execution, ExecutionEvent, DeadLetter

Submission & Dispatch
  5. registry.py          ─ HandlerRegistry, register_task/operation
  6. dispatcher.py        ─ EventDispatcher (THE public API)
  7. handlers.py          ─ built-in example handlers

Infrastructure
  8. context.py           ─ ExecutionContext, tracked_execution
  9. ledger.py            ─ ExecutionLedger (persistent storage)
 10. repository.py        ─ analytics + maintenance queries
 11. concurrency.py       ─ ConcurrencyGuard (DB-level locking)
 12. dlq.py               ─ DLQManager (dead-letter queue)

Resilience
 13. retry.py             ─ ExponentialBackoff, with_retry
 14. circuit_breaker.py   ─ CircuitBreaker + registry
 15. rate_limit.py        ─ TokenBucket, SlidingWindow, Keyed, Composite
 16. timeout.py           ─ DeadlineContext, with_deadline

Batch & Async
 17. batch.py             ─ BatchExecutor (thread-pool fan-out)
 18. async_batch.py       ─ AsyncBatchExecutor (asyncio fan-out)

Workers & Integration
 19. worker.py            ─ WorkerLoop (polling background worker)
 20. workflow_executor.py ─ bridge: dispatcher → orchestration runner
 21. fastapi.py           ─ /runs REST API router
 22. health.py            ─ ExecutionHealthChecker
 23. tasks.py             ─ Celery task stubs

Executors (sub-package)
 24. executors/protocol.py    ─ Executor protocol
 25. executors/memory.py      ─ in-process (testing)
 26. executors/local.py       ─ ThreadPool
 27. executors/async_local.py ─ asyncio semaphore
 28. executors/process.py     ─ ProcessPool (GIL escape)
 29. executors/celery.py      ─ distributed (experimental)
 30. executors/stub.py        ─ no-op (dry-run)

Example::

    from spine.execution import EventDispatcher, task_spec, register_task
    from spine.execution.executors import MemoryExecutor

    @register_task("send_email")
    async def send_email(params):
        return {"sent": True}

    dispatcher = EventDispatcher(executor=MemoryExecutor())
    run_id = await dispatcher.submit_task("send_email", {"to": "user@example.com"})
    run = await dispatcher.get_run(run_id)
    print(run.status)  # RunStatus.COMPLETED

*Source: [`__init__.py`](spine-core/src/spine/execution/__init__.py#L1)*

I/O-bound work (HTTP downloads, DB queries, LLM API calls) benefits
from async concurrency without OS threads.  ``AsyncLocalExecutor``
uses ``asyncio.Semaphore`` for bounded parallelism on a single
event loop — the recommended executor for feedspine-style async work.

ARCHITECTURE
────────────
::

    AsyncLocalExecutor(max_concurrency=10)
      ├── .register(kind, name, handler)  ─ async handler
      ├── .submit(spec)                   ─ enqueue coroutine
      ├── .wait(ref)                      ─ await completion
      └── .get_status(ref)                ─ poll result

    Handlers must be ``async def`` coroutines.

BEST PRACTICES
──────────────
- Use for SEC EDGAR downloads, LLM API calls, async DB queries.
- Set ``max_concurrency`` to respect upstream rate limits.
- Combine with ``RateLimiter`` for per-endpoint throttling.

Related modules:
    protocol.py     — Executor protocol
    local.py        — ThreadPool version for sync handlers
    async_batch.py  — higher-level batch API using asyncio

Example::

    executor = AsyncLocalExecutor(max_concurrency=10)
    executor.register("task", "download", download_handler)
    ref = await executor.submit(task_spec("download", {"url": url}))
    await executor.wait(ref)

*Source: [`async_local.py`](spine-core/src/spine/execution/executors/async_local.py#L1)*

For production workloads requiring distributed execution across
multiple machines, priority queues, and durable result backends,
Celery provides a mature platform.  This executor wraps it behind
the standard ``Executor`` protocol.

ARCHITECTURE
────────────
::

    CeleryExecutor(app=celery_app)
      ├── .submit(spec)     ─ celery_app.send_task()
      ├── .get_status(ref)  ─ AsyncResult(ref).status
      └── .cancel(ref)      ─ AsyncResult(ref).revoke()

    Requires: ``pip install celery[redis]``
    Optional dependency — graceful ImportError fallback.

Related modules:
    protocol.py — Executor protocol
    tasks.py    — Celery task stubs
    local.py    — non-distributed alternative

*Source: [`celery.py`](spine-core/src/spine/execution/executors/celery.py#L1)*

``MemoryExecutor`` is blocking; ``CeleryExecutor`` requires Redis +
worker processes.  ``LocalExecutor`` sits in between — it uses
``ThreadPoolExecutor`` for real concurrency without external
dependencies.  Good for dev, small production, and integration tests.

ARCHITECTURE
────────────
::

    LocalExecutor(max_workers=4)
      ├── .submit(spec)     ─ submit to ThreadPool
      ├── .get_status(ref)  ─ poll Future
      └── .shutdown()       ─ drain pool

Related modules:
    protocol.py       — Executor protocol
    async_local.py    — asyncio version for I/O-bound work
    process.py        — ProcessPool for CPU-bound work

*Source: [`local.py`](spine-core/src/spine/execution/executors/local.py#L1)*

Unit tests need deterministic, fast execution without threads,
queues, or external services.  ``MemoryExecutor`` runs handlers
synchronously in the calling thread, making test assertions trivial.

ARCHITECTURE
────────────
::

    MemoryExecutor(handlers={"task:echo": echo_fn})
      ├── .submit(spec)     ─ run sync, return ref
      ├── .get_status(ref)  ─ always completed/failed
      └── ._results[ref]    ─ in-memory result store

    NOT for production (blocking, no persistence, lost on crash).

Related modules:
    protocol.py   — Executor protocol this implements
    stub.py       — even simpler (no handler execution)
    local.py      — ThreadPool for concurrent testing

*Source: [`memory.py`](spine-core/src/spine/execution/executors/memory.py#L1)*

CPU-bound work (NLP extraction, PDF parsing, data aggregation)
cannot benefit from threads due to the GIL.  ``ProcessExecutor``
uses ``ProcessPoolExecutor`` to distribute work across cores.

ARCHITECTURE
────────────
::

    ProcessExecutor(max_workers=4)
      ├── .register(kind, name, import_path)  ─ dotted path string
      ├── .submit(spec)                       ─ fork to process
      └── .shutdown()                         ─ drain pool

    Handlers must be top-level picklable functions
    (not closures or lambdas).  Reference by import path:
    ``"myapp.parsers.parse_pdf"``

Related modules:
    protocol.py    — Executor protocol
    local.py       — ThreadPool (I/O-bound or simpler use-case)

Example::

    executor = ProcessExecutor(max_workers=4)
    executor.register("task", "parse_pdf", "myapp.parsers.parse_pdf")
    ref = await executor.submit(task_spec("parse_pdf", {"path": "file.pdf"}))

*Source: [`process.py`](spine-core/src/spine/execution/executors/process.py#L1)*

Regardless of how work is actually executed (threads, processes,
Celery, Kubernetes), the ``EventDispatcher`` needs a uniform
interface.  ``Executor`` is a ``typing.Protocol`` — any object with
the right methods satisfies it, no base class required.

ARCHITECTURE
────────────
::

    Executor (Protocol)
      ├── .submit(spec)    ─ start work, return external_ref
      ├── .get_status(ref) ─ query status (optional)
      └── .cancel(ref)     ─ request cancellation (optional)

    Implementations:
      MemoryExecutor     ─ in-process, sync   (testing)
      LocalExecutor      ─ ThreadPool          (dev / small prod)
      AsyncLocalExecutor ─ asyncio semaphore   (I/O-bound)
      ProcessExecutor    ─ ProcessPool         (CPU-bound)
      CeleryExecutor     ─ distributed         (production)
      StubExecutor       ─ no-op               (dry-run)

Related modules:
    dispatcher.py — EventDispatcher delegates to Executor
    runnable.py   — Runnable protocol (blocking operation interface)

*Source: [`protocol.py`](spine-core/src/spine/execution/executors/protocol.py#L1)*

Sometimes you want to test dispatcher logic, validate WorkSpec
routing, or run in dry-run mode without actually executing any
work.  ``StubExecutor`` always succeeds immediately — the simplest
possible ``Executor`` implementation.

ARCHITECTURE
────────────
::

    StubExecutor()
      ├── .submit(spec)     ─ return ref immediately
      ├── .get_status(ref)  ─ always “completed”
      └── .cancel(ref)      ─ no-op

Related modules:
    protocol.py  — Executor protocol
    memory.py    — actually runs handlers (richer testing)

*Source: [`stub.py`](spine-core/src/spine/execution/executors/stub.py#L1)*

Executor backends must be swappable.  This package provides
    local, async, process-pool, Celery, memory, and stub
    implementations behind a single protocol so deployments
    choose the right backend without changing application code.

*Source: [`__init__.py`](spine-core/src/spine/execution/executors/__init__.py#L1)*

The packager implements the physical archive format.  It uses
    Python's zipapp so the result is a standard .pyz that runs
    with ``python my_operation.pyz`` — no special tooling needed.

*Source: [`packager.py`](spine-core/src/spine/execution/packaging/packager.py#L1)*

Workflows should be deployable as single-file artifacts.
    The packager serialises a workflow definition and its steps
    into a self-contained .pyz archive for air-gapped or
    edge deployments.

*Source: [`__init__.py`](spine-core/src/spine/execution/packaging/__init__.py#L1)*

The JobEngine is the single entry-point for submitting work.
    It resolves the right runtime adapter, validates the spec,
    and records the execution — callers never interact with
    adapters directly.

*Source: [`engine.py`](spine-core/src/spine/execution/runtimes/engine.py#L1)*

In development, restarting the engine to pick up config
    changes wastes time.  HotReload watches for adapter config
    changes and swaps them in-place without downtime.

*Source: [`hot_reload.py`](spine-core/src/spine/execution/runtimes/hot_reload.py#L1)*

The local-process adapter runs operations as subprocesses
    on the same machine.  It is the default for development
    and CI, giving full isolation without container overhead.

*Source: [`local_process.py`](spine-core/src/spine/execution/runtimes/local_process.py#L1)*

Tests should run instantly without real infrastructure.
    Mock adapters simulate runtime behaviour — success, failure,
    timeout — so test suites cover all edge cases in-memory.

*Source: [`mock_adapters.py`](spine-core/src/spine/execution/runtimes/mock_adapters.py#L1)*

A single router selects the right runtime adapter for each
    spec based on declared requirements (GPU, memory, runtime
    label).  Adding a new backend is just registering an adapter.

*Source: [`router.py`](spine-core/src/spine/execution/runtimes/router.py#L1)*

Catching spec-vs-adapter mismatches before submission
    prevents wasted compute and confusing runtime errors.
    The validator checks capabilities, resource limits, and
    image availability up front.

*Source: [`validator.py`](spine-core/src/spine/execution/runtimes/validator.py#L1)*

All runtime adapters inherit from ``BaseRuntimeAdapter``
    which enforces the protocol and provides sensible defaults
    for health checks, logging, and graceful shutdown.

*Source: [`_base.py`](spine-core/src/spine/execution/runtimes/_base.py#L1)*

Shared type definitions live here so adapters and the engine
    import from one place.  This prevents circular imports and
    gives a single source of truth for runtime-layer contracts.

*Source: [`_types.py`](spine-core/src/spine/execution/runtimes/_types.py#L1)*

Runtime adapters abstract the "where" of execution — local
    process, Docker, Kubernetes, or Lambda — behind a single
    protocol.  Operations declare what they need; the engine
    picks the adapter.

*Source: [`__init__.py`](spine-core/src/spine/execution/runtimes/__init__.py#L1)*

## Orchestration

Constructing ``Workflow`` objects by hand with ``Step.operation()`` and
``Step.lambda_()`` is verbose for common patterns.  Composition operators
provide concise, composable functions that produce well-formed
workflows from building blocks.

ARCHITECTURE
────────────
::

    Composition operators:
      chain(name, *steps)                 → sequential workflow
      parallel(name, *steps, merge_fn)    → DAG with shared root
      conditional(name, cond, then, else) → choice-based branching
      retry(name, step, max_attempts)     → retry wrapper around a step
      merge_workflows(name, *workflows)   → combine multiple workflows

    All operators return a ``Workflow`` instance that can be:
      - Executed directly via ``WorkflowRunner``
      - Registered in the ``WorkflowRegistry``
      - Composed further with other operators

BEST PRACTICES
──────────────
- Use ``chain()`` instead of manually listing sequential steps.
- Use ``parallel()`` for independent steps that can run concurrently.
- Nest operators to build complex topologies:
    ``chain("outer", step_a, parallel("inner", step_b, step_c), step_d)``

Related modules:
    templates.py       — higher-level domain-specific patterns
    step_types.py      — Step factories used by operators
    workflow.py        — the Workflow these operators produce

Example::

    from spine.orchestration.composition import chain, parallel

    wf = chain(
        "my.etl",
        Step.operation("extract", "my.extract"),
        Step.operation("transform", "my.transform"),
        Step.operation("load", "my.load"),
    )

    wf = parallel(
        "my.parallel_ingest",
        Step.operation("source_a", "ingest.source_a"),
        Step.operation("source_b", "ingest.source_b"),
        Step.operation("source_c", "ingest.source_c"),
    )

*Source: [`composition.py`](spine-core/src/spine/orchestration/composition.py#L1)*

The Job Engine and Workflow Engine are separate subsystems.  The
    ContainerRunnable bridges them by implementing the ``Runnable``
    protocol so ``WorkflowRunner`` can dispatch steps to either.

*Source: [`container_runnable.py`](spine-core/src/spine/orchestration/container_runnable.py#L1)*

Before running a workflow against production data, developers need to
verify the execution plan: which steps will run, in what order, and
what resources will be consumed.  Dry-run mode executes the workflow
graph *structurally* — evaluating dependencies, validating configs,
and estimating cost — without actually invoking operation backends.

ARCHITECTURE
────────────
::

    dry_run(workflow, params)
    │
    ├── Validate all steps (lint)
    ├── Resolve execution order
    ├── Estimate per-step cost/time
    ├── Check parameter requirements
    │
    ▼
    DryRunResult
    ├── execution_plan: list[DryRunStep]
    ├── total_estimated_seconds: float
    ├── validation_issues: list[str]
    ├── is_valid: bool
    └── summary() → str

    DryRunStep
    ├── step_name, step_type
    ├── order: int
    ├── estimated_seconds: float
    ├── will_execute: bool
    └── notes: list[str]

BEST PRACTICES
──────────────
- Always dry-run before deploying to production.
- Register cost estimators for expensive operations.
- Combine with ``lint_workflow()`` for comprehensive pre-flight checks.

Related modules:
    workflow_runner.py — has ``dry_run=True`` for mock operation runs
    linter.py          — static analysis (complementary)
    visualizer.py      — visual representation of the plan

Example::

    from spine.orchestration.dry_run import dry_run

    result = dry_run(workflow, params={"tier": "NMS_TIER_1"})
    print(result.summary())
    if result.is_valid:
        runner.execute(workflow, params=params)

*Source: [`dry_run.py`](spine-core/src/spine/orchestration/dry_run.py#L1)*

Orchestration failures span many categories (plan resolution, group
    specs, step dependencies, timeout, execution).  A structured hierarchy
    lets callers catch broad (``OrchestrationError``) or narrow
    (``PlanResolutionError``) as needed.

All orchestration exceptions inherit from ``spine.core.errors.OrchestrationError``
so that callers can catch the entire family with a single ``except`` clause.

Hierarchy::

    OrchestrationError  (from spine.core.errors)
      └── GroupError                  ── base for all orchestration errors
            ├── GroupNotFoundError      ── operation group not registered
            ├── StepNotFoundError       ── step references unknown operation
            ├── CycleDetectedError      ── dependency graph has a cycle
            ├── PlanResolutionError     ── cannot resolve execution plan
            ├── InvalidGroupSpecError   ── YAML/dict spec is invalid
            └── DependencyError         ── step dependencies are invalid

*Source: [`exceptions.py`](spine-core/src/spine/orchestration/exceptions.py#L1)*

Run-time failures are expensive.  The linter catches structural issues,
    naming violations, and dependency graph problems *before* execution.

*Source: [`linter.py`](spine-core/src/spine/orchestration/linter.py#L1)*

Existing business functions shouldn't need rewriting to get workflow
    lifecycle management.  ``ManagedWorkflow`` wraps any callable and
    gives it persistence, retry, and observability for free.

*Source: [`managed_workflow.py`](spine-core/src/spine/orchestration/managed_workflow.py#L1)*

Debugging workflows requires stepping through execution interactively.
    The Playground lets developers execute one step at a time, inspect
    intermediate state, and re-execute steps without restarting.

*Source: [`playground.py`](spine-core/src/spine/orchestration/playground.py#L1)*

Reproducing workflow failures requires the exact inputs and outputs
    of every step.  The Recorder captures this as a replayable trace
    for debugging and regression testing.

*Source: [`recorder.py`](spine-core/src/spine/orchestration/recorder.py#L1)*

Business logic functions should not import or depend on the workflow
    framework.  Step adapters wrap plain functions to conform to the
    step interface, keeping business code decoupled and testable.

*Source: [`step_adapters.py`](spine-core/src/spine/orchestration/step_adapters.py#L1)*

Every step (lambda, operation, choice) must return a uniform result so
that the WorkflowRunner can: decide success/failure, pass outputs to
the next step, evaluate quality gates, and categorise errors for retry
decisions.  ``StepResult`` is that envelope.

ARCHITECTURE
────────────
::

    StepResult
      ├── .ok(output, context_updates, quality)     → success
      ├── .fail(error, category, quality)            → failure
      ├── .skip(reason)                              → no-op success
      ├── .from_value(any)                           → coerce plain returns
      └── .with_next_step(name)                      → choice branching

    ErrorCategory  ── INTERNAL, DATA_QUALITY, TRANSIENT, TIMEOUT, ...
    QualityMetrics ── record_count, valid_count, passed, custom_metrics

BEST PRACTICES
──────────────
- Prefer ``StepResult.ok()`` / ``StepResult.fail()`` factories over
  constructing directly.
- Use ``from_value()`` to wrap plain-function returns automatically.
- Set ``error_category`` on failures so retry policies can distinguish
  transient vs permanent errors.

Related modules:
    step_types.py       — Step definitions that produce StepResults
    workflow_runner.py  — consumes StepResults to drive workflow state
    step_adapters.py    — adapts plain functions to return StepResults

Example::

    from spine.orchestration import StepResult, QualityMetrics

    def validate_data(ctx, config):
        records = fetch_records()
        valid = [r for r in records if is_valid(r)]
        quality = QualityMetrics(record_count=len(records), valid_count=len(valid))
        if quality.valid_rate < 0.95:
            return StepResult.fail("Too few valid", category="DATA_QUALITY", quality=quality)
        return StepResult.ok(output={"valid_count": len(valid)}, quality=quality)

*Source: [`step_result.py`](spine-core/src/spine/orchestration/step_result.py#L1)*

A Workflow is a list of Steps, but steps come in different flavours:
lambda (inline function), operation (registered Operation), choice
(conditional branch), wait (pause), and map (fan-out/fan-in).  This
module defines the ``Step`` dataclass and its factory methods so that
workflow authors never deal with raw internals.

ARCHITECTURE
────────────
::

    Step
      ├── .operation(name, operation_name)     ── wraps a registered Operation
      ├── .lambda_(name, handler)             ── inline function
      ├── .from_function(name, fn)            ── plain Python → adapted handler
      ├── .choice(name, condition, then/else) ── conditional branch
      ├── .wait(name, seconds)                ── pause execution
      └── .map(name, items, iterator)          ── fan-out/fan-in

    StepType      ── enum: LAMBDA, operation, CHOICE, WAIT, MAP
    ErrorPolicy   ── STOP or CONTINUE on step failure
    RetryPolicy   ── max_retries + backoff configuration

Related modules:
    step_result.py     — StepResult returned by every step
    step_adapters.py   — adapt plain functions into step handlers
    workflow.py        — Workflow that contains the steps

Example::

    from spine.orchestration import Workflow, Step

    workflow = Workflow(
        name="my.workflow",
        steps=[
            Step.operation("ingest", "my.ingest_operation"),
            Step.lambda_("validate", validate_fn),
            Step.choice("route",
                condition=lambda ctx: ctx.params.get("valid"),
                then_step="process",
                else_step="reject",
            ),
        ],
    )

*Source: [`step_types.py`](spine-core/src/spine/orchestration/step_types.py#L1)*

Many workflows follow the same shape: ETL operations, fan-out/fan-in,
conditional routing, retry wrappers, scheduled batches.  Instead of
re-inventing these each time, templates provide factory functions that
produce a fully-wired ``Workflow`` you can customise and register.

ARCHITECTURE
────────────
::

    Built-in templates:
      etl_operation(name, extract, transform, load)      → 3-step ETL
      fan_out_fan_in(name, items, iterator, merge)      → scatter/gather
      conditional_branch(name, condition, then, else_)  → if/else routing
      retry_wrapper(name, operation, max_retries)        → retry + fallback
      scheduled_batch(name, operation)                   → wait → run → notify

    Template registry:
      register_template(name, factory)   → add custom template
      get_template(name)                 → retrieve factory
      list_templates()                   → available template names

BEST PRACTICES
──────────────
- Templates return a ``Workflow`` — modify ``steps`` or ``defaults``
  before registering.
- Use ``register_template`` for organisation-specific patterns.

Related modules:
    workflow.py        — the Workflow that templates produce
    step_types.py      — Step factories used inside templates
    workflow_registry  — register the produced workflow

Example::

    from spine.orchestration.templates import etl_operation

    wf = etl_operation(
        name="finra.daily_etl",
        extract_operation="finra.fetch_data",
        transform_operation="finra.normalize",
        load_operation="finra.store",
    )

*Source: [`templates.py`](spine-core/src/spine/orchestration/templates.py#L1)*

Testing workflows requires creating ``Runnable`` doubles, setting up
context, and asserting on step results.  This module provides
off-the-shelf helpers so test code is concise and expressive.

ARCHITECTURE
────────────
::

    Test doubles:
      StubRunnable              → always succeeds (configurable outputs)
      FailingRunnable           → always fails (configurable error)
      ScriptedRunnable          → returns pre-configured results per operation

    Assertion helpers:
      assert_workflow_completed(result)
      assert_workflow_failed(result, step=None)
      assert_step_output(result, step_name, key, value)
      assert_step_count(result, expected)
      assert_no_failures(result)

    Factories:
      make_workflow(*handlers)  → quick workflow from plain functions
      make_context(params)      → create a WorkflowContext
      make_runner(runnable)     → WorkflowRunner with defaults

BEST PRACTICES
──────────────
- Use ``StubRunnable`` for workflows that only have lambda steps.
- Use ``ScriptedRunnable`` to test specific operation result handling.
- Prefer ``assert_workflow_completed()`` over manual status checks.

Related modules:
    conftest.py (tests/orchestration/) — internal _NoOpRunnable
    workflow_runner.py                 — the runner under test
    step_result.py                     — StepResult assertions

Example::

    from spine.orchestration.testing import (
        StubRunnable,
        assert_workflow_completed,
        make_workflow,
    )

    def test_simple_workflow():
        wf = make_workflow(lambda ctx, cfg: {"count": 42})
        runner = WorkflowRunner(runnable=StubRunnable())
        result = runner.execute(wf)
        assert_workflow_completed(result)
        assert_step_output(result, "step_1", "count", 42)

*Source: [`testing.py`](spine-core/src/spine/orchestration/testing.py#L1)*

The basic ``WorkflowRunner`` is ephemeral — results vanish when the
process exits.  ``TrackedWorkflowRunner`` adds persistence so that
every step’s outcome is recorded in the database, enabling:

- **Resumability** — restart a failed workflow from the last checkpoint
- **Idempotency** — re-running with the same partition key is a no-op
- **Observability** — query run history, inspect failures, measure timing

ARCHITECTURE
────────────
::

    TrackedWorkflowRunner(conn)
      ├── .execute(workflow, params, partition)   → WorkflowResult
      │       ├── creates WorkManifest (stage tracking)
      │       ├── delegates to WorkflowRunner.execute()
      │       └── records anomalies on failure
      ├── get_workflow_state(conn, run_id)        → manifest + result
      └── list_workflow_failures(conn, name)      → recent failures

    Depends on:
      spine.core.manifest     — WorkManifest for stage tracking
      spine.core.anomalies    — AnomalyRecorder for failure capture
      spine.core.protocols    — Connection protocol (SQLite or Postgres)

Related modules:
    workflow_runner.py     — the ephemeral runner this extends
    managed_workflow.py    — higher-level builder on top of this

Example::

    from spine.orchestration import Workflow, TrackedWorkflowRunner, Step

    runner = TrackedWorkflowRunner(conn)
    result = runner.execute(
        workflow,
        params={"tier": "NMS_TIER_1"},
        partition={"week_ending": "2026-01-10"},
    )

*Source: [`tracked_runner.py`](spine-core/src/spine/orchestration/tracked_runner.py#L1)*

Complex DAG workflows become unmanageable without a visual
    representation.  The visualiser renders workflow topology as
    Mermaid, DOT, or ASCII art so teams can review structure
    before execution.

*Source: [`visualizer.py`](spine-core/src/spine/orchestration/visualizer.py#L1)*

Operations do one thing well; Workflows compose multiple operations (and
lambda/choice/wait steps) into a reliable, observable multi-step process.
The Workflow dataclass is the ‘‘blueprint’’ — it declares **what** to run and
in what order, but never **how** to run it (that’s WorkflowRunner’s job).

ARCHITECTURE
────────────
::

    Workflow           ── defines steps, dependencies, defaults, policy
      ├── steps[]        ── ordered list of Step objects
      ├── execution_policy ─ sequential vs parallel, concurrency, timeout
      ├── defaults{}     ── default params merged into context
      └── domain         ── logical grouping (e.g. "finra.otc")

    WorkflowRunner.execute(workflow, params)   → WorkflowResult
    TrackedWorkflowRunner.execute(...)         → WorkflowResult + DB record

KEY CLASSES
───────────
- ``Workflow``          — the step graph (this module)
- ``ExecutionMode``     — SEQUENTIAL or PARALLEL
- ``FailurePolicy``     — STOP or CONTINUE on step failure
- ``WorkflowExecutionPolicy`` — groups mode + concurrency + timeout

Related modules:
    step_types.py          — Step definitions (lambda, operation, choice)
    workflow_runner.py     — executes the workflow
    workflow_context.py    — immutable context passed between steps

Example::

    from spine.orchestration import Workflow, Step, StepResult

    workflow = Workflow(
        name="finra.weekly_refresh",
        domain="finra.otc_transparency",
        steps=[
            Step.operation("ingest", "finra.otc_transparency.ingest_week"),
            Step.lambda_("validate", validate_fn),
            Step.operation("normalize", "finra.otc_transparency.normalize_week"),
        ],
    )

*Source: [`workflow.py`](spine-core/src/spine/orchestration/workflow.py#L1)*

Steps need to share state without coupling to each other.
    WorkflowContext provides a controlled, immutable-snapshot
    namespace so each step reads a consistent view and writes
    are batched between steps.

*Source: [`workflow_context.py`](spine-core/src/spine/orchestration/workflow_context.py#L1)*

Large applications define workflows in many modules.  The registry
provides a single lookup table so that runners, CLIs, and APIs can
find workflows by name without knowing which module defined them.

ARCHITECTURE
────────────
::

    register_workflow(workflow_or_factory)   → stores in global dict
    get_workflow(name)                       → returns Workflow or raises
    list_workflows(domain=None)             → names, optionally filtered
    clear_workflow_registry()               → reset (for testing)

    WorkflowNotFoundError  ── raised when get_workflow fails

BEST PRACTICES
──────────────
- Call ``clear_workflow_registry()`` in test fixtures to avoid leaks.
- Use domain-based naming (``"finra.otc.ingest"``) for discoverability.
- ``register_workflow`` accepts both a ``Workflow`` instance and a
  zero-arg factory function (decorated or direct).

Related modules:
    workflow.py        — the Workflow dataclass being registered
    workflow_runner.py — executes registered workflows

Example::

    from spine.orchestration.workflow_registry import (
        register_workflow, get_workflow, list_workflows, clear_workflow_registry,
    )

    register_workflow(my_workflow)
    workflow = get_workflow("ingest.daily")
    names = list_workflows(domain="ingest")

*Source: [`workflow_registry.py`](spine-core/src/spine/orchestration/workflow_registry.py#L1)*

Workflow definitions should remain pure data; execution
    concerns (concurrency, retry, persistence) live here in
    the runner so each concern can be tested in isolation.

*Source: [`workflow_runner.py`](spine-core/src/spine/orchestration/workflow_runner.py#L1)*

Workflow authors should be able to define pipelines in YAML
    without writing Python.  This module parses YAML definitions
    into the same Workflow model used by code-first authors,
    keeping both paths first-class.

*Source: [`workflow_yaml.py`](spine-core/src/spine/orchestration/workflow_yaml.py#L1)*

Raw operations (``Runnable.submit_operation_sync``) execute one unit of work.
Orchestration layers **multiple** units into a directed workflow with context
passing, conditional branching, error policies, and optional persistence.

ARCHITECTURE
────────────
::

    Workflow (DAG of Steps)
      ├── Step.lambda_()          ─ inline handler
      ├── Step.operation()         ─ wraps registered Operation
      ├── Step.from_function()    ─ plain-function adapter
      ├── Step.choice()           ─ conditional branch
      ├── Step.wait()             ─ timed pause
      └── Step.map()              ─ fan-out / fan-in

    WorkflowRunner         ─ executes sequentially or parallel (DAG)
    TrackedWorkflowRunner  ─ + database persistence
    WorkflowContext        ─ immutable context flowing step-to-step
    StepResult             ─ ok / fail / skip with quality metrics

    Supporting:
      templates.py         ─ pre-built workflow patterns
      workflow_yaml.py     ─ YAML ↔ Python round-trip
      playground.py        ─ interactive debugger with snapshots
      recorder.py          ─ capture & replay for regression testing
      linter.py            ─ static analysis of workflow graphs
      visualizer.py        ─ Mermaid, ASCII, and summary renderers

MODULE MAP (recommended reading order)
──────────────────────────────────────
1. exceptions.py         ─ error hierarchy
2. step_result.py        ─ StepResult + QualityMetrics
3. step_types.py         ─ Step dataclass + factory methods
4. step_adapters.py      ─ plain-function → step handler adapter
5. workflow_context.py   ─ immutable context object
6. workflow.py           ─ Workflow dataclass + dependency helpers
7. workflow_runner.py    ─ sequential + parallel execution engine
8. workflow_registry.py  ─ global name → Workflow lookup
9. tracked_runner.py     ─ database-backed runner wrapper
10. managed_workflow.py  ─ high-level import-and-manage API
11. templates.py         ─ pre-built workflow patterns
12. workflow_yaml.py     ─ YAML serialization / deserialization
13. playground.py        ─ interactive step-by-step debugger
14. container_runnable.py ─ DI-container Runnable bridge

Tier availability:
- Basic: Workflow, Step (lambda, operation, from_function), WorkflowRunner
- Intermediate: + ChoiceStep (conditional branching)
- Advanced: + WaitStep, MapStep, Checkpointing, Resume

Example (classic — framework-aware handler):
    from spine.orchestration import (
        Workflow,
        Step,
        StepResult,
        WorkflowRunner,
    )

    def validate_fn(ctx, config):
        count = ctx.get_output("ingest", "record_count", 0)
        if count < 100:
            return StepResult.fail("Too few records")
        return StepResult.ok(output={"validated": True})

    workflow = Workflow(
        name="finra.weekly_refresh",
        steps=[
            Step.operation("ingest", "finra.otc_transparency.ingest_week"),
            Step.lambda_("validate", validate_fn),
            Step.operation("normalize", "finra.otc_transparency.normalize_week"),
        ],
    )

    runner = WorkflowRunner()
    result = runner.execute(workflow, params={"tier": "NMS_TIER_1"})

Example (plain function — framework-agnostic):
    from spine.orchestration import Workflow, Step, workflow_step

    @workflow_step(name="validate")
    def validate_records(record_count: int, threshold: int = 100) -> dict:
        passed = record_count >= threshold
        return {"passed": passed, "count": record_count}

    # Direct call (notebook, script, market-spine — no framework):
    validate_records(record_count=42)

    # As a workflow step:
    workflow = Workflow(
        name="my.operation",
        steps=[
            Step.from_function("ingest", fetch_data),
            validate_records.as_step(),
        ],
    )

*Source: [`__init__.py`](spine-core/src/spine/orchestration/__init__.py#L1)*

LLM calls cost money.  A runaway workflow could burn through an
entire budget in minutes.  ``TokenBudget`` tracks cumulative token
usage and raises ``BudgetExhaustedError`` before the limit is
exceeded.

ARCHITECTURE
────────────
::

    TokenBudget(max_tokens)
    ├── .record(usage: TokenUsage) → track spending
    ├── .check(estimated)          → raise if over budget
    ├── .remaining                 → tokens left
    ├── .used                      → tokens spent
    └── .utilization               → 0.0 – 1.0

    BudgetExhaustedError           → raised when budget exceeded

Example::

    budget = TokenBudget(max_tokens=10_000)
    budget.record(response.usage)
    budget.check(estimated_tokens=500)   # raises if over

*Source: [`budget.py`](spine-core/src/spine/orchestration/llm/budget.py#L1)*

Testing LLM-powered workflows requires a provider that returns
predictable results without network calls.  ``MockLLMProvider``
supports canned responses, response scripting, and call tracking.

ARCHITECTURE
────────────
::

    MockLLMProvider
      ├── .complete(messages) → LLMResponse (canned or scripted)
      ├── .models()           → list of fake model names
      ├── .calls              → list of all calls made
      └── .call_count         → total calls

    Configuration:
      default_response   — text returned for all calls
      responses          — mapping of prompt substrings → responses
      sequence           — list of responses returned in order

Example::

    provider = MockLLMProvider(default_response="42")
    resp = provider.complete([Message.user("What is 6*7?")])
    assert resp.content == "42"

    provider = MockLLMProvider(sequence=["first", "second"])
    assert provider.complete([Message.user("1")]).content == "first"
    assert provider.complete([Message.user("2")]).content == "second"

*Source: [`mock.py`](spine-core/src/spine/orchestration/llm/mock.py#L1)*

Workflows that include LLM steps need a backend-agnostic interface.
This module defines the ``LLMProvider`` protocol, message types, and
response models so any backend (OpenAI, Bedrock, Ollama, mock) can
be swapped transparently.

ARCHITECTURE
────────────
::

    LLMProvider (Protocol)
      ├── .complete(messages, model, **kwargs) → LLMResponse
      └── .models() → list[str]

    Message(role, content)        — chat message
    Role                          — system | user | assistant
    TokenUsage(prompt, completion, total)
    LLMResponse(content, model, usage, metadata)

Related modules:
    mock.py     — MockLLMProvider for tests
    router.py   — route to provider by model name
    budget.py   — token budget enforcement

Example::

    class BedrockProvider:
        def complete(self, messages, model="anthropic.claude-v2", **kw):
            # call Bedrock API
            return LLMResponse(content="...", model=model, usage=...)

        def models(self):
            return ["anthropic.claude-v2", "amazon.titan-text"]

*Source: [`protocol.py`](spine-core/src/spine/orchestration/llm/protocol.py#L1)*

Workflows may use different models for different steps (e.g. a cheap
model for classification, an expensive one for generation).  The router
selects the appropriate ``LLMProvider`` based on the model name.

ARCHITECTURE
────────────
::

    LLMRouter
      ├── register(prefix, provider)     → add a provider
      ├── complete(messages, model)      → route to matching provider
      ├── models()                       → aggregate all models
      └── default_provider               → fallback

Example::

    router = LLMRouter()
    router.register("gpt-", openai_provider)
    router.register("claude-", bedrock_provider)
    router.default_provider = mock_provider

    # Routes to openai_provider:
    router.complete([Message.user("hi")], model="gpt-4")

    # Routes to bedrock_provider:
    router.complete([Message.user("hi")], model="claude-v2")

*Source: [`router.py`](spine-core/src/spine/orchestration/llm/router.py#L1)*

LLM providers differ wildly in API shape and billing.  The LLM
    subpackage defines a single ``LLMProvider`` protocol so workflows
    can call any model through one interface, with budgets and mocks
    for safe development.

*Source: [`__init__.py`](spine-core/src/spine/orchestration/llm/__init__.py#L1)*

## API Layer

The app factory is the single composition root — all middleware,
    routers, and lifecycle hooks are wired here so the rest of the
    codebase never touches ``FastAPI`` directly.

*Source: [`app.py`](spine-core/src/spine/api/app.py#L1)*

Dependency injection keeps routers thin.  Singletons (settings,
    DB connection) are created once; per-request objects (OpContext)
    carry request-scoped state through the call chain.

*Source: [`deps.py`](spine-core/src/spine/api/deps.py#L1)*

Shipped examples prove the happy path works and give new users
    something to explore in the dashboard from the first launch.

*Source: [`example_workflows.py`](spine-core/src/spine/api/example_workflows.py#L1)*

API settings extend the base so transport-level knobs (CORS,
    rate-limiting, auth) are separate from core business settings.

*Source: [`settings.py`](spine-core/src/spine/api/settings.py#L1)*

Utility functions shared across routers should live in one place
    so bug-fixes propagate everywhere and routers stay thin.

*Source: [`utils.py`](spine-core/src/spine/api/utils.py#L1)*

This package owns the HTTP boundary.  All business logic lives
    in ``spine.ops``; routers here handle only serialisation,
    authentication, error mapping, and request context.

*Source: [`__init__.py`](spine-core/src/spine/api/__init__.py#L1)*

API-key authentication is the simplest secure default.
    Bypass paths let health-checks and OpenAPI docs work
    without credentials.

*Source: [`auth.py`](spine-core/src/spine/api/middleware/auth.py#L1)*

Users should never see raw stack traces.  This middleware
    converts internal exceptions to structured JSON error bodies
    following RFC 7807 so clients get actionable diagnostics.

*Source: [`errors.py`](spine-core/src/spine/api/middleware/errors.py#L1)*

Rate-limiting protects the API from accidental or malicious
    overload.  The in-memory implementation works out of the box;
    production deployments can swap to Redis without code changes.

*Source: [`rate_limit.py`](spine-core/src/spine/api/middleware/rate_limit.py#L1)*

Every request gets a unique ID so logs, traces, and error
    reports can be correlated across services.

*Source: [`request_id.py`](spine-core/src/spine/api/middleware/request_id.py#L1)*

Server-side latency should be visible to every caller
    without extra instrumentation.  The timing header makes
    slow requests immediately obvious in browser dev-tools.

*Source: [`timing.py`](spine-core/src/spine/api/middleware/timing.py#L1)*

Cross-cutting concerns (auth, rate-limiting, timing, errors)
    belong in middleware so routers stay focused on business logic.

*Source: [`__init__.py`](spine-core/src/spine/api/middleware/__init__.py#L1)*

Alert channels must be configurable at runtime so operators
    can add Slack, email, or PagerDuty targets without redeploying.

*Source: [`alerts.py`](spine-core/src/spine/api/routers/alerts.py#L1)*

Surfacing data anomalies through the API gives dashboards
    real-time visibility into quality issues without polling the DB.

*Source: [`anomalies.py`](spine-core/src/spine/api/routers/anomalies.py#L1)*

Database introspection endpoints let operators check table
    counts, run integrity checks, and trigger backups through
    the API rather than direct SQL access.

*Source: [`database.py`](spine-core/src/spine/api/routers/database.py#L1)*

Deployment state should be queryable so CI/CD pipelines
    and operators can verify which version is running.

*Source: [`deploy.py`](spine-core/src/spine/api/routers/deploy.py#L1)*

External consumers need to discover available operations,
    handlers, and capabilities at runtime for dynamic integration.

*Source: [`discovery.py`](spine-core/src/spine/api/routers/discovery.py#L1)*

Failed executions must be inspectable and retryable through
    the API so operators don't need direct database access.

*Source: [`dlq.py`](spine-core/src/spine/api/routers/dlq.py#L1)*

Execution events should stream to consumers via SSE or polling
    so UIs and monitoring tools get near-real-time updates.

*Source: [`events.py`](spine-core/src/spine/api/routers/events.py#L1)*

Built-in example endpoints let new users explore the API
    interactively without setting up real data sources first.

*Source: [`examples.py`](spine-core/src/spine/api/routers/examples.py#L1)*

Registered handler functions should be invocable and
    inspectable through the API for ad-hoc execution and debugging.

*Source: [`functions.py`](spine-core/src/spine/api/routers/functions.py#L1)*

Interactive workflow exploration needs a safe sandbox where
    users can step through execution without touching production data.

*Source: [`playground.py`](spine-core/src/spine/api/routers/playground.py#L1)*

Data quality metrics should be accessible via API so dashboards
    can display freshness, completeness, and accuracy scores.

*Source: [`quality.py`](spine-core/src/spine/api/routers/quality.py#L1)*

Submitting and tracking runs via REST enables both UI
    dashboards and CI/CD pipelines to interact with execution.

*Source: [`runs.py`](spine-core/src/spine/api/routers/runs.py#L1)*

Schedules drive recurring execution.  CRUD endpoints let
    operators manage cron-like triggers without SSH access.

*Source: [`schedules.py`](spine-core/src/spine/api/routers/schedules.py#L1)*

Data sources must be manageable through the API so operators
    can add, update, and monitor ingestion endpoints dynamically.

*Source: [`sources.py`](spine-core/src/spine/api/routers/sources.py#L1)*

Aggregate statistics should be available via API for executive
    dashboards and capacity planning without custom queries.

*Source: [`stats.py`](spine-core/src/spine/api/routers/stats.py#L1)*

External systems must be able to trigger spine operations
    via simple HTTP POST without custom client libraries.

*Source: [`webhooks.py`](spine-core/src/spine/api/routers/webhooks.py#L1)*

Workflows are the primary unit of work.  These endpoints let
    dashboards list, inspect, and trigger any registered workflow.

*Source: [`workflows.py`](spine-core/src/spine/api/routers/workflows.py#L1)*

Each router module owns one API domain (runs, alerts, sources,
    etc.) and delegates to ``spine.ops`` for business logic.

*Source: [`__init__.py`](spine-core/src/spine/api/routers/__init__.py#L1)*

Every API response uses the same envelope so clients parse
    success, pagination, and errors with one set of models.

*Source: [`common.py`](spine-core/src/spine/api/schemas/common.py#L1)*

Domain-specific schemas keep validation close to the business
    rules so the API rejects invalid data before it hits the ops layer.

*Source: [`domains.py`](spine-core/src/spine/api/schemas/domains.py#L1)*

Example schemas for OpenAPI documentation give users copy-paste
    request bodies so they can start integrating faster.

*Source: [`examples.py`](spine-core/src/spine/api/schemas/examples.py#L1)*

Pydantic schemas define the API contract.  Centralising them
    here keeps routers and ops decoupled from serialisation details.

*Source: [`__init__.py`](spine-core/src/spine/api/schemas/__init__.py#L1)*

## Tooling

### ChangelogGenerator

Documentation should be generated FROM code, not written separately.
    This generator turns structured docstrings and git commit metadata
    into first-class documentation artifacts — deterministically,
    without manual authoring or drift.

*Source: [`ChangelogGenerator`](spine-core/src/spine/tools/changelog/generator.py#L59)*

### DocHeader

Module docstrings are the single source of truth for module
    classification. Doc Headers provide machine-readable metadata
    (Stability, Tier, Doc-Types) without sacrificing human readability.
    They sit between the summary line and prose body, parsed via
    pure regex — no imports needed.

*Source: [`DocHeader`](spine-core/src/spine/tools/changelog/model.py#L118)*

---

*224 principles extracted from 6 packages*

*Generated by document-spine*