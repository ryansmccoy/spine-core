# Spine Core — Examples

> **144 examples** across **15 categories** — auto-generated from docstrings.
> Regenerate: `python examples/generate_readme.py`

---

## Quick Start

```bash
# Run ALL examples (auto-discovered, isolated subprocesses)
python examples/run_all.py

# Run a single example
python examples/01_core/01_result_pattern.py
```

## Learning Path

Categories are numbered by conceptual dependency — start at `01` and work forward.

| # | Category | Examples | Description |
|---|----------|---------|-------------|
| 01 | `01_core/` | 24 | Core primitives — Result pattern, errors, temporal, quality, idempotency, hashing, tagging. |
| 02 | `02_execution/` | 23 | Execution engine — WorkSpec, handlers, dispatcher, executors, lifecycle, ledger. |
| 03 | `03_resilience/` | 6 | Resilience patterns — Retry, circuit breaker, rate limiting, dead-letter queue. |
| 04 | `04_orchestration/` | 25 | Orchestration — Workflows, step adapters, DAG execution, and YAML specs. |
| 05 | `05_infrastructure/` | 2 | Infrastructure integration — Complete operation with all components wired together. |
| 06 | `06_observability/` | 3 | Observability — Structured logging, metrics collection, context binding. |
| 07 | `07_real_world/` | 5 | Real-world integration — EntitySpine, FeedSpine, and cross-project scenarios. |
| 08 | `08_framework/` | 7 | Framework — Operation building blocks, alerts, connectors, and structured logging. |
| 09 | `09_data_layer/` | 11 | Data layer — Adapters, protocols, DB portability, ORM, migrations. |
| 10 | `10_operations/` | 10 | Operations — Database lifecycle, runs, alerts, sources, processing, schedules, locks, DLQ, quality. |
| 11 | `11_scheduling/` | 5 | Scheduling — Backends, distributed locks, scheduler service. |
| 12 | `12_deploy/` | 12 | Deploy — Container orchestration, testbed runs, compose generation, and result models. |
| 13 | `13_runtimes/` | 4 | Job Engine runtimes --- verbose deep-dive examples for every capability. |
| 13 | `13_workflows/` | 1 | Workflows |
| 14 | `14_golden_workflows/` | 6 | Golden Workflows — end-to-end "golden path" workflow patterns. |

## Examples by Category

### 01_core — Core

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_result_pattern.py](01_core/01_result_pattern.py) | Result Pattern — Explicit Success/Failure Handling Without Exceptions |
| 02 | [02_error_handling.py](01_core/02_error_handling.py) | Error Handling — Structured Error Types with Automatic Retry Decisions |
| 03 | [03_advanced_errors.py](01_core/03_advanced_errors.py) | Advanced Error Handling — SpineError Hierarchy with Result[T] Integration |
| 04 | [04_reject_handling.py](01_core/04_reject_handling.py) | RejectSink — Capturing Validation Failures Without Stopping Operations |
| 05 | [05_temporal_weekending.py](01_core/05_temporal_weekending.py) | WeekEnding — Friday-Anchored Temporal Primitive for Financial Data |
| 06 | [06_temporal_envelope.py](01_core/06_temporal_envelope.py) | Temporal Envelope — PIT-correct timestamp wrappers and bi-temporal records |
| 07 | [07_rolling_windows.py](01_core/07_rolling_windows.py) | RollingWindow — Time-Series Aggregations Over Sliding Periods |
| 08 | [08_watermark_tracking.py](01_core/08_watermark_tracking.py) | Watermark Store — Cursor-based progress tracking for incremental operations |
| 09 | [09_quality_checks.py](01_core/09_quality_checks.py) | Quality Checks — Automated Data Validation Framework |
| 10 | [10_idempotency.py](01_core/10_idempotency.py) | Idempotency — Safe, Re-runnable Data Operations |
| 11 | [11_anomaly_recording.py](01_core/11_anomaly_recording.py) | AnomalyRecorder — Structured Operation Anomaly Tracking and Resolution |
| 12 | [12_content_hashing.py](01_core/12_content_hashing.py) | Hashing — Deterministic Record Hashing for Deduplication |
| 13 | [13_execution_context.py](01_core/13_execution_context.py) | ExecutionContext — Lineage Tracking and Correlation IDs for Data Operations |
| 14 | [14_work_manifest.py](01_core/14_work_manifest.py) | WorkManifest — Multi-Stage Workflow Progress Tracking |
| 15 | [15_backfill_planning.py](01_core/15_backfill_planning.py) | Backfill Plan — Structured backfill planning with checkpoint resume |
| 16 | [16_cache_backends.py](01_core/16_cache_backends.py) | Cache Backends — Tiered Caching with Protocol-Based Swappability |
| 17 | [17_versioned_content.py](01_core/17_versioned_content.py) | Versioned Content — Immutable Version History with Event-Sourcing Semantics |
| 18 | [18_domain_primitives.py](01_core/18_domain_primitives.py) | Enums and Timestamps — Shared Domain Primitives for the Spine Ecosystem |
| 19 | [19_tagging.py](01_core/19_tagging.py) | Multi-Dimensional Tagging — Faceted Search with Provenance Tracking |
| 20 | [20_asset_tracking.py](01_core/20_asset_tracking.py) | Asset Tracking — Dagster-Inspired Data Artifact Management |
| 21 | [21_finance_adjustments.py](01_core/21_finance_adjustments.py) | Finance Adjustments — Factor-based adjustment math for per-share metrics |
| 22 | [22_finance_corrections.py](01_core/22_finance_corrections.py) | Finance Corrections — Why-an-observation-changed taxonomy with audit trail |
| 23 | [23_feature_flags.py](01_core/23_feature_flags.py) | Feature Flags — Runtime Feature Toggling with Environment Overrides |
| 24 | [24_secrets_resolver.py](01_core/24_secrets_resolver.py) | Secrets Resolver — Pluggable Credential Management with Automatic Redaction |

