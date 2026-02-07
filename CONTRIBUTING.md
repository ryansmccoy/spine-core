# Contributing to spine-core

Thank you for your interest in contributing to spine-core!

## Table of Contents

- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)
- [Architecture Overview](#architecture-overview)

---

## Development Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/mccoy-lab/py-sec-edgar.git
   cd py-sec-edgar/spine-core
   ```

2. Install dependencies with uv:
   ```bash
   uv sync --dev
   ```

3. Verify installation:
   ```bash
   uv run python -c "import spine; print(spine.__version__)"
   ```

---

## Running Tests

### Quick Test Run

```bash
# Run all tests (excluding slow tests)
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/core/test_temporal.py
```

### Full Test Suite

```bash
# Include slow tests
uv run pytest -m ""

# With coverage report
uv run pytest --cov=src/spine --cov-report=html
```

### Test Categories

Tests are organized by markers:

| Marker | Description | Default |
|--------|-------------|---------|
| `unit` | Fast, isolated tests | Included |
| `integration` | Tests with temp files/subprocess | Included |
| `slow` | Long-running tests | **Excluded** |
| `golden` | Fixture-based tests | Included |
| `asyncio` | Async tests | Included |

Run specific categories:
```bash
uv run pytest -m "unit"
uv run pytest -m "integration"
uv run pytest -m "slow"  # Include slow tests
```

---

## Code Style

### Linting

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check for issues
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .

# Check formatting
uv run ruff format --check .

# Auto-format
uv run ruff format .
```

### Style Guidelines

1. **Type Hints**: All public APIs must have type hints
2. **Docstrings**: Use Google-style docstrings for public functions/classes
3. **Line Length**: 100 characters max
4. **Imports**: Use absolute imports, sorted by isort

### Example

```python
from spine.core import ExecutionContext, new_context


def process_data(
    data: list[dict],
    ctx: ExecutionContext | None = None,
) -> dict[str, int]:
    """Process data records and return summary.

    Args:
        data: List of data records to process.
        ctx: Optional execution context for lineage tracking.

    Returns:
        Dictionary with processing summary statistics.

    Raises:
        ValueError: If data is empty.
    """
    if not data:
        raise ValueError("Data cannot be empty")
    
    ctx = ctx or new_context()
    return {"processed": len(data), "execution_id": ctx.execution_id}
```

---

## Pull Request Process

### Branch Strategy

- `master` - Stable releases only
- `dev` - Development branch (target for PRs)
- `feature/*` - Feature branches

### Creating a PR

1. **Create a feature branch** from `dev`:
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/my-feature
   ```

2. **Make your changes** and commit:
   ```bash
   git add .
   git commit -m "feat: add new feature"
   ```

3. **Run tests and linting**:
   ```bash
   uv run pytest
   uv run ruff check .
   uv run ruff format --check .
   ```

4. **Push and create PR**:
   ```bash
   git push origin feature/my-feature
   ```

5. **Target the `dev` branch** in your PR

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Description |
|--------|-------------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `test:` | Adding/updating tests |
| `refactor:` | Code refactoring |
| `chore:` | Maintenance tasks |
| `build:` | Build system changes |

Examples:
```
feat: add circuit breaker to execution framework
fix: correct WeekEnding validation for leap years
docs: update README with quick start guide
test: add integration tests for workflow runner
```

### PR Checklist

- [ ] Tests pass locally
- [ ] Linting passes
- [ ] New code has type hints
- [ ] Public APIs have docstrings
- [ ] CHANGELOG.md updated (for significant changes)

---

## Architecture Overview

### Package Structure

```
src/spine/
├── core/           # Platform primitives (sync-only)
├── execution/      # Unified execution framework
├── orchestration/  # Workflow orchestration
├── framework/      # Application infrastructure
└── observability/  # Logging and metrics
```

### Key Principles

1. **Sync-Only Core**: All core primitives use synchronous APIs
2. **Registry-Driven**: Components register themselves for discovery
3. **Domain Isolation**: Domains extend without modifying core
4. **Protocol-First**: Use protocols for abstraction

### Adding New Features

1. **Core Primitives** (`spine.core`): Domain-agnostic utilities
2. **Execution** (`spine.execution`): Runtime and execution patterns
3. **Orchestration** (`spine.orchestration`): Workflow coordination
4. **Framework** (`spine.framework`): Application-level features

---

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/mccoy-lab/py-sec-edgar/issues)
- **Documentation**: [docs/](./docs/)
- **Examples**: [examples/](./examples/)

---

Thank you for contributing! 🎉
