#!/usr/bin/env python3
"""Quality Checks — Automated Data Validation Framework.

================================================================================
WHY DATA QUALITY CHECKS?
================================================================================

Data pipelines fail silently. A pipeline can "succeed" while producing:
- Null values where there should be prices
- Duplicate records from overlapping runs
- Future dates from timezone bugs
- Negative trading volumes (impossible!)

These issues propagate downstream, causing:
- Wrong portfolio valuations
- Incorrect risk calculations
- Compliance violations
- Lost customer trust

**Quality checks** catch these issues BEFORE they reach production tables.


================================================================================
QUALITY CHECK ARCHITECTURE
================================================================================

::

    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
    │   Extract   │────►│  Quality    │────►│  Transform  │────►│    Load     │
    │             │     │   Runner    │     │             │     │             │
    └─────────────┘     └──────┬──────┘     └─────────────┘     └─────────────┘
                              │
                              ▼
                    ┌─────────────────────────────┐
                    │  Run Defined Checks:      │
                    │  - check_positive_prices  │
                    │  - check_no_nulls         │
                    │  - check_date_range       │
                    │  - check_referential_int  │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
              All Pass                       Any Fail
                    │                             │
                    ▼                             ▼
           ┌─────────────┐               ┌───────────────────┐
           │  Continue   │               │  Reject + Alert   │
           │  Pipeline   │               │  (optional: halt) │
           └─────────────┘               └───────────────────┘


================================================================================
QUALITY CATEGORIES AND SEVERITIES
================================================================================

::

    QualityCategory            Description
    ────────────────────────────────────────────────────────────────────
    COMPLETENESS    Are all expected records present?
    CONSISTENCY     Do values agree across sources/tables?
    VALIDITY        Are values within allowed ranges?
    UNIQUENESS      Are there unexpected duplicates?
    TIMELINESS      Is data arriving on schedule?
    ACCURACY        Does computed data match expectations?


    QualityStatus    Severity    Pipeline Action
    ────────────────────────────────────────────────────────────────────
    PASS            ✓           Continue processing
    WARN            ⚠           Continue, but log warning
    FAIL            ✗           Halt pipeline, reject batch
    SKIP            -           Check not applicable (e.g., empty data)


================================================================================
DATABASE SCHEMA: QUALITY RESULTS
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Table: core_quality_results                                            │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  id              SERIAL        PRIMARY KEY                              │
    │  execution_id    VARCHAR(36)   NOT NULL   -- Links to pipeline run     │
    │  check_name      VARCHAR(100)  NOT NULL   -- "check_positive_prices"   │
    │  category        VARCHAR(20)   NOT NULL   -- "validity", "completeness"│
    │  status          VARCHAR(10)   NOT NULL   -- "pass", "warn", "fail"    │
    │  message         TEXT          NOT NULL   -- Human-readable result     │
    │  expected_value  TEXT                     -- What we expected          │
    │  actual_value    TEXT                     -- What we got               │
    │  checked_at      TIMESTAMP     NOT NULL                                │
    │  duration_ms     INTEGER                  -- Check execution time      │
    └─────────────────────────────────────────────────────────────────────────┘

    -- Find all failed checks for today
    SELECT * FROM core_quality_results
    WHERE status = 'fail' AND checked_at > CURRENT_DATE;

    -- Quality trend over time
    SELECT DATE(checked_at), status, COUNT(*)
    FROM core_quality_results
    GROUP BY DATE(checked_at), status;


================================================================================
COMMON CHECK PATTERNS
================================================================================

**Completeness Check**::

    def check_all_symbols_present(ctx: dict) -> QualityResult:
        expected = set(ctx["expected_symbols"])
        actual = {r["symbol"] for r in ctx["records"]}
        missing = expected - actual
        if missing:
            return QualityResult(
                status=QualityStatus.FAIL,
                message=f"Missing {len(missing)} symbols",
                expected_value=list(expected),
                actual_value=list(missing),
            )
        return QualityResult(status=QualityStatus.PASS, message="All symbols present")

**Validity Check** (range bounds)::

    def check_prices_positive(ctx: dict) -> QualityResult:
        invalid = [r for r in ctx["records"] if r["price"] <= 0]
        if invalid:
            return QualityResult(
                status=QualityStatus.FAIL,
                message=f"{len(invalid)} records with non-positive prices",
                expected_value="price > 0",
                actual_value=[r["symbol"] for r in invalid[:10]],  # First 10
            )
        return QualityResult(status=QualityStatus.PASS, message="All prices positive")

**Uniqueness Check**::

    def check_no_duplicates(ctx: dict) -> QualityResult:
        keys = [(r["symbol"], r["date"]) for r in ctx["records"]]
        duplicates = [k for k, count in Counter(keys).items() if count > 1]
        if duplicates:
            return QualityResult(
                status=QualityStatus.FAIL,
                message=f"{len(duplicates)} duplicate keys found",
                actual_value=duplicates[:10],
            )
        return QualityResult(status=QualityStatus.PASS, message="No duplicates")


================================================================================
BEST PRACTICES
================================================================================

1. **Check early in the pipeline**::

       # Run quality checks BEFORE transformation
       raw_data = extract()
       results = runner.run(raw_data)  # Catch bad data early
       if results.has_failures:
           reject_batch(raw_data)
           return
       transformed = transform(raw_data)

2. **Use WARN for soft limits, FAIL for hard limits**::

       # Soft: unusual but acceptable
       if null_rate > 0.01:
           return QualityResult(status=QualityStatus.WARN, ...)
       # Hard: unacceptable
       if null_rate > 0.10:
           return QualityResult(status=QualityStatus.FAIL, ...)

3. **Include context in failure messages**::

       # BAD
       message="Check failed"

       # GOOD
       message=f"Found {len(invalid)} prices <= 0 out of {len(records)} total"

4. **Persist results for trend analysis**::

       # Track quality over time to catch gradual degradation
       runner.persist_results(conn, execution_id)


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/09_quality_checks.py

See Also:
    - :mod:`spine.core.quality` — QualityRunner, QualityCheck, QualityResult
    - :mod:`spine.core.anomaly` — AnomalyRecorder for outlier tracking
    - :mod:`spine.core.rejects` — Reject handling for failed records
"""
import sqlite3
from datetime import date
from spine.core import (
    QualityRunner,
    QualityCheck,
    QualityStatus,
    QualityCategory,
    QualityResult,
    WeekEnding,
    create_core_tables,
)


