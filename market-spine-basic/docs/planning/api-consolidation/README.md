# API & Command Layer Consolidation

> Planning documents for Basic Tier API stabilization

## Document Index

| File | Purpose | Status |
|------|---------|--------|
| [00-current-state.md](00-current-state.md) | What exists and is accepted | ✅ Reference |
| [01-architectural-lock-ins.md](01-architectural-lock-ins.md) | Non-negotiable constraints | 🔒 Locked |
| [02-phase1-cli-refactor.md](02-phase1-cli-refactor.md) | CLI → Command refactor plan | 🔴 Not Started |
| [03-phase2-api-hardening.md](03-phase2-api-hardening.md) | API error/contract cleanup | 🔴 Not Started |
| [04-phase3-capabilities.md](04-phase3-capabilities.md) | Capability endpoint finalization | 🔴 Not Started |
| [05-phase4-testing.md](05-phase4-testing.md) | Test coverage gaps | 🔴 Not Started |
| [06-phase5-deferred.md](06-phase5-deferred.md) | Out of scope items | 🔒 Frozen |
| [07-fastapi-assessment.md](07-fastapi-assessment.md) | FastAPI/Pydantic evaluation | ✅ Approved |
| [08-risks-mitigations.md](08-risks-mitigations.md) | Risk analysis | ⚠️ Active Risks |
| [09-next-actions.md](09-next-actions.md) | Master TODO list | 📋 Tracking |

## Quick Start

1. **Review current state** → [00-current-state.md](00-current-state.md)
2. **Understand constraints** → [01-architectural-lock-ins.md](01-architectural-lock-ins.md)
3. **Start implementation** → [02-phase1-cli-refactor.md](02-phase1-cli-refactor.md)
4. **Track progress** → [09-next-actions.md](09-next-actions.md)

## Phase Order

```
Phase 1: CLI → Command Refactor  [HIGH PRIORITY]
    │
    ▼
Phase 2: API Surface Hardening   [MEDIUM]
    │
    ▼
Phase 3: Capabilities & Versioning [LOW]
    │
    ▼
Phase 4: Testing Gaps            [MEDIUM]
```

## Key Decisions Locked

1. ✅ FastAPI + Pydantic acceptable for API layer
2. ✅ Dataclasses for commands/services (no Pydantic)
3. ✅ No DI containers or command buses
4. ✅ Sync execution only in Basic tier
5. ✅ CLI remains primary UX
6. ✅ Reserved fields for async evolution

## Active Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| CLI Drift vs API | High | Phase 1 |
| Testing Blind Spots | Medium | Phase 4 |
| Error Inconsistency | Medium | Phase 2 |

See [08-risks-mitigations.md](08-risks-mitigations.md) for details.