### 02_execution — Execution

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_workspec_basics.py](02_execution/01_workspec_basics.py) | WorkSpec — The Universal Work Description for Tasks, Operations, and Workflows |
| 02 | [02_handler_registration.py](02_execution/02_handler_registration.py) | Handler Registration — Mapping WorkSpecs to Executable Functions |
| 03 | [03_dispatcher_basics.py](02_execution/03_dispatcher_basics.py) | Dispatcher — The Central Hub for Submitting and Tracking Work |
| 04 | [04_run_lifecycle.py](02_execution/04_run_lifecycle.py) | Run Lifecycle — Understanding RunRecord State Transitions |
| 05 | [05_memory_executor.py](02_execution/05_memory_executor.py) | MemoryExecutor — In-Process Async Execution for Development and Testing |
| 06 | [06_local_executor.py](02_execution/06_local_executor.py) | LocalExecutor — ThreadPool-Based Execution for I/O-Bound Concurrency |
| 07 | [07_async_patterns.py](02_execution/07_async_patterns.py) | Async Patterns — Coordination Strategies for Concurrent Operation Tasks |
| 08 | [08_fastapi_integration.py](02_execution/08_fastapi_integration.py) | FastAPI Integration — Building REST APIs for Operation Orchestration |
| 09 | [09_execution_ledger.py](02_execution/09_execution_ledger.py) | ExecutionLedger — Persistent Execution Audit Trail with Full Lifecycle |
| 10 | [10_execution_repository.py](02_execution/10_execution_repository.py) | ExecutionRepository — Analytics and Maintenance Queries for Executions |
| 11 | [11_batch_execution.py](02_execution/11_batch_execution.py) | BatchExecutor — Coordinated Multi-Operation Execution with Progress Tracking |
| 12 | [12_health_checks.py](02_execution/12_health_checks.py) | ExecutionHealthChecker — System Health Monitoring for Operation Infrastructure |
| 13 | [13_tracked_execution.py](02_execution/13_tracked_execution.py) | TrackedExecution — Context Manager for Automatic Execution Recording |
| 14 | [14_worker_loop.py](02_execution/14_worker_loop.py) | WorkerLoop — Background Polling Engine for Database-Backed Task Execution |
| 15 | [15_async_local_executor.py](02_execution/15_async_local_executor.py) | AsyncLocalExecutor — Native asyncio Execution Without Thread Overhead |
| 16 | [16_async_batch_executor.py](02_execution/16_async_batch_executor.py) | AsyncBatchExecutor — Bounded Fan-Out for Concurrent Async Operations |
| 17 | [17_state_machine.py](02_execution/17_state_machine.py) | State Machine Transitions — Enforced Lifecycle for Job Executions |
| 18 | [18_hot_reload_adapter.py](02_execution/18_hot_reload_adapter.py) | Hot-Reload Adapter — dynamic config reloading for runtime adapters |
| 19 | [19_local_process_adapter.py](02_execution/19_local_process_adapter.py) | LocalProcessAdapter — run container specs as local subprocesses |
| 20 | [20_job_engine_lifecycle.py](02_execution/20_job_engine_lifecycle.py) | JobEngine — unified entry-point for job submission and lifecycle management |
| 21 | [21_runtime_router.py](02_execution/21_runtime_router.py) | RuntimeAdapterRouter — multi-runtime registry, routing, and health |
| 22 | [22_spec_validator.py](02_execution/22_spec_validator.py) | SpecValidator — pre-flight validation for ContainerJobSpec submissions |
| 23 | [23_workflow_packager.py](02_execution/23_workflow_packager.py) | WorkflowPackager — pack workflows into portable .pyz archives |

