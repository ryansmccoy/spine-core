# Market Spine Basic

A minimal, CLI-driven analytics pipeline system for market data. This is the **Basic tier** of Market Spine, using SQLite and synchronous execution.

## What is this?

Market Spine Basic is a teaching tool and reference implementation for data pipelines. It demonstrates:

- **Structured logging** with tracing and timing
- **Idempotent pipelines** with manifest tracking
- **Data lineage** via `execution_id`, `batch_id`, `capture_id`
- **Domain separation** (business logic vs. infrastructure)
- **CLI + API parity** (same operations available via both interfaces)

This project uses **uv** for fast, reliable Python package management.

---

## Quick Start

```bash
# Install uv (if not installed)
# Windows: powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# Unix: curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
cd market-spine-basic
uv sync

# Initialize database
uv run spine db init

# Run a pipeline (using fixture data)
uv run spine run run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1 \
  --file data/fixtures/otc/week_2025-12-26.psv

# Normalize the ingested data
uv run spine run run finra.otc_transparency.normalize_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1

# Query results
uv run spine query weeks --tier NMS_TIER_1
uv run spine query symbols --tier NMS_TIER_1 --week 2025-12-26

# List available pipelines
uv run spine pipelines list

# Start API server
uv run uvicorn market_spine.api.app:app --host 0.0.0.0 --port 8000 --reload

# Run smoke test (validates CLI + API)
uv run python scripts/smoke_test.py
```

---

## Project Structure

```
market-spine-basic/
├── src/market_spine/
│   ├── app/                    # Application layer
│   │   ├── commands/           # Command pattern (executions, queries, pipelines)
│   │   ├── services/           # Business services (tier, params, ingest)
│   │   └── models.py           # Dataclasses (NOT Pydantic)
│   │
│   ├── cli/                    # CLI layer (Typer)
│   │   ├── commands/           # CLI command groups (run, query, verify, etc.)
│   │   ├── interactive/        # Interactive mode (questionary)
│   │   ├── params.py           # CLI parameter parsing
│   │   └── console.py          # Rich console helpers
│   │
│   ├── api/                    # API layer (FastAPI)
│   │   └── routes/v1/          # Versioned API routes
│   │
│   ├── config.py               # Environment configuration
│   └── db.py                   # SQLite connection provider
│
├── data/
│   └── fixtures/otc/           # Test fixture files (synthetic FINRA data)
│
├── scripts/
│   └── smoke_test.py           # End-to-end smoke test
│
├── tests/                      # Test suite (95+ tests)
├── docs/                       # Documentation
└── pyproject.toml
```

---

## Architecture

### Layer Responsibilities

| Layer | Package | Responsibility |
|-------|---------|----------------|
| **CLI** | `market_spine.cli` | Parse arguments, render output |
| **API** | `market_spine.api` | HTTP routing, Pydantic serialization |
| **Commands** | `market_spine.app.commands` | Orchestrate operations |
| **Services** | `market_spine.app.services` | Business logic (tier normalization, etc.) |
| **Framework** | `spine.framework` | Execution, dispatch, registry |
| **Domain** | `spine.domains.*` | Pure business logic, calculations |
| **Core** | `spine.core` | Primitives (manifest, rejects, quality) |

### Key Design Decisions

1. **CLI ↔ API Parity**: Both use the same Command layer
2. **Pydantic at Boundary Only**: API uses Pydantic; internal code uses dataclasses
3. **ParamParser vs ParameterResolver**:
   - `cli/params.py` → Parses CLI arguments into raw dict
   - `app/services/params.py` → Normalizes values (e.g., tier aliases)
4. **Interactive Mode**: Uses `subprocess.run()` to shell out to CLI commands (intentional design for process isolation)

---

## CLI Commands

### Pipeline Operations

```bash
# List all pipelines
uv run spine pipelines list

# Describe a pipeline (show parameters)
uv run spine pipelines describe finra.otc_transparency.ingest_week

# Run a pipeline
uv run spine run run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-26 \
  --tier NMS_TIER_1 \
  --file data/fixtures/otc/week_2025-12-26.psv

# Dry run (validate without executing)
uv run spine run run finra.otc_transparency.ingest_week \
  --week-ending 2025-12-26 \
  --tier tier1 \
  --file data/fixtures/otc/week_2025-12-26.psv \
  --dry-run
```

