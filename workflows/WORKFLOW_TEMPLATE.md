# {Workflow Name}

**Type:** {Operational / Development / Incident}  
**Frequency:** {Daily / Weekly / As needed}  
**Duration:** {Estimated time}  
**Owner:** {Team / Role}

---

## Trigger

Describe when and why to run this workflow.

---

## Prerequisites

- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Access/permissions needed

---

## Steps

### 1. Step Name

**Description of what this step does.**

**Command:**
```bash
# Command to run
```

**Expected outcome:**
- What success looks like
- What to watch for

### 2. Step Name

**Description.**

**Command:**
```bash
# Command
```

### 3. Verification Step

**How to verify the workflow succeeded.**

```sql
-- Verification query
SELECT ...
```

---

## Success Criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] All checks pass

---

## Common Issues

### Issue: Description

**Cause:** What causes this  
**Fix:** 
```bash
# How to fix
```

---

## Rollback

**If workflow fails or produces bad results:**

```bash
# Rollback commands
```

---

## References

- **Script:** `scripts/...`
- **Prompt:** `llm-prompts/prompts/...`
- **Related workflow:** `workflows/.../...`
- **Documentation:** `docs/...`
