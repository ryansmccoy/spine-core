# 05: Pipeline - Aggregate Week

> **Purpose**: Compute per-week aggregates (symbol summaries, venue market shares) from normalized venue volume data. This pipeline also runs quality checks.

---

## Pipeline Specification

| Property | Value |
|----------|-------|
| **Name** | `otc.aggregate_week` |
| **Idempotency** | Level 3: State-Idempotent (DELETE + INSERT pattern) |
| **Dependencies** | `otc.normalize_week` (manifest stage >= NORMALIZED) |
| **Writes To** | `otc_symbol_summary`, `otc_venue_share`, `otc_quality_checks`, `otc_week_manifest` |
| **Lane** | NORMAL |

---

## Parameters Schema

```python
@dataclass
class AggregateWeekParams:
    """Parameters for otc.aggregate_week pipeline."""
    
    # Required
    tier: str                        # "NMS_TIER_1" | "NMS_TIER_2" | "OTC"
    week_ending: str                 # ISO Friday date
    
    # Options
    force: bool = False              # Re-aggregate even if already done
    calculation_version: str = None  # Override version (default: current)
```

---

## Aggregation Logic

### Symbol Summary
For each unique `(week_ending, tier, symbol)`:

```python
symbol_summary = {
    "total_volume": SUM(venue_volume.total_shares),
    "total_trades": SUM(venue_volume.total_trades),
    "venue_count": COUNT(DISTINCT venue_volume.mpid),
    "avg_trade_size": total_volume / total_trades  # if total_trades > 0
}
```

### Venue Market Share
For each unique `(week_ending, tier, mpid)`:

```python
venue_share = {
    "total_volume": SUM(venue_volume.total_shares),
    "total_trades": SUM(venue_volume.total_trades),
    "market_share_pct": (total_volume / tier_total_volume) * 100
}
```

Where `tier_total_volume` = SUM of all volume for the tier in that week.

---

## Quality Checks

The aggregate pipeline runs these quality checks:

| Check Name | Category | Pass Condition | Tolerance |
|------------|----------|----------------|-----------|
| `no_negative_volumes` | INTEGRITY | All volumes >= 0 | N/A |
| `no_negative_trades` | INTEGRITY | All trade counts >= 0 | N/A |
| `market_share_sum_100` | BUSINESS_RULE | Sum between 99.9% and 100.1% | ±0.1% |
| `no_duplicate_symbols` | INTEGRITY | No duplicate (week,tier,symbol) | N/A |
| `symbol_count_positive` | COMPLETENESS | At least 1 symbol | N/A |
| `venue_count_positive` | COMPLETENESS | At least 1 venue | N/A |

---

## Implementation

### File: `domains/otc/pipelines/aggregate_week.py`

