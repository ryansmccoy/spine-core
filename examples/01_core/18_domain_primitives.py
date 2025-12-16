#!/usr/bin/env python3
"""Enums and Timestamps — Shared Domain Primitives for the Spine Ecosystem.

================================================================================
WHY SHARED ENUMS AND TIMESTAMPS?
================================================================================

In a multi-project ecosystem (spine-core, entityspine, feedspine, etc.),
every project needs the same domain primitives.  Without shared definitions::

    # entityspine uses "active"
    entity.status = "active"

    # feedspine uses "ACTIVE"
    feed.status = "ACTIVE"

    # API returns "Active"
    response.status = "Active"

    # Which is canonical?  String comparison fails silently.

Spine-core provides **canonical enums** used across all projects::

    from spine.core.enums import CaseStatus
    entity.status = CaseStatus.ACTIVE  # Type-safe, IDE-autocomplete


================================================================================
KEY PRIMITIVES
================================================================================

**ULID — Universally Unique Lexicographically Sortable Identifier**::

    ULID: 01HYPE3KWZX1B2C3D4E5F6G7H8
          ├─────────┤├─────────────┤
          timestamp   randomness

    Properties:
    - Sorts chronologically (unlike UUID v4)
    - 128-bit compatible with UUID
    - Generated with new_ulid() → "01HYPE3K..."
    - Encodes creation time (extractable)

**ISO 8601 Timestamps**::

    now_iso()      → "2025-12-26T14:30:00+00:00"
    parse_iso(s)   → datetime(2025, 12, 26, 14, 30, tzinfo=UTC)

    Always UTC.  Never naive datetimes.  Never timezone ambiguity.


================================================================================
ENUM CATEGORIES
================================================================================

::

    ┌──────────────────────┬────────────────────────────────────────────┐
    │ Enum                 │ Purpose                                    │
    ├──────────────────────┼────────────────────────────────────────────┤
    │ EventType            │ CREATED, UPDATED, ENRICHED, MERGED, etc.  │
    │ EventStatus          │ PENDING, PROCESSING, COMPLETED, FAILED    │
    │ RunStatus            │ PENDING, RUNNING, COMPLETED, FAILED       │
    │ CaseStatus           │ ACTIVE, INACTIVE, SUSPENDED, DISSOLVED    │
    │ CaseType             │ CORPORATE, INDIVIDUAL, PARTNERSHIP        │
    │ VendorNamespace      │ SEC, FINRA, BLOOMBERG, REFINITIV          │
    │ DataQualitySeverity  │ INFO, WARNING, ERROR, CRITICAL            │
    │ ProvenanceKind       │ MANUAL, LLM, AUTOMATED, INFERRED         │
    └──────────────────────┴────────────────────────────────────────────┘


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/18_domain_primitives.py

See Also:
    - :mod:`spine.core.enums` — All domain enums
    - :mod:`spine.core.timestamps` — ULID generation, ISO 8601 helpers
"""

import time

from spine.core.enums import (
    CaseStatus,
    CaseType,
    DataQualitySeverity,
    EventStatus,
    EventType,
    ProvenanceKind,
    RunStatus,
    VendorNamespace,
)
from spine.core.timestamps import from_iso8601, generate_ulid, to_iso8601, utc_now


def main():
    print("=" * 60)
    print("Enums and Timestamps")
    print("=" * 60)

    # ── 1. ULID generation ──────────────────────────────────────
    print("\n--- 1. ULID generation ---")
    ids = [generate_ulid() for _ in range(5)]
    for i, uid in enumerate(ids):
        print(f"  [{i}] {uid} (len={len(uid)})")

    # ULIDs are time-sortable
    print(f"  Sorted == original order: {ids == sorted(ids)}")

    # Generate with small delay to show time component changes
    time.sleep(0.01)
    later_id = generate_ulid()
    print(f"  Later ULID > earlier: {later_id > ids[0]}")

    # ── 2. Timestamp utilities ──────────────────────────────────
    print("\n--- 2. Timestamps ---")
    now = utc_now()
    print(f"  UTC now: {now}")

    iso_str = to_iso8601(now)
    print(f"  ISO 8601: {iso_str}")

    restored = from_iso8601(iso_str)
    print(f"  Round-trip: {restored == now}")

    # None handling
    print(f"  to_iso8601(None) = {to_iso8601(None)}")
    print(f"  from_iso8601(None) = {from_iso8601(None)}")

    # ── 3. EventType (47 values) ────────────────────────────────
    print("\n--- 3. EventType ---")
    event_categories = {
        "Corporate Actions": [EventType.MERGER_ACQUISITION, EventType.SPINOFF, EventType.RESTRUCTURING],
        "Earnings":          [EventType.EARNINGS_RELEASE, EventType.EARNINGS_CALL, EventType.EARNINGS_GUIDANCE],
        "Stock Events":      [EventType.STOCK_SPLIT, EventType.SHARE_BUYBACK, EventType.IPO],
        "Risk Events":       [EventType.CYBER, EventType.DATA_BREACH, EventType.SUPPLY_CHAIN],
        "Management":        [EventType.CEO_CHANGE, EventType.CFO_CHANGE, EventType.BOARD],
    }
    for category, events in event_categories.items():
        values = [e.value for e in events]
        print(f"  {category}: {values}")
    print(f"  Total EventType values: {len(EventType)}")

    # ── 4. EventStatus lifecycle ────────────────────────────────
    print("\n--- 4. EventStatus lifecycle ---")
    event = {
        "type": EventType.EARNINGS_RELEASE,
        "company": "AAPL",
        "status": EventStatus.ANNOUNCED,
    }
    print(f"  Event: {event['type'].value} for {event['company']}")
    for status in [EventStatus.ANNOUNCED, EventStatus.IN_PROGRESS, EventStatus.COMPLETED]:
        event["status"] = status
        print(f"    -> {status.value}")

    # ── 5. VendorNamespace crosswalk ────────────────────────────
    print("\n--- 5. VendorNamespace crosswalk ---")
    crosswalk = {
        "entity": "Apple Inc.",
        "identifiers": {
            VendorNamespace.SEC: "0000320193",
            VendorNamespace.BLOOMBERG: "AAPL US Equity",
            VendorNamespace.REUTERS: "AAPL.O",
            VendorNamespace.OPENFIGI: "BBG000B9XRY4",
        },
    }
    print(f"  Entity: {crosswalk['entity']}")
    for vendor, identifier in crosswalk["identifiers"].items():
        print(f"    {vendor.value:12s} -> {identifier}")

    # ── 6. RunStatus ────────────────────────────────────────────
    print("\n--- 6. RunStatus ---")
    for status in RunStatus:
        print(f"  {status.value}")

    # ── 7. DataQualitySeverity ──────────────────────────────────
    print("\n--- 7. DataQualitySeverity ---")
    for sev in DataQualitySeverity:
        print(f"  {sev.value}")

    # ── 8. ProvenanceKind ───────────────────────────────────────
    print("\n--- 8. ProvenanceKind ---")
    for pk in ProvenanceKind:
        print(f"  {pk.value}")

    # ── 9. Legal enums ──────────────────────────────────────────
    print("\n--- 9. Legal enums ---")
    case = {"type": CaseType.INVESTIGATION, "status": CaseStatus.OPEN}
    print(f"  Case: {case['type'].value} ({case['status'].value})")
    case["status"] = CaseStatus.SETTLED
    print(f"  Updated: {case['status'].value}")

    print("\n" + "=" * 60)
    print("[OK] Enums and timestamps example complete")


if __name__ == "__main__":
    main()
