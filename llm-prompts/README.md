# LLM Contributor Prompt Pack

**Version:** 1.1  
**Last Updated:** 2026-01-04  
**Purpose:** Copy-paste prompts for LLM agents implementing features in Market Spine while maintaining architectural guardrails.

---

## Quick Start: Which Prompt to Use?

| **Use Case** | **Prompt File** | **When to Use** |
|-------------|----------------|----------------|
| General feature work | [MASTER_PROMPT.md](MASTER_PROMPT.md) | Default starting point for any feature |
| Adding new data source | [prompts/A_DATASOURCE.md](prompts/A_DATASOURCE.md) | New vendor API, file connector, database source |
| Adding new calculation | [prompts/B_CALCULATION.md](prompts/B_CALCULATION.md) | New metric family, rolling averages, aggregations |
| Adding operational feature | [prompts/C_OPERATIONAL.md](prompts/C_OPERATIONAL.md) | Scheduler, gap detection, quality gates, monitoring |
| Modifying spine-core | [prompts/D_CORE_CHANGE.md](prompts/D_CORE_CHANGE.md) | Registry changes, framework extensions (RARE) |
| Reviewing PR/changes | [prompts/E_REVIEW.md](prompts/E_REVIEW.md) | Audit guardrail compliance before merge |

---

## How to Use These Prompts

### For LLM Agents

1. **Start every session** by reading [CONTEXT.md](CONTEXT.md) - it contains repo structure, patterns, and tables
2. **Pick the appropriate prompt** from the table above
3. **Copy-paste the prompt** into your context window
4. **Follow the checklist** in [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md)
5. **Self-review** using [prompts/E_REVIEW.md](prompts/E_REVIEW.md) before submitting

### For Humans

1. **Include relevant prompt** when starting a conversation with an LLM
2. **Reference anti-patterns** in [ANTI_PATTERNS.md](ANTI_PATTERNS.md) when reviewing LLM output
3. **Use templates** in [templates/](templates/) for consistent file structure

---

## Document Index

### Core Documents
| File | Purpose |
|------|---------|
| [CONTEXT.md](CONTEXT.md) | Repository structure, architecture layers, core tables, patterns (INJECT INTO EVERY SESSION) |
| [MASTER_PROMPT.md](MASTER_PROMPT.md) | Universal prompt for any feature implementation |
| [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) | Universal checklist for feature completion |
| [ANTI_PATTERNS.md](ANTI_PATTERNS.md) | What NOT to do (with explanations and correct patterns) |

### Specialized Prompts
| File | Purpose |
|------|---------|
| [prompts/A_DATASOURCE.md](prompts/A_DATASOURCE.md) | Add new data source (API, file, database) |
| [prompts/B_CALCULATION.md](prompts/B_CALCULATION.md) | Add new calculation family |
| [prompts/C_OPERATIONAL.md](prompts/C_OPERATIONAL.md) | Add operational feature (scheduler, quality gate) |
| [prompts/D_CORE_CHANGE.md](prompts/D_CORE_CHANGE.md) | Modify spine-core (requires escalation) |
| [prompts/E_REVIEW.md](prompts/E_REVIEW.md) | Review changes for compliance |

### Templates
| File | Purpose |
|------|---------|
| [templates/pipeline.py](templates/pipeline.py) | Pipeline class template |
| [templates/validator.py](templates/validator.py) | Validator function template |
| [templates/test_feature.py](templates/test_feature.py) | Test file template |
| [templates/FEATURE_DOC.md](templates/FEATURE_DOC.md) | Feature documentation template |

### Reference
| File | Purpose |
|------|---------|
| [reference/SQL_PATTERNS.md](reference/SQL_PATTERNS.md) | Common SQL patterns (as-of, latest, provenance) |
| [reference/CAPTURE_SEMANTICS.md](reference/CAPTURE_SEMANTICS.md) | Capture ID, idempotency, replay patterns |
| [reference/QUALITY_GATES.md](reference/QUALITY_GATES.md) | Quality gate implementation patterns |

---

## Key Principles

### 1. Layering is Sacred
```
spine-core    → Generic framework (AVOID CHANGES)
spine-domains → Domain features (YOUR WORKSPACE)
spine-app     → Commands/services (thin adapters)
trading-desktop → UI (API-driven only)
```

### 2. Registry Over Branching
```python
# ❌ WRONG
if source_type == "finra":
    return FinraSource()
elif source_type == "sec":
    return SecSource()

# ✅ CORRECT
SOURCES.register(FinraSource, name="finra")
SOURCES.register(SecSource, name="sec")
source = SOURCES.get(source_type)
```

### 3. Determinism is Non-Negotiable
```python
# Same inputs → same outputs (excluding audit fields)
assert_equal(
    run_pipeline(params),
    run_pipeline(params),
    exclude=["captured_at", "batch_id", "execution_id"]
)
```

### 4. Errors Must Surface
```python
# ❌ WRONG
try:
    process()
except Exception:
    pass  # Silent failure

# ✅ CORRECT
try:
    process()
except Exception as e:
    record_anomaly(severity="ERROR", category="PROCESSING", message=str(e))
    raise  # Or return partial result
```

### 5. Schema Lives in Files
```sql
-- ❌ WRONG: Runtime view creation
conn.execute("CREATE VIEW IF NOT EXISTS ...")

-- ✅ CORRECT: Schema module file
-- In: schema/02_views.sql
CREATE VIEW IF NOT EXISTS my_view AS ...
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.1 | 2026-01-04 | Split into modular files, added templates and reference docs |
| 1.0 | 2026-01-04 | Initial release as single file |

---

## Contributing

Improve these prompts by:
1. Identifying patterns not covered
2. Proposing new specialized prompts
3. Reporting anti-patterns encountered
4. Adding templates for common file types
5. Submitting clarifications for ambiguous rules

**Maintainer**: Market Spine Core Team
