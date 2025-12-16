#!/usr/bin/env python3
"""Finance Adjustments — Factor-based adjustment math for per-share metrics.

Demonstrates spine-core's financial adjustment primitives:
1. AdjustmentMethod enum (corporate action types)
2. AdjustmentFactor — single factor with adjust/unadjust
3. AdjustmentChain — composing multiple factors
4. Point-in-time adjustment with adjust_as_of()
5. Chain operations: append, merge, factors_between

Real-World Context:
    Apple's stock price history shows $600+ per share before 2014,
    then $100 after the 7-for-1 split.  If your charting tool doesn't
    apply adjustment factors, the price chart has a massive cliff that
    doesn't reflect any real loss.  Similarly, EPS comparisons across
    quarters that straddle a split are meaningless without adjustment.

    This module provides the composable math: individual factors per
    corporate action, composite chains for cumulative adjustment, and
    adjust_as_of() for point-in-time queries ("what was the adjusted
    price as of March 2025, before the June split took effect?").

Run: python examples/01_core/21_finance_adjustments.py
"""

from datetime import date

from spine.core.finance.adjustments import (
    AdjustmentChain,
    AdjustmentFactor,
    AdjustmentMethod,
)


def main():
    print("=" * 60)
    print("Finance Adjustments — Per-Share Adjustment Math")
    print("=" * 60)

    # ── 1. AdjustmentMethod enum ────────────────────────────────
    print("\n--- 1. AdjustmentMethod enum ---")
    for method in AdjustmentMethod:
        print(f"    {method.name:20s} = {method.value}")

    # ── 2. Single AdjustmentFactor ──────────────────────────────
    print("\n--- 2. Single AdjustmentFactor (2-for-1 split) ---")
    split = AdjustmentFactor(
        effective_date=date(2025, 6, 15),
        factor=2.0,
        method=AdjustmentMethod.SPLIT,
        description="2-for-1 stock split",
        entity_key="AAPL",
    )
    print(f"  Date:    {split.effective_date}")
    print(f"  Factor:  {split.factor}")
    print(f"  Method:  {split.method.value}")
    print(f"  Entity:  {split.entity_key}")

    pre_split_price = 200.0
    post_split_price = split.adjust(pre_split_price)
    print(f"\n  Pre-split price:  ${pre_split_price:.2f}")
    print(f"  Post-split price: ${post_split_price:.2f}")
    print(f"  Inverse factor:   {split.inverse_factor}")
    print(f"  Unadjust back:    ${split.unadjust(post_split_price):.2f}")

    # ── 3. Reverse split ────────────────────────────────────────
    print("\n--- 3. Reverse split (1-for-10) ---")
    reverse = AdjustmentFactor(
        effective_date=date(2025, 3, 1),
        factor=0.1,
        method=AdjustmentMethod.REVERSE_SPLIT,
        description="1-for-10 reverse split",
    )
    print(f"  $5.00 pre-reverse  → ${reverse.adjust(5.0):.2f} post-reverse")
    print(f"  $0.50 post-reverse → ${reverse.unadjust(0.5):.2f} restored")

    # ── 4. AdjustmentChain ──────────────────────────────────────
    print("\n--- 4. AdjustmentChain (AAPL history example) ---")
    # Hypothetical: 2-for-1 in Jan, then 4-for-1 in June
    chain = AdjustmentChain(
        factors=[
            AdjustmentFactor(date(2025, 1, 15), 2.0, AdjustmentMethod.SPLIT,
                             "2-for-1 split"),
            AdjustmentFactor(date(2025, 6, 15), 4.0, AdjustmentMethod.SPLIT,
                             "4-for-1 split"),
        ],
        entity_key="AAPL",
    )
    print(f"  Entity:           {chain.entity_key}")
    print(f"  Factors:          {len(chain.factors)}")
    print(f"  Composite factor: {chain.composite_factor}  (2 × 4 = 8)")
    print(f"  Inverse:          {chain.inverse_composite_factor}")

    original_price = 800.0
    adjusted = chain.adjust(original_price)
    restored = chain.unadjust(adjusted)
    print(f"\n  Original:  ${original_price:.2f}")
    print(f"  Adjusted:  ${adjusted:.2f}")
    print(f"  Restored:  ${restored:.2f}")

    # ── 5. Point-in-time adjustment ─────────────────────────────
    print("\n--- 5. adjust_as_of() — partial chain ---")
    # Only the first split (2x) applies as of March 2025
    as_of_march = chain.adjust_as_of(800.0, date(2025, 3, 1))
    # Both splits (8x) apply as of December 2025
    as_of_dec = chain.adjust_as_of(800.0, date(2025, 12, 31))
    # No splits apply as of 2024
    as_of_2024 = chain.adjust_as_of(800.0, date(2024, 12, 31))
    print(f"  As of 2024-12-31: ${as_of_2024:.2f}  (no splits)")
    print(f"  As of 2025-03-01: ${as_of_march:.2f}  (1 split)")
    print(f"  As of 2025-12-31: ${as_of_dec:.2f}  (2 splits)")

    # ── 6. Chain composition: append ────────────────────────────
    print("\n--- 6. Append to chain ---")
    dividend_factor = AdjustmentFactor(
        date(2025, 9, 1), 1.02, AdjustmentMethod.STOCK_DIVIDEND,
        "2% stock dividend",
    )
    extended = chain.append(dividend_factor)
    print(f"  Original chain: {len(chain.factors)} factors, composite={chain.composite_factor}")
    print(f"  Extended chain: {len(extended.factors)} factors, composite={extended.composite_factor:.2f}")

    # ── 7. Chain composition: merge ─────────────────────────────
    print("\n--- 7. Merge two chains ---")
    chain_b = AdjustmentChain(
        factors=[
            AdjustmentFactor(date(2026, 1, 1), 3.0, AdjustmentMethod.SPLIT,
                             "3-for-1 split"),
        ],
    )
    merged = chain.merge(chain_b)
    print(f"  Chain A: {chain.composite_factor}")
    print(f"  Chain B: {chain_b.composite_factor}")
    print(f"  Merged:  {merged.composite_factor}  (8 × 3 = 24)")

    # ── 8. Filter factors by date range ─────────────────────────
    print("\n--- 8. factors_between() ---")
    h1_factors = chain.factors_between(date(2025, 1, 1), date(2025, 6, 30))
    print(f"  Factors in H1 2025: {len(h1_factors)}")
    for f in h1_factors:
        print(f"    {f.effective_date}: {f.factor}x ({f.description})")

    # ── 9. Sorted factors ───────────────────────────────────────
    print("\n--- 9. Sorted factors ---")
    # Create out-of-order chain
    unordered = AdjustmentChain(factors=[
        AdjustmentFactor(date(2025, 12, 1), 5.0, AdjustmentMethod.SPLIT),
        AdjustmentFactor(date(2025, 1, 1), 2.0, AdjustmentMethod.SPLIT),
        AdjustmentFactor(date(2025, 6, 1), 3.0, AdjustmentMethod.SPLIT),
    ])
    for f in unordered.sorted_factors:
        print(f"    {f.effective_date}: {f.factor}x")

    print("\n" + "=" * 60)
    print("[OK] Finance adjustments example complete")


if __name__ == "__main__":
    main()
