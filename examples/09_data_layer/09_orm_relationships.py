#!/usr/bin/env python3
"""ORM Relationships — Navigate parent→child data via relationship().

WHY RELATIONSHIPS MATTER
────────────────────────
Without ORM relationships, fetching an execution’s events requires
a manual JOIN query every time.  With relationship(), you write
`execution.events` and SQLAlchemy handles the query, caching, and
cascade deletes automatically.

RELATIONSHIP MAP
────────────────
    Execution ↔ Events        bidirectional, cascade delete-orphan
    Execution → parent        self-referential (sub-runs)
    Schedule  → Runs + Lock   one-to-many + one-to-one
    Source    → Fetches + Cache  multi-child navigation
    Alert     → Deliveries    routing audit trail
    WorkflowRun → Steps + Events  orchestration graph

ARCHITECTURE
────────────
    ┌─────────────┐     .events     ┌─────────────┐
    │ Execution   │─────────────▶│   Event     │
    └─────────────┘              │  .execution │
          │ .parent             └─────────────┘
          ▼
    ┌─────────────┐
    │ Execution   │  (self-referential)
    └─────────────┘

    Cascade delete-orphan means deleting an Execution
    automatically deletes its Events.

Requires: pip install sqlalchemy (or: pip install spine-core[sqlalchemy])

Run: python examples/09_data_layer/09_orm_relationships.py

See Also:
    08_orm_integration — basic ORM setup and session usage
    10_repository_bridge — BaseRepository over ORM sessions
    11_orm_vs_dialect — when to use ORM vs raw SQL
"""

from __future__ import annotations

import datetime

from spine.core.orm import SpineBase, SpineSession, create_spine_engine
from spine.core.orm.tables import (
    AlertChannelTable,
    AlertDeliveryTable,
    AlertTable,
    ExecutionEventTable,
    ExecutionTable,
    ScheduleLockTable,
    ScheduleRunTable,
    ScheduleTable,
    SourceCacheTable,
    SourceFetchTable,
    SourceTable,
    WorkflowEventTable,
    WorkflowRunTable,
    WorkflowStepTable,
)

NOW = datetime.datetime.now()


