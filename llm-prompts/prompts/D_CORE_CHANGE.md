# Prompt D: Core Change Request

**Use this prompt ONLY when:** Domain-layer or app-layer changes are insufficient and framework changes are required.

**This is RARE.** Most features can be implemented in spine-domains without touching spine-core.

---

## Copy-Paste Prompt

```
I need to modify spine-core framework.

⚠️ STOP: This requires escalation. Complete this questionnaire BEFORE proceeding.

---

ESCALATION QUESTIONNAIRE:

### 1. Which 2+ domains need this change?

| Domain | Why It Needs This | Current Workaround |
|--------|------------------|-------------------|
| {domain_1} | {reason} | {workaround or "none"} |
| {domain_2} | {reason} | {workaround or "none"} |
| {domain_3 if applicable} | {reason} | {workaround or "none"} |

**If only 1 domain needs this**: STOP. Implement in that domain instead.

### 2. What alternatives were tried?

| Alternative | Description | Why Insufficient |
|------------|-------------|-----------------|
| Domain-level solution | {what you tried} | {why it failed} |
| App-level adapter | {what you tried} | {why it failed} |
| Configuration/extension point | {what you tried} | {why it failed} |

**Minimum 3 alternatives required.** If you haven't tried 3, go try them first.

### 3. What is the minimal change?

```
File: spine-core/src/spine/framework/{file}.py
Lines: {approximate line numbers}
Scope: {function / class / method}
Type: {Addition / Modification / Deprecation}
```

**Change description:**
{Exactly what will change and why}

**Backward compatibility:**
- [ ] Fully backward compatible (existing code works unchanged)
- [ ] Requires migration (describe migration path below)
- [ ] Breaking change (requires major version bump)

### 4. Migration path (if not backward compatible)

| Domain | Changes Required | Effort |
|--------|-----------------|--------|
| finra.otc_transparency | {specific changes} | {hours} |
| sec.edgar | {specific changes} | {hours} |
| {other domains} | {specific changes} | {hours} |

**Migration timeline:** {immediate / phased over N weeks}

### 5. Testing strategy

| Test Type | Location | What It Validates |
|-----------|----------|------------------|
| Framework unit tests | `tests/framework/test_{feature}.py` | Core behavior |
| Backward compatibility | `tests/framework/test_compatibility.py` | Existing usage still works |
| Domain integration | `tests/{domain}/test_{integration}.py` | Domains work with new code |

---

APPROVAL CRITERIA (all must be checked):

- [ ] 2+ domains need this change (documented above)
- [ ] 3+ alternatives tried and documented
- [ ] Change is minimal and scoped to single file/function
- [ ] Backward compatibility preserved OR migration path defined
- [ ] Tests planned for framework + domain integration + compatibility
- [ ] Documentation plan for framework docs + affected domain docs

---

IF APPROVED, PROCEED WITH:

### Implementation Order

1. **Change Surface Map** (framework + all affected domains)
2. **Framework changes** (spine-core)
3. **Framework tests** (prove it works)
4. **Domain migrations** (update all domains)
5. **Domain tests** (prove domains work)
6. **Documentation** (framework + all domains + CHANGELOG)

### Required Documentation

1. **Framework documentation:**
   - `packages/spine-core/docs/{FEATURE}.md`
   - Update `packages/spine-core/README.md`

2. **Domain documentation:**
   - Update each affected domain's docs
   - Add migration notes

3. **CHANGELOG entry:**
   ```markdown
   ## [X.Y.Z] - YYYY-MM-DD
   
   ### Changed
   - {Feature}: {Description of change}
   - Migration: {Brief migration steps if applicable}
   ```

---

ANTI-PATTERNS FOR CORE CHANGES:

- ❌ Changing core for single-domain needs
- ❌ Breaking backward compatibility without migration path
- ❌ Large refactors when small additions suffice
- ❌ Adding domain-specific logic to framework
- ❌ Skipping compatibility tests
- ❌ Not documenting rationale

---

DEFINITION OF DONE (Core Changes):

- [ ] Escalation questionnaire completed
- [ ] 2+ domains need confirmed
- [ ] 3+ alternatives tried
- [ ] Minimal change identified
- [ ] Backward compatibility plan
- [ ] Framework tests passing
- [ ] All domain tests passing
- [ ] Framework docs updated
- [ ] All domain docs updated
- [ ] CHANGELOG entry added
- [ ] Migration guide (if applicable)

PROCEED only after questionnaire is complete and approved.
```

---

## When Core Changes Are Actually Needed

**Legitimate reasons:**
- New registry type needed by multiple domains
- Pipeline base class missing hook used by 2+ domains
- Scheduler needs capability for multiple domain patterns
- Core table schema genuinely insufficient

**Not legitimate reasons:**
- "It would be cleaner in core" (keep domain logic in domains)
- "I don't want to duplicate code" (use shared utilities in domains)
- "Future domains might need it" (YAGNI - wait until they do)

---

## Example: Legitimate Core Change

```markdown
### 1. Which 2+ domains need this change?

| Domain | Why It Needs This | Current Workaround |
|--------|------------------|-------------------|
| finra.otc_transparency | Needs pre-run validation hook | Duplicated validation in each pipeline |
| sec.edgar | Needs pre-run validation hook | Duplicated validation in each pipeline |
| nasdaq.itch | Needs pre-run validation hook | Not implemented yet, will need same hook |

### 2. What alternatives were tried?

| Alternative | Description | Why Insufficient |
|------------|-------------|-----------------|
| Mixin class | Created ValidationMixin in each domain | Code duplication, inconsistent implementation |
| Decorator | @validate_before_run decorator | Can't access pipeline state |
| Domain base class | FinraPipeline(Pipeline) | Still duplicated across domains |

### 3. What is the minimal change?

File: spine-core/src/spine/framework/pipeline.py
Lines: 45-60
Scope: Pipeline.run() method
Type: Addition

Change: Add optional pre_run() hook that subclasses can override:

```python
def run(self):
    # NEW: Optional pre-run hook
    if hasattr(self, 'pre_run'):
        pre_result = self.pre_run()
        if pre_result and pre_result.get('skip'):
            return pre_result
    
    # Existing run logic...
```

Backward compatibility: ✅ Fully compatible (hook is optional)
```

---

## Related Documents

- [../CONTEXT.md](../CONTEXT.md) - Architecture layers
- [../ANTI_PATTERNS.md](../ANTI_PATTERNS.md) - What not to do
- [E_REVIEW.md](E_REVIEW.md) - Review checklist for core changes
