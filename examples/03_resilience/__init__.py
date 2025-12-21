"""Resilience patterns — Retry, circuit breaker, rate limiting, dead-letter queue.

Resilience primitives protect operations from transient failures,
service outages, and resource exhaustion.  Each pattern is standalone
and composable — stack them for defence-in-depth.

READING ORDER
─────────────
    01 — Retry strategies (exponential backoff, jitter, max attempts)
    02 — Circuit breaker (fail-fast when services are down)
    03 — Rate limiting (throttle request throughput)
    04 — Concurrency guard (prevent overlapping runs)
    05 — Dead-letter queue (gracefully handle permanent failures)
    06 — Timeout enforcement (deadlines for reliable execution)
"""
