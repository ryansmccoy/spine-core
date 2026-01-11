# Phase 2: API Surface Hardening

> Status: 🔴 Not Started | Priority: MEDIUM

## Goal

Finalize endpoint contracts and ensure error consistency.

## Files Affected

| File | Change | Status |
|------|--------|--------|
| `api/routes/v1/pipelines.py` | Audit error codes, add missing reserved fields | ⬜ Not Started |
| `api/routes/health.py` | No changes expected | ✅ Complete |
| `api/routes/v1/capabilities.py` | Add `api_version` field | ⬜ Not Started |
| `app/models.py` | Ensure all error codes used consistently | ⬜ Not Started |

## What Changes

### Error Response Standardization

Every error response uses `ErrorCode` from models (not inline strings):

```json
{
  "code": "PIPELINE_NOT_FOUND",
  "message": "Pipeline 'foo.bar' not found in registry"
}
```

### Reserved Fields in Execution Response

All execution responses include reserved fields even if null:

| Field | Basic Tier Value | Purpose |
|-------|------------------|---------|
| `execution_id` | UUID (always present) | Unique execution identifier |
| `status` | `"completed"` or `"failed"` | Execution state |
| `poll_url` | `null` | Reserved for async polling (Intermediate) |

### Capabilities Enhancement

Add explicit `api_version: "v1"` to capabilities response.

## What Does NOT Change

- Endpoint paths remain as-is
- Request/response shapes remain as-is
- No new endpoints added

## Why This Phase Exists

API contracts are promises. Clients will code against them. Hardening now prevents breaking changes later.

---

## TODO

- [ ] Audit all `HTTPException` calls in `api/routes/v1/pipelines.py`
- [ ] Replace inline error strings with `ErrorCode` usage
- [ ] Ensure all execution responses include `execution_id`, `status`, `poll_url`
- [ ] Add `api_version` field to capabilities response
- [ ] Document error code meanings