### 03_resilience — Resilience

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_retry_strategies.py](03_resilience/01_retry_strategies.py) | Retry Strategies — Configurable retry patterns for transient failures |
| 02 | [02_circuit_breaker.py](03_resilience/02_circuit_breaker.py) | Circuit Breaker — Fail-fast protection for external services |
| 03 | [03_rate_limiting.py](03_resilience/03_rate_limiting.py) | Rate Limiting — Control request throughput to external services |
| 04 | [04_concurrency_guard.py](03_resilience/04_concurrency_guard.py) | Concurrency Guard — Prevent overlapping operation runs |
| 05 | [05_dead_letter_queue.py](03_resilience/05_dead_letter_queue.py) | Dead Letter Queue — Handle failed executions gracefully |
| 06 | [06_timeout_enforcement.py](03_resilience/06_timeout_enforcement.py) | Timeout Enforcement — Deadlines and timeouts for reliable execution |

### 04_orchestration — Orchestration

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_workflow_basics.py](04_orchestration/01_workflow_basics.py) | Simple Workflow — Basic multi-step orchestration |
| 02 | [02_operation_vs_workflow.py](04_orchestration/02_operation_vs_workflow.py) | Operation vs Workflow — Understanding the differences |
| 03 | [03_workflow_context.py](04_orchestration/03_workflow_context.py) | WorkflowContext — Data passing between steps |
| 04 | [04_step_adapters.py](04_orchestration/04_step_adapters.py) | Decoupled Functions — plain Python that works anywhere AND as workflow steps |
| 05 | [05_choice_branching.py](04_orchestration/05_choice_branching.py) | Choice & Branching — conditional routing and error handling |
| 06 | [06_error_policies.py](04_orchestration/06_error_policies.py) | Error Handling — Managing failures in workflows |
| 07 | [07_parallel_dag.py](04_orchestration/07_parallel_dag.py) | Parallel DAG — diamond-shaped workflow with ThreadPoolExecutor |
| 08 | [08_tracked_runner.py](04_orchestration/08_tracked_runner.py) | TrackedWorkflowRunner — Database-backed workflow execution |
| 09 | [09_workflow_playground.py](04_orchestration/09_workflow_playground.py) | Workflow Playground — interactive step-by-step execution and debugging |
| 10 | [10_workflow_registry_yaml.py](04_orchestration/10_workflow_registry_yaml.py) | Workflow Registry & YAML Specs — discovery, lookup, and declarative definitions |
| 11 | [11_workflow_serialization.py](04_orchestration/11_workflow_serialization.py) | Workflow Serialization — to_dict, from_dict, to_yaml round-trips |
| 12 | [12_managed_workflow.py](04_orchestration/12_managed_workflow.py) | Managed Operations — import existing code, get full lifecycle management |
| 13 | [13_workflow_templates.py](04_orchestration/13_workflow_templates.py) | Workflow Templates — pre-built patterns for common workflow shapes |
| 14 | [14_container_runnable.py](04_orchestration/14_container_runnable.py) | ContainerRunnable — bridging orchestration workflows with container execution |
| 15 | [15_runnable_protocol.py](04_orchestration/15_runnable_protocol.py) | Runnable Protocol — Unified operation execution interface |
| 16 | [16_webhook_triggers.py](04_orchestration/16_webhook_triggers.py) | Webhook Triggers — HTTP-triggered workflow and operation execution |
| 17 | [17_sec_etl_workflow.py](04_orchestration/17_sec_etl_workflow.py) | SEC ETL Workflow — full filing operation with mock and real modes |
| 18 | [18_parallel_vs_multiprocessing.py](04_orchestration/18_parallel_vs_multiprocessing.py) | Multiprocessing Comparison — raw parallelism vs orchestrated workflows |
| 19 | [19_workflow_linter.py](04_orchestration/19_workflow_linter.py) | Workflow Linter — static analysis for workflow definitions |
| 20 | [20_step_recorder.py](04_orchestration/20_step_recorder.py) | Step Recorder — capture and replay workflow executions |
| 21 | [21_workflow_visualizer.py](04_orchestration/21_workflow_visualizer.py) | Workflow Visualizer — Mermaid, ASCII, and summary output |
| 22 | [22_composition_operators.py](04_orchestration/22_composition_operators.py) | Composition Operators — functional workflow builders |
| 23 | [23_dry_run.py](04_orchestration/23_dry_run.py) | Dry-Run Mode — preview workflow execution without running |
| 24 | [24_test_harness.py](04_orchestration/24_test_harness.py) | Test Harness — utilities for testing workflows |
| 25 | [25_llm_provider.py](04_orchestration/25_llm_provider.py) | LLM Provider Protocol — backend-agnostic LLM integration |

