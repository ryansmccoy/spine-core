# Market Spine API Architecture

> **A comprehensive design for building an API layer that evolves naturally from Basic → Intermediate → Advanced → Full tiers.**

---

## Executive Summary

This architecture defines how to add an HTTP API to Market Spine that:

1. **Reuses CLI logic** through a shared command layer
2. **Maintains consistency** between CLI and API behaviors
3. **Scales naturally** across all four system tiers
4. **Avoids premature abstraction** while staying future-proof

### Key Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| CLI as starting point? | **Yes, extract shared logic** | CLI has working logic; don't duplicate |
| Where does API live? | **market-spine-basic** | Tier-specific, not spine-core |
| Shared architecture? | **Command/Use-Case layer** | Same behavior, different presentation |
| Framework choice? | **FastAPI** | OpenAPI generation, async-ready |
| When to abstract? | **After Intermediate ships** | Avoid premature optimization |

---

## Design Documents

### [API_VISION.md](API_VISION.md)
What the API is for, what it intentionally does NOT do yet, and guiding principles.

- Primary mission and consumers
- Explicit non-goals for each tier
- Version strategy and contract stability

### [CLI_TO_API_BOUNDARY.md](CLI_TO_API_BOUNDARY.md)
What logic stays in CLI, what gets extracted, and what should never be shared.

- Classification of current CLI code
- Extraction candidates (tier normalization, param resolution, etc.)
- CLI-only concerns (Rich formatting, interactive prompts)

### [SHARED_COMMAND_ARCHITECTURE.md](SHARED_COMMAND_ARCHITECTURE.md)
The shared command/use-case layer that both CLI and API call.

- Command pattern definition and interface
- Complete command catalog
- Shared services (TierNormalizer, ParameterResolver, IngestResolver)
- Error handling patterns

### [API_SURFACE_BASIC.md](API_SURFACE_BASIC.md)
Proposed endpoints for Basic tier with request/response examples.

- Full endpoint specifications
- CLI command mappings
- Error response formats
- Framework choice discussion

### [PACKAGE_OWNERSHIP.md](PACKAGE_OWNERSHIP.md)
Clear ownership rules for each package in the system.

- spine-core: Framework only
- spine-domains: Domain logic only
- market-spine-*: Tier-specific implementations
- Decision tree for new code placement

### [EVOLUTION_ROADMAP.md](EVOLUTION_ROADMAP.md)
How the architecture scales from Basic to Full tier.

- Tier-by-tier changes
- What remains stable across all tiers
- Migration paths
- Risk mitigation

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ADAPTERS (I/O Layer)                                │
├───────────────────────────────┬───────────────────────────────────────────────────┤
│           CLI                 │                    API                            │
│         (Typer)               │                  (FastAPI)                        │
│                               │                                                   │
│  spine pipelines list         │  GET  /v1/pipelines                              │
│  spine pipelines describe     │  GET  /v1/pipelines/{name}                       │
│  spine run run                │  POST /v1/executions                             │
│  spine query weeks            │  GET  /v1/query/weeks                            │
│  spine doctor doctor          │  GET  /v1/health                                 │
└───────────────┬───────────────┴───────────────────────┬───────────────────────────┘
                │                                       │
                │         Same commands                 │
                ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           COMMAND LAYER                                          │
│                           market_spine/app/                                      │
│                                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │
│  │ ListPipelines   │  │ RunPipeline     │  │ QueryWeeks      │                  │
│  │   Command       │  │   Command       │  │   Command       │                  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘                  │
│           │                    │                    │                           │
│           └──────────────┬─────┴────────────────────┘                           │
│                          │                                                       │
│                          ▼                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐        │
│  │                         SERVICES                                     │        │
│  │  TierNormalizer │ ParameterResolver │ IngestResolver                │        │
│  └─────────────────────────────────────────────────────────────────────┘        │
└───────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                │
                ┌───────────────────────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         FRAMEWORK + DOMAIN LAYER                                 │
│                                                                                  │
│  ┌────────────────────────────┐   ┌────────────────────────────┐                │
│  │       spine.framework      │   │       spine.domains        │                │
│  │  ──────────────────────────│   │  ──────────────────────────│                │
│  │  • Dispatcher              │   │  • FINRA OTC pipelines     │                │
│  │  • Runner                  │   │  • Calculations            │                │
│  │  • Registry                │   │  • Normalizers             │                │
│  │  • Pipeline base           │   │  • Connectors              │                │
│  └────────────────────────────┘   └────────────────────────────┘                │
│                                                                                  │
└───────────────────────────────────────────────────────────────────────────────┬─┘
                                                                                │
                                                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              STORAGE (Tier-specific)                             │
│                                                                                  │
│  Basic:          Intermediate:        Advanced:           Full:                 │
│  SQLite          Postgres             Postgres + Auth     Multi-tenant          │
│                  + Workers            + Scheduler         + External            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Command Layer Extraction (Week 1-2)

1. Create `market_spine/app/` package structure
2. Extract tier normalization to `app/services/tier.py`
3. Extract parameter resolution to `app/services/params.py`
4. Create command classes in `app/commands/`
5. Refactor CLI to call command layer
6. Verify all CLI tests still pass

### Phase 2: Basic API (Week 3-4)

1. Add FastAPI dependency
2. Create `market_spine/api/` package
3. Implement routes calling command layer
4. Add `spine api` CLI command
5. Write API tests
6. Generate and verify OpenAPI docs

### Phase 3: Documentation & Polish (Week 5)

1. Update README with API usage
2. Add examples for common workflows
3. Ensure CLI/API consistency tests
4. Performance baseline

---

## Success Criteria

The architecture is successful when:

| Criterion | Verification |
|-----------|--------------|
| CLI and API produce identical results | Integration tests compare outputs |
| Adding a pipeline requires no API code | New pipeline appears at `/v1/pipelines` automatically |
| Upgrading tiers doesn't break clients | Client written for Basic works on Intermediate |
| OpenAPI docs match implementation | Generated from code, always accurate |
| Command layer is easily testable | Unit tests don't need HTTP or terminal |

---

## Files in This Architecture

```
docs/architecture/
├── README.md                           # This file - index and overview
├── API_VISION.md                       # Purpose and principles
├── CLI_TO_API_BOUNDARY.md              # What to extract from CLI
├── SHARED_COMMAND_ARCHITECTURE.md      # Command layer design
├── API_SURFACE_BASIC.md                # Endpoint specifications
├── PACKAGE_OWNERSHIP.md                # What belongs where
└── EVOLUTION_ROADMAP.md                # How it scales
```

---

## Next Steps

1. **Review** these documents with stakeholders
2. **Validate** the command list covers all needed operations
3. **Prototype** the command layer with one command (e.g., `ListPipelinesCommand`)
4. **Iterate** on the design based on prototype learnings
5. **Implement** following the phased roadmap
