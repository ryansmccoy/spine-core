# Architectural Lock-Ins

> Status: 🔒 Locked | Non-Negotiable Constraints

## Confirmed Constraints

| Constraint | Status | Notes |
|------------|--------|-------|
| ❌ No tier logic in `spine-core` | ✅ Compliant | Tier constants in `spine.domains`, services in `market_spine.app` |
| ❌ No generic `Command[I, O]` ABC | ✅ Compliant | Each command is a concrete class with `execute(Request) → Result` |
| ❌ No DI container | ✅ Compliant | Services instantiated inline or via constructor injection |
| ❌ No command registry / bus | ✅ Compliant | Commands instantiated directly where needed |
| ❌ No middleware abstraction | ✅ Compliant | No custom middleware layers |
| ❌ No async execution in Basic tier | ✅ Compliant | All commands are synchronous, API awaits sync calls |

## Basic Tier Philosophy Compliance

| Principle | Status | Evidence |
|-----------|--------|----------|
| Commands are concrete and boring | ✅ | Each command is a plain class, no magic |
| API is sync | ✅ | FastAPI handlers call sync commands, await is just FastAPI plumbing |
| CLI remains primary UX | ⚠️ Partial | CLI works but doesn't use command layer yet |
| API mirrors CLI behavior | ✅ | Same operations, same parameters |
| Evolution via reserved fields | ✅ | `poll_url`, `execution_id`, `status` in results |

## Violations Detected

**None.** The current implementation adheres to all stated constraints.

---

## TODO

- [ ] Verify no new code introduces DI containers
- [ ] Verify no generic Command ABC is added
- [ ] Complete CLI refactor to achieve full philosophy compliance
