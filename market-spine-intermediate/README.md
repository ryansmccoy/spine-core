# Market Spine Intermediate

Analytics pipeline system with FastAPI, PostgreSQL, and background worker.

## Features

- FastAPI REST API (enqueue-only)
- PostgreSQL database
- LocalBackend with background worker thread
- Docker Compose for local development
- Execution events tracking

## Quick Start

```bash
# Start services
docker compose up -d

# Or run locally with uv
uv venv && .venv\Scripts\activate
uv pip install -e ".[dev]"

# Set database URL
export DATABASE_URL=postgresql://spine:spine_dev@localhost:5432/market_spine

# Run migrations
spine db init

# Start API server
spine api start

# Start worker (in another terminal)
spine worker start
```

## API Usage

```bash
# Submit a pipeline execution
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d '{"pipeline": "otc_full_refresh"}'

# Check execution status
curl http://localhost:8000/api/v1/executions/{execution_id}

# Query daily metrics
curl "http://localhost:8000/api/v1/otc/metrics/daily?symbol=ACME"

# Health check
curl http://localhost:8000/api/v1/health
```

## CLI Commands

```bash
spine db init          # Run migrations
spine db reset         # Reset database
spine api start        # Start FastAPI server
spine worker start     # Start background worker
spine run <pipeline>   # Submit pipeline via CLI
spine list             # List pipelines
spine query metrics    # Query metrics
spine shell            # Interactive REPL
```

## Project Structure

