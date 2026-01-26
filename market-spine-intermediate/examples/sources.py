#!/usr/bin/env python3
"""
Source Framework Example - FileSource for Data Ingestion

This example demonstrates spine-core's source framework:
1. FileSource for reading CSV, PSV, TSV, JSON, Parquet files
2. SourceResult with metadata (hash, timestamps, byte counts)
3. Streaming for large files
4. Change detection for idempotency

Run:
    cd market-spine-intermediate
    uv run python -m examples.sources
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Spine core imports
from spine.framework.sources import (
    SourceType,
    SourceMetadata,
    SourceResult,
    BaseSource,
    SourceRegistry,
    source_registry,
    register_source,
)
from spine.framework.sources.file import FileSource, FileFormat


# =============================================================================
# Example Data
# =============================================================================

SAMPLE_PSV_DATA = """\
week_ending|symbol|tier|shares_or_principal|trade_count
2025-07-04|AAPL|NMS_TIER_1|150000|1200
2025-07-04|MSFT|NMS_TIER_1|120000|950
2025-07-04|GOOG|NMS_TIER_1|80000|600
2025-07-04|AMZN|NMS_TIER_2|45000|320
2025-07-04|TSLA|NMS_TIER_2|200000|1500
"""

SAMPLE_JSON_DATA = """\
[
  {"symbol": "AAPL", "shares": 150000, "trades": 1200},
  {"symbol": "MSFT", "shares": 120000, "trades": 950},
  {"symbol": "GOOG", "shares": 80000, "trades": 600}
]
"""

SAMPLE_CSV_DATA = """\
symbol,price,volume,date
AAPL,189.50,5000000,2025-07-04
MSFT,425.30,3200000,2025-07-04
GOOG,178.20,1800000,2025-07-04
AMZN,192.45,2400000,2025-07-04
"""


# =============================================================================
# Example 1: Reading PSV Files (FINRA-style)
# =============================================================================


def demo_psv_source():
    """Demonstrate reading PSV (pipe-separated) files like FINRA data."""
    print("=" * 70)
    print("EXAMPLE 1: Reading PSV Files (FINRA-style)")
    print("=" * 70)
    print()
    
    # Create temp file with sample data
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".psv", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAMPLE_PSV_DATA)
        psv_path = f.name
    
    try:
        # Create FileSource - format auto-detected from .psv extension
        source = FileSource(
            name="finra.otc_weekly",
            path=psv_path,
            domain="finra.otc_transparency",
        )
        
        print(f"Source: {source.name}")
        print(f"Format: {source.format.value}")
        print(f"Path: {source.path}")
        print()
        
        # Fetch all data
        result = source.fetch()
        
        if result.success:
            data = result.data
            meta = result.metadata
            
            print(f"Fetched {len(data)} records")
            print(f"  Content hash: {meta.content_hash[:16]}...")
            print(f"  Bytes: {meta.bytes_fetched}")
            print(f"  Duration: {meta.duration_ms}ms")
            print()
            
            print("Sample records:")
            for row in data[:3]:
                print(f"  {row['symbol']}: {row['shares_or_principal']} shares, "
                      f"{row['trade_count']} trades ({row['tier']})")
        else:
            print(f"ERROR: {result.error}")
        print()
        
    finally:
        Path(psv_path).unlink(missing_ok=True)


# =============================================================================
# Example 2: Reading JSON Files
# =============================================================================


def demo_json_source():
    """Demonstrate reading JSON array files."""
    print("=" * 70)
    print("EXAMPLE 2: Reading JSON Files")
    print("=" * 70)
    print()
    
    # Create temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAMPLE_JSON_DATA)
        json_path = f.name
    
    try:
        source = FileSource(
            name="market_data",
            path=json_path,
            domain="market",
        )
        
        result = source.fetch()
        
        if result.success:
            data = result.data
            print(f"Fetched {len(data)} JSON records")
            for row in data:
                avg = row["shares"] / row["trades"]
                print(f"  {row['symbol']}: {row['shares']} shares "
                      f"({avg:.1f} avg/trade)")
        else:
            print(f"ERROR: {result.error}")
        print()
        
    finally:
        Path(json_path).unlink(missing_ok=True)


# =============================================================================
# Example 3: Change Detection for Idempotency
# =============================================================================


def demo_change_detection():
    """Demonstrate change detection for idempotent processing."""
    print("=" * 70)
    print("EXAMPLE 3: Change Detection")
    print("=" * 70)
    print()
    
    # Create temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as f:
        f.write(SAMPLE_CSV_DATA)
        csv_path = f.name
    
    try:
        source = FileSource(name="prices", path=csv_path)
        
        # First fetch
        result1 = source.fetch()
        hash1 = result1.metadata.content_hash
        mtime1 = result1.metadata.last_modified
        
        print(f"First fetch:")
        print(f"  Hash: {hash1[:16]}...")
        print(f"  Modified: {mtime1}")
        print()
        
        # Check if changed (should be False - same content)
        has_changed = source.has_changed(last_hash=hash1)
        print(f"Has changed (same file): {has_changed}")
        
        # Modify the file
        with open(csv_path, "a", encoding="utf-8") as f:
            f.write("NVDA,125.80,4100000,2025-07-04\n")
        
        # Check again - should detect change
        has_changed = source.has_changed(last_hash=hash1)
        print(f"Has changed (after append): {has_changed}")
        
        # Fetch again
        result2 = source.fetch()
        hash2 = result2.metadata.content_hash
        
        print(f"\nSecond fetch:")
        print(f"  Hash: {hash2[:16]}...")
        print(f"  Records: {len(result1.data)} -> {len(result2.data)}")
        print(f"  Hash changed: {hash1 != hash2}")
        print()
        
    finally:
        Path(csv_path).unlink(missing_ok=True)


# =============================================================================
# Example 4: Streaming Large Files
# =============================================================================


def demo_streaming():
    """Demonstrate streaming for large files."""
    print("=" * 70)
    print("EXAMPLE 4: Streaming Large Files")
    print("=" * 70)
    print()
    
    # Create a larger CSV file
    lines = ["symbol,price,volume,date"]
    for i in range(1000):
        lines.append(f"SYM{i:04d},{100 + i * 0.01:.2f},{1000 * i},{2025-i % 365:04d}")
    
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as f:
        f.write("\n".join(lines))
        large_csv = f.name
    
    try:
        source = FileSource(name="large_data", path=large_csv)
        
        print(f"Supports streaming: {source.supports_streaming}")
        print(f"File format: {source.format.value}")
        print()
        
        # Stream in batches
        batch_num = 0
        total_rows = 0
        
        print("Streaming with batch_size=100:")
        for batch in source.stream(batch_size=100):
            batch_num += 1
            total_rows += len(batch)
            
            if batch_num <= 3:  # Show first 3 batches
                print(f"  Batch {batch_num}: {len(batch)} rows")
                print(f"    First: {batch[0]['symbol']}, Last: {batch[-1]['symbol']}")
            elif batch_num == 4:
                print("  ...")
        
        print(f"\nTotal: {batch_num} batches, {total_rows} rows")
        print()
        
    finally:
        Path(large_csv).unlink(missing_ok=True)


# =============================================================================
# Example 5: Source Registry
# =============================================================================


class CustomSource(BaseSource):
    """Example custom source implementation."""
    
    def __init__(self, name: str, api_endpoint: str):
        super().__init__(name=name, source_type=SourceType.HTTP)
        self.api_endpoint = api_endpoint
    
    def fetch(self, params: dict | None = None) -> SourceResult:
        """Fetch from custom source (mock implementation)."""
        # In real implementation, this would call the API
        mock_data = [
            {"id": 1, "value": "from_custom_source"},
            {"id": 2, "value": "more_data"},
        ]
        
        metadata = self._create_metadata(params=params)
        
        return SourceResult.ok(mock_data, metadata)


def demo_source_registry():
    """Demonstrate source registry for managing sources."""
    print("=" * 70)
    print("EXAMPLE 5: Source Registry")
    print("=" * 70)
    print()
    
    # Create a custom source instance
    custom = CustomSource(
        name="example.custom",
        api_endpoint="https://api.example.com/data",
    )
    
    # Register with the global registry
    register_source(custom)
    
    print("Registered sources:")
    for name in source_registry.list_sources():
        source = source_registry.get(name)
        print(f"  - {name}: {source.source_type.value}")
    print()
    
    # Fetch from registered source
    try:
        source = source_registry.get("example.custom")
        result = source.fetch()
        if result.success:
            print(f"Fetched from {source.name}: {len(result.data)} records")
    except Exception as e:
        print(f"Error: {e}")
    print()


# =============================================================================
# Main
# =============================================================================


if __name__ == "__main__":
    # Windows console encoding fix
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    demo_psv_source()
    print()
    demo_json_source()
    print()
    demo_change_detection()
    print()
    demo_streaming()
    print()
    demo_source_registry()
    
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print("Key spine-core source framework patterns:")
    print("  1. FileSource: Read CSV, PSV, TSV, JSON, Parquet files")
    print("  2. Auto-format detection from file extension")
    print("  3. SourceResult with rich metadata (hash, timestamps)")
    print("  4. Change detection with content hashing")
    print("  5. Streaming for memory-efficient large file processing")
    print("  6. Source registry for discovery and management")
    print()
