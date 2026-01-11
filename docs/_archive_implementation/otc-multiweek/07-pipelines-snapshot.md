# 07: Pipeline - Research Snapshot Week

> **Purpose**: Build a denormalized, research-ready snapshot table that combines venue volume, symbol summaries, and rolling metrics for easy querying by analysts and downstream systems.

---

## Pipeline Specification

| Property | Value |
|----------|-------|
| **Name** | `otc.research_snapshot_week` |
| **Idempotency** | Level 3: State-Idempotent (DELETE + INSERT pattern) |
| **Dependencies** | `otc.aggregate_week` (rolling optional but included if available) |
| **Writes To** | `otc_research_snapshot`, `otc_week_manifest` |
| **Lane** | NORMAL |

---

## Parameters Schema

```python
@dataclass
class ResearchSnapshotParams:
    """Parameters for otc.research_snapshot_week pipeline."""
    
    # Required
    tier: str                       # "NMS_TIER_1" | "NMS_TIER_2" | "OTC"
    week_ending: str                # ISO Friday date
    
    # Options
    force: bool = False             # Re-build even if exists
    snapshot_version: str = None    # Override version (default: current)
```

---

## Snapshot Design

### Why a Snapshot Table?

The research snapshot solves several analyst pain points:

1. **Single source of truth**: All metrics for a symbol in one row
2. **Pre-joined**: No complex JOINs needed for common queries
3. **Version-controlled**: Know which calculation produced the data
4. **Quality-flagged**: See data quality status at a glance

### Schema Mapping

| Snapshot Column | Source Table | Source Column |
|-----------------|--------------|---------------|
| `total_volume` | `otc_symbol_summary` | `total_volume` |
| `total_trades` | `otc_symbol_summary` | `total_trades` |
| `venue_count` | `otc_symbol_summary` | `venue_count` |
| `avg_trade_size` | `otc_symbol_summary` | `avg_trade_size` |
| `top_venue_mpid` | `otc_venue_volume` | Computed (MAX volume) |
| `top_venue_share_pct` | `otc_venue_share` | `market_share_pct` |
| `rolling_*` | `otc_symbol_rolling_6w` | Various (NULL if not available) |
| `quality_status` | `otc_quality_checks` | Aggregated status |

---

## Implementation

### File: `domains/otc/pipelines/research_snapshot.py`

