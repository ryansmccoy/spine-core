# FastAPI & Pydantic Assessment

> Status: ✅ Approved | With Constraints

## Is FastAPI + Pydantic Acceptable in Basic Tier?

**Yes**, given what already exists and the following constraints.

## Why Acceptable

| Reason | Explanation |
|--------|-------------|
| Already implemented | Rewriting would be waste |
| Minimal surface | 8 endpoints, no custom middleware |
| Pydantic is for API boundaries only | Internal models use dataclasses |
| Sync execution | FastAPI's async is cosmetic (sync commands called with `await`) |
| No auth/middleware complexity | Plain request → response |

## Rules to Prevent Overuse

| Rule | Rationale | Status |
|------|-----------|--------|
| Pydantic models only in `api/routes/` | Keep API concerns out of commands | ✅ Compliant |
| No Pydantic in commands or services | Dataclasses suffice; no validation magic needed | ✅ Compliant |
| No dependency injection via FastAPI `Depends` | Commands construct their own services | ✅ Compliant |
| No background tasks | Sync execution only | ✅ Compliant |
| No WebSocket endpoints | Out of scope for Basic | ✅ Compliant |
| No custom exception handlers beyond HTTPException | Keep error handling simple | ✅ Compliant |

## Current Compliance

The implementation already follows these rules:

- `app/models.py` uses dataclasses ✅
- `api/routes/v1/pipelines.py` uses Pydantic for request/response only ✅
- Commands are instantiated directly, not injected ✅

## Boundary Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        API Layer                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Pydantic Models (Request/Response)                 │   │
│  │  - PipelineSummaryResponse                          │   │
│  │  - RunPipelineBody                                  │   │
│  │  - ExecutionResponse                                │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Command Layer                          │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Dataclass Models (Internal)                        │   │
│  │  - RunPipelineRequest                               │   │
│  │  - RunPipelineResult                                │   │
│  │  - CommandError                                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## What Would Trigger Reassessment

- Adding >20 endpoints
- Need for WebSocket support
- Complex validation logic bleeding into commands
- Performance issues from Pydantic overhead

---

## TODO

- [ ] Periodically audit for Pydantic creep into command layer
- [ ] Ensure new endpoints follow existing patterns
- [ ] No `Depends()` usage for command injection