### 05_infrastructure — Infrastructure

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_complete_operation.py](05_infrastructure/01_complete_operation.py) | Complete Execution Infrastructure — Full operation with all resilience primitives |
| 02 | [02_mcp_server.py](05_infrastructure/02_mcp_server.py) | MCP Server — AI-native Orchestration Interface |

### 06_observability — Observability

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_structured_logging.py](06_observability/01_structured_logging.py) | Structured Logging — Production-ready logging with structlog |
| 02 | [02_metrics.py](06_observability/02_metrics.py) | Metrics Collection — Prometheus-style metrics for monitoring |
| 03 | [03_context_binding.py](06_observability/03_context_binding.py) | Context Binding — Thread-local context for observability |

### 07_real_world — Real World

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_entityspine_integration.py](07_real_world/01_entityspine_integration.py) | EntitySpine Integration — Using spine-core with EntitySpine |
| 02 | [02_feedspine_integration.py](07_real_world/02_feedspine_integration.py) | FeedSpine Integration — Using spine-core with FeedSpine |
| 03 | [03_combined_workflow.py](07_real_world/03_combined_workflow.py) | Combined Workflow — Using EntitySpine and FeedSpine together |
| 04 | [04_feed_ingestion.py](07_real_world/04_feed_ingestion.py) | Feed Ingestion Operation — Production-style feed processing |
| 05 | [05_sec_filing_workflow.py](07_real_world/05_sec_filing_workflow.py) | SEC Filing Workflow — Multi-step filing processing operation |

### 08_framework — Framework

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_operation_basics.py](08_framework/01_operation_basics.py) | Operation Base Class — The building block of Spine workflows |
| 02 | [02_operation_runner.py](08_framework/02_operation_runner.py) | OperationRunner — Executing operations by name |
| 03 | [03_operation_registry.py](08_framework/03_operation_registry.py) | Operation Registry — Registering and discovering operations |
| 04 | [04_params_validation.py](08_framework/04_params_validation.py) | Parameter Validation — OperationSpec with ParamDef |
| 05 | [05_alert_routing.py](08_framework/05_alert_routing.py) | Alert Routing — AlertRegistry and delivery channels |
| 06 | [06_source_connectors.py](08_framework/06_source_connectors.py) | Source Connectors — File ingestion with change detection |
| 07 | [07_framework_logging.py](08_framework/07_framework_logging.py) | Framework Logging — Structured logging with context and timing |

### 09_data_layer — Data Layer

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_adapters.py](09_data_layer/01_adapters.py) | Database Adapters — Portable data access with SQLiteAdapter |
| 02 | [02_protocols_and_storage.py](09_data_layer/02_protocols_and_storage.py) | Protocols and Storage — Type contracts and cross-dialect SQL |
| 03 | [03_db_provider.py](09_data_layer/03_db_provider.py) | Database Provider — Tier-agnostic connection injection |
| 04 | [04_migration_runner.py](09_data_layer/04_migration_runner.py) | Migration Runner — Versioned schema upgrades with tracking |
| 05 | [05_data_retention.py](09_data_layer/05_data_retention.py) | Data Retention — Purge old records with configurable policies |
| 06 | [06_schema_loader.py](09_data_layer/06_schema_loader.py) | Schema Loader — Bulk schema loading and introspection |
| 07 | [07_database_portability.py](09_data_layer/07_database_portability.py) | Database Portability — Write SQL that runs on any backend |
| 08 | [08_orm_integration.py](09_data_layer/08_orm_integration.py) | ORM Integration — SQLAlchemy ORM alongside the Dialect layer |
| 09 | [09_orm_relationships.py](09_data_layer/09_orm_relationships.py) | ORM Relationships — Navigate parent→child data via relationship() |
| 10 | [10_repository_bridge.py](09_data_layer/10_repository_bridge.py) | Repository Bridge — Use BaseRepository over an ORM Session |
| 11 | [11_orm_vs_dialect.py](09_data_layer/11_orm_vs_dialect.py) | ORM vs Dialect — Side-by-side comparison of both data access paths |

