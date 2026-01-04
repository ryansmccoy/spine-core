# 03: Pipeline - Ingest Week

> **Purpose**: Ingest raw OTC data for a single week from a FINRA-format file. This is the first pipeline in the per-week processing chain.

---

## Pipeline Specification

| Property | Value |
|----------|-------|
| **Name** | `otc.ingest_week` |
| **Idempotency** | Level 2: Input-Idempotent (same file → same records via hash dedup) |
| **Dependencies** | None (entry point) |
| **Writes To** | `otc_raw`, `otc_week_manifest`, `otc_rejects` |
| **Lane** | NORMAL |

---

## Parameters Schema

```python
@dataclass
class IngestWeekParams:
    """Parameters for otc.ingest_week pipeline."""
    
    # Required
    tier: str                    # "NMS_TIER_1" | "NMS_TIER_2" | "OTC"
    week_ending: str             # ISO Friday date, e.g., "2025-12-26"
    
    # Source (one required)
    source_type: str = "file"    # "file" | "url"
    file_path: str = None        # Path to PSV file (if source_type=file)
    url: str = None              # URL to download (if source_type=url)
    
    # Options
    force: bool = False          # Re-ingest even if week already ingested
```

---

## File Format

FINRA OTC transparency files are pipe-delimited (PSV):

```
WeekEnding|Tier|Symbol|MPID|TotalShares|TotalTrades
2025-12-26|NMS_TIER_1|AAPL|NITE|1500000|8500
2025-12-26|NMS_TIER_1|AAPL|CITD|1200000|6200
2025-12-26|NMS_TIER_1|TSLA|VIRTU|980000|4100
```

Header row is optional (auto-detected).

---

## Implementation

### File: `domains/otc/pipelines/ingest_week.py`