```python
"""
OTC Research Snapshot Pipeline

Builds a denormalized, research-ready snapshot combining:
- Symbol summaries
- Top venue information
- Rolling metrics (if available)
- Quality status

Idempotency: Level 3 (State-Idempotent)
"""
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import sqlite3

from spine.core.pipeline import Pipeline, PipelineResult, PipelineStatus
from spine.core.registry import register_pipeline

from ..enums import Tier, ManifestStage, QualityStatus
from ..validators import WeekEnding
from ..models import ResearchSnapshot

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = "v1.0.0"


@register_pipeline("otc.research_snapshot_week")
class ResearchSnapshotPipeline(Pipeline):
    """
    Build research-ready snapshot for a single week.
    
    Creates:
    - Denormalized records in otc_research_snapshot
    - Updates otc_week_manifest stage to SNAPSHOT
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
        """Execute the snapshot pipeline."""
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
        snapshot_version = self.params.get("snapshot_version", SNAPSHOT_VERSION)
        
        conn = self.get_connection()
        
        # Check prerequisites
        manifest = conn.execute(
            "SELECT stage FROM otc_week_manifest WHERE week_ending = ? AND tier = ?",
            (str(week), tier.value)
        ).fetchone()
        
        if not manifest:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=f"Week {week}/{tier.value} not found in manifest",
                metrics={}
            )
        
        current_stage = ManifestStage(manifest["stage"])
        if current_stage < ManifestStage.AGGREGATED:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=f"Week {week}/{tier.value} not aggregated (stage={current_stage.value})",
                metrics={}
            )
        
        # Check if already built (unless force=True)
        if not force and current_stage >= ManifestStage.SNAPSHOT:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                metrics={
                    "week_ending": str(week),
                    "tier": tier.value,
                    "skipped": True,
                    "reason": "Snapshot already built (use force=true to rebuild)"
                }
            )
        
        # Clear existing snapshot (idempotency)
        self._clear_existing_data(conn, str(week), tier.value)
        
        # Fetch symbol summaries
        summaries = self._fetch_symbol_summaries(conn, str(week), tier.value)
        
        if not summaries:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                metrics={
                    "week_ending": str(week),
                    "tier": tier.value,
                    "symbols_snapshotted": 0,
                    "warning": "No symbol summaries found"
                }
            )
        
        # Fetch top venues per symbol
        top_venues = self._fetch_top_venues(conn, str(week), tier.value)
        
        # Fetch rolling metrics (may be empty)
        rolling = self._fetch_rolling_metrics(conn, str(week), tier.value)
        
        # Fetch quality status
        quality_status = self._compute_quality_status(conn, str(week), tier.value)
        
        # Build snapshots
        snapshots = self._build_snapshots(
            summaries, top_venues, rolling, quality_status,
            str(week), tier.value, snapshot_version
        )
        
        # Insert snapshots
        self._insert_snapshots(conn, snapshots)
        
        # Update manifest
        self._update_manifest(conn, str(week), tier.value)
        
        conn.commit()
        
        has_rolling_count = sum(1 for s in snapshots if s.has_rolling_data)
        
        logger.info(
            f"Built snapshot for {len(snapshots)} symbols for {tier.value}/{str(week)} "
            f"({has_rolling_count} with rolling data)"
        )
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            metrics={
                "week_ending": str(week),
                "tier": tier.value,
                "symbols_snapshotted": len(snapshots),
                "symbols_with_rolling": has_rolling_count,
                "snapshot_version": snapshot_version
            }
        )
    
    def _clear_existing_data(
        self, 
        conn: sqlite3.Connection, 
        week_ending: str, 
        tier: str
    ) -> None:
        """Clear existing snapshot for idempotency."""
        conn.execute(
            "DELETE FROM otc_research_snapshot WHERE week_ending = ? AND tier = ?",
            (week_ending, tier)
        )
    
    def _fetch_symbol_summaries(
        self,
        conn: sqlite3.Connection,
        week_ending: str,
        tier: str
    ) -> list[dict]:
        """Fetch symbol summaries."""
        rows = conn.execute("""
            SELECT symbol, total_volume, total_trades, venue_count, avg_trade_size
            FROM otc_symbol_summary
            WHERE week_ending = ? AND tier = ?
        """, (week_ending, tier)).fetchall()
        
        return [dict(r) for r in rows]
    
    def _fetch_top_venues(
        self,
        conn: sqlite3.Connection,
        week_ending: str,
        tier: str
    ) -> dict[str, dict]:
        """
        Fetch top venue (by volume) for each symbol.
        
        Returns:
            Dict mapping symbol -> {mpid, share_pct}
        """
        # Find max volume venue per symbol
        rows = conn.execute("""
            WITH ranked AS (
                SELECT 
                    vv.symbol,
                    vv.mpid,
                    vv.total_shares,
                    vs.market_share_pct,
                    ROW_NUMBER() OVER (PARTITION BY vv.symbol ORDER BY vv.total_shares DESC) as rn
                FROM otc_venue_volume vv
                LEFT JOIN otc_venue_share vs 
                    ON vs.week_ending = vv.week_ending 
                    AND vs.tier = vv.tier 
                    AND vs.mpid = vv.mpid
                WHERE vv.week_ending = ? AND vv.tier = ?
            )
            SELECT symbol, mpid, market_share_pct
            FROM ranked
            WHERE rn = 1
        """, (week_ending, tier)).fetchall()
        
        return {r["symbol"]: {"mpid": r["mpid"], "share_pct": r["market_share_pct"]} for r in rows}
    
    def _fetch_rolling_metrics(
        self,
        conn: sqlite3.Connection,
        week_ending: str,
        tier: str
    ) -> dict[str, dict]:
        """
        Fetch rolling metrics for symbols.
        
        Returns:
            Dict mapping symbol -> rolling metrics dict
        """
        rows = conn.execute("""
            SELECT symbol, avg_6w_volume, avg_6w_trades, 
                   trend_direction, weeks_in_window, is_complete_window
            FROM otc_symbol_rolling_6w
            WHERE week_ending = ? AND tier = ?
        """, (week_ending, tier)).fetchall()
        
        return {
            r["symbol"]: {
                "avg_6w_volume": r["avg_6w_volume"],
                "avg_6w_trades": r["avg_6w_trades"],
                "trend_direction": r["trend_direction"],
                "weeks_available": r["weeks_in_window"],
                "is_complete": bool(r["is_complete_window"])
            }
            for r in rows
        }
    
    def _compute_quality_status(
        self,
        conn: sqlite3.Connection,
        week_ending: str,
        tier: str
    ) -> QualityStatus:
        """
        Compute overall quality status for the week.
        
        Returns worst status across all checks.
        """
        rows = conn.execute("""
            SELECT status, COUNT(*) as cnt
            FROM otc_quality_checks
            WHERE week_ending = ? AND tier = ?
            GROUP BY status
        """, (week_ending, tier)).fetchall()
        
        if not rows:
            return QualityStatus.PASS
        
        status_counts = {r["status"]: r["cnt"] for r in rows}
        
        if status_counts.get("FAIL", 0) > 0:
            return QualityStatus.FAIL
        elif status_counts.get("WARN", 0) > 0:
            return QualityStatus.WARN
        else:
            return QualityStatus.PASS
    
    def _build_snapshots(
        self,
        summaries: list[dict],
        top_venues: dict[str, dict],
        rolling: dict[str, dict],
        quality_status: QualityStatus,
        week_ending: str,
        tier: str,
        snapshot_version: str
    ) -> list[ResearchSnapshot]:
        """Build snapshot records by combining all data sources."""
        snapshots = []
        
        for summary in summaries:
            symbol = summary["symbol"]
            
            # Top venue
            top_venue = top_venues.get(symbol, {})
            top_venue_mpid = top_venue.get("mpid")
            top_venue_share = top_venue.get("share_pct")
            
            # Rolling
            symbol_rolling = rolling.get(symbol)
            has_rolling = symbol_rolling is not None
            
            snapshot = ResearchSnapshot(
                week_ending=week_ending,
                tier=tier,
                symbol=symbol,
                
                # From summary
                total_volume=summary["total_volume"],
                total_trades=summary["total_trades"],
                venue_count=summary["venue_count"],
                avg_trade_size=Decimal(summary["avg_trade_size"]) if summary["avg_trade_size"] else Decimal("0"),
                
                # Top venue
                top_venue_mpid=top_venue_mpid or "",
                top_venue_share_pct=Decimal(top_venue_share) if top_venue_share else Decimal("0"),
                
                # Rolling (may be None)
                rolling_avg_6w_volume=symbol_rolling["avg_6w_volume"] if has_rolling else None,
                rolling_avg_6w_trades=symbol_rolling["avg_6w_trades"] if has_rolling else None,
                rolling_trend_direction=symbol_rolling["trend_direction"] if has_rolling else None,
                rolling_weeks_available=symbol_rolling["weeks_available"] if has_rolling else None,
                rolling_is_complete=symbol_rolling["is_complete"] if has_rolling else None,
                
                # Quality
                has_rolling_data=has_rolling,
                quality_status=quality_status,
                
                # Metadata
                snapshot_version=snapshot_version,
                execution_id=self.execution_id,
                batch_id=self.batch_id
            )
            
            snapshots.append(snapshot)
        
        return snapshots
    
    def _insert_snapshots(
        self, 
        conn: sqlite3.Connection, 
        snapshots: list[ResearchSnapshot]
    ) -> None:
        """Insert snapshot records."""
        for s in snapshots:
            conn.execute("""
                INSERT INTO otc_research_snapshot (
                    week_ending, tier, symbol,
                    total_volume, total_trades, venue_count,
                    top_venue_mpid, top_venue_share_pct, avg_trade_size,
                    rolling_avg_6w_volume, rolling_avg_6w_trades,
                    rolling_trend_direction, rolling_weeks_available, rolling_is_complete,
                    has_rolling_data, quality_status,
                    snapshot_version, execution_id, batch_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                s.week_ending,
                s.tier,
                s.symbol,
                s.total_volume,
                s.total_trades,
                s.venue_count,
                s.top_venue_mpid,
                str(s.top_venue_share_pct),
                str(s.avg_trade_size),
                s.rolling_avg_6w_volume,
                s.rolling_avg_6w_trades,
                s.rolling_trend_direction,
                s.rolling_weeks_available,
                1 if s.rolling_is_complete else 0 if s.rolling_is_complete is not None else None,
                1 if s.has_rolling_data else 0,
                s.quality_status.value if s.quality_status else None,
                s.snapshot_version,
                s.execution_id,
                s.batch_id
            ))
    
    def _update_manifest(
        self, 
        conn: sqlite3.Connection, 
        week_ending: str, 
        tier: str
    ) -> None:
        """Update manifest to SNAPSHOT stage."""
        conn.execute("""
            UPDATE otc_week_manifest
            SET stage = ?,
                execution_id = ?,
                batch_id = ?,
                updated_at = datetime('now')
            WHERE week_ending = ? AND tier = ?
        """, (
            ManifestStage.SNAPSHOT.value,
            self.execution_id,
            self.batch_id,
            week_ending,
            tier
        ))
```

