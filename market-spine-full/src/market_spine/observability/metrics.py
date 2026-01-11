"""Prometheus metrics for observability."""

from prometheus_client import Counter, Gauge, Histogram, Info

# Application info
app_info = Info("spine_app", "Market Spine application info")
app_info.info({"version": "1.0.0", "component": "market-spine-full"})

# Execution metrics
execution_submitted_counter = Counter(
    "spine_executions_submitted_total",
    "Total number of executions submitted",
    ["pipeline"],
)

execution_status_gauge = Gauge(
    "spine_executions_by_status",
    "Number of executions by status",
    ["pipeline", "status"],
)

execution_completed_counter = Counter(
    "spine_executions_completed_total",
    "Total number of completed executions",
    ["pipeline", "result"],
)

pipeline_duration_histogram = Histogram(
    "spine_pipeline_duration_seconds",
    "Pipeline execution duration in seconds",
    ["pipeline"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# DLQ metrics
dead_letters_counter = Counter(
    "spine_dead_letters_total",
    "Total number of dead letter entries",
    ["pipeline"],
)

dead_letters_retried_counter = Counter(
    "spine_dead_letters_retried_total",
    "Total number of DLQ retries",
    ["pipeline"],
)

# Database metrics
db_query_duration_histogram = Histogram(
    "spine_db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

db_connections_gauge = Gauge(
    "spine_db_connections",
    "Number of database connections",
    ["state"],
)

# API metrics
api_request_duration_histogram = Histogram(
    "spine_api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint", "status_code"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

api_requests_total = Counter(
    "spine_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status_code"],
)

# Domain-specific metrics are in domains/<domain>/metrics.py
