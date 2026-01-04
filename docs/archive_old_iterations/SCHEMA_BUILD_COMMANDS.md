# Schema Build Commands — Quick Reference

## Building Schema from Modules

After editing schema module files, rebuild the combined schema:

### Using Python Directly
```bash
python scripts/build_schema.py
```

### Using Make (Unix/macOS)
```bash
make schema-build
```

### Using Just (Cross-platform)
**Note:** `just` is a separate tool (not a Python package) that must be installed first.

**Install just:**
- Windows: `scoop install just` or `choco install just`
- macOS: `brew install just`
- Linux: `cargo install just`
- Or download from: https://github.com/casey/just

```bash
just schema-build
```

### Using Docker Compose
```bash
cd market-spine-basic
docker compose --profile schema run --rm schema-build
```

---

## Full Development Workflow

### 1. Edit Schema Module
```bash
# Edit the appropriate module file
vim packages/spine-core/src/spine/core/schema/00_core.sql
# OR
vim packages/spine-domains/src/spine/domains/finra/otc_transparency/schema/00_tables.sql
```

### 2. Rebuild Combined Schema
```bash
just schema-build
# Output: market-spine-basic/migrations/schema.sql
```

### 3. Validate Changes
```bash
pytest tests/test_schema_modules.py -v
```

### 4. Apply to Database
```bash
just db-reset  # Reset and reinitialize
# OR manually
spine db reset --yes
spine db init
```

### 5. Commit Both Files
```bash
git add packages/*/src/*/schema/*.sql
git add market-spine-basic/migrations/schema.sql
git commit -m "feat(schema): Add new table"
```

---

## Available Commands

### Makefile (Unix/macOS)
| Command | Description |
|---------|-------------|
| `make schema-build` | Build schema from modules |
| `make install` | Install package |
| `make dev` | Install with dev dependencies |
| `make test` | Run tests |
| `make lint` | Run linter |
| `make format` | Format code |
| `make check` | Run all checks |

### Justfile (All Platforms)
| Command | Description |
|---------|-------------|
| `just schema-build` | Build schema from modules |
| `just db-init` | Initialize database |
| `just db-reset` | Reset and reinitialize database |
| `just test` | Run tests |
| `just coverage` | Run tests with coverage |
| `just lint` | Run linter |
| `just format` | Format code |
| `just check` | Run all checks |

### Docker Compose
| Command | Description |
|---------|-------------|
| `docker compose --profile schema run --rm schema-build` | Build schema from modules |
| `docker compose build` | Build Docker image |
| `docker compose run --rm db-init` | Initialize database |
| `docker compose up api` | Start API server (http://localhost:8000) |
| `docker compose up -d api` | Start API server in background |
| `docker compose run --rm spine spine run <pipeline>` | Run pipeline |

---

## Docker Workflow

### First-Time Setup
```bash
cd market-spine-basic

# Build the image
docker compose build

# Initialize database
docker compose run --rm db-init
```

### Running the API Server
```bash
# Start API (foreground)
docker compose up api

# Or start in background
docker compose up -d api

# View logs
docker compose logs -f api

# Stop
docker compose down
```

**API Endpoints:**
- **Swagger UI:** http://localhost:8000/docs
- **Health:** http://localhost:8000/health
- **Capabilities:** http://localhost:8000/capabilities
- **List Pipelines:** http://localhost:8000/pipelines

### Running Pipelines
```bash
# Run a pipeline
docker compose run --rm spine spine run finra.otc_transparency.ingest_week \
  -p week_ending=2025-12-26 \
  -p tier=NMS_TIER_1 \
  -p file_path=/app/data/fixtures/otc/week_2025-12-26.psv

# List available pipelines
docker compose run --rm spine spine list

# Check status
docker compose run --rm spine spine status
```

### Development with Docker
```bash
# Build schema (if you edited module files)
docker compose --profile schema run --rm schema-build

# Rebuild image after schema changes
docker compose build

# Reset database
docker compose run --rm spine spine db reset --yes
docker compose run --rm db-init
```

---

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Build Schema
  run: python scripts/build_schema.py

- name: Validate Schema Modules
  run: pytest tests/test_schema_modules.py -v

- name: Check for Schema Changes
  run: |
    if git diff --exit-code market-spine-basic/migrations/schema.sql; then
      echo "✅ Schema is up to date"
    else
      echo "❌ Schema out of sync with modules"
      echo "Run: python scripts/build_schema.py"
      exit 1
    fi
```

### Pre-commit Hook
Add to `.git/hooks/pre-commit`:
```bash
#!/bin/bash
# Ensure schema is up to date
python scripts/build_schema.py
git add market-spine-basic/migrations/schema.sql
```

---

## Troubleshooting

### Schema not updating?
```bash
# Check module files exist
ls -la packages/spine-core/src/spine/core/schema/
ls -la packages/spine-domains/src/spine/domains/*/schema/

# Rebuild with verbose output
python scripts/build_schema.py

# Validate modules
pytest tests/test_schema_modules.py -v
```

### Database out of sync?
```bash
# Reset database
just db-reset

# OR manually
spine db reset --yes
spine db init
```

### Docker build failing?
```bash
# Ensure schema is built before Docker build
just schema-build

# Then build Docker image
docker compose build
```

---

## See Also

- [Schema Module Architecture Guide](docs/architecture/SCHEMA_MODULE_ARCHITECTURE.md)
- [Schema Refactoring Summary](SCHEMA_REFACTORING_COMPLETE.md)
- [Institutional Hardening Documentation](docs/ops/INSTITUTIONAL_HARDENING_SUMMARY.md)
