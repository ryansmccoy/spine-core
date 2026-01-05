"""
Example: Rolling Quality Gate in Action
========================================

This script demonstrates the history window quality gate for rolling calculations.
"""

import sqlite3
from datetime import date

from spine.domains.finra.otc_transparency.validators import (
    get_symbols_with_sufficient_history,
    require_history_window,
)


def setup_test_database():
    """Create test database with sample data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    
    conn.execute("""
        CREATE TABLE finra_otc_transparency_symbol_summary (
            week_ending TEXT,
            tier TEXT,
            symbol TEXT,
            total_volume INTEGER,
            total_trades INTEGER,
            venue_count INTEGER,
            capture_id TEXT,
            captured_at TEXT,
            calculated_at TEXT
        )
    """)
    
    # AAPL: Full 6-week history
    aapl_weeks = ["2025-12-05", "2025-12-12", "2025-12-19", "2025-12-26", "2026-01-02", "2026-01-09"]
    for week in aapl_weeks:
        conn.execute(
            """INSERT INTO finra_otc_transparency_symbol_summary
               VALUES (?, 'NMS_TIER_1', 'AAPL', 1000000, 5000, 3, 'cap1', '2026-01-04', '2026-01-04')""",
            (week,),
        )
    
    # MSFT: Only 3 weeks (insufficient)
    msft_weeks = ["2025-12-26", "2026-01-02", "2026-01-09"]
    for week in msft_weeks:
        conn.execute(
            """INSERT INTO finra_otc_transparency_symbol_summary
               VALUES (?, 'NMS_TIER_1', 'MSFT', 800000, 4000, 2, 'cap1', '2026-01-04', '2026-01-04')""",
            (week,),
        )
    
    # GOOGL: Full 6-week history
    for week in aapl_weeks:
        conn.execute(
            """INSERT INTO finra_otc_transparency_symbol_summary
               VALUES (?, 'NMS_TIER_1', 'GOOGL', 500000, 2500, 2, 'cap1', '2026-01-04', '2026-01-04')""",
            (week,),
        )
    
    conn.commit()
    return conn


def example_1_check_tier_history():
    """Example 1: Check if tier has sufficient history."""
    print("\n" + "="*80)
    print("Example 1: Check Tier-Level History")
    print("="*80)
    
    conn = setup_test_database()
    
    ok, missing = require_history_window(
        conn,
        table="finra_otc_transparency_symbol_summary",
        week_ending=date(2026, 1, 9),
        window_weeks=6,
        tier="NMS_TIER_1",
    )
    
    print(f"\nTier: NMS_TIER_1")
    print(f"Window: 6 weeks ending 2026-01-09")
    print(f"Has sufficient history: {ok}")
    if not ok:
        print(f"Missing weeks: {missing}")
    else:
        print("✅ Tier has complete 6-week history")
    
    conn.close()


def example_2_check_symbol_history():
    """Example 2: Check per-symbol history."""
    print("\n" + "="*80)
    print("Example 2: Check Per-Symbol History")
    print("="*80)
    
    conn = setup_test_database()
    
    symbols = ["AAPL", "MSFT", "GOOGL"]
    
    for symbol in symbols:
        ok, missing = require_history_window(
            conn,
            table="finra_otc_transparency_symbol_summary",
            week_ending=date(2026, 1, 9),
            window_weeks=6,
            tier="NMS_TIER_1",
            symbol=symbol,
        )
        
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"\n{symbol}: {status}")
        if not ok:
            print(f"  Missing weeks: {missing}")
            print(f"  ({len(missing)} weeks short)")
    
    conn.close()


def example_3_filter_valid_symbols():
    """Example 3: Get symbols with sufficient history."""
    print("\n" + "="*80)
    print("Example 3: Filter Symbols by History")
    print("="*80)
    
    conn = setup_test_database()
    
    valid_symbols = get_symbols_with_sufficient_history(
        conn,
        table="finra_otc_transparency_symbol_summary",
        week_ending=date(2026, 1, 9),
        window_weeks=6,
        tier="NMS_TIER_1",
    )
    
    print(f"\nTarget week: 2026-01-09")
    print(f"Window size: 6 weeks")
    print(f"Tier: NMS_TIER_1")
    print(f"\nSymbols with complete history: {sorted(valid_symbols)}")
    print(f"Total valid symbols: {len(valid_symbols)}")
    
    print("\n📊 What happens in rolling calculation:")
    print("   • AAPL: ✅ Compute rolling average")
    print("   • GOOGL: ✅ Compute rolling average")
    print("   • MSFT: ❌ Skip (only 3 weeks)")
    
    conn.close()


def example_4_production_workflow():
    """Example 4: Production workflow with quality gate."""
    print("\n" + "="*80)
    print("Example 4: Production Workflow")
    print("="*80)
    
    conn = setup_test_database()
    
    week_ending = date(2026, 1, 9)
    window_weeks = 6
    tier = "NMS_TIER_1"
    
    print(f"\n🔧 Running rolling calculation for {week_ending}")
    
    # Step 1: Tier-level check
    print("\nStep 1: Tier-level validation")
    has_sufficient, missing = require_history_window(
        conn,
        table="finra_otc_transparency_symbol_summary",
        week_ending=week_ending,
        window_weeks=window_weeks,
        tier=tier,
    )
    
    if not has_sufficient:
        print(f"❌ ERROR: Tier missing {len(missing)} weeks: {missing}")
        print("   → Skip entire tier, record ERROR anomaly, return early")
        return
    else:
        print("✅ Tier has sufficient data")
    
    # Step 2: Symbol-level filtering
    print("\nStep 2: Symbol-level filtering")
    valid_symbols = get_symbols_with_sufficient_history(
        conn,
        table="finra_otc_transparency_symbol_summary",
        week_ending=week_ending,
        window_weeks=window_weeks,
        tier=tier,
    )
    
    print(f"✅ Found {len(valid_symbols)} symbols with complete history: {sorted(valid_symbols)}")
    
    # Step 3: Compute rolling metrics (simulated)
    print("\nStep 3: Computing rolling metrics")
    computed = 0
    skipped = 0
    
    all_symbols = ["AAPL", "MSFT", "GOOGL"]
    for symbol in all_symbols:
        if symbol in valid_symbols:
            print(f"  ✅ {symbol}: Computing 6-week rolling average")
            computed += 1
        else:
            print(f"  ⚠️  {symbol}: Skipped (insufficient history)")
            skipped += 1
    
    print(f"\n📊 Results:")
    print(f"   Computed: {computed}")
    print(f"   Skipped: {skipped}")
    
    if skipped > 0:
        print(f"   → Record WARN anomaly: {skipped} symbols skipped")
    
    print("\n✅ Pipeline completed successfully")
    
    conn.close()


if __name__ == "__main__":
    print("\n" + "="*80)
    print("ROLLING QUALITY GATE EXAMPLES")
    print("="*80)
    print("\nThese examples show how the history window quality gate works")
    print("in rolling calculations to ensure data quality.\n")
    
    example_1_check_tier_history()
    example_2_check_symbol_history()
    example_3_filter_valid_symbols()
    example_4_production_workflow()
    
    print("\n" + "="*80)
    print("✅ All examples completed")
    print("="*80 + "\n")
