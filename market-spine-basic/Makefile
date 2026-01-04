# Makefile for market-spine-basic
# Works on Unix/macOS. For Windows, use the PowerShell commands directly.

.PHONY: help install dev lint format test coverage clean check all schema-build

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install package in editable mode
	pip install -e .

dev:  ## Install with dev dependencies
	pip install -e ".[dev]"
	pre-commit install

lint:  ## Run linter (ruff check)
	ruff check src tests

format:  ## Format code (ruff format)
	ruff format src tests
	ruff check --fix src tests

test:  ## Run tests
	pytest tests/ -v

coverage:  ## Run tests with coverage report
	pytest tests/ --cov=src --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

typecheck:  ## Run type checker (mypy)
	mypy src/

check:  ## Run all checks (lint + typecheck + test)
	ruff check src tests
	mypy src/ --ignore-missing-imports
	pytest tests/ -v

schema-build:  ## Build combined schema from modules
	python ../scripts/build_schema.py

clean:  ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

all: format lint test  ## Format, lint, and test
