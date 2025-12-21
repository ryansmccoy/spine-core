# Changelog

All notable changes to spine-core will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-02-10

### Added

#### Data Layer
- **MigrationRunner** - SQL schema migration tracking and application
  - `apply_pending()` applies numbered SQL files in order
  - Tracks applied migrations in `_migrations` table
  - Idempotent - safe to run multiple times
  - `rollback_last()` removes tracking record
- **Data Retention** - Configurable purge utilities for old records
  - `purge_all(conn, config)` for unified cleanup
  - Per-table functions: `purge_executions`, `purge_rejects`, `purge_anomalies`
  - `RetentionConfig` dataclass for configurable periods
  - `get_table_counts()` for monitoring
- **Schema Loader** - Utilities for applying SQL schemas
  - `apply_all_schemas(conn)` for quick database setup
  - `create_test_db()` for unit test fixtures
  - `get_table_schema()` for introspection

#### Orchestration
- **Typed YAML Validation** - Pydantic models for operation group definitions
  - `GroupSpec`, `StepSpec`, `PolicySpec`, `MetadataSpec` models
  - Validates dependencies, detects duplicates, enforces API version
  - `from_yaml()` for direct YAML parsing
  - `validate_yaml_group()` convenience function

### Changed
- Error hierarchy unified - `framework.exceptions` now re-exports from `core.errors`
- `orchestration.exceptions.GroupError` now inherits from `core.errors.OrchestrationError`
- Fixed structlog `PrintLoggerFactory` issue - now uses `stdlib.LoggerFactory`

### Fixed
- 28 pre-existing test failures resolved (dispatcher + integration tests)
- `OperationStatus.SUCCESS` → `OperationStatus.COMPLETED` enum fix

### Testing
- Test count: 1345 (up from 1102)
- Coverage: 84.97% (up from ~78%)
- 63 runnable examples (4 new for Phase 3 features)

## [0.1.0] - 2026-02-08

### Added

#### Core Primitives
- Result[T] monad with Ok/Err for explicit error handling
- Rich functional combinators: `map`, `flat_map`, `or_else`, `unwrap_or`
- Batch collection utilities: `collect_results`, `partition_results`
- SpineError hierarchy with ErrorCategory for structured errors
- Error context chaining with retryable semantics and retry_after hints
- ExecutionContext for lineage tracking through operation execution
- WeekEnding for Friday date validation in financial workflows
- WorkManifest for multi-stage workflow progress tracking
- QualityRunner framework for data validation gates
- Timestamp utilities: `generate_ulid`, `utc_now`, `to_iso8601`, `from_iso8601`

#### Execution Framework
- Dispatcher as unified submission API for all work types
- Executor protocol with MemoryExecutor and LocalExecutor implementations
- WorkSpec universal work specification supporting tasks, operations, workflows
- RetryStrategy with ExponentialBackoff, LinearBackoff, ConstantBackoff
- CircuitBreaker for failure protection with automatic half-open recovery
- RateLimiter with TokenBucket and SlidingWindow algorithms
- Batch processing utilities with configurable batch sizes
- Concurrency control with ConcurrencyGuard
- Event emission for observability (RunEvent)
- Run tracking with RunRecord and RunStatus

#### Orchestration
- Workflow v2 with context-aware steps and inter-step data passing
- Step types: Lambda steps (inline functions), Operation steps, Choice steps (conditional branching)
- WorkflowContext for accessing step outputs and passing data
- WorkflowRunner for stateless workflow execution
- TrackedWorkflowRunner for database-persisted workflow state with idempotency
- OperationGroups v1 for static DAG execution (legacy pattern)
- Workflow YAML loading support
- Quality gate integration in workflows

#### Observability
- Structured JSON logging with context binding
- LogContext for hierarchical log context propagation
- Metrics primitives (Counter, Gauge, Histogram) with Prometheus compatibility
- StructLog integration (optional dependency)
- Event-based observability hooks

#### Framework Infrastructure
- Operation base class for reusable data transformations
- OperationResult with status, timing, error tracking, and metrics
- OperationRegistry for operation discovery and invocation
- Database connection protocol for sync operations
- Schema management for core tables (manifest, quality, anomalies, rejects)

#### Error Handling
- Comprehensive error hierarchy: TransientError, SourceError, ValidationError, ConfigError, AuthError, OperationError, OrchestrationError
- Error categorization: NETWORK, DATABASE, STORAGE, SOURCE, PARSE, VALIDATION, CONFIG, AUTH, operation, ORCHESTRATION, INTERNAL, UNKNOWN
- Structured ErrorContext with operation, source, URL, and custom fields
- Utility: `is_retryable(error)` for retry decision logic

#### Type Safety & Developer Experience
- Full type hints across all modules
- `py.typed` marker for downstream type checking
- Protocol-based abstractions for extensibility
- Comprehensive docstrings with architecture diagrams and examples

### Documentation
- Comprehensive README with installation, quickstart, and feature overview
- CONTRIBUTING.md with development setup and testing guide
- 45 runnable examples demonstrating all features in `examples/` directory
- Extensive docstrings with Manifesto, Architecture, Examples, Performance, Guardrails sections
- License: MIT

### Testing
- 1102 passing tests with unit, integration, and example coverage
- pytest configuration with markers: unit, integration, slow, golden, asyncio
- Test fixtures and support utilities in `tests/_support/`
- Coverage tracking with branch coverage enabled

### Infrastructure
- Modern build system using hatchling
- uv-based dependency management with workspace support
- Optional dependency groups: `[settings]`, `[mcp]`, `[all]`
- GitHub Actions CI/CD configuration
- Makefile with common development commands
- MkDocs documentation setup

## [0.0.1] - 2025-12-01

### Added
- Initial project structure
- Basic execution primitives (early prototypes)

---

[Unreleased]: https://github.com/mccoy-lab/py-sec-edgar/compare/spine-core-v0.1.0...HEAD
[0.1.0]: https://github.com/mccoy-lab/py-sec-edgar/releases/tag/spine-core-v0.1.0
[0.0.1]: https://github.com/mccoy-lab/py-sec-edgar/releases/tag/spine-core-v0.0.1