### 10_operations — Operations

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_database_lifecycle.py](10_operations/01_database_lifecycle.py) | Database Lifecycle — Initialize, inspect, health-check, and purge |
| 02 | [02_run_management.py](10_operations/02_run_management.py) | Run Management — List, inspect, cancel, and retry execution runs |
| 03 | [03_workflow_ops.py](10_operations/03_workflow_ops.py) | Workflow Operations — List, inspect, and run registered workflows |
| 04 | [04_health_and_capabilities.py](10_operations/04_health_and_capabilities.py) | Health & Capabilities — Aggregate health checks and runtime introspection |
| 05 | [05_alert_management.py](10_operations/05_alert_management.py) | Alert Management — Channels, alerts, acknowledgement, and delivery tracking |
| 06 | [06_source_management.py](10_operations/06_source_management.py) | Source Management — Data sources, fetches, cache, and database connections |
| 07 | [07_operation_data.py](10_operations/07_operation_data.py) | Operation Data Processing — Manifest, rejects, and work items |
| 08 | [08_schedule_metadata.py](10_operations/08_schedule_metadata.py) | Schedule Metadata — Calc dependencies, expected schedules, and data readiness |
| 09 | [09_locks_dlq_quality.py](10_operations/09_locks_dlq_quality.py) | Lock and DLQ Management — Concurrency locks, schedule locks, dead letters |
| 10 | [10_full_table_population.py](10_operations/10_full_table_population.py) | Full Table Population - Populates ALL 27 tables into a persistent SQLite file |

### 11_scheduling — Scheduling

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_backend_basics.py](11_scheduling/01_backend_basics.py) | Backend Basics — Pluggable timing backends and the SchedulerBackend protocol |
| 02 | [02_schedule_repository.py](11_scheduling/02_schedule_repository.py) | Schedule Repository — CRUD, cron evaluation, and run tracking |
| 03 | [03_distributed_locks.py](11_scheduling/03_distributed_locks.py) | Distributed Locks — Atomic lock acquire/release with TTL expiry |
| 04 | [04_scheduler_service.py](11_scheduling/04_scheduler_service.py) | Scheduler Service — Full lifecycle: start, tick, dispatch, pause, resume, health |
| 05 | [05_health_monitoring.py](11_scheduling/05_health_monitoring.py) | Health Monitoring — NTP drift detection and tick interval stability analysis |

### 12_deploy — Deploy

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_quickstart.py](12_deploy/01_quickstart.py) | Deploy Quickstart — Configuration, backends, and result models |
| 02 | [02_backend_registry.py](12_deploy/02_backend_registry.py) | Backend Registry — Browse, filter, and inspect database backend specs |
| 03 | [03_compose_generation.py](12_deploy/03_compose_generation.py) | Compose Generation — Build docker-compose YAML on the fly |
| 04 | [04_testbed_workflow.py](12_deploy/04_testbed_workflow.py) | Testbed Workflow — Multi-backend database verification |
| 05 | [05_result_models.py](12_deploy/05_result_models.py) | Result Models — Lifecycle, aggregation, and serialisation |
| 06 | [06_log_collector.py](12_deploy/06_log_collector.py) | Log Collector — Structured output, summaries, and HTML reports |
| 07 | [07_env_configuration.py](12_deploy/07_env_configuration.py) | Environment Configuration — Build config from environment variables |
| 08 | [08_schema_executor.py](12_deploy/08_schema_executor.py) | Schema Executor — Verify table creation against a real database |
| 09 | [09_container_lifecycle.py](12_deploy/09_container_lifecycle.py) | Container Lifecycle — Docker container management patterns |
| 10 | [10_workflow_integration.py](12_deploy/10_workflow_integration.py) | Workflow Integration — Deploy as a spine-core workflow |
| 11 | [11_cli_programmatic.py](12_deploy/11_cli_programmatic.py) | CLI Programmatic — Invoke deploy commands from Python |
| 12 | [12_ci_artifacts.py](12_deploy/12_ci_artifacts.py) | CI Artifacts — Structured output for continuous integration |

### 13_runtimes — Runtimes

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_container_job_spec.py](13_runtimes/01_container_job_spec.py) | ContainerJobSpec — complete field reference with all 30+ parameters |
| 02 | [02_stub_adapter.py](13_runtimes/02_stub_adapter.py) | StubRuntimeAdapter — injectable test double for unit testing |
| 03 | [03_error_taxonomy.py](13_runtimes/03_error_taxonomy.py) | Error taxonomy — JobError, ErrorCategory, and retryable semantics |
| 04 | [04_mock_adapters.py](13_runtimes/04_mock_adapters.py) | Mock Runtime Adapters — test doubles for edge-case simulation |

### 13_workflows — Workflows

| # | Example | Description |
|---|---------|-------------|
| 04 | [04_sec_etl_workflow.py](13_workflows/04_sec_etl_workflow.py) | SEC ETL Workflow — full filing operation with mock and real modes |

### 14_golden_workflows — Golden Workflows

