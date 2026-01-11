# 04: Pipeline - Normalize Week

> **Purpose**: Transform raw OTC records into validated, normalized venue volume data. This pipeline validates domain invariants and creates the mapping table for lineage.

---

## Pipeline Specification

| Property | Value |
|----------|-------|
| **Name** | `otc.normalize_week` |
| **Idempotency** | Level 3: State-Idempotent (re-run → DELETE + INSERT → same final state) |
| **Dependencies** | `otc.ingest_week` (manifest stage >= INGESTED) |
| **Writes To** | `otc_venue_volume`, `otc_normalization_map`, `otc_rejects`, `otc_week_manifest` |
| **Lane** | NORMAL |

---

## Parameters Schema

```python
@dataclass
class NormalizeWeekParams:
    """Parameters for otc.normalize_week pipeline."""
    
    # Required
    tier: str                    # "NMS_TIER_1" | "NMS_TIER_2" | "OTC"
    week_ending: str             # ISO Friday date
    
    # Options
    force: bool = False          # Re-normalize even if already normalized
    reject_zero_volume: bool = False  # Treat zero volume as rejection (default: accept)
```

---

## Normalization Rules

### Accepted Records
A raw record is **ACCEPTED** if:
1. Symbol is valid (starts with letter, alphanumeric + dots/hyphens, max 10 chars)
2. MPID is valid (exactly 4 alphanumeric characters)
3. `total_shares >= 0` (or > 0 if `reject_zero_volume=true`)
4. `total_trades >= 0`
5. Natural key `(week_ending, tier, symbol, mpid)` is unique within this run

### Rejected Records
A raw record is **REJECTED** if any validation fails. Rejection reasons:

| Code | Condition |
|------|-----------|
| `INVALID_SYMBOL` | Symbol fails format validation |
| `INVALID_MPID` | MPID not 4 chars or not alphanumeric |
| `NEGATIVE_VOLUME` | `total_shares < 0` |
| `NEGATIVE_TRADES` | `total_trades < 0` |
| `ZERO_VOLUME` | `total_shares == 0` (only if `reject_zero_volume=true`) |
| `DUPLICATE_KEY` | Natural key already processed in this run |

---

## Implementation

### File: `domains/otc/pipelines/normalize_week.py`

