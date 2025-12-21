# GUARDRAILS

**What NOT to Do — Anti-patterns and Constraints**

*Auto-generated from code annotations on 2026-02-19*

---

## Table of Contents

1. [Core Primitives](#core-primitives) (100 rules)
2. [Tooling](#tooling) (5 rules)

---

## Core Primitives

### Err

#### ❌ Call unwrap() on Err - it raises the error

✅ **Instead:** Use unwrap_or() or pattern matching to handle errors

*From [`Err`](spine-core/src/spine/core/result.py#L299)*

#### ❌ Use plain Exception - loses metadata

✅ **Instead:** Use SpineError subclasses with category/retryable

*From [`Err`](spine-core/src/spine/core/result.py#L299)*

#### ❌ Ignore Err in chains - they propagate silently

✅ **Instead:** Check is_err() or use partition_results() at the end

*From [`Err`](spine-core/src/spine/core/result.py#L299)*

### ErrorCategory

#### ❌ Create custom categories as strings

✅ **Instead:** Use predefined ErrorCategory values

*From [`ErrorCategory`](spine-core/src/spine/core/errors.py#L142)*

#### ❌ Use UNKNOWN for known error types

✅ **Instead:** Classify errors into appropriate categories

*From [`ErrorCategory`](spine-core/src/spine/core/errors.py#L142)*

### ErrorContext

#### ❌ Store large objects in metadata

✅ **Instead:** Store IDs and small values for logging

*From [`ErrorContext`](spine-core/src/spine/core/errors.py#L253)*

#### ❌ Store sensitive data

**Why:** passwords, tokens

✅ **Instead:** Redact sensitive values before adding

*From [`ErrorContext`](spine-core/src/spine/core/errors.py#L253)*

### ExecutionContext

#### ❌ Mutate execution_id or parent_execution_id

✅ **Instead:** Treat context as immutable, use child()/with_batch()

*From [`ExecutionContext`](spine-core/src/spine/core/execution.py#L121)*

#### ❌ Share context across concurrent operations

✅ **Instead:** Each concurrent task gets its own child context

*From [`ExecutionContext`](spine-core/src/spine/core/execution.py#L121)*

#### ❌ Generate execution_id manually

✅ **Instead:** Let the default factory generate UUIDs

*From [`ExecutionContext`](spine-core/src/spine/core/execution.py#L121)*

#### ❌ Use flat string keys

**Why:** "sec_filings_10k"

✅ **Instead:** Use hierarchical keys: AssetKey("sec", "filings", "10-K")

*From [`assets.py`](spine-core/src/spine/core/assets.py#L1)*

#### ❌ Record materializations before successful writes

✅ **Instead:** Record materializations AFTER data is committed

*From [`assets.py`](spine-core/src/spine/core/assets.py#L1)*

#### ❌ Skip execution_id — it breaks lineage tracking

✅ **Instead:** Always include execution_id from ExecutionContext

*From [`assets.py`](spine-core/src/spine/core/assets.py#L1)*

#### ❌ Run backfills without a BackfillPlan

**Why:** no audit trail

✅ **Instead:** Always create a plan with reason for compliance tracking

*From [`backfill.py`](spine-core/src/spine/core/backfill.py#L1)*

#### ❌ Restart from scratch after a crash

✅ **Instead:** Use checkpoint-based resume via completed_keys

*From [`backfill.py`](spine-core/src/spine/core/backfill.py#L1)*

#### ❌ Backfill without checking watermarks first

✅ **Instead:** Use WatermarkStore.list_gaps() to drive backfill decisions

*From [`backfill.py`](spine-core/src/spine/core/backfill.py#L1)*

#### ❌ Use InMemoryCache in multi-process deployments

**Why:** no sharing

✅ **Instead:** Use RedisCache for distributed caching in Tier 2+

*From [`cache.py`](spine-core/src/spine/core/cache.py#L1)*

#### ❌ Cache without TTL

**Why:** unbounded growth

✅ **Instead:** Always set default_ttl_seconds or per-key ttl_seconds

*From [`cache.py`](spine-core/src/spine/core/cache.py#L1)*

#### ❌ Import sqlite3 or psycopg2 directly in domain code

✅ **Instead:** Use create_connection() for all database access

*From [`connection.py`](spine-core/src/spine/core/connection.py#L1)*

#### ❌ Hardcode backend-specific SQL in domain code

✅ **Instead:** Use dialect abstraction from spine.core.dialect

*From [`connection.py`](spine-core/src/spine/core/connection.py#L1)*

#### ❌ Write backend-specific SQL in domain repositories

✅ **Instead:** Use Dialect methods for placeholders, timestamps, upserts

*From [`dialect.py`](spine-core/src/spine/core/dialect.py#L1)*

#### ❌ Import sqlite3 or psycopg2 in domain code

✅ **Instead:** Use Dialect + Connection protocol for all SQL access

*From [`dialect.py`](spine-core/src/spine/core/dialect.py#L1)*

#### ❌ Use generic Exception - loses all metadata

✅ **Instead:** Use appropriate SpineError subclass

*From [`errors.py`](spine-core/src/spine/core/errors.py#L1)*

#### ❌ Set retryable=True for validation/config errors

✅ **Instead:** Let the error type's default_retryable handle it

*From [`errors.py`](spine-core/src/spine/core/errors.py#L1)*

#### ❌ Swallow the original exception

✅ **Instead:** Pass it as cause= for error chaining

*From [`errors.py`](spine-core/src/spine/core/errors.py#L1)*

#### ❌ Mutate execution context

**Why:** it's a dataclass, not frozen

✅ **Instead:** Use child() or with_batch() to create new contexts

*From [`execution.py`](spine-core/src/spine/core/execution.py#L1)*

#### ❌ Create execution_id manually

✅ **Instead:** Use new_context() for root, child() for sub-operations

*From [`execution.py`](spine-core/src/spine/core/execution.py#L1)*

#### ❌ Pass context by reference and modify it

✅ **Instead:** Each function should receive its own context

*From [`execution.py`](spine-core/src/spine/core/execution.py#L1)*

#### ❌ Store complex state in feature flags

✅ **Instead:** Use config/settings for structured configuration

*From [`feature_flags.py`](spine-core/src/spine/core/feature_flags.py#L1)*

#### ❌ Use feature flags for user-facing A/B testing

✅ **Instead:** Use a proper A/B system for personalization

*From [`feature_flags.py`](spine-core/src/spine/core/feature_flags.py#L1)*

#### ❌ Use non-snake_case flag names

**Why:** validated on registration

✅ **Instead:** Use descriptive snake_case: ``enable_async_ingestion``

*From [`feature_flags.py`](spine-core/src/spine/core/feature_flags.py#L1)*

#### ❌ Use for security-sensitive hashing

**Why:** passwords, tokens

✅ **Instead:** Use for deduplication and content change detection only

*From [`hashing.py`](spine-core/src/spine/core/hashing.py#L1)*

#### ❌ Include mutable fields (timestamps, random IDs) in hash inputs

✅ **Instead:** Hash only stable business keys and content fields

*From [`hashing.py`](spine-core/src/spine/core/hashing.py#L1)*

#### ❌ Change the delimiter or algorithm without a migration plan

✅ **Instead:** Treat the '|' delimiter and SHA-256 as part of the contract

*From [`hashing.py`](spine-core/src/spine/core/hashing.py#L1)*

#### ❌ Create custom health endpoints per service

✅ **Instead:** Use create_health_router() for consistency

*From [`health.py`](spine-core/src/spine/core/health.py#L1)*

#### ❌ Mark optional dependencies as required

**Why:** breaks readiness

✅ **Instead:** Set required=False for non-critical dependencies (Redis cache)

*From [`health.py`](spine-core/src/spine/core/health.py#L1)*

#### ❌ Duplicate Connection(Protocol) in other modules

✅ **Instead:** Import from spine.core.protocols (single source of truth)

*From [`protocols.py`](spine-core/src/spine/core/protocols.py#L1)*

#### ❌ Add async methods to the Connection protocol

✅ **Instead:** Use AsyncConnection for async needs; domain code stays sync

*From [`protocols.py`](spine-core/src/spine/core/protocols.py#L1)*

#### ❌ Add implementation logic to protocol classes

✅ **Instead:** Keep protocols pure contracts — implementations go in adapters

*From [`protocols.py`](spine-core/src/spine/core/protocols.py#L1)*

#### ❌ Use quality checks for data transformation

**Why:** they only observe

✅ **Instead:** Keep checks pure — read data and return QualityResult

*From [`quality.py`](spine-core/src/spine/core/quality.py#L1)*

#### ❌ Make all checks blocking by default

✅ **Instead:** Use has_failures() for explicit quality gates at operation boundaries

*From [`quality.py`](spine-core/src/spine/core/quality.py#L1)*

#### ❌ Delete quality results

**Why:** they form a compliance audit trail

✅ **Instead:** Use retention policies for cleanup of old results

*From [`quality.py`](spine-core/src/spine/core/quality.py#L1)*

#### ❌ Write raw SQL in ops modules

✅ **Instead:** Use the appropriate repository class

*From [`repositories.py`](spine-core/src/spine/core/repositories.py#L1)*

#### ❌ Return raw cursor results from repositories

✅ **Instead:** Return typed dicts or (list[dict], int) tuples

*From [`repositories.py`](spine-core/src/spine/core/repositories.py#L1)*

#### ❌ Use conn.execute() directly in domain code

✅ **Instead:** Subclass BaseRepository and use self.execute() / self.query()

*From [`repository.py`](spine-core/src/spine/core/repository.py#L1)*

#### ❌ Hardcode SQL placeholders

**Why:** ?, %s

✅ **Instead:** Use self.ph(n) for dialect-portable placeholders

*From [`repository.py`](spine-core/src/spine/core/repository.py#L1)*

#### ❌ Use unwrap() without checking is_ok() first

✅ **Instead:** Use unwrap_or() or pattern matching for safe extraction

*From [`result.py`](spine-core/src/spine/core/result.py#L1)*

#### ❌ Raise exceptions inside map/flat_map functions

✅ **Instead:** Return Err from flat_map if the operation can fail

*From [`result.py`](spine-core/src/spine/core/result.py#L1)*

#### ❌ Store mutable values in Ok

**Why:** frozen dataclass

✅ **Instead:** Use immutable types or create copies

*From [`result.py`](spine-core/src/spine/core/result.py#L1)*

#### ❌ Set retention below compliance minimums

**Why:** e.g., 30 days for rejects

✅ **Instead:** Use RetentionConfig with documented defaults

*From [`retention.py`](spine-core/src/spine/core/retention.py#L1)*

#### ❌ Run purge without checking get_table_counts() first

✅ **Instead:** Monitor before/after counts for validation

*From [`retention.py`](spine-core/src/spine/core/retention.py#L1)*

#### ❌ Purge anomalies too aggressively

**Why:** they're audit evidence

✅ **Instead:** Keep anomalies for at least 180 days (default)

*From [`retention.py`](spine-core/src/spine/core/retention.py#L1)*

#### ❌ Create domain-specific infrastructure tables

**Why:** manifest, rejects, etc.

✅ **Instead:** Use shared core tables with domain column as partition key

*From [`schema.py`](spine-core/src/spine/core/schema.py#L1)*

#### ❌ Modify DDL without a migration

**Why:** see spine.core.migrations

✅ **Instead:** Use the migrations framework for schema changes

*From [`schema.py`](spine-core/src/spine/core/schema.py#L1)*

#### ❌ Query across domains without explicit WHERE domain = X

✅ **Instead:** Always filter by domain to prevent cross-contamination

*From [`schema.py`](spine-core/src/spine/core/schema.py#L1)*

#### ❌ Log secrets

**Why:** use SecretValue wrapper for repr safety

✅ **Instead:** Use masked repr: ``SecretValue('***')``

*From [`secrets.py`](spine-core/src/spine/core/secrets.py#L1)*

#### ❌ Hardcode secrets in source code

✅ **Instead:** Use environment variables or file-based secrets

*From [`secrets.py`](spine-core/src/spine/core/secrets.py#L1)*

#### ❌ Skip fallback for development environments

✅ **Instead:** Provide sensible defaults or .env file support

*From [`secrets.py`](spine-core/src/spine/core/secrets.py#L1)*

#### ❌ Use a single ``created_at`` for all temporal needs

✅ **Instead:** Separate event_time, publish_time, ingest_time, effective_time

*From [`temporal_envelope.py`](spine-core/src/spine/core/temporal_envelope.py#L1)*

#### ❌ Set ingest_time to the original capture time during backfill

✅ **Instead:** Set ingest_time to NOW during re-ingest (reflects actual capture)

*From [`temporal_envelope.py`](spine-core/src/spine/core/temporal_envelope.py#L1)*

#### ❌ Skip effective_time — it defaults to event_time if omitted

✅ **Instead:** Set effective_time explicitly for corrections and adjustments

*From [`temporal_envelope.py`](spine-core/src/spine/core/temporal_envelope.py#L1)*

#### ❌ Move watermark backward

**Why:** causes duplicate processing

✅ **Instead:** Use advance() which enforces forward-only semantics

*From [`watermarks.py`](spine-core/src/spine/core/watermarks.py#L1)*

#### ❌ Skip gap detection after backfills

✅ **Instead:** Run list_gaps() periodically for completeness audits

*From [`watermarks.py`](spine-core/src/spine/core/watermarks.py#L1)*

#### ❌ Store mutable state in watermark metadata

✅ **Instead:** Use metadata for context only (source URL, batch_id)

*From [`watermarks.py`](spine-core/src/spine/core/watermarks.py#L1)*

#### ❌ ``conn.execute("SELECT * FROM t WHERE id=" + user_input)``

✅ **Instead:** ``conn.execute("SELECT * FROM t WHERE id=?", [user_input])``

*From [`__init__.py`](spine-core/src/spine/core/adapters/__init__.py#L1)*

#### ❌ Importing optional drivers at module scope

✅ **Instead:** Import-guarded at ``connect()`` time with clear ``ConfigError``

*From [`__init__.py`](spine-core/src/spine/core/adapters/__init__.py#L1)*

#### ❌ ``adapter = PostgreSQLAdapter(...)`` directly

✅ **Instead:** ``adapter = get_adapter(DatabaseType.POSTGRESQL, config)``

*From [`__init__.py`](spine-core/src/spine/core/adapters/__init__.py#L1)*

#### ❌ Parsing env vars ad-hoc in each module

✅ **Instead:** ``get_settings().database_url`` from the cached singleton

*From [`__init__.py`](spine-core/src/spine/core/config/__init__.py#L1)*

#### ❌ Constructing engines/schedulers with raw ``create_engine()``

✅ **Instead:** ``create_database_engine(settings)`` via the factory layer

*From [`__init__.py`](spine-core/src/spine/core/config/__init__.py#L1)*

#### ❌ Hard-coding backend choices in application code

✅ **Instead:** ``settings.infer_tier()`` with automatic backend selection

*From [`__init__.py`](spine-core/src/spine/core/config/__init__.py#L1)*

#### ❌ Importing modules directly to send notifications

✅ **Instead:** ``await bus.publish(Event(event_type="run.completed", ...))``

*From [`__init__.py`](spine-core/src/spine/core/events/__init__.py#L1)*

#### ❌ Passing raw dicts as event payloads without type info

✅ **Instead:** Using typed ``Event`` dataclass with ``event_type`` taxonomy

*From [`__init__.py`](spine-core/src/spine/core/events/__init__.py#L1)*

#### ❌ Creating event bus instances per-module

✅ **Instead:** ``get_event_bus()`` singleton with ``set_event_bus()`` override

*From [`__init__.py`](spine-core/src/spine/core/events/__init__.py#L1)*

#### ❌ Running schedule callbacks without acquiring a distributed lock

✅ **Instead:** ``LockManager.acquire_schedule_lock()`` before dispatch

*From [`__init__.py`](spine-core/src/spine/core/scheduling/__init__.py#L1)*

#### ❌ Silently skipping misfired schedules

✅ **Instead:** ``misfire_grace_seconds`` with explicit skip/fire decision

*From [`__init__.py`](spine-core/src/spine/core/scheduling/__init__.py#L1)*

#### ❌ Constructing scheduler components individually

✅ **Instead:** ``create_scheduler(conn, dispatcher)`` factory function

*From [`__init__.py`](spine-core/src/spine/core/scheduling/__init__.py#L1)*

### IdempotencyHelper

#### ❌ Delete without transaction

**Why:** partial state on failure

✅ **Instead:** Wrap delete+insert in transaction

*From [`IdempotencyHelper`](spine-core/src/spine/core/idempotency.py#L156)*

#### ❌ Use partial key for delete

**Why:** deletes too much

✅ **Instead:** Use complete logical key for delete

*From [`IdempotencyHelper`](spine-core/src/spine/core/idempotency.py#L156)*

### IdempotencyLevel

#### ❌ Use L1 for derived tables

**Why:** duplicates on re-run

✅ **Instead:** Use L3 for any table with natural/logical keys

*From [`IdempotencyLevel`](spine-core/src/spine/core/idempotency.py#L78)*

#### ❌ Assume L2 prevents all duplicates

**Why:** hash collisions

✅ **Instead:** Use cryptographic hashes (SHA-256) for L2

*From [`IdempotencyLevel`](spine-core/src/spine/core/idempotency.py#L78)*

### LogicalKey

#### ❌ Use surrogate keys for business operations

✅ **Instead:** Use LogicalKey with natural domain keys

*From [`LogicalKey`](spine-core/src/spine/core/idempotency.py#L286)*

#### ❌ Build WHERE clauses manually

✅ **Instead:** Use LogicalKey.where_clause() for consistency

*From [`LogicalKey`](spine-core/src/spine/core/idempotency.py#L286)*

### Ok

#### ❌ Mutate the value inside Ok

**Why:** it's frozen

✅ **Instead:** Use map() to create a new Ok with transformed value

*From [`Ok`](spine-core/src/spine/core/result.py#L140)*

#### ❌ Assume map() modifies in place

✅ **Instead:** Chain or assign the result: result = ok.map(f)

*From [`Ok`](spine-core/src/spine/core/result.py#L140)*

### QualityRunner

#### ❌ Ignore has_failures() for critical operations

✅ **Instead:** Check has_failures() and decide how to handle

*From [`QualityRunner`](spine-core/src/spine/core/quality.py#L281)*

#### ❌ Run heavy computations in check_fn

✅ **Instead:** Pre-compute values, pass via context

*From [`QualityRunner`](spine-core/src/spine/core/quality.py#L281)*

### RollingResult

#### ❌ Ignore is_complete for financial reporting

✅ **Instead:** Check is_complete or periods_present before using aggregates

*From [`RollingResult`](spine-core/src/spine/core/rolling.py#L89)*

#### ❌ Assume aggregates exist if periods_present=0

✅ **Instead:** Check if aggregates is non-empty before accessing

*From [`RollingResult`](spine-core/src/spine/core/rolling.py#L89)*

### RollingWindow

#### ❌ Do heavy computation in step_back

✅ **Instead:** Keep step_back simple (e.g., week.previous())

*From [`RollingWindow`](spine-core/src/spine/core/rolling.py#L178)*

#### ❌ Throw exceptions in fetch_fn for missing data

✅ **Instead:** Return None for missing periods

*From [`RollingWindow`](spine-core/src/spine/core/rolling.py#L178)*

#### ❌ Assume aggregates exist if window is empty

✅ **Instead:** Check periods_present > 0 before accessing aggregates

*From [`RollingWindow`](spine-core/src/spine/core/rolling.py#L178)*

### SpineError

#### ❌ Use plain Exception for expected error cases

✅ **Instead:** Use appropriate SpineError subclass

*From [`SpineError`](spine-core/src/spine/core/errors.py#L387)*

#### ❌ Override retryable to True for validation/config errors

✅ **Instead:** Use TransientError subclass for retryable errors

*From [`SpineError`](spine-core/src/spine/core/errors.py#L387)*

#### ❌ Forget to chain the original exception

✅ **Instead:** Always pass cause= when wrapping exceptions

*From [`SpineError`](spine-core/src/spine/core/errors.py#L387)*

### TransientError

#### ❌ Use for permanent failures

**Why:** file not found, invalid data

✅ **Instead:** Use SourceError or ValidationError for non-transient issues

*From [`TransientError`](spine-core/src/spine/core/errors.py#L598)*

#### ❌ Retry forever - limit retry attempts

✅ **Instead:** Use exponential backoff with max attempts

*From [`TransientError`](spine-core/src/spine/core/errors.py#L598)*

#### ❌ Ignore retry_after from APIs

**Why:** 429 responses

✅ **Instead:** Honor retry_after when the upstream specifies it

*From [`TransientError`](spine-core/src/spine/core/errors.py#L598)*

### WeekEnding

#### ❌ Pass arbitrary dates without validation

✅ **Instead:** Use from_any_date() for arbitrary dates

*From [`WeekEnding`](spine-core/src/spine/core/temporal.py#L72)*

#### ❌ Store week_ending as plain strings

✅ **Instead:** Use WeekEnding type for validation guarantees

*From [`WeekEnding`](spine-core/src/spine/core/temporal.py#L72)*

#### ❌ Manually compute previous/next week

✅ **Instead:** Use previous()/next() methods

*From [`WeekEnding`](spine-core/src/spine/core/temporal.py#L72)*

## Tooling

### ChangelogGenerator

#### ❌ Do NOT import modules to read docstrings

✅ **Instead:** Use AST-only extraction

*From [`ChangelogGenerator`](spine-core/src/spine/tools/changelog/generator.py#L59)*

#### ❌ Do NOT require git for testing

✅ **Instead:** Fixture mode with commits.json

*From [`ChangelogGenerator`](spine-core/src/spine/tools/changelog/generator.py#L59)*

#### ❌ Do NOT add runtime dependencies

✅ **Instead:** stdlib-only (ast, subprocess, json, tomllib)

*From [`ChangelogGenerator`](spine-core/src/spine/tools/changelog/generator.py#L59)*

### DocHeader

#### ❌ Do NOT import modules to read their docstrings

✅ **Instead:** Use ast.parse() only

*From [`DocHeader`](spine-core/src/spine/tools/changelog/model.py#L118)*

#### ❌ Do NOT allow invalid enum values silently

✅ **Instead:** Emit ValidationWarning for unknown values

*From [`DocHeader`](spine-core/src/spine/tools/changelog/model.py#L118)*

---

*105 guardrails across 2 packages*