# Intermediate Plan

High-level plan for Market Spine Intermediate tier. This is a planning document, not implementation.

## What Basic Provides (Foundation)

- SQLite single-file database
- Synchronous CLI execution
- Structured logging with span tracing
- WorkManifest for stage tracking
- Idempotent pipelines
- Three-clock model (week_ending, source_update, captured_at)
- 75 passing tests

## What Intermediate Adds

### 1. Persistent Execution Events Table

**Problem**: Basic logs to console/file. No queryable history of executions.

**Solution**: 
- Add `core_execution_events` table
- Write execution lifecycle events (submitted, started, completed, failed)
- Enable SQL queries: "Show me all failed executions this week"

**Scope**: 
- Migration for events table
- Event writer in dispatcher
- CLI command: `spine executions list --status=failed --since=7d`

### 2. Multi-Backend Orchestration (Celery)

**Problem**: Basic runs synchronously. Long pipelines block.

**Solution**:
- Add Celery backend alongside sync
- `Lane.BACKGROUND` routes to Celery
- Retries with exponential backoff
- Progress tracking via events table

**Scope**:
- `backends/celery.py` module
- Dispatcher backend routing
- Redis/RabbitMQ for task queue
- `spine run --async` flag

### 3. Point-in-Time Query Helpers

**Problem**: Basic has capture_id but no ergonomic way to query "latest" or "as of".

**Solution**:
- SQL views: `otc_symbol_summary_latest`
- Helper functions: `get_latest_capture(week, tier)`
- CLI: `spine query otc.summary --week=2025-12-19 --as-of=latest`

**Scope**:
- Migration for views
- Query helper functions
- CLI query subcommand

### 4. Stronger Idempotency / Dedupe Semantics

**Problem**: Basic uses simple hash-based dedup within a capture. Cross-capture dedup is manual.

**Solution**:
- Explicit "replace capture" mode
- Garbage collection for old captures
- Capture comparison reports

**Scope**:
- `--replace-capture` flag
- `spine captures gc --keep=3`
- `spine captures diff <id1> <id2>`

## What Stays the Same (Invariants Carried Forward)

| Invariant | Preserved |
|-----------|-----------|
| All execution through Dispatcher | ✅ |
| Domains never import market_spine | ✅ |
| Business logic in calculations.py | ✅ |
| Pipelines are idempotent | ✅ |
| Every row has lineage | ✅ |
| Stable logging schema | ✅ |
| UTC timestamps | ✅ |
| Week-ending derived in pipeline | ✅ |

## Migration Strategy: Basic → Intermediate

### Database Migration

1. Intermediate runs same migrations as Basic (001, 020, 025)
2. Add new migrations (030_execution_events.sql, etc.)
3. No breaking schema changes to existing tables
4. Views are additive (don't break raw table queries)

### Code Migration

1. `spine.core` remains unchanged (shared library)
2. `spine.domains.otc` remains unchanged (shared domain)
3. `market_spine` becomes `market_spine_intermediate`
4. Add new modules: `backends/`, `query/`

### Configuration

1. Keep same env vars (SPINE_DATABASE_PATH, etc.)
2. Add new vars: SPINE_CELERY_BROKER, SPINE_REDIS_URL
3. Feature flags for optional backends

## Proposed Milestones

### Milestone 1: Execution Events (1-2 days)

**PR 1**: Add core_execution_events table
- Migration 030_execution_events.sql
- EventWriter class
- Dispatcher integration

**PR 2**: CLI for execution history
- `spine executions list`
- `spine executions show <id>`
- JSON and table output formats

### Milestone 2: Celery Backend (2-3 days)

**PR 3**: Celery backend skeleton
- `backends/celery.py`
- Task definition
- Backend protocol

**PR 4**: Dispatcher backend routing
- Lane → Backend mapping
- Async submission
- Status polling

**PR 5**: Retry and error handling
- Exponential backoff
- Dead letter queue
- Alerting hooks

### Milestone 3: PIT Helpers (1-2 days)

**PR 6**: Latest views
- Migration 031_latest_views.sql
- `*_latest` views for each table

**PR 7**: Query helpers and CLI
- `spine query` subcommand
- `--as-of` flag
- Output formatting

### Milestone 4: Capture Management (1-2 days)

**PR 8**: Capture comparison
- `spine captures list`
- `spine captures diff`

**PR 9**: Capture garbage collection
- `spine captures gc --keep=N`
- Dry-run mode

## What NOT to Do in Intermediate

- ❌ Rewrite core primitives
- ❌ Change domain structure
- ❌ Add web UI (that's Full tier)
- ❌ Multi-database support (that's Advanced)
- ❌ Real-time streaming (that's Advanced)
- ❌ Multi-tenant isolation (that's Full)

## Success Criteria for Intermediate

1. All Basic tests still pass
2. Can run pipelines async via Celery
3. Can query execution history via SQL
4. Can query "latest" data easily
5. Capture lifecycle is manageable
6. Documentation updated for new features
7. <5 minute setup for local Celery dev

## Dependencies

| Feature | External Dependency |
|---------|---------------------|
| Celery backend | Redis or RabbitMQ |
| Async tasks | celery[redis] package |
| Progress tracking | Redis for state |

## Estimated Timeline

| Milestone | Effort | Dependencies |
|-----------|--------|--------------|
| Execution Events | 1-2 days | None |
| Celery Backend | 2-3 days | Redis/RabbitMQ |
| PIT Helpers | 1-2 days | Events table |
| Capture Management | 1-2 days | Events table |

**Total**: 5-9 days of focused work

## Open Questions

1. **Redis vs RabbitMQ**: Which broker for Celery?
   - Recommendation: Redis (simpler, also useful for caching)

2. **Execution events retention**: How long to keep?
   - Recommendation: 90 days default, configurable

3. **Async result storage**: Where to store task results?
   - Recommendation: SQLite (same as data), not Redis

4. **Progress tracking granularity**: Row-level or step-level?
   - Recommendation: Step-level (matches log_step)
