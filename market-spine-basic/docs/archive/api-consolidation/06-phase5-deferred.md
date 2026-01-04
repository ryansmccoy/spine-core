# Phase 5: Deferred / Explicitly Out of Scope

> Status: 🔒 Frozen | Do Not Implement in Basic Tier

## What We Intentionally Do NOT Do in Basic

| Item | Reason | Tier Target |
|------|--------|-------------|
| Async execution | Tier boundary | Intermediate |
| Execution history / polling | Requires persistence layer | Intermediate |
| Authentication | Basic is single-user/local | Intermediate |
| Rate limiting | No multi-tenant concerns | Intermediate |
| Scheduling | Requires orchestration | Advanced |
| Webhook callbacks | Requires async + outbound HTTP | Advanced |
| OpenTelemetry / tracing | Infrastructure concern | Out of scope |
| CLI → API delegation | CLI calls commands directly, not via HTTP | Never |

## Frozen Packages (Do Not Touch)

| Package | Reason |
|---------|--------|
| `spine-core` | Framework only, no tier-specific logic |
| `spine-domains` | Tier constants are complete |

## Frozen Schemas

| Schema | Reason |
|--------|--------|
| Database tables | No migrations in Basic tier |
| `finra_otc_transparency_normalized` | Stable schema |
| `finra_otc_transparency_raw` | Stable schema |

## Reserved for Future Tiers

These fields/patterns exist but are unused in Basic:

| Item | Current Value | Future Use |
|------|---------------|------------|
| `poll_url` in results | `null` | Async polling URL |
| `ExecutionStatus.PENDING` | Unused | Async state |
| `ExecutionStatus.RUNNING` | Unused | Async state |
| `execution_history` capability | `false` | Query past runs |
| `authentication` capability | `false` | Token validation |

## Why This Phase Exists

Explicit documentation of what NOT to do prevents scope creep and maintains tier boundaries.

---

## TODO

- [ ] Review this list when starting Intermediate tier
- [ ] Ensure no Basic tier code introduces deferred features
- [ ] Document tier upgrade path in separate doc
