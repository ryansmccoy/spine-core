# Prompt E: Review Changes

**Use this prompt when:** Reviewing PRs, diffs, or changes before merge.

---

## Copy-Paste Prompt

```
Review the following changes for Market Spine compliance.

CONTEXT:
- Read llm-prompts/CONTEXT.md for architecture rules
- Read llm-prompts/ANTI_PATTERNS.md for forbidden patterns

CHANGES TO REVIEW:
{Paste diff, PR description, or file list here}

---

AUDIT CHECKLIST:

### 1. Layering Compliance

| Check | Status | Notes |
|-------|--------|-------|
| spine-core changes justified? (2+ domains need it) | ⬜ | |
| spine-domains changes in correct domain folder? | ⬜ | |
| spine-app adapters thin? (no business logic) | ⬜ | |
| trading-desktop API-driven? (no direct DB) | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 2. Schema Ownership

| Check | Status | Notes |
|-------|--------|-------|
| Core tables (core_*) modified in spine-core/schema/? | ⬜ | |
| Domain tables modified in domain schema modules? | ⬜ | |
| Views defined in schema/02_views.sql (not runtime)? | ⬜ | |
| build_schema.py run to generate artifact? | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 3. Capture ID Semantics

| Check | Status | Notes |
|-------|--------|-------|
| Pipeline outputs include capture_id? | ⬜ | |
| capture_id format correct? (domain.stage.partition.timestamp) | ⬜ | |
| Tracked in core_manifest? | ⬜ | |
| Idempotent? (same capture_id reruns UPDATE, not duplicate) | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 4. Determinism

| Check | Status | Notes |
|-------|--------|-------|
| Same inputs → same outputs? | ⬜ | |
| No randomness in computation? | ⬜ | |
| No timestamp-dependent logic? | ⬜ | |
| Audit fields excluded from comparisons? | ⬜ | |
| (captured_at, batch_id, execution_id) | | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 5. Registry Compliance

| Check | Status | Notes |
|-------|--------|-------|
| New sources registered in SOURCES? | ⬜ | |
| New calculations registered in CALCS? | ⬜ | |
| New pipelines registered in PIPELINES? | ⬜ | |
| NO if/elif branching factories? | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 6. Error Surfacing

| Check | Status | Notes |
|-------|--------|-------|
| Errors recorded in core_anomalies? | ⬜ | |
| Severity set correctly? (DEBUG/INFO/WARN/ERROR/CRITICAL) | ⬜ | |
| Category set correctly? (QUALITY_GATE/NETWORK/etc.) | ⬜ | |
| partition_key set for filtering? | ⬜ | |
| NO silent failures (try/except pass)? | ⬜ | |
| Partial success supported? | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 7. Quality Gates

| Check | Status | Notes |
|-------|--------|-------|
| Input validation before compute? | ⬜ | |
| Consecutive week check (if rolling window)? | ⬜ | |
| Anomaly filtering scoped (partition_key exact match)? | ⬜ | |
| Provenance tracking (input_min/max_capture_id)? | ⬜ | |
| is_complete flag set correctly? | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 8. Tests

| Check | Status | Notes |
|-------|--------|-------|
| Unit tests written? | ⬜ | |
| Integration tests written? | ⬜ | |
| Determinism test written? | ⬜ | |
| Idempotency test written? | ⬜ | |
| Fitness test written (if multi-pipeline)? | ⬜ | |
| All tests passing? | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 9. Documentation

| Check | Status | Notes |
|-------|--------|-------|
| docs/{FEATURE}.md created/updated? | ⬜ | |
| README.md updated? | ⬜ | |
| Usage examples included? | ⬜ | |
| Monitoring queries documented? | ⬜ | |
| Edge cases documented? | ⬜ | |

**Verdict:** ⬜ Pass ⬜ Fail ⬜ N/A

### 10. Anti-Patterns Check

| Anti-Pattern | Found? | Location |
|-------------|--------|----------|
| Runtime CREATE VIEW | ⬜ | |
| Branching factories (if/elif) | ⬜ | |
| MAX(version) queries | ⬜ | |
| Silent failures (except: pass) | ⬜ | |
| Hardcoded week/date lists | ⬜ | |
| Global anomaly filtering | ⬜ | |
| Audit fields in determinism checks | ⬜ | |
| Missing capture_id | ⬜ | |
| Missing provenance | ⬜ | |
| Non-consecutive window check | ⬜ | |

**Verdict:** ⬜ Pass (none found) ⬜ Fail (anti-patterns present)

---

## REVIEW OUTCOME

⬜ **APPROVED**: All checks pass. Ready to merge.

⬜ **NEEDS REVISION**: Issues found (see below). Requires changes before merge.

⬜ **ESCALATION REQUIRED**: Core changes need justification per Prompt D.

---

## ISSUES FOUND

| # | Severity | Category | Description | File/Line |
|---|----------|----------|-------------|-----------|
| 1 | {HIGH/MED/LOW} | {category} | {description} | {location} |
| 2 | | | | |
| 3 | | | | |

---

## RECOMMENDATIONS

### Issue 1: {Title}
**Problem:** {What's wrong}
**Fix:** {How to fix it}
**Example:**
```python
# Before (wrong)
{code}

# After (correct)
{code}
```

### Issue 2: {Title}
...

---

## SUMMARY

- **Checks Passed:** {X}/10
- **Checks Failed:** {X}/10
- **Checks N/A:** {X}/10
- **Anti-Patterns Found:** {X}
- **Overall:** {APPROVED / NEEDS REVISION / ESCALATION REQUIRED}
```

---

## Quick Review Checklist (Copy-Paste for Comments)

```markdown
## Review Checklist

### Critical (must fix)
- [ ] No runtime CREATE VIEW
- [ ] No silent failures (try/except pass)
- [ ] Capture ID in all outputs
- [ ] Anomaly filtering scoped by partition_key
- [ ] Tests exist and pass

### Important (should fix)
- [ ] Documentation updated
- [ ] Determinism test exists
- [ ] Idempotency test exists
- [ ] No anti-patterns

### Nice to have
- [ ] Monitoring queries documented
- [ ] Examples in docs run successfully
```

---

## Red Flags (Immediate Rejection)

These require immediate revision:

1. **Modifying spine-core without justification**
   - Ask: "Which 2+ domains need this?"
   - If only 1 domain: Reject, move to domain layer

2. **Silent exception swallowing**
   ```python
   # REJECT THIS
   try:
       process()
   except Exception:
       pass
   ```

3. **Runtime schema changes**
   ```python
   # REJECT THIS
   conn.execute("CREATE VIEW IF NOT EXISTS ...")
   ```

4. **Global anomaly filtering**
   ```sql
   -- REJECT THIS
   WHERE NOT EXISTS (SELECT 1 FROM core_anomalies WHERE severity = 'ERROR')
   ```

5. **Missing capture_id in output tables**
   - Every output table MUST have capture_id, captured_at, execution_id, batch_id

6. **No tests**
   - Minimum: unit test + determinism test + idempotency test

---

## Related Documents

- [../CONTEXT.md](../CONTEXT.md) - Architecture rules
- [../ANTI_PATTERNS.md](../ANTI_PATTERNS.md) - What not to do
- [../DEFINITION_OF_DONE.md](../DEFINITION_OF_DONE.md) - Complete checklist
