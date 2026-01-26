# Feature History - Spine Core

<!-- Auto-generated from commits. Run `make todos` or edit manually for major features. -->

> Track new features as they're added. Newest first.

---

## 2026-01-20 - Multi-Tier Docker Deployment

- Basic tier (SQLite) for fastest startup
- Intermediate tier (PostgreSQL) for production-like
- Full tier (TimescaleDB + Redis) for complete stack
- PowerShell scripts for easy management

## 2026-01-15 - Registry Architecture

- Pipeline registry for automatic source discovery
- Schema registry for data validation
- Domain isolation pattern

## 2026-01-10 - Core Primitives

- `ExecutionContext` for pipeline execution
- `Result[T]` pattern for error handling
- Capture semantics (append-only with revision tracking)

---

*This file documents major feature additions. For detailed changes, see [CHANGELOG.md](CHANGELOG.md).*
