You are Claude Code Opus acting as a staff-level Python platform engineer. Generate four separate starter projects for Market Spine, one per maturity level:

market-spine-basic/

market-spine-intermediate/

market-spine-advanced/

market-spine-full/

Each is a distinct repo scaffold, runnable, progressively more capable, and designed so the next tier feels like a natural evolution (minimal churn, no rewrites of core concepts).

Market Spine: What it is

Market Spine is an analytics pipeline system for market computations and signals. Pipelines are computations and transformations. It must scale from “run one calc locally” to “event-sourced orchestration on Kubernetes.”

Must include a realistic demo domain: OTC Transparency

Each repo must include an OTC Transparency demo pipeline that:

Pulls data from a source

Stores raw data point-in-time

Transforms/normalizes into structured tables

Computes metrics (aggregates, spreads, volumes, VWAP)

Serves results via API (Intermediate+)

Supports replay/backfill later (Advanced/Full via execution ledger)

Data source (choose one pragmatic option)

Pick ONE of these approaches and implement it consistently:

Option A (preferred): ship a small sample dataset under data/otc_sample.csv and implement a “simulated fetch” that reads it (no network dependency)

Option B: a real public endpoint if stable (but avoid brittle scraping)

Option C: generate synthetic trades deterministically (seeded RNG)

Important: Even if you use a sample file, structure the code as if it’s ingesting externally (connector abstraction), so it can be swapped later.

Non-negotiable End-State (Advanced/Full MUST implement)

Advanced and Full must converge to:

Control-plane / execution-plane split

Execution ledger: executions, execution_events, dead_letters

Single canonical entrypoint: dispatcher.submit(pipeline, params, lane, trigger_source)

API/CLI are enqueue-only

Exactly one processing entrypoint: run_pipeline(execution_id)

Pluggable backend interface (Celery implemented)

DLQ + retry creates NEW execution

Concurrency guard

Health metrics derived from ledger (not queue depth)

doctor CLI command

OTC Transparency: Required Minimal Data Model

Include these concepts in the schema (sqlite in Basic is fine; Postgres in others):

Raw capture (bronze)

otc_trades_raw

capture_id / batch_id

source

captured_at

payload (json/text)

record_hash (for dedupe)

Normalized trades (silver)

otc_trades

trade_id (or derived)

symbol

trade_date / trade_ts

price

size

notional

venue / ats

side (if known)

source

ingested_at

Aggregates (gold)

otc_metrics_daily

symbol

date

trade_count

total_volume

total_notional

vwap

optional: high_price, low_price

Provide at least one queryable output: “daily metrics for a symbol between dates”.

Required Pipelines (at least these)
Pipeline 1: otc_ingest

Reads from the connector (sample file / synthetic generator)

Writes to otc_trades_raw as a capture batch (point in time)

Emits events (Advanced/Full)

Pipeline 2: otc_normalize

Transforms raw payload → normalized otc_trades

Dedupes by record hash or trade_id

Pipeline 3: otc_compute_daily_metrics

Computes daily aggregates into otc_metrics_daily

Pipeline 4 (Advanced/Full): otc_backfill_range

Params: start_date, end_date, symbols?

Runs ingest/normalize/compute in sequence per day or batch

Uses execution ledger events + concurrency to avoid overlap

API Requirements (Intermediate+)
Intermediate must include:

POST /executions (enqueue-only)

GET /executions/{id}

GET /otc/metrics/daily?symbol=...&start=...&end=...

GET /otc/trades?symbol=...&start=...&end=... (optional)

Advanced/Full must include:

all above plus:

GET /executions/{id}/events

GET /dead-letters

POST /dead-letters/{id}/retry

GET /health/metrics (ledger-based)

Level-by-Level Requirements
1) market-spine-basic

CLI only is fine

sqlite or in-memory

Synchronous runner + pipeline registry

Must demonstrate:

run ingest → normalize → compute

query daily metrics from DB

Include data/otc_sample.csv (or synthetic generator) and deterministic outputs

2) market-spine-intermediate

FastAPI + Postgres via Docker Compose

Background worker can be a simple thread/async queue (no Celery)

Must demonstrate:

call API to submit backfill for a date range

poll execution status

query /otc/metrics/daily endpoint

3) market-spine-advanced

Full event-sourced orchestration + Celery + Redis

Exactly one processing task run_pipeline(execution_id)

Beat scheduling (optional) for recurring ingest (e.g., every 60s reads next batch)

Must include:

executions/events/DLQ migrations

concurrency guard for otc_backfill_range or per-symbol-per-day

DLQ behavior when normalize fails (e.g., malformed row in sample)

retry from DLQ creates a NEW execution

4) market-spine-full

Production-grade + Kubernetes-ready

Provide:

Docker Compose and Kubernetes manifests (or Helm scaffold)

separate deployments: api, worker, beat

migration job/init container

observability hooks

CI guardrails enforcing invariants

retention/cleanup job

backpressure safeguards

optional stub backend interface for Temporal/Dagster/Prefect (no full implementation required)

Deliverables for EACH repo

Each repo must include:

README with exact commands to:

run services

run a backfill

query results

Folder structure with clean boundaries:

services/ contains OTC connector + normalization + calculations

pipelines/ defines pipeline stages

api/ is enqueue-only

Tests:

Basic: unit tests for normalize + compute

Intermediate: API test for metrics endpoint

Advanced: dispatcher invariant tests

Full: at least one integration test (compose-based ok)

Output Format (Strict)

For EACH project:

Print file tree

Output every file content:

## path/to/file

fenced code block

If output size is too large:

prioritize Advanced + Full

and for Basic/Intermediate provide file tree + key files + notes

Final Instruction

Do not hand-wave. Make these starter repos credible and runnable.

Start with market-spine-basic, then intermediate, advanced, full.