```python
"""
OTC Normalize Week Pipeline

Transforms raw OTC records into validated, normalized venue volume data.
Creates normalization map for lineage tracking.

Idempotency: Level 3 (State-Idempotent)
- Re-running DELETEs existing normalized data for week, then re-inserts
- Same raw data → same normalized output
"""
import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import sqlite3

from spine.core.pipeline import Pipeline, PipelineResult, PipelineStatus
from spine.core.registry import register_pipeline

from ..enums import Tier, ManifestStage, NormalizationStatus, RejectStage
from ..validators import WeekEnding, Symbol, MPID
from ..models import NormalizedVenueVolume, NormalizationResult, Reject

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "v1.0.0"


@dataclass
class NormalizeMetrics:
    """Metrics collected during normalization."""
    week_ending: str
    tier: str
    records_read: int
    records_accepted: int
    records_rejected: int


@register_pipeline("otc.normalize_week")
class NormalizeWeekPipeline(Pipeline):
    """
    Normalize raw OTC data for a single week.
    
    Creates:
    - Records in otc_venue_volume
    - Mapping entries in otc_normalization_map
    - Rejected records in otc_rejects
    - Updates otc_week_manifest stage
    """
    
    def validate_params(self) -> Optional[str]:
        """Validate required parameters."""
        params = self.params
        
        if not params.get("tier"):
            return "Missing required parameter: tier"
        try:
            Tier.from_string(params["tier"])
        except ValueError as e:
            return str(e)
        
        if not params.get("week_ending"):
            return "Missing required parameter: week_ending"
        try:
            WeekEnding(params["week_ending"])
        except ValueError as e:
            return str(e)
        
        return None
    
    def run(self) -> PipelineResult:
        """Execute the normalization pipeline."""
        validation_error = self.validate_params()
        if validation_error:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=validation_error,
                metrics={}
            )
        
        tier = Tier.from_string(self.params["tier"])
        week = WeekEnding(self.params["week_ending"])
        force = self.params.get("force", False)
        reject_zero_volume = self.params.get("reject_zero_volume", False)
        
        conn = self.get_connection()
        
        # Check prerequisites: week must be ingested
        manifest = conn.execute(
            "SELECT stage FROM otc_week_manifest WHERE week_ending = ? AND tier = ?",
            (str(week), tier.value)
        ).fetchone()
        
        if not manifest:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=f"Week {week}/{tier.value} not found in manifest. Run otc.ingest_week first.",
                metrics={}
            )
        
        current_stage = ManifestStage(manifest["stage"])
        if current_stage < ManifestStage.INGESTED:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=f"Week {week}/{tier.value} not yet ingested (stage={current_stage.value})",
                metrics={}
            )
        
        # Check if already normalized (unless force=True)
        if not force and current_stage >= ManifestStage.NORMALIZED:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                metrics={
                    "week_ending": str(week),
                    "tier": tier.value,
                    "skipped": True,
                    "reason": "Already normalized (use force=true to re-normalize)"
                }
            )
        
        # Delete existing normalized data (idempotency)
        self._clear_existing_data(conn, str(week), tier.value)
        
        # Fetch raw records
        raw_records = conn.execute("""
            SELECT record_hash, week_ending, tier, symbol, mpid, total_shares, total_trades
            FROM otc_raw
            WHERE week_ending = ? AND tier = ?
        """, (str(week), tier.value)).fetchall()
        
        if not raw_records:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                metrics={
                    "week_ending": str(week),
                    "tier": tier.value,
                    "records_read": 0,
                    "records_accepted": 0,
                    "records_rejected": 0,
                    "warning": "No raw records found for this week/tier"
                }
            )
        
        # Normalize each record
        results = []
        seen_keys = set()  # Track natural keys for duplicate detection
        
        for row in raw_records:
            result = self._normalize_record(
                row, 
                reject_zero_volume=reject_zero_volume,
                seen_keys=seen_keys
            )
            results.append(result)
            
            if result.status == NormalizationStatus.ACCEPTED:
                # Add to seen keys
                key = (str(week), tier.value, result.normalized.symbol.value, result.normalized.mpid.value)
                seen_keys.add(key)
        
        # Insert accepted records
        accepted = [r for r in results if r.status == NormalizationStatus.ACCEPTED]
        self._insert_normalized(conn, accepted)
        
        # Insert mapping entries
        self._insert_mapping(conn, results)
        
        # Insert rejects
        rejected = [r for r in results if r.status == NormalizationStatus.REJECTED]
        self._insert_rejects(conn, rejected, str(week), tier.value)
        
        # Update manifest
        self._update_manifest(conn, str(week), tier.value, len(accepted), len(rejected))
        
        conn.commit()
        
        logger.info(
            f"Normalized {len(accepted)} records for {tier.value}/{str(week)} "
            f"({len(rejected)} rejected)"
        )
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            metrics={
                "week_ending": str(week),
                "tier": tier.value,
                "records_read": len(raw_records),
                "records_accepted": len(accepted),
                "records_rejected": len(rejected)
            }
        )
    
    def _clear_existing_data(
        self, 
        conn: sqlite3.Connection, 
        week_ending: str, 
        tier: str
    ) -> None:
        """Clear existing normalized data for idempotency."""
        conn.execute(
            "DELETE FROM otc_venue_volume WHERE week_ending = ? AND tier = ?",
            (week_ending, tier)
        )
        conn.execute(
            "DELETE FROM otc_normalization_map WHERE week_ending = ? AND tier = ?",
            (week_ending, tier)
        )
    
    def _normalize_record(
        self,
        row: sqlite3.Row,
        reject_zero_volume: bool,
        seen_keys: set
    ) -> NormalizationResult:
        """
        Validate and normalize a single raw record.
        
        Returns NormalizationResult with ACCEPTED or REJECTED status.
        """
        record_hash = row["record_hash"]
        
        # Validate symbol
        try:
            symbol = Symbol(row["symbol"])
        except ValueError as e:
            return NormalizationResult(
                raw_record_hash=record_hash,
                status=NormalizationStatus.REJECTED,
                reject_reason="INVALID_SYMBOL",
                reject_detail=str(e)
            )
        
        # Validate MPID
        try:
            mpid = MPID(row["mpid"])
        except ValueError as e:
            return NormalizationResult(
                raw_record_hash=record_hash,
                status=NormalizationStatus.REJECTED,
                reject_reason="INVALID_MPID",
                reject_detail=str(e)
            )
        
        # Validate volumes
        total_shares = row["total_shares"]
        total_trades = row["total_trades"]
        
        if total_shares < 0:
            return NormalizationResult(
                raw_record_hash=record_hash,
                status=NormalizationStatus.REJECTED,
                reject_reason="NEGATIVE_VOLUME",
                reject_detail=f"total_shares={total_shares}"
            )
        
        if total_trades < 0:
            return NormalizationResult(
                raw_record_hash=record_hash,
                status=NormalizationStatus.REJECTED,
                reject_reason="NEGATIVE_TRADES",
                reject_detail=f"total_trades={total_trades}"
            )
        
        if reject_zero_volume and total_shares == 0:
            return NormalizationResult(
                raw_record_hash=record_hash,
                status=NormalizationStatus.REJECTED,
                reject_reason="ZERO_VOLUME",
                reject_detail="total_shares=0 and reject_zero_volume=true"
            )
        
        # Check for duplicate natural key
        week = WeekEnding(row["week_ending"])
        tier = Tier.from_string(row["tier"])
        key = (str(week), tier.value, symbol.value, mpid.value)
        
        if key in seen_keys:
            return NormalizationResult(
                raw_record_hash=record_hash,
                status=NormalizationStatus.REJECTED,
                reject_reason="DUPLICATE_KEY",
                reject_detail=f"Natural key {key} already processed"
            )
        
        # Compute avg trade size
        if total_trades > 0:
            avg_trade_size = Decimal(total_shares) / Decimal(total_trades)
            avg_trade_size = avg_trade_size.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            avg_trade_size = Decimal("0")
        
        # Create normalized record
        normalized = NormalizedVenueVolume(
            week_ending=week,
            tier=tier,
            symbol=symbol,
            mpid=mpid,
            total_shares=total_shares,
            total_trades=total_trades,
            avg_trade_size=avg_trade_size,
            raw_record_hash=record_hash,
            execution_id=self.execution_id,
            batch_id=self.batch_id
        )
        
        return NormalizationResult(
            raw_record_hash=record_hash,
            status=NormalizationStatus.ACCEPTED,
            normalized=normalized
        )
    
    def _insert_normalized(
        self, 
        conn: sqlite3.Connection, 
        results: list[NormalizationResult]
    ) -> None:
        """Insert accepted records into otc_venue_volume."""
        for result in results:
            if result.status != NormalizationStatus.ACCEPTED:
                continue
            
            n = result.normalized
            conn.execute("""
                INSERT INTO otc_venue_volume (
                    week_ending, tier, symbol, mpid,
                    total_shares, total_trades, avg_trade_size,
                    execution_id, batch_id, normalized_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                str(n.week_ending),
                n.tier.value,
                str(n.symbol),
                str(n.mpid),
                n.total_shares,
                n.total_trades,
                str(n.avg_trade_size),
                n.execution_id,
                n.batch_id
            ))
    
    def _insert_mapping(
        self, 
        conn: sqlite3.Connection, 
        results: list[NormalizationResult]
    ) -> None:
        """Insert mapping entries into otc_normalization_map."""
        for result in results:
            n = result.normalized
            conn.execute("""
                INSERT INTO otc_normalization_map (
                    raw_record_hash, week_ending, tier, symbol, mpid,
                    status, reject_reason, reject_detail,
                    execution_id, batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.raw_record_hash,
                str(n.week_ending) if n else self.params.get("week_ending"),
                n.tier.value if n else self.params.get("tier"),
                str(n.symbol) if n else None,
                str(n.mpid) if n else None,
                result.status.value,
                result.reject_reason,
                result.reject_detail,
                self.execution_id,
                self.batch_id
            ))
    
    def _insert_rejects(
        self, 
        conn: sqlite3.Connection, 
        results: list[NormalizationResult],
        week_ending: str,
        tier: str
    ) -> None:
        """Insert rejected records into otc_rejects."""
        for result in results:
            if result.status != NormalizationStatus.REJECTED:
                continue
            
            conn.execute("""
                INSERT INTO otc_rejects (
                    week_ending, tier, source_locator, line_number,
                    raw_line, raw_record_hash, stage, reason_code, reason_detail,
                    execution_id, batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                week_ending,
                tier,
                None,  # Source locator not available at normalize stage
                None,  # Line number not available
                None,  # Raw line not available
                result.raw_record_hash,
                RejectStage.NORMALIZE.value,
                result.reject_reason,
                result.reject_detail,
                self.execution_id,
                self.batch_id
            ))
    
    def _update_manifest(
        self, 
        conn: sqlite3.Connection, 
        week_ending: str, 
        tier: str,
        accepted: int,
        rejected: int
    ) -> None:
        """Update manifest with normalization results."""
        conn.execute("""
            UPDATE otc_week_manifest
            SET row_count_normalized = ?,
                row_count_rejected = row_count_rejected + ?,
                stage = ?,
                execution_id = ?,
                batch_id = ?,
                updated_at = datetime('now')
            WHERE week_ending = ? AND tier = ?
        """, (
            accepted,
            rejected,
            ManifestStage.NORMALIZED.value,
            self.execution_id,
            self.batch_id,
            week_ending,
            tier
        ))
```

