# Phase 3: Capabilities & Versioning

> Status: 🔴 Not Started | Priority: LOW

## Goal

Ensure `/v1/capabilities` is the authoritative source of truth for tier detection.

## Files Affected

| File | Change | Status |
|------|--------|--------|
| `api/routes/v1/capabilities.py` | Finalize response schema | ⬜ Not Started |
| Documentation | Document capability contract | ⬜ Not Started |

## What `/v1/capabilities` Must Guarantee

```json
{
  "tier": "basic",
  "api_version": "v1",
  "version": "0.1.0",
  "sync_execution": true,
  "async_execution": false,
  "execution_history": false,
  "authentication": false,
  "scheduling": false,
  "rate_limiting": false,
  "webhook_notifications": false
}
```

## Client Tier Detection Pattern

```python
# Recommended client pattern
caps = client.get("/v1/capabilities")

if caps["async_execution"]:
    # Use poll-based execution
    result = client.post(f"/v1/pipelines/{name}/run", json=params)
    while result["status"] == "pending":
        result = client.get(result["poll_url"])
else:
    # Execution blocks until complete
    result = client.post(f"/v1/pipelines/{name}/run", json=params)
    # result is final
```

## Capability Definitions

| Capability | Type | Meaning |
|------------|------|---------|
| `tier` | string | Tier name: "basic", "intermediate", "advanced" |
| `api_version` | string | API version: "v1" |
| `version` | string | Package version |
| `sync_execution` | bool | Supports synchronous execution |
| `async_execution` | bool | Supports async execution with polling |
| `execution_history` | bool | Stores and queries past executions |
| `authentication` | bool | Requires auth tokens |
| `scheduling` | bool | Supports scheduled/recurring runs |
| `rate_limiting` | bool | Enforces rate limits |
| `webhook_notifications` | bool | Can send webhooks on completion |

## What Does NOT Change

- No capability is added that Basic doesn't support
- No runtime capability negotiation

## Why This Phase Exists

Clients need a stable way to detect features without version string parsing or tier name matching.

---

## TODO

- [ ] Add `api_version` field to capabilities response
- [ ] Verify all capability flags are accurate for Basic tier
- [ ] Document capability contract in README or API docs
- [ ] Add capability response to OpenAPI schema description
