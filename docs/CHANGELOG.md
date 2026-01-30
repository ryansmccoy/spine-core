# Changelog - Spine Core

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **GitHub Actions CI** - Automated testing with uv
- **Standardized Makefile** - `make install`, `make test`, `make lint`
- **Project Metadata** - `project_meta.yaml` for ecosystem tooling

### Changed
- **Domain Types Moved to entityspine** (v2.3.3)
  - `ExecutionContext`, `Result[T]`, `Ok`, `Err` → `entityspine.domain.workflow`
  - `ErrorCategory`, `ErrorContext`, `ErrorRecord` → `entityspine.domain.errors`
  - `QualityStatus`, `QualityResult` → `entityspine.domain.workflow`
  - spine-core now imports these from entityspine and adds infrastructure
  - Why: Domain types (enums, dataclasses) belong in entityspine; infrastructure stays here

### Ecosystem Impact

This separation means:
| Layer | Responsibility | Package |
|-------|---------------|---------|
| Domain types | Enums, dataclasses, validation | entityspine |
| Infrastructure | DB adapters, retry logic, SQL | spine-core |
| Orchestration | WorkManifest, QualityRunner | spine-core |

---

## [0.1.0] - 2026-01-20

### Added
- Multi-tier Docker deployment (basic/intermediate/full)
- Registry-driven pipeline architecture
- Core primitives (`ExecutionContext`, `Result[T]`)
- Domain isolation pattern
- Capture semantics (append-only with revision tracking)
- Quality gates for validation
- PowerShell management scripts

### Infrastructure
- Docker Compose configurations for all tiers
- Port assignments (Frontend: 3100, API: 8100)

### Why spine-core?

spine-core provides:
1. **Pipeline Infrastructure** - WorkManifest, stage tracking, checkpointing
2. **Quality Gates** - QualityRunner validates data at each stage
3. **Idempotency** - Skip/force checks, delete+insert patterns
4. **Temporal Utilities** - WeekEnding, rolling windows for financial data

---

*For feature highlights, see [FEATURES.md](FEATURES.md).*