---

## Normalization Map Usage

The `otc_normalization_map` table enables lineage queries:

```sql
-- Find all accepted records from a specific raw file
SELECT nm.symbol, nm.mpid, nm.status
FROM otc_normalization_map nm
JOIN otc_raw r ON nm.raw_record_hash = r.record_hash
WHERE r.week_ending = '2025-12-26'
  AND nm.status = 'ACCEPTED';

-- Find why a specific symbol was rejected
SELECT raw_record_hash, reject_reason, reject_detail
FROM otc_normalization_map
WHERE week_ending = '2025-12-26'
  AND symbol = 'BAD$YM'
  AND status = 'REJECTED';

-- Rejection breakdown by reason
SELECT reject_reason, COUNT(*) as count
FROM otc_normalization_map
WHERE week_ending = '2025-12-26' AND status = 'REJECTED'
GROUP BY reject_reason;
```

---

## CLI Usage

```powershell
# Basic usage (after ingest_week)
spine run otc.normalize_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26

# Force re-normalize
spine run otc.normalize_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p force=true

# Reject zero-volume records
spine run otc.normalize_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p reject_zero_volume=true
```

---

## Verification Queries

```sql
-- Check manifest stage updated
SELECT week_ending, tier, stage, row_count_normalized
FROM otc_week_manifest
WHERE week_ending = '2025-12-26';

-- Check normalized data
SELECT week_ending, tier, symbol, mpid, total_shares, avg_trade_size
FROM otc_venue_volume
WHERE week_ending = '2025-12-26'
ORDER BY total_shares DESC;

-- Check mapping for complete lineage
SELECT status, COUNT(*) as count
FROM otc_normalization_map
WHERE week_ending = '2025-12-26'
GROUP BY status;
```

---

## Next: Read [05-pipelines-aggregate.md](05-pipelines-aggregate.md) for aggregation pipeline
