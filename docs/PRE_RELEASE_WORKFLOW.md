# Pre-Release Workflow - spine-core

**Version**: 1.0  
**Last Updated**: February 3, 2026  
**Status**: Active Standard

---

## Overview

This document defines the **mandatory pre-release checklist** for pushing **spine-core** to GitHub. As the shared framework foundation, spine-core requires extra care since all other spine projects depend on it.

## About spine-core

Spine-core provides shared framework primitives and workflows for the entire spine ecosystem:
- Core data structures and types
- Shared utilities and helpers
- Common patterns and abstractions
- Base classes for extension

**CRITICAL**: Changes to spine-core affect ALL dependent projects (feedspine, entityspine, etc.)

---

## Quick Start

```bash
cd spine-launchpad

# Run complete pre-release workflow
uv run python -m scripts util pre-release --projects spine-core

# Or use interactive mode
uv run python -m scripts util pre-release --pick
# Select: spine-core
```

---

## Pre-Release Checklist

### Phase 1: Structure & Standards ⚙️

#### 1.1 Validate Project Structure
```bash
cd spine-launchpad
uv run python -m scripts util validate
```

**Checks**:
- ✅ Python version consistency (>=3.12)
- ✅ Ruff version consistency (>=0.9.0)
- ✅ pyproject.toml formatting
- ✅ Standard directory structure

**Success Criteria**: Zero failures.

---

#### 1.2 Standardize Configuration Files
```bash
cd spine-launchpad
uv run python -m scripts util standardize --dry-run
# If changes look good:
uv run python -m scripts util standardize
```

---

#### 1.3 Documentation Structure Check

**Verify docs/ directory has**:
```
spine-core/docs/
├── index.md                    # Landing page
├── CHANGELOG.md               # Version history ✅
├── FEATURES.md                # Feature history ✅
├── architecture/              # System design
├── api/                       # API documentation
├── design/                    # Design documents
└── tutorials/                 # Usage tutorials
```

**Check for stray markdown files**:
```bash
# Should only find README.md in root
Get-ChildItem .\spine-core\*.md -Name
```

---

### Phase 2: Code Quality & Testing 🧪

#### 2.1 Comprehensive Audit
```bash
cd spine-launchpad
uv run python -m scripts audit ecosystem --export exports/spine-core-audit.json
```

---

#### 2.2 Test Coverage Analysis
```bash
cd spine-launchpad
uv run python -m scripts audit tests --project spine-core
```

**Requirements**:
- **Minimum**: 80% coverage (higher bar for shared framework)
- **Target**: 90%+ coverage
- All public APIs must have tests

---

#### 2.3 Code Quality Check
```bash
cd spine-launchpad
uv run python -m scripts audit quality --project spine-core
```

---

#### 2.4 Run Test Suite
```bash
cd spine-core
uv run pytest tests/ -v --tb=short
```

**Success Criteria**: 100% tests passing.

---

#### 2.5 Dependency Impact Check

**CRITICAL for spine-core**: Check downstream compatibility

```bash
# Test that feedspine works with spine-core changes
cd feedspine
uv run pytest tests/ -v --tb=short

# Test that entityspine works with spine-core changes  
cd ../entityspine
uv run pytest tests/ -v --tb=short
```

---

### Phase 3: Documentation Generation 📚

#### 3.1 Generate Changelog
```bash
cd spine-launchpad
uv run python -m scripts util changelog --project spine-core --output ../spine-core/docs/CHANGELOG.md
```

---

#### 3.2 Generate Feature Documentation
```bash
cd spine-launchpad
uv run python -m scripts util features spine-core --output ../spine-core/docs/FEATURES_AUTO.md
```

---

#### 3.3 Extract and Review TODOs
```bash
cd spine-launchpad
uv run python -m scripts audit todos --project spine-core
```

---

### Phase 4: Pre-Release Verification ✅

#### 4.1 Git Status Check
```bash
cd spine-core
git status
```

**Verify**:
- No uncommitted changes
- No merge conflicts
- On correct branch

---