### Query Commands

```bash
# List processed weeks
uv run spine query weeks --tier NMS_TIER_1

# Top symbols by volume
uv run spine query symbols --tier NMS_TIER_1 --week 2025-12-26 --top 10
```

### Verification Commands

```bash
# Check table structure
uv run spine verify tables

# Check data counts by tier
uv run spine verify data --tier NMS_TIER_1

# Check quality events
uv run spine verify quality
```

### Database Commands

```bash
# Initialize database
uv run spine db init

# Reset database (destructive!)
uv run spine db reset --yes
```

### Health & Diagnostics

```bash
# System health check
uv run spine doctor check

# Show version
uv run spine --version

# Interactive mode
uv run spine ui
```

---

## API Endpoints

Start the server:
```bash
uv run uvicorn market_spine.api:app --reload --port 8000
```

### Discovery

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /v1/capabilities` | Tier capabilities (feature flags) |

### Pipelines

| Endpoint | Description |
|----------|-------------|
| `GET /v1/pipelines` | List all pipelines |
| `GET /v1/pipelines/{name}` | Describe pipeline |
| `POST /v1/pipelines/{name}/run` | Execute pipeline |

### Queries

| Endpoint | Description |
|----------|-------------|
| `GET /v1/query/weeks?tier=...` | List processed weeks |
| `GET /v1/query/symbols?tier=...&week=...` | Top symbols |

### Example API Calls

```bash
# Health check
curl http://localhost:8000/health

# List pipelines
curl http://localhost:8000/v1/pipelines

# Get capabilities
curl http://localhost:8000/v1/capabilities

# Run a pipeline
curl -X POST http://localhost:8000/v1/pipelines/finra.otc_transparency.normalize_week/run \
  -H "Content-Type: application/json" \
  -d '{"params": {"tier": "NMS_TIER_1", "week_ending": "2025-12-26"}}'

# Query weeks
curl "http://localhost:8000/v1/query/weeks?tier=NMS_TIER_1"
```

---

## Pipelines

| Pipeline | Description |
|----------|-------------|
| `finra.otc_transparency.ingest_week` | Parse FINRA PSV file → raw table |
| `finra.otc_transparency.normalize_week` | Validate and normalize → normalized table |
| `finra.otc_transparency.aggregate_week` | Symbol-level aggregation → summary table |
| `finra.otc_transparency.compute_rolling` | Rolling 4-week metrics |
| `finra.otc_transparency.backfill_range` | Batch process date range |

### Tier Values

| Canonical | Aliases |
|-----------|---------|
| `OTC` | `otc` |
| `NMS_TIER_1` | `tier1`, `Tier1`, `nms_tier_1` |
| `NMS_TIER_2` | `tier2`, `Tier2`, `nms_tier_2` |

---

## Configuration

Environment variables (or `.env` file):

| Variable | Default | Description |
|----------|---------|-------------|
| `SPINE_DATABASE_PATH` | `spine.db` | SQLite database path |
| `SPINE_DATA_DIR` | `./data` | Data directory |
| `SPINE_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `SPINE_LOG_FORMAT` | `console` | Log format (`console` or `json`) |

---

## Troubleshooting

### "No data yet" / Empty Results

1. Check if database is initialized: `uv run spine db init`
2. Run ingest pipeline first (with fixture data):
   ```bash
   uv run spine run run finra.otc_transparency.ingest_week \
     --week-ending 2025-12-26 --tier NMS_TIER_1 \
     --file data/fixtures/otc/week_2025-12-26.psv
   ```
3. Verify data exists: `uv run spine verify data`

### Where to Find Logs

- CLI: Logs print to stdout (configurable with `--log-level`)
- API: Logs print to uvicorn console
- JSON format: `--log-format json` or `SPINE_LOG_FORMAT=json`

### Reset Database