```
market-spine-intermediate/
├── docker-compose.yml
├── Dockerfile
├── migrations/
├── src/market_spine/
│   ├── api/              # FastAPI routes
│   ├── orchestration/    # Backend protocol + LocalBackend
│   ├── pipelines/        # Pipeline definitions
│   ├── repositories/     # Data access layer
│   └── services/         # Business logic
└── tests/
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | PostgreSQL connection URL |
| `BACKEND_TYPE` | `local` | Orchestration backend |
| `WORKER_POLL_INTERVAL` | `0.5` | Worker poll interval (seconds) |
| `WORKER_MAX_CONCURRENT` | `4` | Max concurrent executions |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `console` | `console` or `json` |

## License

MIT
(market-spine-basic) PS C:\projects\spine-core\market-spine-intermediate> .venv\Scripts\python.exe -m pytest tests/ -v --no-header
=========================================================================== test session starts ============================================================================
collected 30 items                                                                                                                                                          

tests/test_api.py::TestHealthEndpoints::test_health_response_format PASSED                                                                                            [  3%] 
tests/test_api.py::TestHealthEndpoints::test_readiness_response_format PASSED                                                                                         [  6%] 
tests/test_api.py::TestExecutionEndpointSchemas::test_execution_create_schema PASSED                                                                                  [ 10%]
tests/test_api.py::TestExecutionEndpointSchemas::test_execution_create_defaults PASSED                                                                                [ 13%] 
tests/test_api.py::TestOTCEndpointSchemas::test_trade_response_schema PASSED                                                                                          [ 16%] 
tests/test_api.py::TestOTCEndpointSchemas::test_daily_metrics_response_schema PASSED                                                                                  [ 20%] 
tests/test_dispatcher.py::TestOrchestratorBackendProtocol::test_mock_backend_implements_protocol PASSED                                                               [ 23%] 
tests/test_dispatcher.py::TestOrchestratorBackendProtocol::test_submit_returns_run_id PASSED                                                                          [ 26%] 
tests/test_dispatcher.py::TestOrchestratorBackendProtocol::test_cancel_returns_bool PASSED                                                                            [ 30%] 
tests/test_dispatcher.py::TestOrchestratorBackendProtocol::test_health_returns_dict PASSED                                                                            [ 33%] 
tests/test_dispatcher.py::TestDispatcherLogic::test_logical_key_format PASSED                                                                                         [ 36%] 
tests/test_dispatcher.py::TestDispatcherLogic::test_logical_key_uniqueness PASSED                                                                                     [ 40%] 
tests/test_metrics.py::TestVWAPCalculation::test_vwap_single_trade PASSED                                                                                             [ 43%] 
tests/test_metrics.py::TestVWAPCalculation::test_vwap_multiple_trades PASSED                                                                                          [ 46%] 
tests/test_metrics.py::TestVWAPCalculation::test_vwap_weighted_by_volume PASSED                                                                                       [ 50%] 
tests/test_metrics.py::TestMetricsAggregation::test_high_low_calculation PASSED                                                                                       [ 53%] 
tests/test_metrics.py::TestMetricsAggregation::test_trade_count PASSED                                                                                                [ 56%] 
tests/test_metrics.py::TestMetricsAggregation::test_total_volume PASSED                                                                                               [ 60%] 
tests/test_metrics.py::TestMetricsAggregation::test_total_notional PASSED                                                                                             [ 63%] 
tests/test_normalizer.py::TestOTCNormalizer::test_parse_date_iso_format PASSED                                                                                        [ 66%] 
tests/test_normalizer.py::TestOTCNormalizer::test_parse_date_us_format PASSED                                                                                         [ 70%]
tests/test_normalizer.py::TestOTCNormalizer::test_parse_date_datetime_object PASSED                                                                                   [ 73%] 
tests/test_normalizer.py::TestOTCNormalizer::test_parse_date_invalid PASSED                                                                                           [ 76%] 
tests/test_normalizer.py::TestOTCNormalizer::test_parse_decimal_string PASSED                                                                                         [ 80%] 
tests/test_normalizer.py::TestOTCNormalizer::test_parse_decimal_with_commas PASSED                                                                                    [ 83%] 
tests/test_normalizer.py::TestOTCNormalizer::test_parse_decimal_float PASSED                                                                                          [ 86%] 
tests/test_normalizer.py::TestOTCNormalizer::test_normalize_trade_valid PASSED                                                                                        [ 90%] 
tests/test_normalizer.py::TestOTCNormalizer::test_normalize_trade_missing_required_field PASSED                                                                       [ 93%] 
tests/test_normalizer.py::TestOTCNormalizer::test_normalize_trade_invalid_price PASSED                                                                                [ 96%] 
tests/test_normalizer.py::TestOTCNormalizer::test_normalize_trade_short_side_codes PASSED                                                                             [100%] 

============================================================================ 30 passed in 0.55s ============================================================================ 
(market-spine-basic) PS C:\projects\spine-core\market-spine-intermediate> .venv\Scripts\spine.exe --version
2026-01-02 01:42:34 [debug    ] pipeline_registered            name=otc.ingest
2026-01-02 01:42:34 [debug    ] pipeline_registered            name=otc.normalize
2026-01-02 01:42:34 [debug    ] pipeline_registered            name=otc.compute
2026-01-02 01:42:34 [debug    ] pipeline_registered            name=otc.full_refresh
2026-01-02 01:42:34 [info     ] default_pipelines_registered   count=4
spine, version 0.2.0
(market-spine-basic) PS C:\projects\spine-core\market-spine-intermediate> .venv\Scripts\spine.exe pipeline list
2026-01-02 01:42:38 [debug    ] pipeline_registered            name=otc.ingest
2026-01-02 01:42:38 [debug    ] pipeline_registered            name=otc.normalize
2026-01-02 01:42:38 [debug    ] pipeline_registered            name=otc.compute
2026-01-02 01:42:38 [debug    ] pipeline_registered            name=otc.full_refresh
2026-01-02 01:42:38 [info     ] default_pipelines_registered   count=4

Available Pipelines:
------------------------------------------------------------
  otc.ingest                Ingest OTC trades from CSV into bronze layer
  otc.normalize             Normalize raw OTC trades (bronze -> silver)
  otc.compute               Compute OTC daily metrics (silver -> gold)
  otc.full_refresh          Full OTC data refresh (ingest + normalize + compute)
