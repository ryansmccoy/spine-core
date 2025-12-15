.PHONY: install test lint format clean build docs help up down up-standard up-full logs ps

# Default target
help:
	@echo "spine-core development commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Development:"
	@echo "  install       Install dependencies with uv"
	@echo "  test          Run tests (excluding slow tests)"
	@echo "  test-all      Run all tests including slow tests"
	@echo "  test-cov      Run tests with coverage report"
	@echo "  lint          Run ruff linter"
	@echo "  format        Format code with ruff"
	@echo "  check         Run all checks (lint + test)"
	@echo "  build         Build package"
	@echo "  clean         Remove build artifacts"
	@echo "  docs          Build documentation"
	@echo ""
	@echo "Docker (Tiered Architecture):"
	@echo "  up            Tier 1: API + Frontend (SQLite)"
	@echo "  up-standard   Tier 2: + PostgreSQL + Worker + Docs"
	@echo "  up-full       Tier 3: + Redis + Celery + Monitoring"
	@echo "  down          Stop all containers"
	@echo "  logs          Tail container logs"
	@echo "  ps            Show running containers"
	@echo "  rebuild       Rebuild and restart all images"

# Install dependencies
install:
	uv sync --dev

# Run tests (excluding slow tests - default)
test:
	uv run pytest -q

# Run all tests including slow tests
test-all:
	uv run pytest -m "" --timeout=30
	cd frontend && npm run build

# Run scenario-driven tests only (all 3 layers)
test-scenarios:
	uv run pytest tests/workflow/ tests/api/ -v

# Run frontend E2E tests (requires running backend + frontend)
test-e2e:
	cd frontend && npx playwright test --reporter=line

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

# Build documentation
docs:
	@echo "Documentation is in docs/ directory"
	@echo "To serve locally: uv run mkdocs serve (requires mkdocs)"

# ====================================================================
# Docker — Tiered Architecture
# ====================================================================
# Compose file: docker/compose.yml (included via root docker-compose.yml)

COMPOSE = docker compose -f docker/compose.yml

# Tier 1: Minimal — API + Frontend with SQLite (zero dependencies)
up:
	$(COMPOSE) up -d --build
	@echo ""
	@echo "✓ Tier 1 (Minimal) running:"
	@echo "  API:      http://localhost:12000"
	@echo "  Frontend: http://localhost:12001"
	@echo "  Swagger:  http://localhost:12000/api/v1/docs"

# Tier 2: Standard — + PostgreSQL + Worker + Docs
up-standard:
	SPINE_DATABASE_URL=postgresql://spine:spine@postgres:5432/spine \
	$(COMPOSE) --profile standard up -d --build
	@echo ""
	@echo "✓ Tier 2 (Standard) running:"
	@echo "  API:      http://localhost:12000"
	@echo "  Frontend: http://localhost:12001"
	@echo "  Docs:     http://localhost:12002"
	@echo "  Postgres: localhost:10432"
	@echo "  Worker:   background (poll-based)"
	@echo "  Swagger:  http://localhost:12000/api/v1/docs"

# Tier 3: Full — + Redis + Celery + Prometheus + Grafana
up-full:
	SPINE_DATABASE_URL=postgresql://spine:spine@timescaledb:5432/spine \
	SPINE_REDIS_URL=redis://redis:6379/0 \
	SPINE_CELERY_BROKER_URL=redis://redis:6379/1 \
	$(COMPOSE) --profile full up -d --build
	@echo ""
	@echo "✓ Tier 3 (Full) running:"
	@echo "  API:        http://localhost:12000"
	@echo "  Frontend:   http://localhost:12001"
	@echo "  Docs:       http://localhost:12002"
	@echo "  TimescaleDB:localhost:10432"
	@echo "  Redis:      localhost:10379"
	@echo "  Prometheus: http://localhost:12500"
	@echo "  Grafana:    http://localhost:12501"
	@echo "  Swagger:    http://localhost:12000/api/v1/docs"

# Stop everything
down:
	$(COMPOSE) --profile standard --profile full --profile dev down

# Tail logs
logs:
	$(COMPOSE) --profile standard --profile full logs -f --tail=50

# Show running containers
ps:
	$(COMPOSE) --profile standard --profile full ps

# Rebuild images (no cache)
rebuild:
	$(COMPOSE) --profile standard --profile full build --no-cache
	$(COMPOSE) --profile standard --profile full up -d
