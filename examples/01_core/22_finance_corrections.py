#!/usr/bin/env python3
"""Finance Corrections — Why-an-observation-changed taxonomy with audit trail.

Demonstrates spine-core's financial correction primitives:
1. CorrectionReason enum (9 standard reasons)
2. CorrectionRecord — immutable correction with auto-generated ID
3. Delta and percentage change calculations
4. Serialisation to dict for DB/JSON storage
5. Edge cases (zero original, large corrections)

Real-World Context:
    Financial data changes after publication more often than expected.
    Bloomberg and Zacks may report different "actual" EPS for the same
    quarter (see feedspine estimates-vs-actuals).  When Apple files a
    10-K/A (amended annual report) revising diluted EPS from $1.52 to
    $1.46, every downstream consumer — dashboards, models, compliance
    reports — needs to know what changed, by how much, and why.

    CorrectionRecord captures this as a first-class concept: old value,
    new value, reason (RESTATEMENT, DATA_ERROR, VENDOR_CORRECTION, etc.),
    delta, pct_change, and full audit trail.  Never silently overwrite.

Run: python examples/01_core/22_finance_corrections.py
"""

from spine.core.finance.corrections import CorrectionReason, CorrectionRecord


def main():
    print("=" * 60)
    print("Finance Corrections — Observation Change Tracking")
    print("=" * 60)

    # ── 1. CorrectionReason enum ────────────────────────────────
    print("\n--- 1. CorrectionReason enum ---")
    for reason in CorrectionReason:
        print(f"    {reason.name:22s} = {reason.value}")

    # ── 2. Create a correction record ───────────────────────────
    print("\n--- 2. EPS restatement ---")
    rec = CorrectionRecord.create(
        entity_key="AAPL",
        field_name="eps_diluted",
        original_value=1.52,
        corrected_value=1.46,
        reason=CorrectionReason.RESTATEMENT,
        corrected_by="sec_filing_parser",
        source_ref="10-K/A filed 2025-03-15",
        notes="Restated per amended annual filing",
    )
    print(f"  ID:           {rec.correction_id}")
    print(f"  Entity:       {rec.entity_key}")
    print(f"  Field:        {rec.field_name}")
    print(f"  Original:     {rec.original_value}")
    print(f"  Corrected:    {rec.corrected_value}")
    print(f"  Reason:       {rec.reason.value}")
    print(f"  Corrected by: {rec.corrected_by}")
    print(f"  Source ref:   {rec.source_ref}")
    print(f"  Timestamp:    {rec.corrected_at}")

    # ── 3. Delta and percentage calculations ────────────────────
    print("\n--- 3. Delta & percentage ---")
    print(f"  Delta:        {rec.delta:.4f}")
    print(f"  Pct change:   {rec.pct_change:.4%}")
    print(f"  Abs pct:      {rec.abs_pct_change:.4%}")

    # ── 4. Revenue correction (large numbers) ───────────────────
    print("\n--- 4. Revenue correction ---")
    rev = CorrectionRecord.create(
        entity_key="MSFT",
        field_name="revenue",
        original_value=56_189_000_000,
        corrected_value=56_517_000_000,
        reason=CorrectionReason.LATE_REPORTING,
        corrected_by="vendor_feed_reconciler",
        metadata={"filing_id": "0001564590-25-012345", "quarter": "Q1-2025"},
    )
    print(f"  Entity:    {rev.entity_key}")
    print(f"  Delta:     ${rev.delta:,.0f}")
    print(f"  Pct:       {rev.pct_change:.4%}")
    print(f"  Metadata:  {rev.metadata}")

    # ── 5. Different correction reasons ─────────────────────────
    print("\n--- 5. Various correction types ---")
    corrections = [
        ("GOOG", "shares_outstanding", 1_000_000, 1_200_000,
         CorrectionReason.DATA_ERROR, "Vendor sent wrong share count"),
        ("TSLA", "pe_ratio", 45.2, 42.8,
         CorrectionReason.METHODOLOGY_CHANGE, "Switched to trailing EPS"),
        ("AMZN", "revenue", 143_083_000_000, 143_083_000_000,
         CorrectionReason.ROUNDING, "No material change, rounding only"),
        ("META", "eps_basic", 4.71, 4.39,
         CorrectionReason.VENDOR_CORRECTION, "Bloomberg correction notice"),
    ]
    for entity, field, old, new, reason, notes in corrections:
        c = CorrectionRecord.create(
            entity_key=entity,
            field_name=field,
            original_value=old,
            corrected_value=new,
            reason=reason,
            notes=notes,
        )
        pct = f"{c.pct_change:.2%}" if c.pct_change is not None else "N/A"
        print(f"    {entity:5s} {field:22s} {reason.value:22s} delta={c.delta:>15,.2f}  pct={pct}")

    # ── 6. Zero original (edge case) ───────────────────────────
    print("\n--- 6. Edge case: zero original ---")
    zero = CorrectionRecord.create(
        entity_key="STARTUP",
        field_name="revenue",
        original_value=0.0,
        corrected_value=1_500_000,
        reason=CorrectionReason.LATE_REPORTING,
    )
    print(f"  Delta:    {zero.delta:,.0f}")
    print(f"  Pct:      {zero.pct_change}  (None — division by zero avoided)")
    print(f"  Abs pct:  {zero.abs_pct_change}")

    # ── 7. Serialisation ────────────────────────────────────────
    print("\n--- 7. Serialise to dict ---")
    d = rec.to_dict()
    print(f"  Keys: {sorted(d.keys())}")
    print(f"  reason:       {d['reason']}")
    print(f"  corrected_at: {d['corrected_at']}")
    print(f"  Ready for JSON/DB storage: True")

    # ── 8. Immutability ─────────────────────────────────────────
    print("\n--- 8. Immutability (frozen dataclass) ---")
    try:
        rec.corrected_value = 9.99  # type: ignore[misc]
        print("  ERROR: should not reach here")
    except AttributeError:
        print("  Correctly blocked mutation (frozen=True)")

    print("\n" + "=" * 60)
    print("[OK] Finance corrections example complete")


if __name__ == "__main__":
    main()
