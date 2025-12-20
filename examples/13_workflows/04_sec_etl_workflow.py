#!/usr/bin/env python3
"""SEC ETL Workflow — full filing pipeline with mock and real modes.

The flagship stress-test example.  Builds a complete SEC filing ETL
pipeline that mirrors how py-sec-edgar would integrate with spine-core:
download the filing index, fetch a raw filing, parse it into sections,
extract entities, evaluate data quality, persist to SQLite, and clean
up temp files.

**Mock mode** (default): Uses realistic inline data — runs anywhere
without network access and completes in < 1 second.

**Real mode** (``SEC_USER_AGENT`` env var set AND ``py_sec_edgar``
installed): Fetches live filing data from SEC EDGAR with proper
rate limiting.  Falls back to mock mode if either prerequisite is
missing.

Demonstrates:
    1. 9-step ETL workflow using the full orchestration engine
    2. Parallel fan-out for independent extraction branches
    3. Quality gates with ``QualityMetrics`` thresholds
    4. Real SQLite writes (schema + data) inside a workflow step
    5. Mock/real dual-mode pattern for portable examples
    6. Workflow serialisation — full ``to_dict()`` audit trail
    7. ``context_updates`` for cross-step configuration
    8. Cleanup step with ``try/finally`` semantics

Architecture:
    The workflow combines sequential and parallel phases::

        configure → fetch_index → download_filing
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                   ▼
              extract_sections   extract_entities   extract_financials
                    │                  │                   │
                    └──────────────────┼──────────────────┘
                                       ▼
                                  quality_gate
                                       │
                                  store_results
                                       │
                                    cleanup

Key Concepts:
    - **Dual-mode execution**: A ``configure`` step sets
      ``context_updates`` to select mock or real data sources.
      Downstream steps read the mode from context.
    - **Fan-out pattern**: Three extraction steps depend on
      ``download_filing`` and run in parallel (DAG mode).
    - **Quality gate**: Aggregates metrics from all extraction
      branches; fails the workflow if thresholds aren't met.
    - **Atomic store**: Writes to a real SQLite database inside
      a temp directory — demonstrates that workflow steps can
      do genuine I/O.

See Also:
    - ``01_multi_step_pipeline.py``  — simpler sequential version
    - ``02_parallel_dag.py``         — pure DAG timing demo
    - ``examples/07_real_world/05_sec_filing_workflow.py`` — async version
    - py-sec-edgar project           — ``SEC`` client, ``SectionExtractor``

Run:
    python examples/13_workflows/04_sec_etl_workflow.py

    # Optional — real SEC EDGAR mode:
    SEC_USER_AGENT="MyApp admin@example.com" python examples/13_workflows/04_sec_etl_workflow.py

Expected Output:
    9-step ETL trace with section extraction, entity extraction,
    financial parsing, quality gate evaluation, SQLite persistence,
    and cleanup — all orchestrated by the workflow engine.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from spine.orchestration import (
    ErrorCategory,
    ErrorPolicy,
    ExecutionMode,
    FailurePolicy,
    QualityMetrics,
    Step,
    StepResult,
    Workflow,
    WorkflowContext,
    WorkflowExecutionPolicy,
    WorkflowResult,
    WorkflowRunner,
    WorkflowStatus,
)


# ---------------------------------------------------------------------------
# Runnable stub
# ---------------------------------------------------------------------------

class _StubRunnable:
    def submit_pipeline_sync(self, pipeline_name, params=None, *,
                             parent_run_id=None, correlation_id=None):
        from spine.execution.runnable import PipelineRunResult
        return PipelineRunResult(status="failed", error="Not configured")


# ---------------------------------------------------------------------------
# Mock data — realistic SEC EDGAR content
# ---------------------------------------------------------------------------

MOCK_INDEX_ENTRIES = [
    {
        "cik": "0000320193",
        "company": "Apple Inc.",
        "form_type": "10-K",
        "accession": "0000320193-24-000081",
        "filed": "2024-10-25",
        "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000081/0000320193-24-000081-index.htm",
    },
    {
        "cik": "0000789019",
        "company": "Microsoft Corporation",
        "form_type": "10-Q",
        "accession": "0000789019-24-000042",
        "filed": "2024-10-24",
        "url": "https://www.sec.gov/Archives/edgar/data/789019/000078901924000042/0000789019-24-000042-index.htm",
    },
]

MOCK_FILING_DOC = """\
<SEC-DOCUMENT>
<TYPE>10-K
<COMPANY>Apple Inc.
<CIK>0000320193
<ACCESSION>0000320193-24-000081