```bash
uv run spine db reset --yes
uv run spine db init
```

### Invalid Tier Error

Tier aliases are normalized automatically. Valid inputs:
- `tier1`, `Tier1`, `NMS_TIER_1` → `NMS_TIER_1`
- `tier2`, `Tier2`, `NMS_TIER_2` → `NMS_TIER_2`
- `otc`, `OTC` → `OTC`

---

## Development

### Install Dependencies

```bash
uv sync --group dev
```

### Run Tests

```bash
uv run pytest tests/ -v
```

### Run Smoke Tests

```bash
# Basic smoke test (CLI + API functionality)
uv run python scripts/smoke_test.py

# Cross-domain smoke test (Calendar + FINRA integration)
uv run python scripts/smoke_cross_domain.py
```

#### Smoke Test Details

**Basic Smoke Test** (`scripts/smoke_test.py`):
- Validates core CLI and API functionality
- Tests single-domain FINRA OTC pipelines
- Runs in ~10 seconds with fixture data
- No external dependencies required

**Cross-Domain Smoke Test** (`scripts/smoke_cross_domain.py`):
- Validates cross-domain dependency handling
- Tests Exchange Calendar + FINRA OTC integration
- Covers three scenarios:
  1. **Basic Cross-Domain**: Calendar ingestion → FINRA → volume per trading day
  2. **Year-Boundary Week**: Week spanning 2025-2026 (loads holidays from both years)
  3. **As-Of Dependency**: Pinned calendar_capture_id for deterministic replay
- Runs in ~15 seconds with fixture data
- Uses temporary database (no side effects)

**Expected Outputs**:
```
=== Scenario 1: Basic Cross-Domain Dependency ===
✓ Calendar ingested
✓ FINRA data ingested
✓ Symbol aggregate completed
✓ Volume per trading day completed
✓ Calendar: 10 holidays
✓ FINRA raw: 50 rows
✓ Symbol aggregates: 5 symbols
✓ Scenario 1: PASSED

=== Scenario 2: Year-Boundary Week Handling ===
✓ Both calendars ingested
✓ Calendars: 2025 (10 holidays), 2026 (10 holidays)
✓ Scenario 2: PASSED

=== Scenario 3: As-Of Dependency Mode ===
✓ Capture ID v1: cal_20260104_123456
✓ Volume per day with pinned capture_id completed
✓ Scenario 3: PASSED

=== Summary ===
  Scenario 1: Basic Cross-Domain: PASS
  Scenario 2: Year-Boundary Week: PASS
  Scenario 3: As-Of Dependency: PASS

All 3 cross-domain tests passed!
```

**Troubleshooting Failures**:

1. **Fixture not found**: Verify `data/fixtures/calendar/` and `data/fixtures/otc/` directories exist
   ```bash
   ls data/fixtures/calendar/holidays_xnys_2025.json
   ls data/fixtures/otc/week_2026-01-02.psv
   ```

2. **Pipeline execution failed**: Check stderr output for specific error
   - Common: Missing dependency (run calendar ingest first)
   - Common: Wrong tier format (use NMS_TIER_1, not tier1)

3. **Database query failed**: Verify database was initialized
   ```bash
   sqlite3 $SPINE_DATABASE_PATH ".tables"
   ```

4. **Integration test timeout**: Increase timeout in `test_smoke_cross_domain_e2e.py` (default: 120s)

**Running as pytest**:
```bash
# Run cross-domain smoke test via pytest wrapper
uv run pytest tests/test_smoke_cross_domain_e2e.py -v
```

### Lint and Format

```bash
uv run ruff check src tests
uv run ruff format src tests
```

### Type Check

```bash
uv run mypy src/
```

---

## See Also

- [Repository README](../README.md) — Full architecture overview
- [spine-core](../packages/spine-core/README.md) — Platform primitives
- [spine-domains](../packages/spine-domains/README.md) — Domain logic
- [Architecture Map](docs/01-architecture-map.md) — Runtime call paths
- [API Docs](http://localhost:8000/docs) — OpenAPI documentation (when server running)

---

## License

MIT

