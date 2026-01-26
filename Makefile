.PHONY: install lint test docker-basic docker-intermediate docker-full clean

install:
	cd packages/spine-core && uv sync --dev
	cd packages/spine-domains && uv sync --dev

lint:
	cd packages/spine-core && uv run ruff check .
	cd packages/spine-core && uv run ruff format --check .

format:
	cd packages/spine-core && uv run ruff check --fix .
	cd packages/spine-core && uv run ruff format .

test:
	cd packages/spine-core && uv run pytest

# Docker commands
docker-basic:
	docker compose -f docker-compose.basic.yml up -d

docker-intermediate:
	docker compose -f docker-compose.intermediate.yml up -d

docker-full:
	docker compose -f docker-compose.full.yml up -d

docker-down:
	docker compose down

clean:
	rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Generate ecosystem docs
ecosystem:
	cd .. && python scripts/generate_ecosystem_docs.py -o ECOSYSTEM.md

# Extract TODOs
todos:
	cd .. && python scripts/extract_todos.py --project spine-core --output spine-core/docs/TODO.md
