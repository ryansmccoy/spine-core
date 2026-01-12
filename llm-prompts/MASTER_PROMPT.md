# Master Prompt: Implement Any Feature

**Use this prompt as the default starting point for any feature implementation.**

---

## Copy-Paste Prompt

```
I need to implement a feature for Market Spine.

CONTEXT (READ FIRST):
Inject the contents of llm-prompts/CONTEXT.md here, or ensure you have read it.

FEATURE REQUEST:
{Describe the feature here}

---

MANDATORY PRE-WORK: CHANGE SURFACE MAP

Before writing ANY code, create a Change Surface Map listing every file that will change and WHY:

## Change Surface Map

### Domain Layer (spine-domains)
- [ ] `src/spine/domains/{domain}/sources/{file}.py` - WHY: {reason}
- [ ] `src/spine/domains/{domain}/pipelines.py` - WHY: {reason}
- [ ] `src/spine/domains/{domain}/validators.py` - WHY: {reason}
- [ ] `src/spine/domains/{domain}/schema/00_tables.sql` - WHY: {reason}
- [ ] `src/spine/domains/{domain}/schema/02_views.sql` - WHY: {reason}

### Tests
- [ ] `tests/{domain}/test_{feature}.py` - Unit + integration tests
- [ ] `tests/{domain}/test_{feature}_fitness.py` - Multi-pipeline fitness (if applicable)

### Documentation
- [ ] `docs/{FEATURE}.md` - Implementation guide
- [ ] `README.md` - Update with new feature

### App Layer (if needed)
- [ ] `spine-app/src/spine/app/commands/{command}.py` - WHY: {reason}

### Core Layer (REQUIRES ESCALATION)
- [ ] `spine-core/src/spine/framework/{file}.py` - WHY: {reason}
- [ ] JUSTIFICATION: {Prove 2+ domains need this. List alternatives tried.}

---

IMPLEMENTATION RULES:

1. **Layering**: 
   - Default to spine-domains
   - spine-core changes require 2+ domain need + escalation
   - spine-app adapters stay thin (no business logic)

2. **Orchestration** (NEW):
   - Single operation (fetch, transform, calculate)? → Pipeline only
   - Multiple steps with validation between? → Workflow + Pipelines
   - Workflow lambda steps: LIGHTWEIGHT validation only
   - ❌ NEVER copy pipeline logic into workflow lambdas
   - Reference pipelines via: `Step.pipeline("name", "registered.pipeline")`
   - See [prompts/F_WORKFLOW.md](prompts/F_WORKFLOW.md) for workflow patterns

3. **Schema Changes**:
   - Tables in `schema/00_tables.sql`
   - Views in `schema/02_views.sql`
   - Run `python scripts/build_schema.py` after changes
   - NO runtime CREATE VIEW in Python code

4. **Capture ID Semantics**:
   - Every output row has: capture_id, captured_at, execution_id, batch_id
   - Format: `{domain}.{stage}.{partition_key}.{timestamp}`
   - Track in core_manifest
   - Idempotent: same capture_id reruns UPDATE (don't duplicate)

5. **Error Handling**:
   - NO silent failures (try/except pass)
   - Record anomalies: INSERT INTO core_anomalies
   - Include: domain, stage, partition_key, severity, category, message
   - Allow partial success (skip bad items, process good ones)

6. **Quality Gates**:
   - Validate inputs before compute
   - Use scoped anomaly filtering (partition_key exact match)
   - Track provenance (input_min/max_capture_id)

7. **Determinism**:
   - Same inputs → same outputs
   - Exclude audit fields from comparisons: captured_at, batch_id, execution_id

8. **Registry**:
   - Register classes in CALCS/SOURCES/PIPELINES
   - NO if/elif branching factories

---

REQUIRED TESTS:

1. **Unit Test**: Test individual functions
2. **Integration Test**: Full pipeline with real DB
3. **Determinism Test**: Run twice, compare excluding audit fields
4. **Idempotency Test**: Same capture_id twice, verify no duplicates
5. **Fitness Test**: Multi-pipeline workflow (if applicable)
6. **Workflow Test**: If using workflows, test full workflow execution

---

REQUIRED DOCUMENTATION:

1. `docs/{FEATURE}.md`:
   - Overview (what/why)
   - Components implemented
   - Usage examples (code + SQL)
   - Behavior changes (before/after)
   - Monitoring queries

2. Update `README.md` with new feature

---

ANTI-PATTERNS TO AVOID:

- ❌ Runtime CREATE VIEW (use schema/02_views.sql)
- ❌ Branching factories (use registries)
- ❌ MAX(version) queries (use ROW_NUMBER)
- ❌ Silent failures (record anomalies)
- ❌ Global anomaly filtering (scope by partition_key)
- ❌ Audit fields in determinism checks
- ❌ Hardcoded week lists (use period utils)
- ❌ Non-consecutive window checks (enforce all weeks)
- ❌ **Copying pipeline logic into workflow lambdas** (use Step.pipeline())
- ❌ **Business logic in workflow lambda steps** (lambdas validate only)
- ❌ **Workflows without registered pipelines** (pipelines first, then workflow)

---

DEFINITION OF DONE:

- [ ] Change Surface Map created
- [ ] Code minimal and in correct layer
- [ ] Schema in module files, build_schema.py run
- [ ] Capture ID semantics correct
- [ ] Idempotency verified
- [ ] Determinism verified
- [ ] Errors surfaced via core_anomalies
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] Determinism test passing
- [ ] Idempotency test passing
- [ ] Documentation written
- [ ] README updated
- [ ] No anti-patterns

PROCEED by first creating the Change Surface Map, then implementing.
```

---

## When to Use This Prompt

- **Default choice** when you're not sure which specialized prompt to use
- **General features** that don't fit neatly into datasource/calculation/operational categories
- **Refactoring** existing code
- **Bug fixes** that require understanding the architecture

---

## When to Use Specialized Prompts Instead

| If you're doing this... | Use this prompt instead |
|------------------------|------------------------|
| Adding a new data source (API, file, DB) | [prompts/A_DATASOURCE.md](prompts/A_DATASOURCE.md) |
| Adding a new calculation/metric | [prompts/B_CALCULATION.md](prompts/B_CALCULATION.md) |
| Adding scheduler, quality gate, monitoring | [prompts/C_OPERATIONAL.md](prompts/C_OPERATIONAL.md) |
| Modifying spine-core framework | [prompts/D_CORE_CHANGE.md](prompts/D_CORE_CHANGE.md) |
| Reviewing someone else's changes | [prompts/E_REVIEW.md](prompts/E_REVIEW.md) |
| **Orchestrating multiple pipelines** | [prompts/F_WORKFLOW.md](prompts/F_WORKFLOW.md) |

---

## Related Documents

- [CONTEXT.md](CONTEXT.md) - Repository structure and patterns
- [ANTI_PATTERNS.md](ANTI_PATTERNS.md) - What not to do
- [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) - Complete checklist
- [reference/SQL_PATTERNS.md](reference/SQL_PATTERNS.md) - Common SQL patterns