def main():
    print("=" * 60)
    print("Quality Check Examples")
    print("=" * 60)
    
    # === 1. Quality categories ===
    print("\n[1] Quality Categories")
    
    for cat in QualityCategory:
        print(f"  {cat.name}: {cat.value}")
    
    # === 2. Quality statuses ===
    print("\n[2] Quality Statuses")
    
    for status in QualityStatus:
        print(f"  {status.name}: {status.value}")
    
    # === 3. Define quality checks ===
    print("\n[3] Define Quality Checks")
    
    # Sample data
    records = [
        {"symbol": "AAPL", "price": 150.0, "volume": 1000000},
        {"symbol": "MSFT", "price": 350.0, "volume": 500000},
        {"symbol": "INVALID", "price": -10.0, "volume": 0},
        {"symbol": "GOOGL", "price": 140.0, "volume": 750000},
    ]
    
    # Define checks - check_fn takes a context dict and returns QualityResult
    def check_positive_prices(ctx: dict) -> QualityResult:
        """All prices must be positive."""
        data = ctx["records"]
        invalid = [r for r in data if r["price"] <= 0]
        if invalid:
            return QualityResult(
                status=QualityStatus.FAIL,
                message=f"Found {len(invalid)} records with non-positive prices",
                actual_value=[r["symbol"] for r in invalid],
                expected_value="all positive",
            )
        return QualityResult(
            status=QualityStatus.PASS,
            message=f"All {len(data)} records have positive prices",
        )
    
    def check_volume_threshold(ctx: dict) -> QualityResult:
        """Volume should exceed minimum threshold."""
        data = ctx["records"]
        min_volume = ctx.get("min_volume", 100)
        low_volume = [r for r in data if r["volume"] < min_volume]
        if low_volume:
            return QualityResult(
                status=QualityStatus.WARN,
                message=f"Found {len(low_volume)} records with low volume",
                actual_value=[r["symbol"] for r in low_volume],
                expected_value=f">= {min_volume}",
            )
        return QualityResult(
            status=QualityStatus.PASS,
            message=f"All {len(data)} records meet volume threshold",
        )
    
    # Run checks manually (without runner)
    print("\n  Running checks manually...")
    
    ctx = {"records": records}
    price_result = check_positive_prices(ctx)
    print(f"  Price check: {price_result.status.name} - {price_result.message}")
    
    volume_result = check_volume_threshold(ctx)
    print(f"  Volume check: {volume_result.status.name} - {volume_result.message}")
    
    # === 4. Using QualityCheck objects ===
    print("\n[4] Using QualityCheck Objects")
    
    checks = [
        QualityCheck(
            name="positive_prices",
            category=QualityCategory.INTEGRITY,
            check_fn=check_positive_prices,
        ),
        QualityCheck(
            name="volume_threshold",
            category=QualityCategory.BUSINESS_RULE,
            check_fn=check_volume_threshold,
        ),
    ]
    
    for check in checks:
        print(f"  Check: {check.name} (category: {check.category.name})")
    
    # === 5. QualityRunner (with database) ===
    print("\n[5] QualityRunner")
    
    conn = sqlite3.connect(":memory:")
    create_core_tables(conn)
    
    runner = QualityRunner(conn, domain="demo", execution_id="example-001")
    for check in checks:
        runner.add(check)
    
    context = {"records": records}
    partition_key = {"date": "2025-01-19"}
    results = runner.run_all(context, partition_key)
    
    print("  Results:")
    for name, status in results.items():
        print(f"    {name}: {status.name}")
    
    # Summary
    passed = sum(1 for s in results.values() if s == QualityStatus.PASS)
    warned = sum(1 for s in results.values() if s == QualityStatus.WARN)
    failed = sum(1 for s in results.values() if s == QualityStatus.FAIL)
    
    print(f"\n  Summary: {passed} passed, {warned} warnings, {failed} failed")
    
    # Quality gate
    if runner.has_failures():
        print(f"  ⚠ Quality gate FAILED: {runner.failures()}")
    else:
        print("  ✓ Quality gate passed")
    
    # === 6. Real-world: Weekly data quality ===
    print("\n[6] Real-world: Weekly Data Quality")
    
    we = WeekEnding.from_any_date(date.today())
    
    def check_record_count(ctx: dict) -> QualityResult:
        """Ensure minimum record count."""
        data = ctx["records"]
        min_count = ctx.get("min_count", 3)
        if len(data) < min_count:
            return QualityResult(
                status=QualityStatus.FAIL,
                message=f"Only {len(data)} records, expected at least {min_count}",
                actual_value=len(data),
                expected_value=min_count,
            )
        return QualityResult(
            status=QualityStatus.PASS,
            message=f"Record count {len(data)} meets minimum {min_count}",
            actual_value=len(data),
            expected_value=min_count,
        )
    
    weekly_checks = [
        QualityCheck(
            name=f"record_count_{we}",
            category=QualityCategory.COMPLETENESS,
            check_fn=check_record_count,
        ),
        QualityCheck(
            name=f"data_freshness_{we}",
            category=QualityCategory.COMPLETENESS,
            check_fn=lambda ctx: QualityResult(
                status=QualityStatus.PASS,
                message="Data is current",
            ),
        ),
    ]
    
    weekly_runner = QualityRunner(conn, domain="weekly_demo", execution_id="weekly-001")
    for check in weekly_checks:
        weekly_runner.add(check)
    
    results = weekly_runner.run_all(
        {"records": records, "min_count": 3},
        partition_key={"week_ending": str(we)},
    )
    
    print(f"  Week ending {we}:")
    for name, status in results.items():
        status_icon = "✓" if status == QualityStatus.PASS else "✗"
        print(f"    {status_icon} {name}: {status.name}")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("[OK] Quality Checks Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
