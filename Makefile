.PHONY: install test lint format clean build docs help

# Default target
help:
	@echo "spine-core development commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install     Install dependencies with uv"
	@echo "  test        Run tests (excluding slow tests)"
	@echo "  test-all    Run all tests including slow tests"
	@echo "  test-cov    Run tests with coverage report"
	@echo "  lint        Run ruff linter"
	@echo "  format      Format code with ruff"
	@echo "  check       Run all checks (lint + test)"
	@echo "  build       Build package"
	@echo "  clean       Remove build artifacts"
	@echo "  docs        Build documentation"

# Install dependencies
install:
	uv sync --dev

# Run tests (excluding slow tests - default)
test:
	uv run pytest -q

# Run all tests including slow tests
test-all:
	uv run pytest -m "" --timeout=30

# Run tests with coverage
test-cov:
	uv run pytest --cov=src/spine --cov-report=html --cov-report=term

# Run linter
lint:
	uv run ruff check .
	uv run ruff format --check .

# Format code
format:
	uv run ruff check --fix .
	uv run ruff format .

# Run all checks
check: lint test

# Build package
build:
	uv build

# Clean build artifacts
clean:
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Build documentation (if mkdocs is configured)
docs:
	uv run mkdocs build