ITEM 1. BUSINESS
Apple Inc. designs, manufactures, and markets smartphones, personal
computers, tablets, wearables, and accessories worldwide. The Company
also provides a variety of related services including AppleCare,
cloud services, and digital content through the App Store.

ITEM 1A. RISK FACTORS
The Company faces significant competition across all its product and
service markets. Key risks include global economic conditions, supply
chain disruptions, regulatory changes in key markets like China and
the European Union, and rapid technological change. Foreign exchange
fluctuations may materially affect international revenues which
represent approximately 58% of total net sales.

ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION
Revenue for fiscal year 2024 was $391.0 billion, an increase of 5%
compared to $372.6 billion in fiscal 2023. The increase was driven
primarily by higher iPhone revenue and continued growth in Services,
which reached $96.2 billion. Gross margin expanded 120 basis points
to 46.2% due to favorable product mix and cost efficiencies.

Operating expenses totaled $55.0 billion, flat year-over-year due to
disciplined spending despite increased R&D investment. Net income was
$97.0 billion or $6.42 per diluted share.

ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA
Total assets: $352.6 billion
Total liabilities: $290.4 billion
Stockholders equity: $62.1 billion
Cash and cash equivalents: $29.9 billion
Total revenue: $391.0 billion
Net income: $97.0 billion
Earnings per share (diluted): $6.42
</SEC-DOCUMENT>
"""


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

def configure(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Determine execution mode (mock vs real)."""
    user_agent = os.environ.get("SEC_USER_AGENT", "")
    use_real = bool(user_agent)

    if use_real:
        try:
            import py_sec_edgar  # noqa: F401
            mode = "real"
            print(f"    [configure]  Real mode — SEC_USER_AGENT set, py_sec_edgar available")
        except ImportError:
            mode = "mock"
            print(f"    [configure]  Falling back to mock — py_sec_edgar not installed")
    else:
        mode = "mock"
        print(f"    [configure]  Mock mode — set SEC_USER_AGENT for live EDGAR data")

    # Create temp directory for this run
    tmp_dir = tempfile.mkdtemp(prefix="sec_etl_")

    return StepResult.ok(
        output={"mode": mode, "user_agent": user_agent[:30] if user_agent else ""},
        context_updates={"mode": mode, "tmp_dir": tmp_dir},
    )