def main() -> None:
    engine = create_spine_engine("sqlite:///:memory:", echo=False)
    SpineBase.metadata.create_all(engine)
    print("=" * 60)
    print("ORM Relationship Navigation")
    print("=" * 60)

    with SpineSession(bind=engine) as session:
        # ── 1. Execution ↔ Events (bidirectional) ──────────────
        print("\n--- 1. Execution ↔ Events (bidirectional) ---")

        parent_exec = ExecutionTable(
            id="exec-001", workflow="sec-filings", lane="normal",
            trigger_source="api", status="completed",
            created_at=NOW, retry_count=0,
        )
        session.add(parent_exec)

        # Add events — relationship auto-links via execution_id FK
        for i, event_type in enumerate(["started", "progress", "completed"], 1):
            session.add(ExecutionEventTable(
                id=f"ev-{i:03d}", execution_id="exec-001",
                event_type=event_type, timestamp=NOW,
            ))
        session.commit()

        # Navigate parent → children
        loaded = session.get(ExecutionTable, "exec-001")
        print(f"  Execution '{loaded.id}' has {len(loaded.events)} events:")
        for ev in loaded.events:
            print(f"    {ev.id}: {ev.event_type}")

        # Navigate child → parent (back_populates)
        first_event = loaded.events[0]
        print(f"  Event '{first_event.id}' → execution: {first_event.execution.id}")

        # ── 2. Self-referential parent ──────────────────────────
        print("\n--- 2. Self-referential Parent Execution ---")

        child_exec = ExecutionTable(
            id="exec-002", workflow="sec-filings-retry", lane="normal",
            trigger_source="retry", status="running",
            created_at=NOW, retry_count=1,
            parent_execution_id="exec-001",  # FK to parent
        )
        session.add(child_exec)
        session.commit()

        child = session.get(ExecutionTable, "exec-002")
        print(f"  Child '{child.id}' parent → '{child.parent.id}' "
              f"(workflow: {child.parent.workflow})")

        # ── 3. Schedule → Runs + Lock ──────────────────────────
        print("\n--- 3. Schedule → Runs + Lock ---")

        schedule = ScheduleTable(
            id="sch-daily", name="daily-ingest",
            target_name="sec-filings", schedule_type="cron",
            cron_expression="0 6 * * *", timezone="US/Eastern",
            enabled=True, max_instances=1,
            misfire_grace_seconds=300, version=1,
        )
        session.add(schedule)

        # Two historical runs
        for j in range(1, 3):
            session.add(ScheduleRunTable(
                id=f"sr-{j:03d}", schedule_id="sch-daily",
                schedule_name="daily-ingest",
                scheduled_at=NOW, status="COMPLETED",
            ))

        # Active lock (uselist=False → single object, not a list)
        session.add(ScheduleLockTable(
            schedule_id="sch-daily", locked_by="worker-01",
            locked_at=NOW, expires_at=NOW,
        ))
        session.commit()

        sch = session.get(ScheduleTable, "sch-daily")
        print(f"  Schedule '{sch.name}' has {len(sch.runs)} runs")
        if sch.lock:
            print(f"  Lock held by: {sch.lock.locked_by}")
        else:
            print("  No active lock")

        # ── 4. Source → Fetches + Cache ────────────────────────
        print("\n--- 4. Source → Fetches + Cache ---")

        source = SourceTable(
            id="src-edgar", name="SEC EDGAR",
            source_type="api",
            config_json={"base_url": "https://efts.sec.gov"},
            enabled=True,
        )
        session.add(source)

        session.add(SourceFetchTable(
            id="sf-001", source_id="src-edgar",
            source_name="SEC EDGAR", source_type="api",
            source_locator="https://efts.sec.gov/LATEST/search-index",
            status="ok", record_count=150,
            started_at=NOW,
        ))

        session.add(SourceCacheTable(
            cache_key="edgar-full-index-2026",
            source_id="src-edgar",
            source_type="api",
            source_locator="https://efts.sec.gov/LATEST/search-index",
            content_hash="sha256:abc123",
            content_size=1024,
            fetched_at=NOW,
        ))
        session.commit()

        src = session.get(SourceTable, "src-edgar")
        print(f"  Source '{src.name}': "
              f"{len(src.fetches)} fetches, "
              f"{len(src.cache_entries)} cache entries")
        print(f"    Latest fetch: {src.fetches[0].record_count} records")

        # ── 5. Alert → Deliveries ──────────────────────────────
        print("\n--- 5. Alert → Deliveries ---")

        channel = AlertChannelTable(
            id="ch-slack", name="eng-alerts",
            channel_type="slack",
            config_json={"webhook": "https://hooks.slack.com/xxx"},
            enabled=True, throttle_minutes=15,
            consecutive_failures=0,
        )
        session.add(channel)

        alert = AlertTable(
            id="alert-001", severity="ERROR",
            title="Pipeline failed", message="sec-filings timed out",
            source="scheduler", execution_id="exec-001",
        )
        session.add(alert)

        session.add(AlertDeliveryTable(
            id="ad-001", alert_id="alert-001",
            channel_id="ch-slack", channel_name="eng-alerts",
            attempt=1, status="DELIVERED",
        ))
        session.commit()

        al = session.get(AlertTable, "alert-001")
        print(f"  Alert '{al.title}' → {len(al.deliveries)} delivery(ies)")
        print(f"    Channel: {al.deliveries[0].channel_name}, "
              f"status: {al.deliveries[0].status}")

        # ── 6. WorkflowRun → Steps + Events ───────────────────
        print("\n--- 6. WorkflowRun → Steps + Events ---")

        wf_run = WorkflowRunTable(
            run_id="wf-001", workflow_name="daily-pipeline",
            domain="sec", status="COMPLETED", triggered_by="scheduler",
        )
        session.add(wf_run)

        for k, step_name in enumerate(["fetch", "validate", "load"], 1):
            session.add(WorkflowStepTable(
                step_id=f"ws-{k:03d}", run_id="wf-001",
                step_name=step_name, step_type="pipeline",
                step_order=k, status="COMPLETED",
            ))

        session.add(WorkflowEventTable(
            run_id="wf-001", event_type="workflow_started",
        ))
        session.add(WorkflowEventTable(
            run_id="wf-001", event_type="workflow_completed",
        ))
        session.commit()

        wf = session.get(WorkflowRunTable, "wf-001")
        print(f"  Workflow '{wf.workflow_name}': "
              f"{len(wf.steps)} steps, {len(wf.events)} events")
        for step in sorted(wf.steps, key=lambda s: s.step_order):
            print(f"    Step {step.step_order}: {step.step_name} → {step.status}")

    print("\n" + "=" * 60)
    print("Done — all 6 relationship groups navigated successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()
