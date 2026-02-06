# Spine-Core Release Audit Prompt

> **Purpose:** Audit spine-core monorepo for PyPI release readiness
> **Location:** `b:\github\py-sec-edgar\spine-core\`
> **Monorepo Structure:** Contains `packages/spine-core` (v0.1.0) and `packages/spine-domains` (v0.1.0)
> **PyPI Status:** Not published
> **Created:** January 31, 2026

---

## 🎯 Mission

Audit the spine-core monorepo for PyPI publication. This repo contains **TWO packages**:
1. **spine-core** - Platform primitives and framework for temporal data processing
2. **spine-domains** - Market data domains (depends on spine-core)

Also verify the various frontend/orchestration components are properly organized.

---

## TASK 1: Repository Organization Audit

### 1.1 Monorepo Structure

```
spine-core/                      # Git repo root
├── packages/
│   ├── spine-core/              # PyPI package 1
│   │   └── src/spine/           # Core framework
│   └── spine-domains/           # PyPI package 2
│       └── src/spine/           # Domain modules (overlays spine-core)
├── market-spine-basic/          # Frontend variant?
├── market-spine-intermediate/   # Frontend variant?
├── market-spine-advanced/       # Frontend variant?
├── market-spine-full/           # Frontend variant?
├── trading-desktop/             # React frontend
├── trading-desktop-temp/        # Archive this?
└── trading-desktop.zip          # Archive this?
```

### 1.2 Items to Archive/Clean

Check these for archival:
- [ ] `trading-desktop-temp/` - Archive or delete?
- [ ] `trading-desktop.zip` - Remove if redundant?
- [ ] `market-spine-*` variants - Are all needed?

### 1.3 llm-prompts Directory

Review `llm-prompts/` for organization:
- [ ] Which prompts are current vs completed?
- [ ] Should completed prompts move to archive?
- [ ] Does it align with `prompts/` in main repo?

---

## TASK 2: Package 1 - spine-core

### 2.1 Location and Version

```
packages/spine-core/
├── pyproject.toml      # version = "0.1.0"
├── README.md
├── src/spine/
│   ├── __init__.py
│   ├── core/           # Core primitives
│   ├── framework/      # Framework components
│   └── orchestration/  # Orchestration tools
└── tests/
```

### 2.2 Core Feature Matrix

| Module | Purpose | Tests | Docs |
|--------|---------|-------|------|
| `spine.core.temporal` | Temporal primitives | ? | ? |
| `spine.core.record` | Record abstraction | ? | ? |
| `spine.core.identity` | Identity management | ? | ? |
| `spine.framework.pipeline` | Pipeline framework | ? | ? |
| `spine.framework.storage` | Storage backends | ? | ? |
| `spine.orchestration.*` | Orchestration | ? | ? |

### 2.3 Quality Checks

```bash
cd packages/spine-core

# Tests (475 passed previously)
python -m pytest tests/ -v --tb=short

# Coverage
python -m pytest tests/ --cov=src/spine --cov-report=term-missing

# Linting
ruff check src/
ruff format --check src/

# Type checking
mypy src/spine --ignore-missing-imports
```

### 2.4 Build Verification

```bash
cd packages/spine-core
pip install build
python -m build

pip install dist/spine_core-0.1.0-py3-none-any.whl
python -c "from spine.core import Record; print('OK')"
```

---

## TASK 3: Package 2 - spine-domains

### 3.1 Location and Version

```
packages/spine-domains/
├── pyproject.toml      # version = "0.1.0"
├── README.md
├── src/spine/
│   ├── domains/        # Domain modules
│   │   ├── copilot_chat/    # NEW - just committed
│   │   └── earnings/        # NEW - just committed
│   └── ...
├── examples/           # Usage examples
└── tests/
```

### 3.2 Domain Feature Matrix

| Domain | Purpose | Tests | Docs | Examples |
|--------|---------|-------|------|----------|
| `spine.domains.copilot_chat` | VS Code Copilot sessions | ? | ? | ? |
| `spine.domains.earnings` | Earnings estimates/actuals | ? | ? | ? |

### 3.3 Dependency on spine-core

Check `pyproject.toml`:
```toml
dependencies = ["spine-core"]  # Should reference spine-core package
```

For local development (uv):
```toml
[tool.uv.sources]
spine-core = { path = "../spine-core", editable = true }
```

### 3.4 Quality Checks

```bash
cd packages/spine-domains

# First install spine-core
pip install -e ../spine-core

# Then run tests
python -m pytest tests/ -v

# Linting
ruff check src/
```

### 3.5 Build Verification

```bash
cd packages/spine-domains
pip install build
python -m build