```python
"""
OTC Aggregate Week Pipeline

Computes per-week aggregates from normalized venue volume data.
Runs quality checks and records results.

Idempotency: Level 3 (State-Idempotent)
- Re-running DELETEs existing aggregates, then re-inserts
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import sqlite3

from spine.core.pipeline import Pipeline, PipelineResult, PipelineStatus
from spine.core.registry import register_pipeline

from ..enums import (
    Tier, ManifestStage, QualityStatus, QualityCategory
)
from ..validators import WeekEnding
from ..models import SymbolSummary, VenueShare, QualityCheck

logger = logging.getLogger(__name__)

CALCULATION_VERSION = "v1.0.0"


@register_pipeline("otc.aggregate_week")
class AggregateWeekPipeline(Pipeline):
    """
    Aggregate normalized venue volume data for a single week.
    
    Creates:
    - Symbol summaries in otc_symbol_summary
    - Venue market shares in otc_venue_share
    - Quality check results in otc_quality_checks
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
        """Execute the aggregation pipeline."""
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
        calc_version = self.params.get("calculation_version", CALCULATION_VERSION)
        
        conn = self.get_connection()
        
        # Check prerequisites
        manifest = conn.execute(
            "SELECT stage FROM otc_week_manifest WHERE week_ending = ? AND tier = ?",
            (str(week), tier.value)
        ).fetchone()
        
        if not manifest:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=f"Week {week}/{tier.value} not found. Run ingest_week first.",
                metrics={}
            )
        
        current_stage = ManifestStage(manifest["stage"])
        if current_stage < ManifestStage.NORMALIZED:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=f"Week {week}/{tier.value} not normalized (stage={current_stage.value})",
                metrics={}
            )
        
        if not force and current_stage >= ManifestStage.AGGREGATED:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                metrics={
                    "week_ending": str(week),
                    "tier": tier.value,
                    "skipped": True,
                    "reason": "Already aggregated (use force=true to re-aggregate)"
                }
            )
        
        # Clear existing aggregates (idempotency)
        self._clear_existing_data(conn, str(week), tier.value)
        
        # Fetch normalized data
        venue_data = conn.execute("""
            SELECT symbol, mpid, total_shares, total_trades
            FROM otc_venue_volume
            WHERE week_ending = ? AND tier = ?
        """, (str(week), tier.value)).fetchall()
        
        if not venue_data:
            # No data - record quality check and return
            self._record_quality_check(conn, str(week), tier.value,
                "symbol_count_positive", QualityCategory.COMPLETENESS,
                QualityStatus.FAIL, "0", ">0", None, "No normalized data found")
            conn.commit()
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                metrics={
                    "week_ending": str(week),
                    "tier": tier.value,
                    "symbols_aggregated": 0,
                    "venues_aggregated": 0,
                    "warning": "No normalized data found"
                }
            )
        
        # Compute symbol summaries
        symbol_summaries = self._compute_symbol_summaries(
            venue_data, str(week), tier.value, calc_version
        )
        
        # Compute venue shares
        venue_shares = self._compute_venue_shares(
            venue_data, str(week), tier.value, calc_version
        )
        
        # Insert aggregates
        self._insert_symbol_summaries(conn, symbol_summaries)
        self._insert_venue_shares(conn, venue_shares)
        
        # Run quality checks
        quality_results = self._run_quality_checks(
            conn, str(week), tier.value, symbol_summaries, venue_shares
        )
        self._insert_quality_checks(conn, quality_results)
        
        # Update manifest
        self._update_manifest(conn, str(week), tier.value)
        
        conn.commit()
        
        # Determine overall quality status
        failed_checks = [q for q in quality_results if q.status == QualityStatus.FAIL]
        warn_checks = [q for q in quality_results if q.status == QualityStatus.WARN]
        
        logger.info(
            f"Aggregated {len(symbol_summaries)} symbols, {len(venue_shares)} venues "
            f"for {tier.value}/{str(week)} "
            f"(quality: {len(failed_checks)} FAIL, {len(warn_checks)} WARN)"
        )
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            metrics={
                "week_ending": str(week),
                "tier": tier.value,
                "symbols_aggregated": len(symbol_summaries),
                "venues_aggregated": len(venue_shares),
                "calculation_version": calc_version,
                "quality_checks_passed": len(quality_results) - len(failed_checks) - len(warn_checks),
                "quality_checks_warned": len(warn_checks),
                "quality_checks_failed": len(failed_checks)
            }
        )
    
    def _clear_existing_data(
        self, 
        conn: sqlite3.Connection, 
        week_ending: str, 
        tier: str
    ) -> None:
        """Clear existing aggregates for idempotency."""
        conn.execute(
            "DELETE FROM otc_symbol_summary WHERE week_ending = ? AND tier = ?",
            (week_ending, tier)
        )
        conn.execute(
            "DELETE FROM otc_venue_share WHERE week_ending = ? AND tier = ?",
            (week_ending, tier)
        )
        conn.execute(
            "DELETE FROM otc_quality_checks WHERE week_ending = ? AND tier = ? AND pipeline_name = ?",
            (week_ending, tier, "otc.aggregate_week")
        )
    
    def _compute_symbol_summaries(
        self,
        venue_data: list[sqlite3.Row],
        week_ending: str,
        tier: str,
        calc_version: str
    ) -> list[SymbolSummary]:
        """Compute per-symbol aggregates."""
        # Group by symbol
        by_symbol = defaultdict(list)
        for row in venue_data:
            by_symbol[row["symbol"]].append(row)
        
        summaries = []
        for symbol, rows in by_symbol.items():
            total_volume = sum(r["total_shares"] for r in rows)
            total_trades = sum(r["total_trades"] for r in rows)
            venue_count = len(set(r["mpid"] for r in rows))
            
            if total_trades > 0:
                avg_trade_size = Decimal(total_volume) / Decimal(total_trades)
                avg_trade_size = avg_trade_size.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                avg_trade_size = Decimal("0")
            
            summaries.append(SymbolSummary(
                week_ending=week_ending,
                tier=tier,
                symbol=symbol,
                total_volume=total_volume,
                total_trades=total_trades,
                venue_count=venue_count,
                avg_trade_size=avg_trade_size,
                calculation_version=calc_version,
                execution_id=self.execution_id,
                batch_id=self.batch_id
            ))
        
        return summaries
    
    def _compute_venue_shares(
        self,
        venue_data: list[sqlite3.Row],
        week_ending: str,
        tier: str,
        calc_version: str
    ) -> list[VenueShare]:
        """Compute per-venue market shares."""
        # Total volume for this tier/week
        tier_total = sum(r["total_shares"] for r in venue_data)
        
        # Group by venue (mpid)
        by_venue = defaultdict(list)
        for row in venue_data:
            by_venue[row["mpid"]].append(row)
        
        shares = []
        for mpid, rows in by_venue.items():
            total_volume = sum(r["total_shares"] for r in rows)
            total_trades = sum(r["total_trades"] for r in rows)
            
            if tier_total > 0:
                share_pct = (Decimal(total_volume) / Decimal(tier_total)) * 100
                share_pct = share_pct.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            else:
                share_pct = Decimal("0")
            
            shares.append(VenueShare(
                week_ending=week_ending,
                tier=tier,
                mpid=mpid,
                total_volume=total_volume,
                total_trades=total_trades,
                market_share_pct=share_pct,
                calculation_version=calc_version,
                execution_id=self.execution_id,
                batch_id=self.batch_id
            ))
        
        return shares
    
    def _insert_symbol_summaries(
        self, 
        conn: sqlite3.Connection, 
        summaries: list[SymbolSummary]
    ) -> None:
        """Insert symbol summaries."""
        for s in summaries:
            conn.execute("""
                INSERT INTO otc_symbol_summary (
                    week_ending, tier, symbol,
                    total_volume, total_trades, venue_count, avg_trade_size,
                    calculation_version, execution_id, batch_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                s.week_ending,
                s.tier,
                s.symbol,
                s.total_volume,
                s.total_trades,
                s.venue_count,
                str(s.avg_trade_size),
                s.calculation_version,
                s.execution_id,
                s.batch_id
            ))
    
    def _insert_venue_shares(
        self, 
        conn: sqlite3.Connection, 
        shares: list[VenueShare]
    ) -> None:
        """Insert venue market shares."""
        for v in shares:
            conn.execute("""
                INSERT INTO otc_venue_share (
                    week_ending, tier, mpid,
                    total_volume, total_trades, market_share_pct,
                    calculation_version, execution_id, batch_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                v.week_ending,
                v.tier,
                v.mpid,
                v.total_volume,
                v.total_trades,
                str(v.market_share_pct),
                v.calculation_version,
                v.execution_id,
                v.batch_id
            ))
    
    def _run_quality_checks(
        self,
        conn: sqlite3.Connection,
        week_ending: str,
        tier: str,
        summaries: list[SymbolSummary],
        shares: list[VenueShare]
    ) -> list[QualityCheck]:
        """Run all quality checks and return results."""
        checks = []
        
        # Check 1: No negative volumes
        negative_vols = [s for s in summaries if s.total_volume < 0]
        checks.append(QualityCheck(
            week_ending=week_ending,
            tier=tier,
            pipeline_name="otc.aggregate_week",
            check_name="no_negative_volumes",
            check_category=QualityCategory.INTEGRITY,
            status=QualityStatus.PASS if not negative_vols else QualityStatus.FAIL,
            check_value=str(len(negative_vols)),
            expected_value="0",
            message=f"{len(negative_vols)} symbols with negative volume" if negative_vols else "All volumes non-negative",
            execution_id=self.execution_id,
            batch_id=self.batch_id
        ))
        
        # Check 2: No negative trades
        negative_trades = [s for s in summaries if s.total_trades < 0]
        checks.append(QualityCheck(
            week_ending=week_ending,
            tier=tier,
            pipeline_name="otc.aggregate_week",
            check_name="no_negative_trades",
            check_category=QualityCategory.INTEGRITY,
            status=QualityStatus.PASS if not negative_trades else QualityStatus.FAIL,
            check_value=str(len(negative_trades)),
            expected_value="0",
            message=f"{len(negative_trades)} symbols with negative trades" if negative_trades else "All trades non-negative",
            execution_id=self.execution_id,
            batch_id=self.batch_id
        ))
        
        # Check 3: Market share sums to ~100%
        total_share = sum(Decimal(str(v.market_share_pct)) for v in shares)
        share_ok = Decimal("99.9") <= total_share <= Decimal("100.1")
        checks.append(QualityCheck(
            week_ending=week_ending,
            tier=tier,
            pipeline_name="otc.aggregate_week",
            check_name="market_share_sum_100",
            check_category=QualityCategory.BUSINESS_RULE,
            status=QualityStatus.PASS if share_ok else QualityStatus.WARN,
            check_value=str(total_share),
            expected_value="100.0",
            tolerance="0.1",
            message=f"Market share sum: {total_share}%",
            execution_id=self.execution_id,
            batch_id=self.batch_id
        ))
        
        # Check 4: Symbol count positive
        checks.append(QualityCheck(
            week_ending=week_ending,
            tier=tier,
            pipeline_name="otc.aggregate_week",
            check_name="symbol_count_positive",
            check_category=QualityCategory.COMPLETENESS,
            status=QualityStatus.PASS if summaries else QualityStatus.FAIL,
            check_value=str(len(summaries)),
            expected_value=">0",
            message=f"{len(summaries)} symbols aggregated",
            execution_id=self.execution_id,
            batch_id=self.batch_id
        ))
        
        # Check 5: Venue count positive
        checks.append(QualityCheck(
            week_ending=week_ending,
            tier=tier,
            pipeline_name="otc.aggregate_week",
            check_name="venue_count_positive",
            check_category=QualityCategory.COMPLETENESS,
            status=QualityStatus.PASS if shares else QualityStatus.FAIL,
            check_value=str(len(shares)),
            expected_value=">0",
            message=f"{len(shares)} venues aggregated",
            execution_id=self.execution_id,
            batch_id=self.batch_id
        ))
        
        return checks
    
    def _record_quality_check(
        self,
        conn: sqlite3.Connection,
        week_ending: str,
        tier: str,
        check_name: str,
        category: QualityCategory,
        status: QualityStatus,
        check_value: str,
        expected: str,
        tolerance: Optional[str],
        message: str
    ) -> None:
        """Record a single quality check."""
        conn.execute("""
            INSERT INTO otc_quality_checks (
                week_ending, tier, pipeline_name, check_name, check_category,
                status, check_value, expected_value, tolerance, message,
                execution_id, batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            week_ending, tier, "otc.aggregate_week", check_name,
            category.value, status.value, check_value, expected,
            tolerance, message, self.execution_id, self.batch_id
        ))
    
    def _insert_quality_checks(
        self, 
        conn: sqlite3.Connection, 
        checks: list[QualityCheck]
    ) -> None:
        """Insert all quality check results."""
        for c in checks:
            conn.execute("""
                INSERT INTO otc_quality_checks (
                    week_ending, tier, pipeline_name, check_name, check_category,
                    status, check_value, expected_value, tolerance, message,
                    execution_id, batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c.week_ending, c.tier, c.pipeline_name, c.check_name,
                c.check_category.value, c.status.value, c.check_value,
                c.expected_value, c.tolerance, c.message,
                c.execution_id, c.batch_id
            ))
    
    def _update_manifest(
        self, 
        conn: sqlite3.Connection, 
        week_ending: str, 
        tier: str
    ) -> None:
        """Update manifest to AGGREGATED stage."""
        conn.execute("""
            UPDATE otc_week_manifest
            SET stage = ?,
                execution_id = ?,
                batch_id = ?,
                updated_at = datetime('now')
            WHERE week_ending = ? AND tier = ?
        """, (
            ManifestStage.AGGREGATED.value,
            self.execution_id,
            self.batch_id,
            week_ending,
            tier
        ))
```

---

## CLI Usage

```powershell
# Basic usage
spine run otc.aggregate_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26

# Force re-aggregate
spine run otc.aggregate_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p force=true
```

---

## Verification Queries

```sql
-- Symbol summaries
SELECT symbol, total_volume, total_trades, venue_count, avg_trade_size
FROM otc_symbol_summary
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
ORDER BY total_volume DESC;

-- Venue market shares
SELECT mpid, market_share_pct, total_volume
FROM otc_venue_share
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
ORDER BY market_share_pct DESC;

-- Quality check results
SELECT check_name, status, check_value, message
FROM otc_quality_checks
WHERE week_ending = '2025-12-26' AND pipeline_name = 'otc.aggregate_week';
```

---

## Next: Read [06-pipelines-rolling.md](06-pipelines-rolling.md) for rolling metrics pipeline
