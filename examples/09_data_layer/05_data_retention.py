#!/usr/bin/env python3
"""Data Retention — Purge old records with configurable policies.

WHY DATA RETENTION
──────────────────
Execution logs, dead letters, and anomaly records grow endlessly.
Without automated purging, queries slow down, storage fills up, and
GDPR/compliance rules are violated.  The retention module provides
configurable per-table policies with a single purge_all() entry point.

ARCHITECTURE
────────────
    RetentionConfig
    ┌───────────────────────────────────┐
    │ core_executions:  30 days       │
    │ core_dead_letters: 90 days      │
    │ core_anomalies:   60 days       │
    │ core_events:      14 days       │
    └────────────────┬──────────────────┘
                     │ purge_all(conn, config)
                     ▼
    DELETE FROM table WHERE created_at < cutoff

    Individual functions: purge_executions(), purge_dead_letters()
    for targeted cleanup.

BEST PRACTICES
──────────────
• Run purge_all() on a daily or weekly schedule.
• Keep execution logs ≥ 30 days for post-mortem analysis.
• Keep DLQ entries ≥ 90 days for compliance.
• Monitor table counts before and after purge.

Run: python examples/09_data_layer/05_data_retention.py

See Also:
    02_execution/09_execution_ledger — what gets purged
    03_resilience/05_dead_letter_queue — DLQ retention
"""

import sqlite3
from datetime import datetime, timedelta, timezone

from spine.core.protocols import Connection
from spine.core.retention import (
    RetentionConfig,
    compute_cutoff,
    get_table_counts,
    purge_all,
    purge_executions,
)


def create_test_tables(conn: Connection):
    """Create minimal test versions of core tables."""
    conn.executescript("""
        CREATE TABLE core_executions (
            id TEXT PRIMARY KEY,
            pipeline TEXT,
            created_at TEXT
        );
        CREATE TABLE core_rejects (
            id INTEGER PRIMARY KEY,
            domain TEXT,
            created_at TEXT
        );
        CREATE TABLE core_quality (
            id INTEGER PRIMARY KEY,
            domain TEXT,
            created_at TEXT
        );
        CREATE TABLE core_anomalies (
            id INTEGER PRIMARY KEY,
            domain TEXT,
            created_at TEXT
        );
        CREATE TABLE core_work_items (
            id INTEGER PRIMARY KEY,
            domain TEXT,
            state TEXT,
            completed_at TEXT
        );
    """)


def insert_sample_data(conn: Connection):
    """Insert test data with mix of old and new timestamps."""
    now = datetime.now(timezone.utc)

    # Old data (100 days ago)
    old_ts = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%S")
    # Recent data (yesterday)
    recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

    # Insert old records
    for i in range(5):
        conn.execute(
            "INSERT INTO core_executions (id, pipeline, created_at) VALUES (?, ?, ?)",
            (f"old-exec-{i}", "test.pipeline", old_ts),
        )
        conn.execute(
            "INSERT INTO core_rejects (domain, created_at) VALUES (?, ?)",
            ("test.domain", old_ts),
        )
        conn.execute(
            "INSERT INTO core_quality (domain, created_at) VALUES (?, ?)",
            ("test.domain", old_ts),
        )
        conn.execute(
            "INSERT INTO core_anomalies (domain, created_at) VALUES (?, ?)",
            ("test.domain", old_ts),
        )
        conn.execute(
            "INSERT INTO core_work_items (domain, state, completed_at) VALUES (?, ?, ?)",
            ("test.domain", "COMPLETE", old_ts),
        )

    # Insert recent records
    for i in range(3):
        conn.execute(
            "INSERT INTO core_executions (id, pipeline, created_at) VALUES (?, ?, ?)",
            (f"new-exec-{i}", "test.pipeline", recent_ts),
        )
        conn.execute(
            "INSERT INTO core_rejects (domain, created_at) VALUES (?, ?)",
            ("test.domain", recent_ts),
        )

    conn.commit()


def main():
    print("=" * 60)
    print("Data Retention Example")
    print("=" * 60)

    conn = sqlite3.connect(":memory:")
    create_test_tables(conn)
    insert_sample_data(conn)

    # 1. Check table counts before purge
    print("\n1. Table counts before purge...")
    counts_before = get_table_counts(conn)
    for table, count in counts_before.items():
        print(f"   {table}: {count} rows")

    # 2. Compute cutoff dates
    print("\n2. Retention cutoff dates...")
    print(f"   30-day cutoff: {compute_cutoff(30)}")
    print(f"   90-day cutoff: {compute_cutoff(90)}")
    print(f"   180-day cutoff: {compute_cutoff(180)}")

    # 3. Individual table purge
    print("\n3. Individual purge - core_executions (90 days)...")
    result = purge_executions(conn, days=90)
    print(f"   Deleted: {result.deleted} rows")
    print(f"   Cutoff: {result.cutoff}")

    # 4. Check default retention config
    print("\n4. Default retention configuration...")
    config = RetentionConfig()
    print(f"   Executions: {config.executions} days")
    print(f"   Rejects: {config.rejects} days")
    print(f"   Quality: {config.quality} days")
    print(f"   Anomalies: {config.anomalies} days")
    print(f"   Work Items: {config.work_items} days")

    # 5. Purge all with custom config
    print("\n5. Purge all tables with custom config...")
    custom_config = RetentionConfig(
        executions=30,  # More aggressive
        rejects=30,
        quality=30,
        anomalies=90,   # Keep anomalies longer
        work_items=30,
    )
    report = purge_all(conn, config=custom_config)
    print(f"   Success: {report.success}")
    print(f"   Total deleted: {report.total_deleted}")
    for r in report.results:
        print(f"   - {r.table}: {r.deleted} deleted")

    # 6. Table counts after purge
    print("\n6. Table counts after purge...")
    counts_after = get_table_counts(conn)
    for table, count in counts_after.items():
        before = counts_before[table]
        print(f"   {table}: {before} -> {count} ({before - count} deleted)")

    # 7. Verify recent data preserved
    print("\n7. Recent data preserved...")
    cursor = conn.execute("SELECT id FROM core_executions WHERE id LIKE 'new-%'")
    recent_execs = cursor.fetchall()
    print(f"   Recent executions remaining: {len(recent_execs)}")

    cursor = conn.execute("SELECT COUNT(*) FROM core_rejects")
    print(f"   Recent rejects remaining: {cursor.fetchone()[0]}")

    conn.close()

    print("\n" + "=" * 60)
    print("Data Retention Example Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