| # | Example | Description |
|---|---------|-------------|
| 01 | [01_golden_path_workflow.py](14_golden_workflows/01_golden_path_workflow.py) | Golden Path Workflow — all 7 phases in one end-to-end run |
| 02 | [02_medallion_operation.py](14_golden_workflows/02_medallion_operation.py) | Multi-Stage Medallion Workflow — Bronze → Silver → Gold with quality gates |
| 03 | [03_long_running_monitor.py](14_golden_workflows/03_long_running_monitor.py) | Long-Running Workflow Monitor — timeouts, progress, concurrency guards |
| 04 | [04_container_deployment.py](14_golden_workflows/04_container_deployment.py) | Container Deployment — same workflow running in Docker/Podman |
| 05 | [05_cli_sdk_api_parity.py](14_golden_workflows/05_cli_sdk_api_parity.py) | CLI / SDK / API Parity — one workflow, three surfaces, same results |
| 06 | [06_e2e_validate_everything.py](14_golden_workflows/06_e2e_validate_everything.py) | End-to-End Validation Workflow — spin up, ingest, calculate, store, verify |

## Architecture Highlights

These examples include architecture diagrams — key for understanding data flow and component interaction.

### Decoupled Functions — plain Python that works anywhere AND as workflow steps.
*From [04_step_adapters.py](04_orchestration/04_step_adapters.py)*

```
Plain functions are bridged into the workflow engine by an
    **adapter layer** that:

    1. Merges ``config`` and ``ctx.params`` into a kwargs dict
    2. Filters kwargs to only the params the function declares
    3. Calls the function with matched kwargs
    4. Coerces the return value via ``StepResult.from_value()``
    5. Catches exceptions → ``StepResult.fail()``

    ::

        Your function                     Workflow engine
        ────────────                      ───────────────
        def score(revenue, debt):         WorkflowRunner calls
            return {"ratio": ...}    ◄──  adapter(ctx, config) → StepResult
```

### Choice & Branching — conditional routing and error handling.
*From [05_choice_branching.py](04_orchestration/05_choice_branching.py)*

```
Workflow A — Conditional Routing::

        classify_filing
            │
        route_by_type ─── condition: is_annual?
            │                 │
          (True)           (False)
            │                 │
        process_annual    process_quarterly
            │                 │
            └────── summarize ◄┘
                       │
                     store

    Workflow B — Error Handling::

        step_ok_1 ─(continue)─► step_fail ─(continue)─► step_ok_2
                                                         │
        Result: PARTIAL (2 completed, 1 failed)
```

### Parallel DAG — diamond-shaped workflow with ThreadPoolExecutor.
*From [07_parallel_dag.py](04_orchestration/07_parallel_dag.py)*

```
The DAG looks like a diamond::

        fetch_filing  (root — no deps, runs first)
           ├── extract_text      (depends: fetch_filing)
           ├── extract_exhibits  (depends: fetch_filing)
           └── parse_xbrl        (depends: fetch_filing)
        merge_results  (depends: extract_text, extract_exhibits, parse_xbrl)
        store          (depends: merge_results)

    With ``max_concurrency=3``, the three extract/parse steps run
    concurrently after ``fetch_filing`` completes.  ``merge_results``
    waits for all three, then ``store`` runs last.
```

### Workflow Registry & YAML Specs — discovery, lookup, and declarative definitions.
*From [10_workflow_registry_yaml.py](04_orchestration/10_workflow_registry_yaml.py)*

```
The registry is an in-memory dictionary keyed by workflow name.
    Workflows are registered eagerly via ``register_workflow()`` and
    looked up lazily via ``get_workflow()``.  Domain filtering lets
    teams partition workflows by subsystem (e.g. ``ingest``, ``sec``).

    The YAML spec system uses Pydantic v2 models for strict validation::

        WorkflowSpec   ← root (apiVersion, kind, metadata, spec)
        ├── WorkflowMetadataSpec  (name, domain, version, description, tags)
        └── WorkflowSpecSection   (steps, defaults, policy)
            ├── WorkflowStepSpec[]  (name, operation, depends_on, params)
            └── WorkflowPolicySpec  (execution, max_concurrency, failure)
```

### Workflow Serialization — to_dict, from_dict, to_yaml round-trips.
*From [11_workflow_serialization.py](04_orchestration/11_workflow_serialization.py)*

```
Serialization flows in two directions::

        Runtime                    Serialized
        ──────────────────────────────────────────────
        Workflow.to_dict()    →    dict (JSON-safe)
        Workflow.from_dict()  ←    dict
        Workflow.to_yaml()    →    str (YAML document)
        WorkflowSpec.from_yaml() ← str

    Lambda steps with named handlers serialize their ``handler_ref`` as
    ``"module:qualname"`` for later import.  Inline lambdas serialize
    without a ref — they must be rewired after deserialization.
```

