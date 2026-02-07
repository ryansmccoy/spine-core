# Release Checklist - spine-core v0.1.0

**Target Version:** 0.1.0 (Alpha)  
**Target Date:** February 2026  
**Status:** 🟡 Nearly Ready

---

## Pre-Release Checklist

### 1. Code Quality ✅

- [x] All tests passing (800+ tests)
- [x] Ruff linting passes
- [x] Type hints present (`py.typed` marker)
- [x] No critical TODOs blocking release
- [x] Rate limiter tests marked as `@pytest.mark.slow`

### 2. Package Configuration ✅

- [x] `pyproject.toml` complete
  - [x] Name: `spine-core`
  - [x] Version: `0.1.0`
  - [x] Description present
  - [x] Author: Ryan McCoy
  - [x] License: MIT
  - [x] Python: `>=3.12`
  - [x] Keywords defined
  - [x] Classifiers defined
  - [x] URLs configured
- [x] `py.typed` marker present
- [x] Build system: hatchling

### 3. Documentation

- [x] README.md present
- [x] CHANGELOG.md present (in docs/)
- [x] FEATURES.md present (in docs/)
- [ ] **LICENSE file** ❌ MISSING
- [ ] **CONTRIBUTING.md** ❌ MISSING
- [x] API documentation (in docs/)
- [x] Architecture documentation (in docs/)
- [x] Examples directory

### 4. CI/CD

- [x] GitHub Actions CI workflow (`ci.yml`)
  - [x] Lint job
  - [x] Test job
  - [x] Docker build job
- [ ] **Release workflow** ❌ MISSING (`release.yml`)
- [ ] **Docs workflow** ❌ OPTIONAL (`docs.yml`)

### 5. Git Hygiene

- [ ] Feature branch merged to `dev`
- [ ] `dev` merged to `master`
- [ ] Version tag created (`v0.1.0`)
- [ ] No uncommitted changes

---

## Required Actions

### Critical (Blocking Release)

```bash
# 1. Create LICENSE file
# See template below

# 2. Create CONTRIBUTING.md
# See template below

# 3. Merge branches
git checkout dev
git merge feature/unified-execution-contract
git checkout master
git merge dev

# 4. Tag release
git tag -a v0.1.0 -m "Release v0.1.0 - Initial alpha release"
git push origin master --tags
```

### Recommended (Non-Blocking)

```bash
# 1. Create release workflow for PyPI
# See template below

# 2. Build and test package locally
uv build
uv run twine check dist/*

# 3. Test install from wheel
pip install dist/spine_core-0.1.0-py3-none-any.whl
```

---

## File Templates

### LICENSE (MIT)

```
MIT License

Copyright (c) 2026 Ryan McCoy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### CONTRIBUTING.md

```markdown
# Contributing to spine-core

Thank you for your interest in contributing to spine-core!

## Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/mccoy-lab/py-sec-edgar.git
   cd py-sec-edgar/spine-core
   ```

2. Install dependencies:
   ```bash
   uv sync --dev
   ```

3. Run tests:
   ```bash
   uv run pytest
   ```

4. Run linting:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   ```

## Pull Request Process

1. Create a feature branch from `dev`
2. Make your changes
3. Ensure all tests pass
4. Submit a PR to `dev`

## Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for public APIs
- Add tests for new features
```

### .github/workflows/release.yml

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      
      - name: Build package
        run: uv build
        
      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: |
          uv run pip install twine
          uv run twine upload dist/*
          
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          files: dist/*
          generate_release_notes: true
```

---

## PyPI Publishing Steps

### First-Time Setup

1. Create PyPI account at https://pypi.org/
2. Create API token at https://pypi.org/manage/account/token/
3. Add token to GitHub secrets as `PYPI_TOKEN`

### Manual Publishing (Alternative)

```bash
# Build
uv build

# Check package
uv run pip install twine
uv run twine check dist/*

# Upload to TestPyPI first
uv run twine upload --repository testpypi dist/*

# Test install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ spine-core

# Upload to PyPI
uv run twine upload dist/*
```

---

## Post-Release

- [ ] Verify package on PyPI
- [ ] Test `pip install spine-core`
- [ ] Update documentation links
- [ ] Announce release
- [ ] Create GitHub release with changelog

---

## Version History

| Version | Date | Notes |
|---------|------|-------|
| 0.1.0 | Feb 2026 | Initial alpha release |

---

*Last updated: February 6, 2026*