---

## Research Query Examples

The snapshot table enables simple, efficient queries:

```sql
-- Top 10 symbols by volume this week
SELECT symbol, total_volume, total_trades, venue_count, 
       rolling_trend_direction, quality_status
FROM otc_research_snapshot
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
ORDER BY total_volume DESC
LIMIT 10;

-- Trending up symbols with complete rolling data
SELECT symbol, total_volume, rolling_avg_6w_volume,
       (total_volume - rolling_avg_6w_volume) as vol_vs_avg
FROM otc_research_snapshot
WHERE week_ending = '2025-12-26' 
  AND tier = 'NMS_TIER_1'
  AND rolling_trend_direction = 'UP'
  AND rolling_is_complete = 1
ORDER BY vol_vs_avg DESC;

-- Venue concentration (symbols dominated by one venue)
SELECT symbol, top_venue_mpid, top_venue_share_pct
FROM otc_research_snapshot
WHERE week_ending = '2025-12-26'
  AND tier = 'NMS_TIER_1'
  AND CAST(top_venue_share_pct AS REAL) > 50
ORDER BY top_venue_share_pct DESC;

-- Data quality overview
SELECT quality_status, COUNT(*) as symbol_count
FROM otc_research_snapshot
WHERE week_ending = '2025-12-26'
GROUP BY quality_status;
```

---

## CLI Usage

```powershell
# Build snapshot for a week
spine run otc.research_snapshot_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26

# Force rebuild
spine run otc.research_snapshot_week `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p force=true
```

---

## Next: Read [08-pipelines-backfill.md](08-pipelines-backfill.md) for orchestration pipeline
