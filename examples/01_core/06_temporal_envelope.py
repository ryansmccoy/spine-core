#!/usr/bin/env python3
"""Temporal Envelope — PIT-correct timestamp wrappers and bi-temporal records.

Demonstrates spine-core's temporal envelope primitives:
1. Creating a TemporalEnvelope with 4-timestamp semantics
2. Point-in-time queries (known_as_of, effective_as_of, published_as_of)
3. Factory helpers (now_envelope)
4. BiTemporalRecord with valid_time + system_time axes
5. Supersede workflow for corrections (close old, create new)

Real-World Context:
    Every financial data pipeline faces the "which timestamp?" problem.
    When Apple reports EPS on Jan 30 for its Q4 ending Dec 31, the SEC
    filing is published Jan 31, Bloomberg distributes it Feb 1, and your
    pipeline ingests it Feb 2.  Four different dates — and using the wrong
    one causes look-ahead bias in backtests or stale data in live dashboards.

    TemporalEnvelope makes these four timestamps explicit on every record.
    BiTemporalRecord extends this with full bi-temporal versioning so you
    can answer: "What did we know about AAPL's EPS as of last Tuesday?"

Run: python examples/01_core/06_temporal_envelope.py
"""

from datetime import datetime, timedelta, timezone

from spine.core.temporal_envelope import BiTemporalRecord, TemporalEnvelope


def main():
    print("=" * 60)
    print("Temporal Envelope & Bi-Temporal Records")
    print("=" * 60)

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    last_week = now - timedelta(days=7)

    # ── 1. Create a 4-timestamp envelope ────────────────────────
    print("\n--- 1. TemporalEnvelope (4 timestamps) ---")
    env = TemporalEnvelope(
        payload={"ticker": "AAPL", "eps": 1.52},
        event_time=last_week,
        publish_time=yesterday,
        ingest_time=now,
    )
    print(f"  Payload:      {env.payload}")
    print(f"  Event time:   {env.event_time.date()}")
    print(f"  Publish time: {env.publish_time.date()}")
    print(f"  Ingest time:  {env.ingest_time.date()}")
    print(f"  Effective:    {env.effective_time.date()}  (defaults to event_time)")

    # ── 2. Point-in-time queries ────────────────────────────────
    print("\n--- 2. Point-in-time queries ---")
    # Was this known as of yesterday?
    print(f"  Known as of yesterday?    {env.known_as_of(yesterday)}")
    # Not known as of two weeks ago
    two_weeks_ago = now - timedelta(days=14)
    print(f"  Known as of 2 weeks ago?  {env.known_as_of(two_weeks_ago)}")
    # Was it effective as of yesterday?
    print(f"  Effective as of yesterday? {env.effective_as_of(yesterday)}")
    # Was it published as of today?
    print(f"  Published as of today?     {env.published_as_of(now)}")

    # ── 3. Factory helper: now_envelope ─────────────────────────
    print("\n--- 3. now_envelope() factory ---")
    quick = TemporalEnvelope.now_envelope(
        payload={"metric": "revenue", "value": 94_930_000_000},
    )
    print(f"  Payload:    {quick.payload}")
    print(f"  All times:  {quick.event_time == quick.publish_time == quick.ingest_time}")
    print(f"  Timestamps: {quick.timestamps_dict().keys()}")

    # ── 4. Serialisation round-trip ─────────────────────────────
    print("\n--- 4. timestamps_dict() ---")
    ts = env.timestamps_dict()
    for key, val in ts.items():
        print(f"  {key}: {val}")

    # ── 5. BiTemporalRecord ─────────────────────────────────────
    print("\n--- 5. BiTemporalRecord (valid + system axes) ---")
    rec = BiTemporalRecord(
        record_id="fact-001",
        entity_key="AAPL",
        valid_from=last_week,
        valid_to=None,
        system_from=now,
        system_to=None,
        payload={"ticker": "AAPL", "eps": 1.52},
    )
    print(f"  Record ID:    {rec.record_id}")
    print(f"  Valid from:   {rec.valid_from.date()}")
    print(f"  Valid to:     {rec.valid_to}  (None = still valid)")
    print(f"  System from:  {rec.system_from.date()}")
    print(f"  System to:    {rec.system_to}  (None = current version)")
    print(f"  Is current?   {rec.is_current}")

    # ── 6. Temporal queries on BiTemporalRecord ─────────────────
    print("\n--- 6. Bi-temporal queries ---")
    print(f"  Valid at yesterday?  {rec.valid_at(yesterday)}")
    print(f"  Valid at 2w ago?     {rec.valid_at(two_weeks_ago)}")
    print(f"  Known at now?        {rec.known_at(now)}")
    print(f"  As-of (valid=yesterday, known=now)? {rec.as_of(yesterday, now)}")

    # ── 7. Supersede workflow (correction) ──────────────────────
    print("\n--- 7. Supersede (correction workflow) ---")
    print(f"  Original: eps={rec.payload['eps']}")
    closed_old, new_version = rec.supersede(
        new_record_id="fact-002",
        new_payload={"ticker": "AAPL", "eps": 1.46},
        correction_time=now,
    )
    print(f"  Old closed:   system_to={closed_old.system_to is not None}, is_current={closed_old.is_current}")
    print(f"  New version:  eps={new_version.payload['eps']}, is_current={new_version.is_current}")
    print(f"  New record ID: {new_version.record_id}")

    print("\n" + "=" * 60)
    print("[OK] Temporal envelope example complete")


if __name__ == "__main__":
    main()
