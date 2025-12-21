# spine.core

The foundational layer providing type-safe primitives, database abstractions, and cross-cutting utilities.

## Key Modules

| Module | Purpose |
|--------|---------|
| `result` | `Result[T]`, `Ok`, `Err` — functional error handling |
| `errors` | `SpineError` hierarchy with categories and retry semantics |
| `temporal` | `WeekEnding`, `BiTemporalRecord` — financial date handling |
| `timestamps` | `generate_ulid()`, `utc_now()`, ISO-8601 helpers |
| `protocols` | `Connection` protocol for database backends |
| `dialect` | SQL generation for SQLite, PostgreSQL, MySQL, DB2, Oracle |
| `repository` | `BaseRepository` with dialect-aware CRUD |
| `quality` | `QualityRunner`, `QualityCheck` — data validation gates |
| `manifest` | `WorkManifest` for multi-stage progress tracking |
| `anomalies` | `AnomalyRecorder` for data anomaly tracking |
| `feature_flags` | `FlagRegistry`, `FlagDefinition` — runtime toggles |
| `cache` | `CacheBackend` protocol with in-memory and Redis backends |
| `secrets` | `SecretsResolver` with pluggable backends |
| `hashing` | Deterministic record hashing for deduplication |
| `idempotency` | `IdempotencyHelper` with L1/L2/L3 levels |
| `rejects` | `RejectSink` for validation failure handling |
| `rolling` | `RollingWindow` for time-series aggregations |
| `assets` | `AssetRegistry` for Dagster-inspired asset tracking |

## API Reference

See the full auto-generated API docs at [API Reference — spine.core](../api/core.md).