```python
"""
OTC Ingest Week Pipeline

Ingests raw OTC data for a single week from a FINRA-format PSV file.
This is the entry point for per-week processing.

Idempotency: Level 2 (Input-Idempotent)
- Same file ingested twice → same records (via record_hash dedup)
- Safe to retry on failure
"""
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
import sqlite3

from spine.core.pipeline import Pipeline, PipelineResult, PipelineStatus
from spine.core.registry import register_pipeline

from ..enums import Tier, ManifestStage, RejectStage
from ..validators import WeekEnding, compute_record_hash
from ..models import RawOTCRecord, ParseError, Reject

logger = logging.getLogger(__name__)

# Pipeline version for tracking
PIPELINE_VERSION = "v1.0.0"


@dataclass
class IngestMetrics:
    """Metrics collected during ingestion."""
    week_ending: str
    tier: str
    source_locator: str
    source_sha256: str
    source_bytes: int
    row_count_raw: int        # Total lines in file (excluding header)
    row_count_parsed: int     # Successfully parsed
    row_count_inserted: int   # Inserted into otc_raw (after dedup)
    row_count_rejected: int   # Rejected (parse errors, validation failures)
    row_count_skipped: int    # Skipped (duplicate hashes)


@register_pipeline("otc.ingest_week")
class IngestWeekPipeline(Pipeline):
    """
    Ingest raw OTC data for a single week.
    
    Creates:
    - Records in otc_raw
    - Week manifest entry in otc_week_manifest
    - Rejected records in otc_rejects
    """
    
    def validate_params(self) -> Optional[str]:
        """Validate required parameters. Returns error message or None."""
        params = self.params
        
        # Required: tier
        if not params.get("tier"):
            return "Missing required parameter: tier"
        try:
            Tier.from_string(params["tier"])
        except ValueError as e:
            return str(e)
        
        # Required: week_ending
        if not params.get("week_ending"):
            return "Missing required parameter: week_ending"
        try:
            WeekEnding(params["week_ending"])
        except ValueError as e:
            return str(e)
        
        # Required: source
        source_type = params.get("source_type", "file")
        if source_type == "file":
            if not params.get("file_path"):
                return "Missing required parameter: file_path (when source_type=file)"
            if not Path(params["file_path"]).exists():
                return f"File not found: {params['file_path']}"
        elif source_type == "url":
            if not params.get("url"):
                return "Missing required parameter: url (when source_type=url)"
        else:
            return f"Invalid source_type: {source_type}. Expected 'file' or 'url'"
        
        return None
    
    def run(self) -> PipelineResult:
        """Execute the ingestion pipeline."""
        # Validate parameters
        validation_error = self.validate_params()
        if validation_error:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=validation_error,
                metrics={}
            )
        
        tier = Tier.from_string(self.params["tier"])
        week = WeekEnding(self.params["week_ending"])
        source_type = self.params.get("source_type", "file")
        force = self.params.get("force", False)
        
        conn = self.get_connection()
        
        # Check if already ingested (unless force=True)
        if not force:
            existing = conn.execute(
                "SELECT stage FROM otc_week_manifest WHERE week_ending = ? AND tier = ?",
                (str(week), tier.value)
            ).fetchone()
            
            if existing and ManifestStage(existing["stage"]) >= ManifestStage.INGESTED:
                return PipelineResult(
                    status=PipelineStatus.COMPLETED,
                    metrics={
                        "week_ending": str(week),
                        "tier": tier.value,
                        "skipped": True,
                        "reason": "Already ingested (use force=true to re-ingest)"
                    }
                )
        
        # Get source file
        if source_type == "file":
            file_path = Path(self.params["file_path"])
            source_locator = str(file_path)
        else:
            # URL handling would go here (download to temp file)
            # For Basic tier, we only support file
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error="URL source not implemented in Basic tier",
                metrics={}
            )
        
        # Compute file hash and size
        source_sha256 = self._compute_file_hash(file_path)
        source_bytes = file_path.stat().st_size
        
        # Parse file
        records, parse_errors = self._parse_file(file_path, tier, week)
        
        # Insert records (with dedup)
        inserted, skipped = self._insert_records(conn, records)
        
        # Insert rejects
        self._insert_rejects(conn, parse_errors, source_locator)
        
        # Update manifest
        metrics = IngestMetrics(
            week_ending=str(week),
            tier=tier.value,
            source_locator=source_locator,
            source_sha256=source_sha256,
            source_bytes=source_bytes,
            row_count_raw=len(records) + len(parse_errors),
            row_count_parsed=len(records),
            row_count_inserted=inserted,
            row_count_rejected=len(parse_errors),
            row_count_skipped=skipped
        )
        
        self._update_manifest(conn, metrics)
        
        conn.commit()
        
        logger.info(
            f"Ingested {metrics.row_count_inserted} records for "
            f"{tier.value}/{str(week)} ({metrics.row_count_rejected} rejected, "
            f"{metrics.row_count_skipped} duplicates skipped)"
        )
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            metrics={
                "week_ending": str(week),
                "tier": tier.value,
                "records_parsed": metrics.row_count_parsed,
                "records_inserted": metrics.row_count_inserted,
                "records_rejected": metrics.row_count_rejected,
                "records_skipped": metrics.row_count_skipped,
                "source_sha256": source_sha256
            }
        )
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _parse_file(
        self, 
        file_path: Path, 
        tier: Tier, 
        week: WeekEnding
    ) -> tuple[list[RawOTCRecord], list[ParseError]]:
        """
        Parse FINRA PSV file into records.
        
        Returns:
            Tuple of (parsed_records, parse_errors)
        """
        records = []
        errors = []
        
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        if not lines:
            return records, errors
        
        # Detect header (first line contains "WeekEnding" or similar)
        start_line = 0
        first_line = lines[0].strip().lower()
        if "weekending" in first_line or "week_ending" in first_line or "symbol" in first_line:
            start_line = 1
        
        for line_num, line in enumerate(lines[start_line:], start=start_line + 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                record = self._parse_line(line, line_num, tier, week)
                records.append(record)
            except ValueError as e:
                errors.append(ParseError(
                    line_number=line_num,
                    raw_line=line,
                    error_code="PARSE_ERROR",
                    error_detail=str(e)
                ))
        
        return records, errors
    
    def _parse_line(
        self, 
        line: str, 
        line_num: int, 
        expected_tier: Tier, 
        expected_week: WeekEnding
    ) -> RawOTCRecord:
        """
        Parse a single line into a RawOTCRecord.
        
        Raises ValueError on parse failure.
        """
        parts = line.split("|")
        
        if len(parts) < 6:
            raise ValueError(f"Expected 6 pipe-delimited fields, got {len(parts)}")
        
        week_ending, tier_str, symbol, mpid, shares_str, trades_str = parts[:6]
        
        # Validate week matches expected
        try:
            file_week = WeekEnding(week_ending.strip())
        except ValueError as e:
            raise ValueError(f"Invalid week_ending: {e}")
        
        if file_week != expected_week:
            raise ValueError(
                f"Week mismatch: file has {file_week}, expected {expected_week}"
            )
        
        # Validate tier matches expected
        try:
            file_tier = Tier.from_string(tier_str.strip())
        except ValueError as e:
            raise ValueError(f"Invalid tier: {e}")
        
        if file_tier != expected_tier:
            raise ValueError(
                f"Tier mismatch: file has {file_tier.value}, expected {expected_tier.value}"
            )
        
        # Parse numeric fields
        try:
            total_shares = int(shares_str.strip())
        except ValueError:
            raise ValueError(f"Invalid total_shares: '{shares_str}'")
        
        try:
            total_trades = int(trades_str.strip())
        except ValueError:
            raise ValueError(f"Invalid total_trades: '{trades_str}'")
        
        # Compute hash
        record_hash = compute_record_hash(
            week_ending=str(file_week),
            tier=file_tier.value,
            symbol=symbol.strip().upper(),
            mpid=mpid.strip().upper(),
            total_shares=total_shares,
            total_trades=total_trades
        )
        
        return RawOTCRecord(
            week_ending=str(file_week),
            tier=file_tier.value,
            symbol=symbol.strip().upper(),
            mpid=mpid.strip().upper(),
            total_shares=total_shares,
            total_trades=total_trades,
            source_line_number=line_num,
            record_hash=record_hash,
            execution_id=self.execution_id,
            batch_id=self.batch_id
        )
    
    def _insert_records(
        self, 
        conn: sqlite3.Connection, 
        records: list[RawOTCRecord]
    ) -> tuple[int, int]:
        """
        Insert records into otc_raw with dedup via record_hash.
        
        Returns:
            Tuple of (inserted_count, skipped_count)
        """
        inserted = 0
        skipped = 0
        
        for record in records:
            # Check if hash already exists
            existing = conn.execute(
                "SELECT 1 FROM otc_raw WHERE record_hash = ?",
                (record.record_hash,)
            ).fetchone()
            
            if existing:
                skipped += 1
                continue
            
            conn.execute("""
                INSERT INTO otc_raw (
                    week_ending, tier, symbol, mpid, 
                    total_shares, total_trades,
                    record_hash, execution_id, batch_id, ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                record.week_ending,
                record.tier,
                record.symbol,
                record.mpid,
                record.total_shares,
                record.total_trades,
                record.record_hash,
                record.execution_id,
                record.batch_id
            ))
            inserted += 1
        
        return inserted, skipped
    
    def _insert_rejects(
        self, 
        conn: sqlite3.Connection, 
        errors: list[ParseError], 
        source_locator: str
    ) -> None:
        """Insert parse errors into otc_rejects."""
        for error in errors:
            conn.execute("""
                INSERT INTO otc_rejects (
                    week_ending, tier, source_locator, line_number,
                    raw_line, raw_record_hash, stage, reason_code, reason_detail,
                    execution_id, batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.params.get("week_ending"),
                self.params.get("tier"),
                source_locator,
                error.line_number,
                error.raw_line[:500],  # Truncate to avoid huge strings
                None,  # No hash for parse errors
                RejectStage.INGEST.value,
                error.error_code,
                error.error_detail,
                self.execution_id,
                self.batch_id
            ))
    
    def _update_manifest(
        self, 
        conn: sqlite3.Connection, 
        metrics: IngestMetrics
    ) -> None:
        """Create or update week manifest entry."""
        conn.execute("""
            INSERT INTO otc_week_manifest (
                week_ending, tier, source_type, source_locator,
                source_sha256, source_bytes,
                row_count_raw, row_count_parsed, row_count_inserted, row_count_rejected,
                stage, execution_id, batch_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(week_ending, tier) DO UPDATE SET
                source_type = excluded.source_type,
                source_locator = excluded.source_locator,
                source_sha256 = excluded.source_sha256,
                source_bytes = excluded.source_bytes,
                row_count_raw = excluded.row_count_raw,
                row_count_parsed = excluded.row_count_parsed,
                row_count_inserted = excluded.row_count_inserted,
                row_count_rejected = excluded.row_count_rejected,
                stage = excluded.stage,
                execution_id = excluded.execution_id,
                batch_id = excluded.batch_id,
                updated_at = datetime('now')
        """, (
            metrics.week_ending,
            metrics.tier,
            self.params.get("source_type", "file"),
            metrics.source_locator,
            metrics.source_sha256,
            metrics.source_bytes,
            metrics.row_count_raw,
            metrics.row_count_parsed,
            metrics.row_count_inserted,
            metrics.row_count_rejected,
            ManifestStage.INGESTED.value,
            self.execution_id,
            self.batch_id
        ))
```