### SEC ETL Workflow — full filing operation with mock and real modes.
*From [17_sec_etl_workflow.py](04_orchestration/17_sec_etl_workflow.py)*

```
The workflow combines sequential and parallel phases::

        configure → fetch_index → download_filing
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                   ▼
              extract_sections   extract_entities   extract_financials
                    │                  │                   │
                    └──────────────────┼──────────────────┘
                                       ▼
                                  quality_gate
                                       │
                                  store_results
                                       │
                                    cleanup
```

### Multiprocessing Comparison — raw parallelism vs orchestrated workflows.
*From [18_parallel_vs_multiprocessing.py](04_orchestration/18_parallel_vs_multiprocessing.py)*

```
Four benchmarks run in sequence::

        A. CPU-bound — multiprocessing.Pool (4 workers)
        B. CPU-bound — workflow DAG threads (4 concurrent, GIL-bound)
        C. I/O-bound — ThreadPoolExecutor (4 workers)
        D. I/O-bound — workflow DAG threads (4 concurrent)
```

### Deploy Quickstart — Configuration, backends, and result models.
*From [01_quickstart.py](12_deploy/01_quickstart.py)*

```
┌──────────────────────────────────────────────────────────┐
    │                  Configuration Layer                      │
    │  DeploymentConfig │ TestbedConfig │ TestbedSettings       │
    ├──────────────────────────────────────────────────────────┤
    │                   Backend Registry                        │
    │  POSTGRESQL │ MYSQL │ DB2 │ ORACLE │ SQLITE │ TIMESCALE  │
    ├──────────────────────────────────────────────────────────┤
    │                   Result Models                           │
    │  BackendResult │ TestbedRunResult │ DeploymentResult      │
    └──────────────────────────────────────────────────────────┘
```

### Backend Registry — Browse, filter, and inspect database backend specs.
*From [02_backend_registry.py](12_deploy/02_backend_registry.py)*

```
┌─────────────────────────────────────────────────────┐
    │              BackendSpec (frozen dataclass)          │
    │  name │ dialect │ image │ port │ healthcheck_cmd    │
    │  env │ connection_url_template │ requires_license   │
    └────────────────────┬────────────────────────────────┘
                         │
    ┌────────────────────▼────────────────────────────────┐
    │  BACKENDS dict   (6 entries)                        │
    │  SQLITE │ POSTGRESQL │ MYSQL │ DB2 │ ORACLE │ TS   │
    └─────────────────────────────────────────────────────┘
```

### Compose Generation — Build docker-compose YAML on the fly.
*From [03_compose_generation.py](12_deploy/03_compose_generation.py)*

```
BackendSpec[]  ──▶  generate_testbed_compose()   ──▶  YAML string
    ServiceSpec[]  ──▶  generate_deployment_compose() ──▶  YAML string
                                                              │
                                                              ▼
                                                     write_compose_file()
```

### Testbed Workflow — Multi-backend database verification.
*From [04_testbed_workflow.py](12_deploy/04_testbed_workflow.py)*

```
┌────────────┐    ┌──────────────┐    ┌──────────────┐
    │ TestbedConfig ──▶ TestbedRunner ──▶ TestbedRunResult│
    └────────────┘    └──────┬───────┘    └──────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    ┌──────────┐       ┌──────────┐       ┌──────────┐
    │PostgreSQL│       │  MySQL   │       │TimescaleDB│
    │container │       │container │       │container  │
    └────┬─────┘       └────┬─────┘       └────┬─────┘
         │                   │                   │
         ▼                   ▼                   ▼
    BackendResult       BackendResult       BackendResult
```

### Result Models — Lifecycle, aggregation, and serialisation.
*From [05_result_models.py](12_deploy/05_result_models.py)*

```
SchemaResult ─┐
    TestResult ───┤
    ExampleResult ┼──▶ BackendResult ──▶ TestbedRunResult
    SmokeResult ──┘

    ServiceStatus ──▶ DeploymentResult
```

### Log Collector — Structured output, summaries, and HTML reports.
*From [06_log_collector.py](12_deploy/06_log_collector.py)*

```
TestbedRunResult ──▶ LogCollector ──▶  {output_dir}/{run_id}/
                                           ├── summary.json
                                           ├── report.html
                                           ├── postgresql/
                                           │   ├── schema.json
                                           │   └── container.log
                                           └── mysql/
                                               ├── schema.json
                                               └── container.log
```

### Schema Executor — Verify table creation against a real database.
*From [08_schema_executor.py](12_deploy/08_schema_executor.py)*

