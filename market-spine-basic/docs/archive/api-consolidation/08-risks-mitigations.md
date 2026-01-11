# Risks & Mitigations

> If We Do Nothing Else, These Are the Risks

## Risk 1: CLI Drift vs API

### Description
CLI and API diverge in behavior. A fix in one isn't reflected in the other.

### Current State
- CLI calls framework directly
- API calls commands
- They're parallel implementations

### Impact
- **High** — Bugs fixed in API may not be fixed in CLI (or vice versa)
- Users get inconsistent behavior depending on interface

### Mitigation
Complete Phase 1 (CLI → Command Refactor). This is the most important remaining work.

### If Deferred
Accept that CLI and API may behave differently. Document which is authoritative (CLI).

### Status: 🔴 Active Risk

---

## Risk 2: Overexposure of Internal Concepts

### Description
API exposes internal names (e.g., `Lane.BACKFILL`) that become frozen contracts.

### Current State
- `RunPipelineBody.lane` accepts "default", "backfill", "realtime" strings
- Mapping happens in handler

### Impact
- **Low** — Already mitigated by string → enum mapping

### Mitigation
Already mitigated. Keep string → enum mapping in API layer, not in commands.

### Ongoing Rule
Never expose framework enums directly in API schemas.

### Status: ✅ Mitigated

---

## Risk 3: Sync → Async Transition Pain

### Description
When Intermediate tier adds async, the command layer needs rewriting.

### Current State
- Commands are sync
- Reserved fields (`poll_url`, `status`) exist but are unused

### Impact
- **Medium** — Could require significant refactoring

### Mitigation
- Commands stay sync in Basic (they run to completion)
- Intermediate tier wraps commands with async orchestration
- Commands don't change; orchestration layer handles async

### Design Principle
Commands describe *what* to do. Orchestration (sync/async) is a *how* concern handled at the tier boundary.

### Status: ✅ Mitigated by Design

---

## Risk 4: Testing Blind Spots

### Description
API layer bugs (wrong status codes, missing fields) aren't caught.

### Current State
- Services and commands have tests
- API routes do not

### Impact
- **Medium** — Bugs in request parsing or response mapping undetected

### Mitigation
Complete Phase 4 (Testing Gaps). Use FastAPI `TestClient` for endpoint tests.

### Minimum Coverage
- Happy path for each endpoint
- One error case per error code used
- Capability response structure

### Status: 🔴 Active Risk

---

## Risk 5: Error Code Inconsistency

### Description
Different endpoints return different error structures, breaking client parsing.

### Current State
- Most errors use `ErrorCode` enum
- Some use inline strings in `HTTPException.detail`

### Impact
- **Medium** — Clients can't reliably parse errors

### Mitigation
Audit in Phase 2. All errors should return:

```json
{
  "code": "ERROR_CODE",
  "message": "Human readable"
}
```

### Status: 🟡 Partial Risk

---

## Risk Summary

| Risk | Severity | Status | Mitigation Phase |
|------|----------|--------|------------------|
| CLI Drift vs API | High | 🔴 Active | Phase 1 |
| Overexposure of Internal Concepts | Low | ✅ Mitigated | N/A |
| Sync → Async Transition | Medium | ✅ Mitigated | N/A |
| Testing Blind Spots | Medium | 🔴 Active | Phase 4 |
| Error Code Inconsistency | Medium | 🟡 Partial | Phase 2 |

---

## TODO

- [ ] Complete Phase 1 to eliminate CLI drift risk
- [ ] Complete Phase 2 to standardize error codes
- [ ] Complete Phase 4 to eliminate testing blind spots
- [ ] Review risks after each phase completion
