# Contributing to Market Spine

Thank you for your interest in contributing to Market Spine!

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Clone and Install

```bash
git clone <repository-url>
cd spine-core/market-spine-basic
uv sync
```

### Verify Installation

```bash
uv run pytest tests/
uv run spine --help
```

## Code Quality

### Formatting

We use [ruff](https://docs.astral.sh/ruff/) for code formatting and linting.

```bash
# Format all code
uv run ruff format .

# Check for lint errors
uv run ruff check .

# Auto-fix lint errors
uv run ruff check --fix .
```

### Pre-commit Hooks

Install pre-commit hooks to run checks automatically:

```bash
uv run pre-commit install
```

Hooks run:
- `ruff` formatter and linter
- Trailing whitespace removal
- YAML syntax check
- Basic pytest check

### Type Checking

```bash
uv run pyright
```

## Testing

### Running Tests

```bash
# All tests
uv run pytest tests/

# Specific file
uv run pytest tests/test_param_validation.py

# With coverage
uv run pytest tests/ --cov=market_spine --cov=spine

# Verbose output
uv run pytest tests/ -v
```

### Test Structure

```
tests/
├── domains/otc/          # Domain-specific tests
│   └── test_otc.py
├── data_scenarios/       # Data edge case tests
│   └── test_messy_data.py
├── test_dispatcher.py    # Dispatcher tests
├── test_pipelines.py     # Pipeline tests
├── test_param_validation.py  # Parameter validation
├── test_error_handling.py    # Error classification
└── test_registry.py      # Registry tests
```

### Writing Tests

Follow these conventions:

```python
"""Tests for feature X."""

import pytest

from spine.framework.some_module import SomeClass


class TestSomeClass:
    """Tests for SomeClass."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test."""
        # Initialize resources
        pass

    def test_some_feature(self):
        """Test that some_feature works correctly."""
        result = SomeClass().some_feature()
        assert result == expected_value
```

## Project Structure

```
market-spine-basic/
├── src/market_spine/
│   ├── cli.py           # CLI entry points
│   ├── config.py        # Configuration
│   └── db.py            # Database utilities
├── tests/               # Test suite
├── docs/                # Documentation
│   └── CLI.md           # CLI reference
└── pyproject.toml       # Project config

packages/
├── spine-core/          # Core framework
│   └── src/spine/
│       ├── core/        # Core utilities
│       └── framework/   # Framework components
│           ├── dispatcher.py
│           ├── runner.py
│           ├── registry.py
│           ├── params.py       # Parameter validation
│           ├── exceptions.py   # Exception types
│           └── pipelines/
│               └── base.py
└── spine-domains/       # Domain implementations
    └── src/spine/domains/finra/otc_transparency/
        ├── schema.py
        ├── connector.py
        ├── normalizer.py
        ├── calculations.py
        └── pipelines.py
```

## Adding a New Domain

1. Create package structure:
   ```
   packages/spine-domains/src/spine/domains/your_domain/
   ├── __init__.py
   ├── schema.py        # Constants, enums, table definitions
   ├── connector.py     # Data fetching/parsing
   ├── normalizer.py    # Data transformation
   ├── calculations.py  # Business logic
   └── pipelines.py     # Pipeline definitions
   ```

2. Define pipelines with specs:
   ```python
   from spine.framework.params import ParamDef, PipelineSpec, date_format
   from spine.framework.pipelines import Pipeline, PipelineResult
   from spine.framework.registry import register_pipeline

   @register_pipeline("your_domain.some_pipeline")
   class SomePipeline(Pipeline):
       name = "your_domain.some_pipeline"
       description = "Does something useful"
       spec = PipelineSpec(
           required_params={
               "date": ParamDef(
                   name="date",
                   type=str,
                   description="Processing date",
                   validator=date_format,
               ),
           },
       )

       def run(self) -> PipelineResult:
           # Implementation
           ...
   ```

3. Register in `__init__.py`:
   ```python
   from your_domain import pipelines  # noqa: F401 - registers pipelines
   ```

## Pull Request Process

1. Create a feature branch
2. Make changes with tests
3. Run `uv run ruff format .` and `uv run ruff check .`
4. Run `uv run pytest tests/`
5. Update documentation if needed
6. Submit PR with clear description

## Commit Messages

Use conventional commits:

```
feat: add new verify command
fix: correct error message for missing params
docs: update CLI reference
test: add parameter validation tests
refactor: simplify dispatcher logic
```

## Questions?

Open an issue for questions or discussions.
