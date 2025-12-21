#!/usr/bin/env python3
"""Metrics Collection — Prometheus-style metrics for monitoring.

WHY APPLICATION METRICS
───────────────────────
Logs tell you *what happened*; metrics tell you *how much* and
*how fast*.  A dashboard showing "p95 ingestion latency = 12 s"
or "4 operation failures in the last hour" catches problems that
would be invisible in log output alone.

METRIC TYPES
────────────
    Type       Direction   Example
    ────────── ────────── ───────────────────────────────
    Counter    Only up     http_requests_total, errors_total
    Gauge      Up & down   active_jobs, queue_depth
    Histogram  Buckets     request_duration_seconds

ARCHITECTURE
────────────
    ┌──────────────────┐
    │ MetricsRegistry  │   (singleton)
    └────────┬─────────┘
             │ register
      ┌──────┼──────────┐
      ▼      ▼          ▼
    Counter  Gauge   Histogram
    .inc()   .set()  .observe()
    .labels  .inc()  .labels()
             .dec()

    Use helper functions: counter(), gauge(), histogram()
    for convenient creation with automatic registration.

LABELED METRICS
───────────────
    # Labels create dimensional metrics:
    requests = counter("reqs", labels=["method", "status"])
    requests.labels(method="GET", status="200").inc()
    requests.labels(method="POST", status="500").inc()
    # → reqs{method="GET",status="200"} = 1
    # → reqs{method="POST",status="500"} = 1

BEST PRACTICES
──────────────
• Use snake_case with _total suffix for counters.
• Keep label cardinality low (≤ 10 values per label).
• Use execution_metrics for pre-built operation tracking.
• Pair histogram buckets with SLO thresholds (e.g., p99 < 5 s).

Run: python examples/06_observability/02_metrics.py

See Also:
    01_structured_logging — log events alongside metrics
    03_context_binding — bind context for correlated metrics+logs
"""
import time
import random
from spine.observability import (
    MetricsRegistry,
    Counter,
    Gauge,
    Histogram,
    get_metrics_registry,
    counter,
    gauge,
    histogram,
    execution_metrics,
)


def main():
    print("=" * 60)
    print("Metrics Collection Examples")
    print("=" * 60)
    
    # === 1. Metrics registry ===
    print("\n[1] Metrics Registry")
    
    registry = get_metrics_registry()
    print(f"  Global registry: {type(registry).__name__}")
    
    # === 2. Counter metrics ===
    print("\n[2] Counter Metrics")
    print("  Counters only go up (monotonic)")
    
    # Create counter
    requests = counter(
        name="http_requests_total",
        description="Total HTTP requests",
        labels=["method", "status"],
    )
    
    # Increment
    requests.labels(method="GET", status="200").inc()
    requests.labels(method="GET", status="200").inc()
    requests.labels(method="POST", status="201").inc()
    requests.labels(method="GET", status="404").inc()
    
    print("  Incremented request counters")
    print("    GET 200: 2 requests")
    print("    POST 201: 1 request")
    print("    GET 404: 1 request")
    
    # === 3. Gauge metrics ===
    print("\n[3] Gauge Metrics")
    print("  Gauges can go up or down")
    
    active_jobs = gauge(
        name="active_jobs",
        description="Currently running jobs",
    )
    
    # Set, inc, dec
    active_jobs.set(5)
    print("  Set to 5")
    
    active_jobs.inc()
    print("  Incremented to 6")
    
    active_jobs.dec(2)
    print("  Decremented by 2 to 4")
    
    # === 4. Histogram metrics ===
    print("\n[4] Histogram Metrics")
    print("  Histograms track distributions")
    
    request_duration = histogram(
        name="request_duration_seconds",
        description="Request duration in seconds",
        buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )
    
    # Observe values
    durations = [0.05, 0.12, 0.23, 0.45, 0.8, 1.2, 2.1]
    for d in durations:
        request_duration.observe(d)
    
    print(f"  Observed {len(durations)} request durations")
    print(f"  Values: {durations}")
    
    # === 5. Labeled metrics ===
    print("\n[5] Labeled Metrics")
    
    operation_runs = counter(
        name="operation_runs_total",
        description="Total operation runs",
        labels=["operation", "status"],
    )
    
    # Different operations
    operation_runs.labels(operation="otc_volume", status="success").inc(10)
    operation_runs.labels(operation="otc_volume", status="failure").inc(2)
    operation_runs.labels(operation="price_fetch", status="success").inc(50)
    
    print("  Operation run counts:")
    print("    otc_volume: 10 success, 2 failure")
    print("    price_fetch: 50 success")
    
    # === 6. Timing with histogram ===
    print("\n[6] Timing with Histogram")
    
    operation_time = histogram(
        name="operation_duration_seconds",
        description="Operation duration",
    )
    
    def timed_operation():
        """Operation that tracks its duration."""
        start = time.time()
        
        # Simulate work
        time.sleep(random.uniform(0.01, 0.1))
        
        duration = time.time() - start
        operation_time.observe(duration)
        return duration
    
    print("  Running 5 timed operations:")
    for i in range(5):
        duration = timed_operation()
        print(f"    Operation {i+1}: {duration*1000:.1f}ms")
    
    # === 7. Execution Metrics (pre-defined) ===
    print("\n[7] Execution Metrics (pre-defined)")
    print("  execution_metrics provides pre-built operation tracking metrics")
    
    # execution_metrics is an ExecutionMetrics instance with:
    #   .submitted (counter), .completed (counter), .duration (histogram)
    # Use record_submission / record_completion for tracking
    execution_metrics.record_submission("data_processing")
    start_time = time.time()
    time.sleep(0.05)  # Simulate work
    duration = time.time() - start_time
    execution_metrics.record_completion("data_processing", "success", duration)
    
    print(f"  Recorded submission + completion for 'data_processing'")
    print(f"  Duration: {duration*1000:.1f}ms")
    print("  Metrics tracked: submitted count, completed count, duration histogram")
    
    # === 8. Real-world: Operation metrics ===
    print("\n[8] Real-world: Operation Metrics")
    
    # Define operation metrics
    records_processed = counter(
        name="records_processed_total",
        description="Total records processed",
        labels=["operation", "stage"],
    )
    
    processing_errors = counter(
        name="processing_errors_total",
        description="Processing errors",
        labels=["operation", "error_type"],
    )
    
    batch_size = histogram(
        name="batch_size",
        description="Batch size distribution",
        labels=["operation"],
    )
    
    def run_operation_with_metrics(name: str, data: list):
        """Operation with comprehensive metrics."""
        # Record batch size
        batch_size.labels(operation=name).observe(len(data))
        
        # Extract stage
        records_processed.labels(operation=name, stage="extract").inc(len(data))
        
        # Transform stage (simulate some errors)
        valid = int(len(data) * 0.95)
        invalid = len(data) - valid
        
        records_processed.labels(operation=name, stage="transform").inc(valid)
        processing_errors.labels(operation=name, error_type="validation").inc(invalid)
        
        # Load stage
        records_processed.labels(operation=name, stage="load").inc(valid)
        
        return {"processed": valid, "errors": invalid}
    
    # Run operation
    data = list(range(100))
    result = run_operation_with_metrics("otc_volume", data)
    
    print(f"  Operation complete:")
    print(f"    Processed: {result['processed']}")
    print(f"    Errors: {result['errors']}")
    
    print("\n" + "=" * 60)
    print("[OK] Metrics Collection Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