---

## Error Handling

### Parse Errors (Written to `otc_rejects`)

| Condition | Reason Code | Detail |
|-----------|-------------|--------|
| Wrong delimiter | `PARSE_ERROR` | "Expected 6 pipe-delimited fields, got N" |
| Invalid date | `PARSE_ERROR` | "Invalid week_ending: ..." |
| Not Friday | `PARSE_ERROR` | "Week ending must be Friday" |
| Week mismatch | `PARSE_ERROR` | "Week mismatch: file has X, expected Y" |
| Tier mismatch | `PARSE_ERROR` | "Tier mismatch: file has X, expected Y" |
| Invalid shares | `PARSE_ERROR` | "Invalid total_shares: 'X'" |
| Invalid trades | `PARSE_ERROR` | "Invalid total_trades: 'X'" |

### Deduplication

Records are deduplicated by `record_hash`:
- Hash includes: week_ending, tier, symbol, mpid, total_shares, total_trades
- Same record ingested twice → skipped (counted as `row_count_skipped`)
- Different volume for same natural key → treated as new record (allows corrections)

---

## CLI Usage

```powershell
# Basic usage
spine run otc.ingest_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p file_path=data/fixtures/otc/week_2025-12-26.psv

# Force re-ingest
spine run otc.ingest_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p file_path=data/fixtures/otc/week_2025-12-26.psv `
  -p force=true

# Output (success)
# Pipeline: otc.ingest_week
# Status: COMPLETED
# Metrics:
#   week_ending: 2025-12-26
#   tier: NMS_TIER_1
#   records_parsed: 15
#   records_inserted: 15
#   records_rejected: 0
#   records_skipped: 0
#   source_sha256: a1b2c3d4...
```

---

## Verification Queries

```sql
-- Check manifest after ingestion
SELECT week_ending, tier, stage, row_count_inserted, source_sha256
FROM otc_week_manifest
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1';

-- Check raw records
SELECT week_ending, tier, symbol, mpid, total_shares
FROM otc_raw
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
ORDER BY symbol, mpid;

-- Check rejects (should be empty for valid file)
SELECT line_number, reason_code, reason_detail
FROM otc_rejects
WHERE week_ending = '2025-12-26' AND stage = 'INGEST';
```

---

## Next: Read [04-pipelines-normalize.md](04-pipelines-normalize.md) for normalization pipeline