```
TestbedExecutor
        │
        ├── run_schema_verification(url, dialect)
        │       ├── apply_all_schemas()    ← spine.core.schema_loader
        │       ├── get_table_list()       ← spine.core.schema_loader
        │       └── compare vs CORE_TABLES
        │
        └── run_test_suite(url, backend, test_filter)
                ├── subprocess: python -m pytest ...
                └── parse JUnit XML → TestResult
```

### Container Lifecycle — Docker container management patterns.
*From [09_container_lifecycle.py](12_deploy/09_container_lifecycle.py)*

```
ContainerManager
        ├── is_docker_available()     ← static check
        ├── create_network(run_id)
        ├── start_backend(spec, run_id)
        │       ├── docker run --detach ... ← subprocess
        │       ├── _get_mapped_port()
        │       └── _wait_for_healthy()     ← exponential backoff
        ├── start_service(spec, run_id)
        ├── stop_container(info)
        ├── collect_logs(info)
        └── cleanup_orphans()
```

### Workflow Integration — Deploy as a spine-core workflow.
*From [10_workflow_integration.py](12_deploy/10_workflow_integration.py)*

```
create_testbed_workflow(backends)
        └── Workflow
            ├── Step: validate_environment
            └── Step: run_testbed        ← TestbedRunner(config).run()

    create_deployment_workflow(targets, profile)
        └── Workflow
            ├── Step: deploy             ← DeploymentRunner(config).run()
            └── Step: health_check       ← DeploymentRunner(status).run()
```

### CLI Programmatic — Invoke deploy commands from Python.
*From [11_cli_programmatic.py](12_deploy/11_cli_programmatic.py)*

```
CLI:    spine-core deploy testbed --backend sqlite
    Python: TestbedRunner(TestbedConfig(backends=["sqlite"])).run()

    Both produce the same TestbedRunResult — the CLI just adds
    Rich formatting and exit code handling.
```

### CI Artifacts — Structured output for continuous integration.
*From [12_ci_artifacts.py](12_deploy/12_ci_artifacts.py)*

```
TestbedRunner.run()
        └── LogCollector
            ├── write_summary()      → summary.json
            ├── write_html_report()  → report.html
            ├── save_schema_result() → {backend}/schema.json
            ├── save_test_result()   → {backend}/tests.json
            └── backend_dir()        → {backend}/ (JUnit XML, logs)
```

### SEC ETL Workflow — full filing operation with mock and real modes.
*From [04_sec_etl_workflow.py](13_workflows/04_sec_etl_workflow.py)*

```
The workflow combines sequential and parallel phases::

        configure → fetch_index → download_filing
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                   ▼
              extract_sections   extract_entities   extract_financials
                    │                  │                   │
                    └──────────────────┼──────────────────┘
                                       ▼
                                  quality_gate
                                       │
                                  store_results
                                       │
                                    cleanup
```

### Multi-Stage Medallion Workflow — Bronze → Silver → Gold with quality gates.
*From [02_medallion_operation.py](14_golden_workflows/02_medallion_operation.py)*

```
┌──────────┐   QualityGate   ┌──────────┐   QualityGate   ┌──────────┐
    │  Bronze  │ ──────────────→ │  Silver  │ ──────────────→ │   Gold   │
    │ (raw)    │  completeness   │(cleaned) │  business rules │(enriched)│
    └──────────┘                 └──────────┘                 └──────────┘
         ↑                            ↑                            ↑
    Ingest raw data          Validate & normalize         Aggregate & score
    from external source     null handling, types         derived metrics

Key patterns:
    - Each stage is its own ManagedWorkflow with persistence
    - QualityRunner gates between stages prevent bad data propagation
    - Failed quality checks halt the workflow with full audit trail
    - Each stage's output becomes the next stage's input
    - Summary JSON captures the entire multi-stage run

Spine modules used:
    - spine.orchestration.managed_workflow — ManagedWorkflow builder
    - spine.core.quality                  — QualityRunner, QualityCheck
    - spine.core.connection               — create_connection
    - spine.framework.alerts.protocol     — Alert, AlertSeverity

Tier: Basic (spine-core only)
```

## Prerequisites

Some examples require optional dependencies:

```bash
pip install spine-core[mcp]
```

## Infrastructure

| File | Purpose |
|------|---------|
| [`_registry.py`](_registry.py) | Auto-discovers examples via AST — no hardcoded lists |
| [`run_all.py`](run_all.py) | Runs every example as an isolated subprocess (60s timeout) |
| [`generate_readme.py`](generate_readme.py) | Generates this README from docstrings |

The [`mock/`](mock/) directory contains shared test fixtures and mock implementations used by integration examples.

---

*Generated on 2026-02-19 from 144 examples across 15 categories.*