#### 4.2 Build Verification
```bash
cd spine-core
uv build
```

**Success Criteria**: Clean build with no errors.

---

#### 4.3 Quick Health Check
```bash
cd spine-launchpad
uv run python -m scripts quick health
```

---

#### 4.4 Release Readiness Check
```bash
cd spine-launchpad
uv run python -m scripts release check spine-core --verbose --tests --build
```

---

### Phase 5: Manual Checks 👁️

#### 5.1 No Stray Files
- ✅ No `.md` files in project root (except README.md)
- ✅ No test files in `src/` directories
- ✅ No `__pycache__` or `.pyc` files committed
- ✅ No `.env` or secret files

#### 5.2 Documentation Review
- ✅ README.md is clear and up-to-date
- ✅ All public APIs documented
- ✅ Type hints comprehensive
- ✅ Docstrings follow standards

#### 5.3 API Stability Check
- ✅ No unintentional breaking changes
- ✅ Deprecated features marked
- ✅ Migration path documented for any breaking changes

#### 5.4 Security Check
- ✅ No hardcoded credentials
- ✅ No security vulnerabilities in dependencies

#### 5.5 License & Attribution
- ✅ LICENSE file exists
- ✅ Copyright notices correct

---

## One-Command Pre-Release

```bash
# Complete workflow (recommended)
cd spine-launchpad
uv run python -m scripts util pre-release --projects spine-core --export pre-release-spine-core.json

# With tests and build verification
uv run python -m scripts release prep spine-core
```

---

## Success Criteria

### Must Have ✅
- [ ] All tests passing (100%)
- [ ] No critical code quality issues
- [ ] Clean build (no errors)
- [ ] CHANGELOG.md updated
- [ ] README.md accurate
- [ ] No secrets or credentials
- [ ] LICENSE file present
- [ ] All dependent projects still pass tests

### Should Have 🎯
- [ ] Test coverage ≥80%
- [ ] All public APIs documented
- [ ] Type hints on all public functions
- [ ] No deprecation warnings unaddressed

### Nice to Have 💎
- [ ] FEATURES.md comprehensive
- [ ] Architecture diagrams current
- [ ] Performance benchmarks documented

---

## spine-core-Specific Concerns

### Breaking Changes
- [ ] No unannounced breaking changes to public API
- [ ] If breaking changes: documented in CHANGELOG
- [ ] If breaking changes: version bumped appropriately (major)

### Type Safety
- [ ] All public interfaces have type hints
- [ ] Generic types properly constrained
- [ ] Protocol/ABC definitions complete

### Performance
- [ ] No performance regressions in hot paths
- [ ] Memory usage reasonable
- [ ] No resource leaks

### Compatibility
- [ ] Python 3.12+ compatibility verified
- [ ] All dependencies have compatible versions
- [ ] No circular import issues

---

## Downstream Impact Testing

Before releasing spine-core, verify all dependent projects:

```bash
# Run all downstream tests
cd feedspine && uv run pytest tests/ -v
cd ../entityspine && uv run pytest tests/ -v
cd ../genai-spine && uv run pytest tests/ -v
cd ../capture-spine && uv run pytest tests/ -v
```

If any downstream project fails, **DO NOT RELEASE** until resolved.

---

## Rollback Plan

If issues are found after push:
1. **Minor issues**: Create GitHub issue, fix in next commit
2. **Major issues**: Revert commit immediately, notify dependent project maintainers
3. **Critical issues**: Unpublish, revert, coordinate with all dependent projects

---

## Related Documents

- [spine-launchpad/PRE_RELEASE_WORKFLOW.md](../../spine-launchpad/PRE_RELEASE_WORKFLOW.md) - Master workflow
- [spine-launchpad/CLI_QUICK_REFERENCE.md](../../spine-launchpad/CLI_QUICK_REFERENCE.md) - CLI commands
- [FEATURES.md](./FEATURES.md) - Feature history
- [CHANGELOG.md](./CHANGELOG.md) - Version history

---

**Remember**: spine-core changes ripple through the entire ecosystem. Extra care required! 🚀