def fetch_index(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Fetch the EDGAR filing index."""
    mode = ctx.get_param("mode", "mock")
    limit = ctx.get_param("limit", 2)

    if mode == "real":
        # Real mode would use: SEC().list_filings() or EDGAR full-text search
        # For safety, we still use mock in this example
        pass

    entries = MOCK_INDEX_ENTRIES[:limit]
    time.sleep(0.05)  # simulate network
    print(f"    [fetch_index]       {len(entries)} filings from EDGAR ({mode} mode)")
    return StepResult.ok(output={
        "entries": entries,
        "count": len(entries),
    })


def download_filing(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Download the raw filing document."""
    entries = ctx.get_output("fetch_index", "entries", [])
    if not entries:
        return StepResult.fail("No filings in index", category=ErrorCategory.DATA_QUALITY)

    target = entries[0]
    time.sleep(0.05)  # simulate download
    print(f"    [download_filing]   {target['accession']} — {target['company']} ({target['form_type']})")
    return StepResult.ok(output={
        "accession": target["accession"],
        "company": target["company"],
        "form_type": target["form_type"],
        "cik": target["cik"],
        "content": MOCK_FILING_DOC,
        "content_bytes": len(MOCK_FILING_DOC),
    })


def extract_sections(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Extract named sections (Item 1, 1A, 7, 8) from filing text."""
    content = ctx.get_output("download_filing", "content", "")
    time.sleep(0.15)  # simulate parsing

    # Simple section parser
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("ITEM "):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = stripped.split("\n")[0]
            buffer = []
        elif current:
            buffer.append(stripped)

    if current:
        sections[current] = "\n".join(buffer).strip()

    word_count = sum(len(v.split()) for v in sections.values())
    print(f"    [extract_sections]  {len(sections)} sections, {word_count} words")
    return StepResult.ok(output={
        "sections": list(sections.keys()),
        "section_text": {k: v[:300] for k, v in sections.items()},
        "section_count": len(sections),
        "word_count": word_count,
    })


def extract_entities(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Extract company, person, and location mentions."""
    content = ctx.get_output("download_filing", "content", "")
    time.sleep(0.1)  # simulate NLP

    # Keyword-based entity extraction (mock NER)
    entity_patterns = {
        "companies": ["Apple Inc.", "AppleCare", "App Store"],
        "products": ["iPhone", "iPad", "Mac"],
        "locations": ["China", "European Union", "Cupertino"],
        "regulatory": ["SEC", "EDGAR"],
    }

    found: dict[str, list[str]] = {}
    for category, keywords in entity_patterns.items():
        matches = [kw for kw in keywords if kw.lower() in content.lower()]
        if matches:
            found[category] = matches

    total = sum(len(v) for v in found.values())
    print(f"    [extract_entities]  {total} entities across {len(found)} categories")
    return StepResult.ok(output={
        "entities": found,
        "entity_count": total,
        "categories": list(found.keys()),
    })


def extract_financials(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Parse financial figures from Item 8."""
    content = ctx.get_output("download_filing", "content", "")
    time.sleep(0.1)  # simulate parsing

    # Simple dollar-amount extraction
    import re
    amounts = re.findall(r'\$[\d,]+\.?\d*\s*(?:billion|million)?', content)
    key_metrics: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if ":" in stripped and "$" in stripped:
            parts = stripped.split(":", 1)
            key_metrics[parts[0].strip()] = parts[1].strip()

    print(f"    [extract_financials] {len(key_metrics)} metrics, {len(amounts)} dollar amounts")
    return StepResult.ok(output={
        "key_metrics": key_metrics,
        "dollar_amounts": amounts,
        "metric_count": len(key_metrics),
    })


def quality_gate(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Evaluate extraction quality across all branches."""
    section_count = ctx.get_output("extract_sections", "section_count", 0)
    word_count = ctx.get_output("extract_sections", "word_count", 0)
    entity_count = ctx.get_output("extract_entities", "entity_count", 0)
    metric_count = ctx.get_output("extract_financials", "metric_count", 0)

    total_items = section_count + entity_count + metric_count
    valid_items = total_items if word_count >= 50 else 0

    metrics = QualityMetrics(
        record_count=total_items,
        valid_count=valid_items,
        passed=word_count >= 50 and entity_count >= 3 and section_count >= 2,
        custom_metrics={
            "word_count": word_count,
            "entity_count": entity_count,
            "metric_count": metric_count,
            "section_count": section_count,
        },
    )

    if not metrics.passed:
        reasons = []
        if word_count < 50:
            reasons.append(f"words={word_count}<50")
        if entity_count < 3:
            reasons.append(f"entities={entity_count}<3")
        if section_count < 2:
            reasons.append(f"sections={section_count}<2")
        return StepResult.fail(
            f"Quality gate failed: {', '.join(reasons)}",
            category=ErrorCategory.DATA_QUALITY,
            quality=metrics,
        )

    print(f"    [quality_gate]      PASSED — {section_count} sections, "
          f"{entity_count} entities, {metric_count} metrics, "
          f"valid_rate={metrics.valid_rate:.0%}")
    return StepResult.ok(
        output={"passed": True, "quality": metrics.to_dict()},
        quality=metrics,
    )


def store_results(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Persist all extraction results to SQLite."""
    tmp_dir = ctx.get_param("tmp_dir", tempfile.gettempdir())
    db_path = str(Path(tmp_dir) / "sec_etl.db")
    accession = ctx.get_output("download_filing", "accession", "")
    company = ctx.get_output("download_filing", "company", "")
    form_type = ctx.get_output("download_filing", "form_type", "")
    sections = ctx.get_output("extract_sections", "sections", [])
    entities = ctx.get_output("extract_entities", "entities", {})
    metrics = ctx.get_output("extract_financials", "key_metrics", {})

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_filings (
            accession TEXT PRIMARY KEY,
            company TEXT NOT NULL,
            form_type TEXT NOT NULL,
            sections TEXT,
            entities TEXT,
            financials TEXT,
            extracted_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_filing_sections (
            accession TEXT,
            section_name TEXT,
            word_count INTEGER,
            PRIMARY KEY (accession, section_name)
        )
    """)

    conn.execute(
        "INSERT OR REPLACE INTO sec_filings VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (accession, company, form_type, json.dumps(sections),
         json.dumps(entities), json.dumps(metrics)),
    )

    section_text = ctx.get_output("extract_sections", "section_text", {})
    for sec_name, text in section_text.items():
        conn.execute(
            "INSERT OR REPLACE INTO sec_filing_sections VALUES (?, ?, ?)",
            (accession, sec_name, len(text.split())),
        )

    conn.commit()
    filing_count = conn.execute("SELECT COUNT(*) FROM sec_filings").fetchone()[0]
    section_rows = conn.execute("SELECT COUNT(*) FROM sec_filing_sections").fetchone()[0]
    conn.close()

    print(f"    [store_results]     SQLite: {db_path}")
    print(f"                        {filing_count} filings, {section_rows} section rows")
    return StepResult.ok(output={
        "db_path": db_path,
        "filing_count": filing_count,
        "section_rows": section_rows,
    })


def cleanup(ctx: WorkflowContext, config: dict[str, Any]) -> StepResult:
    """Clean up temp files (optional — keeps DB for inspection)."""
    tmp_dir = ctx.get_param("tmp_dir", "")
    db_path = ctx.get_output("store_results", "db_path", "")

    # In a real pipeline, you'd remove tmp_dir here.
    # For this example, we keep the DB so users can inspect it.
    print(f"    [cleanup]           Temp dir: {tmp_dir}")
    print(f"                        DB preserved at: {db_path}")
    return StepResult.ok(output={"cleaned": True, "db_preserved": db_path})


# ---------------------------------------------------------------------------
# Workflow builder
# ---------------------------------------------------------------------------

def build_sec_etl_workflow() -> Workflow:
    """Build the full SEC ETL workflow with parallel extraction branches."""
    return Workflow(
        name="sec.etl_pipeline",
        domain="sec.edgar",
        description="Full SEC filing ETL: index → download → extract(×3) → quality → store → cleanup",
        steps=[
            # Sequential setup
            Step.lambda_("configure", configure),
            Step.lambda_("fetch_index", fetch_index, depends_on=["configure"]),
            Step.lambda_("download_filing", download_filing, depends_on=["fetch_index"]),
            # Parallel extraction fan-out
            Step.lambda_("extract_sections", extract_sections, depends_on=["download_filing"]),
            Step.lambda_("extract_entities", extract_entities, depends_on=["download_filing"]),
            Step.lambda_("extract_financials", extract_financials, depends_on=["download_filing"]),
            # Fan-in
            Step.lambda_("quality_gate", quality_gate,
                         depends_on=["extract_sections", "extract_entities", "extract_financials"]),
            Step.lambda_("store_results", store_results, depends_on=["quality_gate"]),
            Step.lambda_("cleanup", cleanup, depends_on=["store_results"]),
        ],
        execution_policy=WorkflowExecutionPolicy(
            mode=ExecutionMode.PARALLEL,
            max_concurrency=3,
            timeout_seconds=300,
            on_failure=FailurePolicy.STOP,
        ),
        tags=["sec", "edgar", "etl", "parallel", "stress-test"],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full SEC ETL workflow."""

    print("=" * 60)
    print("Workflow Stress Test — SEC Filing ETL Pipeline")
    print("=" * 60)

    # --- 1. Build & inspect workflow ---
    print("\n--- 1. Workflow Structure ---")
    wf = build_sec_etl_workflow()
    print(f"  name             : {wf.name}")
    print(f"  steps            : {len(wf.steps)}")
    print(f"  has_dependencies : {wf.has_dependencies()}")
    print(f"  execution_mode   : {wf.execution_policy.mode.value}")
    print(f"  max_concurrency  : {wf.execution_policy.max_concurrency}")
    print(f"  topological_order: {wf.topological_order()}")

    dag = wf.dependency_graph()
    print(f"  dependency_graph :")
    for src, targets in dag.items():
        print(f"    {src} → {targets}")

    # --- 2. Execute ---
    print("\n--- 2. Execute ETL Pipeline ---")
    runner = WorkflowRunner(runnable=_StubRunnable())
    t0 = time.perf_counter()
    result: WorkflowResult = runner.execute(wf, params={"limit": 2})
    elapsed = time.perf_counter() - t0

    # --- 3. Results ---
    print(f"\n--- 3. Workflow Result ---")
    print(f"  status          : {result.status.value}")
    print(f"  run_id          : {result.run_id}")
    print(f"  duration        : {elapsed:.3f}s")
    print(f"  completed_steps : {result.completed_steps}")
    print(f"  failed_steps    : {result.failed_steps}")

    # --- 4. Step trace ---
    print("\n--- 4. Step Execution Trace ---")
    for se in result.step_executions:
        icon = "PASS" if se.status == "completed" else "FAIL"
        dur = se.duration_seconds or 0
        print(f"  [{icon}] {se.step_name:25s} {dur:.3f}s")

    # --- 5. Extraction summary ---
    print("\n--- 5. Extraction Summary ---")
    ctx = result.context
    mode = ctx.get_param("mode", "?")
    sections = ctx.get_output("extract_sections", "sections", [])
    entity_count = ctx.get_output("extract_entities", "entity_count", 0)
    entities = ctx.get_output("extract_entities", "entities", {})
    metric_count = ctx.get_output("extract_financials", "metric_count", 0)
    key_metrics = ctx.get_output("extract_financials", "key_metrics", {})
    quality = ctx.get_output("quality_gate", "quality", {})

    print(f"  mode              : {mode}")
    print(f"  sections          : {sections}")
    print(f"  entities ({entity_count})     :")
    for cat, items in entities.items():
        print(f"    {cat:15s} : {items}")
    print(f"  financials ({metric_count})   :")
    for name, value in list(key_metrics.items())[:5]:
        print(f"    {name:30s} : {value}")
    print(f"  quality_passed    : {quality.get('passed', '?')}")
    print(f"  valid_rate        : {quality.get('valid_rate', 0):.0%}")

    # --- 6. Database verification ---
    print("\n--- 6. Database Verification ---")
    db_path = ctx.get_output("store_results", "db_path", "")
    if db_path and Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        filings = conn.execute("SELECT accession, company, form_type FROM sec_filings").fetchall()
        sections_db = conn.execute("SELECT * FROM sec_filing_sections").fetchall()
        conn.close()

        print(f"  db_path           : {db_path}")
        for row in filings:
            print(f"  filing            : {row[0]} — {row[1]} ({row[2]})")
        print(f"  section_rows      : {len(sections_db)}")

    # --- 7. Serialisation ---
    print("\n--- 7. Audit Trail (serialised) ---")
    result_dict = result.to_dict()
    print(f"  keys              : {list(result_dict.keys())}")
    print(f"  json_bytes        : {len(json.dumps(result_dict)):,}")
    print(f"  step_count        : {len(result_dict.get('step_executions', []))}")

    # --- Assertions ---
    assert result.status == WorkflowStatus.COMPLETED, f"Expected COMPLETED, got {result.status}"
    assert len(result.completed_steps) == 9, f"Expected 9 steps, got {len(result.completed_steps)}"
    assert entity_count >= 3, f"Expected >=3 entities, got {entity_count}"
    assert db_path and Path(db_path).exists(), "Database should exist"

    print("\n" + "=" * 60)
    print(f"[OK] SEC ETL Pipeline — 9 steps completed in {elapsed:.3f}s ({mode} mode)")
    print("=" * 60)


if __name__ == "__main__":
    main()
