# Installation

## Requirements

- **Python 3.12+** (3.13 also supported)
- No required runtime dependencies — spine-core is zero-dependency by default

## Install from PyPI

```bash
pip install spine-core
```

Or with [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv add spine-core
```

## Optional Extras

spine-core ships optional extras for specific backends and integrations:

| Extra | What it adds | Install command |
|-------|-------------|-----------------|
| `settings` | Pydantic Settings support | `pip install spine-core[settings]` |
| `mcp` | Model Context Protocol server | `pip install spine-core[mcp]` |
| `postgresql` | PostgreSQL via psycopg2 | `pip install spine-core[postgresql]` |
| `mysql` | MySQL via mysql-connector-python | `pip install spine-core[mysql]` |
| `db2` | IBM DB2 via ibm-db | `pip install spine-core[db2]` |
| `oracle` | Oracle via oracledb | `pip install spine-core[oracle]` |
| `all` | Everything above | `pip install spine-core[all]` |

## Development Setup

```bash
git clone https://github.com/mccoy-lab/py-sec-edgar.git
cd py-sec-edgar/spine-core
uv sync --dev
```

### Verify the installation

```bash
uv run python -c "from spine.core.result import Ok; print(Ok(42))"
```

### Run tests

```bash
make test          # fast tests (excludes slow/integration)
make test-all      # all tests including slow/integration
make test-cov      # tests with coverage report
```

### Code quality

```bash
make lint          # ruff check
make format        # ruff format
make build         # build wheel
```

## Database Backends

spine-core supports 5 database backends through its dialect system:

| Backend | Dialect | Default? |
|---------|---------|----------|
| SQLite | `SQLiteDialect` | Yes — zero-config, file-based |
| PostgreSQL | `PostgreSQLDialect` | Production recommended |
| MySQL | `MySQLDialect` | Supported |
| IBM DB2 | `DB2Dialect` | Supported |
| Oracle | `OracleDialect` | Supported |

SQLite is used by default for development and testing. Set `DATABASE_URL` to switch backends:

```bash
# PostgreSQL
export DATABASE_URL="postgresql://user:pass@localhost:5432/spine"

# MySQL
export DATABASE_URL="mysql://user:pass@localhost:3306/spine"
```

## Docker

Pre-built Docker images are available for serving the API and documentation:

```bash
# API server
docker compose up spine-core

# Documentation site
docker compose up docs
```

See the [Database Architecture](../architecture/DATABASE_ARCHITECTURE.md) guide for multi-tier deployment options.
