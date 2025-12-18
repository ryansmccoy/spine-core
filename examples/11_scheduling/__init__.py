"""Scheduling — Backends, distributed locks, scheduler service.

The scheduling layer adds time-based execution to spine pipelines:
pluggable timing backends, cron-based schedule repositories,
distributed locks for multi-instance safety, and a full scheduler
service with health monitoring.

READING ORDER
─────────────
    01 — Backend basics (SchedulerBackend protocol, pluggable timing)
    02 — Schedule repository (CRUD, cron evaluation, run tracking)
    03 — Distributed locks (atomic acquire/release with TTL)
    04 — Scheduler service (start, tick, dispatch, pause, resume)
    05 — Health monitoring (NTP drift detection, tick stability)
"""
