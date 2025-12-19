"""Managed Pipelines — import existing code, get full lifecycle management.

**This is spine-core's primary integration pattern.**

Take any existing Python functions — from notebooks, scripts, other
projects, or shared libraries — and wrap them into managed pipelines
that give you persistence, idempotency, observability, and queryable
execution history.  Your functions never import spine types.

Key concepts:

- ``ManagedWorkflow`` — fluent builder: ``.step().step().build()``
- ``ManagedPipeline``  — the built result: ``.run()``, ``.show()``,
  ``.history()``, ``.query_db()``
- ``manage()`` — one-liner shortcut for simple sequential pipelines

Database modes (set ``SPINE_EXAMPLES_DB`` env var):

- ``memory``   — (default) in-memory SQLite, fast, ephemeral
- ``file``     — persistent SQLite at ``examples/spine_examples.db``
- ``postgres`` — PostgreSQL via ``docker compose --profile standard up``

Sections:
    1 — ManagedWorkflow builder (fluent API)
    2 — manage() one-liner shortcut
    3 — Persistent mode with SQLite file
    4 — Partition-based idempotency
    5 — Querying execution data
    6 — Importing existing pipelines from external code

Run:
    python examples/04_orchestration/12_managed_workflow.py

Expected Output:
    Six sections demonstrating the full managed pipeline lifecycle.

See Also:
    - ``04_step_adapters.py`` — low-level adapter mechanics
    - ``08_tracked_runner.py``   — TrackedWorkflowRunner internals
    - :mod:`spine.orchestration.managed_workflow` — source module
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# ============================================================================
# SECTION 0 — Pure business functions (NO spine imports)
# ============================================================================
# These could live in any project, notebook, or shared library.
# They know nothing about workflows, persistence, or spine-core.


def fetch_sec_filing(cik: str, form_type: str = "10-K") -> dict:
    """Fetch SEC filing data (mock)."""
    filings = {
        "0000320193": {"company": "Apple Inc.", "revenue": 391_035_000_000, "net_income": 96_995_000_000},
        "0000789019": {"company": "Microsoft Corp.", "revenue": 245_122_000_000, "net_income": 88_136_000_000},
        "0001018724": {"company": "Amazon.com Inc.", "revenue": 574_785_000_000, "net_income": 30_425_000_000},
        "0001326801": {"company": "Meta Platforms", "revenue": 134_902_000_000, "net_income": 39_098_000_000},
    }
    data = filings.get(cik, {"company": "Unknown", "revenue": 0, "net_income": 0})
    return {"cik": cik, "form_type": form_type, **data}


def calculate_risk(revenue: float, net_income: float, debt_ratio: float = 0.5) -> dict:
    """Calculate financial risk score."""
    if revenue <= 0:
        return {"risk_score": 100.0, "grade": "F", "margin": 0.0}
    margin = net_income / revenue
    score = max(0.0, min(100.0, 100 - (margin * 100) - ((1 - debt_ratio) * 20)))
    grade = "A" if score < 20 else "B" if score < 40 else "C" if score < 60 else "D" if score < 80 else "F"
    return {"risk_score": round(score, 2), "grade": grade, "margin": round(margin * 100, 2)}


def classify_sector(cik: str) -> dict:
    """Classify company sector (mock)."""
    sectors = {
        "0000320193": "Technology",
        "0000789019": "Technology",
        "0001018724": "Consumer Discretionary",
        "0001326801": "Communication Services",
    }
    return {"cik": cik, "sector": sectors.get(cik, "Unknown")}


def generate_report(company: str, risk_score: float, grade: str, sector: str) -> str:
    """Generate a one-line risk report."""
    return f"{company} ({sector}): risk={risk_score:.1f} grade={grade}"


def validate_data(record_count: int, min_required: int = 1) -> bool:
    """Validate we have enough records."""
    return record_count >= min_required


# ============================================================================
# Now the spine imports — ONLY where we build managed pipelines
# ============================================================================

# Add examples/ to path so _db.py is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from spine.orchestration.managed_workflow import ManagedWorkflow, ManagedPipeline, manage


# ============================================================================
# SECTION 1 — ManagedWorkflow builder (fluent API)
# ============================================================================

def demo_managed_builder() -> None:
    """Build a managed pipeline with the fluent builder API."""
    print("\n--- Section 1: ManagedWorkflow Builder ---\n")

    # Build a pipeline from plain functions — no framework coupling
    pipeline = (
        ManagedWorkflow("sec.risk_analysis")
        .step("fetch", fetch_sec_filing, config={"cik": "0000320193"})
        .step("score", calculate_risk, config={
            "revenue": 391_035_000_000,
            "net_income": 96_995_000_000,
            "debt_ratio": 0.45,
        })
        .step("sector", classify_sector, config={"cik": "0000320193"})
        .build()
    )

    print(f"  Built: {pipeline}")
    print(f"  Persistent: {pipeline.is_persistent}")

    # Run it
    result = pipeline.run()

    # Pretty-print results
    pipeline.show()

    assert result.status.value == "completed"
    assert len(result.completed_steps) == 3
    print(f"\n  [OK] ManagedWorkflow builder — 3 steps completed")

    pipeline.close()


# ============================================================================
# SECTION 2 — manage() one-liner shortcut
# ============================================================================

def demo_manage_shortcut() -> None:
    """Use the manage() shortcut for quick sequential pipelines."""
    print("\n--- Section 2: manage() One-Liner ---\n")

    # One-liner: functions become steps named after the function
    pipeline = manage(
        fetch_sec_filing,
        classify_sector,
        validate_data,
        configs={
            "fetch_sec_filing": {"cik": "0000789019"},
            "classify_sector": {"cik": "0000789019"},
            "validate_data": {"record_count": 5},
        },
    )

    result = pipeline.run()
    pipeline.show()

    assert result.status.value == "completed"
    # validate_data returns True → StepResult.ok()
    print(f"\n  [OK] manage() shortcut — 3 functions as sequential pipeline")

    pipeline.close()


# ============================================================================
# SECTION 3 — Persistent mode (SQLite file)
# ============================================================================

def demo_persistent_mode() -> ManagedPipeline:
    """Show data persisting to a SQLite file."""
    print("\n--- Section 3: Persistent Mode (SQLite File) ---\n")

    db_path = str(Path(__file__).resolve().parent.parent / "spine_examples.db")

    # Build with persistence
    pipeline = (
        ManagedWorkflow("sec.persistent_demo", db=db_path)
        .step("fetch", fetch_sec_filing, config={"cik": "0001018724"})
        .step("score", calculate_risk, config={
            "revenue": 574_785_000_000,
            "net_income": 30_425_000_000,
            "debt_ratio": 0.6,
        })
        .step("sector", classify_sector, config={"cik": "0001018724"})
        .build()
    )

    print(f"  Pipeline  : {pipeline}")
    print(f"  Persistent: {pipeline.is_persistent}")
    print(f"  DB file   : {db_path}")

    # Run with a partition key (enables tracking + idempotency)
    result = pipeline.run(
        partition={"company": "Amazon", "quarter": "Q4-2025"},
    )

    pipeline.show()

    # Verify data is in the database
    counts = pipeline.table_counts()
    non_empty = {k: v for k, v in counts.items() if v > 0}
    print(f"\n  Tables with data: {len(non_empty)}")
    for table, count in sorted(non_empty.items()):
        print(f"    {table}: {count} rows")

    assert result.status.value == "completed"
    assert len(non_empty) > 0, "Expected data in at least one table"
    print(f"\n  [OK] Persistent mode — data written to SQLite file")

    return pipeline  # keep open for Section 4


# ============================================================================
# SECTION 4 — Idempotent re-execution
# ============================================================================

def demo_idempotency(pipeline: ManagedPipeline) -> None:
    """Show that re-running with the same partition is idempotent."""
    print("\n--- Section 4: Idempotent Re-execution ---\n")

    # Run again with the SAME partition — should be skipped
    result2 = pipeline.run(
        partition={"company": "Amazon", "quarter": "Q4-2025"},
    )

    print(f"  Status : {result2.status.value}")
    print(f"  Error  : {result2.error}")
    print(f"  Steps  : {result2.step_executions}")

    # Different partition — runs normally
    result3 = pipeline.run(
        partition={"company": "Amazon", "quarter": "Q3-2025"},
    )

    pipeline.show()

    # Check history
    history = pipeline.history()
    print(f"\n  Total runs: {len(history)}")
    for h in history:
        print(f"    {h['run_id'][:8]}… status={h['status']} steps={h['completed_steps']}")

    assert len(history) == 3  # run1 + skipped + run3
    print(f"\n  [OK] Idempotency — same partition skipped, new partition ran")

    pipeline.close()


# ============================================================================
# SECTION 5 — Querying execution data
# ============================================================================

def demo_querying() -> None:
    """Query the persistent database for execution history."""
    print("\n--- Section 5: Querying Execution Data ---\n")

    db_path = str(Path(__file__).resolve().parent.parent / "spine_examples.db")

    # Build a multi-company pipeline
    companies = [
        ("0000320193", "Apple"),
        ("0000789019", "Microsoft"),
        ("0001326801", "Meta"),
    ]

    pipeline = (
        ManagedWorkflow("sec.multi_company", db=db_path)
        .step("fetch", fetch_sec_filing, config={"cik": "0000320193"})
        .step("score", calculate_risk, config={
            "revenue": 391_035_000_000,
            "net_income": 96_995_000_000,
        })
        .build()
    )

    # Run for each company (with unique partitions)
    for cik, name in companies:
        pipeline.run(partition={"company": name, "analysis": "risk"})

    pipeline.show()

    # Query the manifest table
    print(f"\n  Querying core_manifest:")
    rows = pipeline.query_db(
        "SELECT domain, partition_key, stage FROM core_manifest "
        "ORDER BY domain, stage_rank"
    )
    for row in rows[:12]:  # limit output
        print(f"    {row.get('domain', '?'):<35} "
              f"stage={row.get('stage', '?'):<20} "
              f"partition={_truncate(row.get('partition_key', '?'), 30)}")

    # Show overall table counts
    print(f"\n  Database table summary:")
    counts = pipeline.table_counts()
    non_empty = {k: v for k, v in counts.items() if v > 0}
    for table, count in sorted(non_empty.items()):
        print(f"    {table}: {count} rows")

    assert len(rows) > 0, "Expected manifest rows"
    print(f"\n  [OK] Query API — {len(rows)} manifest entries found")

    pipeline.close()


# ============================================================================
# SECTION 6 — Importing existing pipelines
# ============================================================================

def demo_import_existing() -> None:
    """Show the full import-and-manage pattern for external code."""
    print("\n--- Section 6: Import Existing Pipelines ---\n")

    # Imagine these functions come from another project:
    #   from market_spine.analysis import fetch_sec_filing, calculate_risk
    #   from shared_lib.classifiers import classify_sector
    #   from reports.generators import generate_report
    #
    # We import them and get full lifecycle management:

    print("  The pattern:")
    print("    1. Import your existing functions (no changes needed)")
    print("    2. Build a ManagedWorkflow with .step() calls")
    print("    3. .run() — every execution is tracked")
    print("    4. .show() / .history() / .query_db() — full observability")
    print("    5. Partition keys give you idempotency for free")

    # Full example with all four functions
    pipeline = (
        ManagedWorkflow(
            "sec.full_analysis",
            description="Complete SEC filing analysis pipeline",
        )
        .step("fetch", fetch_sec_filing, config={"cik": "0000320193"})
        .step("score", calculate_risk, config={
            "revenue": 391_035_000_000,
            "net_income": 96_995_000_000,
            "debt_ratio": 0.45,
        })
        .step("sector", classify_sector, config={"cik": "0000320193"})
        .step("report", generate_report, config={
            "company": "Apple Inc.",
            "risk_score": 64.2,
            "grade": "D",
            "sector": "Technology",
        })
        .build()
    )

    result = pipeline.run()
    pipeline.show()

    # The report step returns a string → StepResult.ok(output={"message": ...})
    report_out = result.context.get_output("report")
    print(f"\n  Report: {report_out.get('message', '?')}")

    assert result.status.value == "completed"
    assert "Apple" in report_out.get("message", "")
    print(f"\n  [OK] Import-and-manage pattern — 4 external functions managed")

    pipeline.close()


# ── Helpers ──────────────────────────────────────────────────────────────

def _truncate(s: str, max_len: int = 60) -> str:
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


# ── Cleanup ──────────────────────────────────────────────────────────────

def _cleanup_db() -> None:
    """Remove the example database file if present."""
    db_path = Path(__file__).resolve().parent.parent / "spine_examples.db"
    if db_path.exists():
        db_path.unlink()


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    """Run all managed pipeline demonstrations."""

    print("=" * 60)
    print("Managed Pipelines — Import & Manage Existing Code")
    print("=" * 60)

    # Clean up from previous runs
    _cleanup_db()

    demo_managed_builder()
    demo_manage_shortcut()
    pipeline = demo_persistent_mode()
    demo_idempotency(pipeline)
    demo_querying()
    demo_import_existing()

    # Final cleanup
    _cleanup_db()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("""
  ManagedWorkflow is the primary integration pattern for spine-core.

  ┌─────────────────────────────────────────────────────────────┐
  │  Existing Code         →  ManagedWorkflow  →  Full Lifecycle│
  │                                                             │
  │  fetch_data()              .step("fetch")     Persistence   │
  │  validate()                .step("validate")  Idempotency   │
  │  transform()               .step("transform") Observability │
  │  report()                  .step("report")    Query History  │
  │                            .build()                         │
  │                            .run()                           │
  └─────────────────────────────────────────────────────────────┘

  Database modes:
    In-memory   → ManagedWorkflow("name")              ← default
    SQLite file → ManagedWorkflow("name", db="a.db")
    PostgreSQL  → ManagedWorkflow("name", db="postgresql://…")

  One-liner shortcut:
    pipeline = manage(fn1, fn2, fn3, db="runs.db")

  Your functions never import spine types.
  The adapter handles everything.
""")
    print("[OK] All managed pipeline demonstrations passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
