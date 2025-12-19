#!/usr/bin/env python3
"""Source Connectors — File ingestion with change detection.

WHY SOURCE ABSTRACTION
──────────────────────
Pipelines and workflows that hard-code `open("trades.csv")` can’t
switch to S3, HTTP, or database sources without rewriting.  FileSource
provides a uniform fetch() → SourceResult interface with:
• Auto-format detection from file extension (CSV, JSON, etc.).
• Content-hash based caching to skip unchanged files.
• SourceMetadata with duration, bytes, row count.

Use FileSource inside a Pipeline’s run() method, inside a plain
@workflow_step function, or in a standalone script — the API is the
same everywhere.

ARCHITECTURE
────────────
    ┌─────────────────────────────────────┐
    │ Pipeline.run()  OR  @workflow_step  │
    └──────────────┬──────────────────────┘
                   │ .fetch()
                   ▼
    ┌─────────────┐                     ┌──────────────────────┐
    │  FileSource  │ ── source.fetch() ──▶  SourceResult         │
    │  name, path  │                     │  .success: bool       │
    └─────────────┘                     │  .data: list[dict]    │
                                        │  .metadata:           │
                                        │    .content_hash      │
                                        │    .duration_ms       │
                                        │    .bytes_fetched     │
                                        │    .row_count         │
                                        └──────────────────────┘

    Cache key = hash(source_name + path + params) for
    content-hash based change detection.

SUPPORTED FORMATS
─────────────────
    FileFormat   Extension     Notes
    ──────────── ───────────── ───────────────────────
    CSV          .csv          Configurable delimiter
    JSON         .json         Array of objects
    (extensible) .txt, etc.    Explicit format= param

BEST PRACTICES
──────────────
• Let auto-detection choose format; override only for .txt.
• Use get_cache_key() + content_hash for incremental processing.
• Set domain= for lineage tracking across the ecosystem.
• Pass source results through WorkflowContext for downstream steps.

Run: python examples/08_framework/06_source_connectors.py

See Also:
    04_params_validation — validate source path parameters
    07_framework_logging — log source fetch durations
    04_orchestration/17_sec_etl_workflow — real-world ETL using sources
"""

import json
import tempfile
from pathlib import Path

from spine.framework.sources.file import FileFormat, FileSource


def main():
    print("=" * 60)
    print("Source Connectors - File Ingestion")
    print("=" * 60)

    # Create temp CSV file for demo
    tmp = Path(tempfile.mkdtemp())
    csv_path = tmp / "trades.csv"
    csv_path.write_text(
        "date,ticker,price,volume\n"
        "2025-01-15,AAPL,198.50,1200000\n"
        "2025-01-15,MSFT,420.30,800000\n"
        "2025-01-15,GOOG,178.20,600000\n"
        "2025-01-16,AAPL,199.10,1100000\n"
        "2025-01-16,MSFT,421.75,750000\n",
        encoding="utf-8",
    )

    # Also create a JSON file
    json_path = tmp / "events.json"
    json_path.write_text(
        json.dumps([
            {"ticker": "AAPL", "event": "earnings_release", "date": "2025-01-30"},
            {"ticker": "MSFT", "event": "earnings_call", "date": "2025-01-29"},
        ]),
        encoding="utf-8",
    )

    # ── 1. Create FileSource (auto-detect CSV) ─────────────────
    print("\n--- 1. FileSource (CSV, auto-detected) ---")
    source = FileSource(name="daily_trades", path=csv_path)
    print(f"  Name:   {source.name}")
    print(f"  Format: {source.format.value}")
    print(f"  Path:   {source.path}")
    print(f"  Streaming: {source.supports_streaming}")

    # ── 2. Fetch data ───────────────────────────────────────────
    print("\n--- 2. Fetch data ---")
    result = source.fetch()
    print(f"  Success: {result.success}")
    print(f"  Records: {len(result.data)}")
    for row in result.data[:3]:
        print(f"    {dict(row)}")

    # ── 3. Inspect metadata ─────────────────────────────────────
    print("\n--- 3. SourceMetadata ---")
    meta = result.metadata
    print(f"  Duration ms:   {meta.duration_ms}" if meta.duration_ms else "  Duration ms:   N/A")
    print(f"  Content hash:  {meta.content_hash[:16]}..." if meta.content_hash else "  Content hash: N/A")
    print(f"  Bytes fetched: {meta.bytes_fetched}" if meta.bytes_fetched else "  Bytes fetched: N/A")
    print(f"  Row count:     {meta.row_count}" if meta.row_count else "  Row count:     N/A")

    # ── 4. JSON source ──────────────────────────────────────────
    print("\n--- 4. FileSource (JSON) ---")
    json_source = FileSource(name="events", path=json_path, domain="market")
    json_result = json_source.fetch()
    print(f"  Format:  {json_source.format.value}")
    print(f"  Records: {len(json_result.data)}")
    for event in json_result.data:
        print(f"    {event}")

    # ── 5. Cache key generation ─────────────────────────────────
    print("\n--- 5. Cache key ---")
    key1 = source.get_cache_key()
    key2 = source.get_cache_key(params={"filter": "AAPL"})
    print(f"  Default key:  {key1}")
    print(f"  With params:  {key2}")
    print(f"  Different:    {key1 != key2}")

    # ── 6. FileFormat enum ──────────────────────────────────────
    print("\n--- 6. Supported formats ---")
    for fmt in FileFormat:
        print(f"  {fmt.value}")

    # ── 7. Explicit format + delimiter ──────────────────────────
    print("\n--- 7. Explicit format ---")
    psv_path = tmp / "data.txt"
    psv_path.write_text(
        "ticker|price|date\n"
        "AAPL|198.50|2025-01-15\n"
        "MSFT|420.30|2025-01-15\n",
        encoding="utf-8",
    )
    psv_source = FileSource(
        name="pipe_data",
        path=psv_path,
        format="csv",  # Treat as CSV with custom delimiter
        delimiter="|",
    )
    psv_result = psv_source.fetch()
    print(f"  Records: {len(psv_result.data)}")
    for row in psv_result.data:
        print(f"    {dict(row)}")

    # Cleanup
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 60)
    print("[OK] Source connectors example complete")


if __name__ == "__main__":
    main()