# Note: Requires spine-core installed first
pip install ../spine-core/dist/spine_core-0.1.0-py3-none-any.whl
pip install dist/spine_domains-0.1.0-py3-none-any.whl
python -c "from spine.domains.earnings import EarningsRecord; print('OK')"
```

---

## TASK 4: Documentation Audit

### 4.1 Root-Level Docs

Check `spine-core/docs/`:
- [ ] Project overview accurate
- [ ] Installation instructions for both packages
- [ ] Quickstart examples

### 4.2 Package READMEs

Verify both packages have proper READMEs:
- [ ] `packages/spine-core/README.md` - Installation, usage
- [ ] `packages/spine-domains/README.md` - Installation, domains list

### 4.3 Examples Working

```bash
# spine-domains examples
cd packages/spine-domains
python examples/copilot_chat_demo.py
python examples/earnings_demo.py
```

---

## TASK 5: Frontend Components

### 5.1 market-spine Variants

Understand the variants:
| Variant | Purpose | Status |
|---------|---------|--------|
| `market-spine-basic/` | Minimal frontend | ? |
| `market-spine-intermediate/` | Mid-tier frontend | ? |
| `market-spine-advanced/` | Full frontend | ? |
| `market-spine-full/` | Complete package | ? |

Questions:
- [ ] Are all variants needed?
- [ ] Can they be consolidated?
- [ ] Are they documented?

### 5.2 trading-desktop

```
trading-desktop/          # React/Electron app
├── package.json
├── src/
└── ...
```

- [ ] Does it build?
- [ ] Is it documented?
- [ ] What's the relationship to market-spine variants?

### 5.3 docker-compose Files

```
docker-compose.yml
docker-compose.basic.yml
docker-compose.dev.yml
docker-compose.full.yml
docker-compose.intermediate.yml
```

- [ ] Are these documented?
- [ ] Which one should users start with?
- [ ] Do they match the market-spine variants?

---

## TASK 6: Integration Points

### 6.1 With feedspine

- [ ] Can spine-domains records flow into feedspine?
- [ ] Is integration documented?

### 6.2 With entityspine

- [ ] Entity linking works?
- [ ] Integration documented?

### 6.3 With genai-spine

- [ ] LLM integration paths?
- [ ] Documentation?

---

## TASK 7: Release Preparation

### 7.1 Version Alignment

Both packages should be 0.1.0 for initial release:
```bash
grep "version" packages/spine-core/pyproject.toml
grep "version" packages/spine-domains/pyproject.toml
```

### 7.2 Publishing Order

Because spine-domains depends on spine-core:
1. Publish spine-core first
2. Wait for PyPI to index
3. Then publish spine-domains

### 7.3 pyproject.toml Completeness

For both packages, verify:
- [ ] `name` - Correct package name
- [ ] `version` - 0.1.0
- [ ] `description` - Clear, descriptive
- [ ] `readme` - Points to README.md
- [ ] `license` - MIT
- [ ] `authors` - Populated
- [ ] `keywords` - SEO friendly
- [ ] `classifiers` - PyPI categories
- [ ] `dependencies` - Minimal core deps
- [ ] `[project.urls]` - Homepage, docs, repo

---

## Deliverables Checklist

### spine-core Package
- [ ] Tests passing (475+)
- [ ] Ruff clean
- [ ] Docstrings adequate
- [ ] README complete
- [ ] Build verified
- [ ] Version 0.1.0

### spine-domains Package
- [ ] Tests passing
- [ ] Ruff clean
- [ ] Examples run
- [ ] README complete
- [ ] Build verified
- [ ] Version 0.1.0

### Monorepo
- [ ] Stale files archived
- [ ] Docker files documented
- [ ] Frontend variants understood
- [ ] llm-prompts organized

---

## Priority Order

1. 🟢 **Run spine-core tests** - Verify 475+ passing
2. 🟢 **Run spine-domains tests** - Verify domains work
3. 🟢 **Build both packages** - Verify wheel creation
4. 🟡 **Archive stale files** - trading-desktop-temp, .zip
5. 🟡 **Document variants** - market-spine-* purpose
6. 🟢 **Publish spine-core first** - PyPI
7. 🟢 **Publish spine-domains second** - After spine-core indexed

---

## Notes

The monorepo structure adds complexity:
- Two packages must be published in order
- Local development uses uv workspace
- PyPI publishing requires spine-core first

Potential simplifications:
- Consider merging spine-domains into spine-core if domains are small
- Consolidate market-spine variants if redundant
- Document docker-compose usage clearly
