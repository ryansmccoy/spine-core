# 06: Pipeline - Compute Rolling 6-Week

> **Purpose**: Compute 6-week rolling metrics (moving averages, trends) for all symbols. This demonstrates the platform's core value: temporal aggregations across weeks.

---

## Pipeline Specification

| Property | Value |
|----------|-------|
| **Name** | `otc.compute_rolling_6w` |
| **Idempotency** | Level 3: State-Idempotent (DELETE + INSERT pattern) |
| **Dependencies** | At least 1 week aggregated (ideally 6 for complete window) |
| **Writes To** | `otc_symbol_rolling_6w`, `otc_quality_checks`, `otc_week_manifest` |
| **Lane** | NORMAL |

---

## Parameters Schema

```python
@dataclass
class ComputeRolling6wParams:
    """Parameters for otc.compute_rolling_6w pipeline."""
    
    # Required
    tier: str                    # "NMS_TIER_1" | "NMS_TIER_2" | "OTC"
    
    # Optional
    week_ending: str = "latest"  # ISO Friday or "latest" for most recent
    rolling_version: str = None  # Override version (default: current)
    force: bool = False          # Re-compute even if exists
```

---

## Rolling Logic

### Window Definition
The 6-week window ends on `week_ending` and includes the 5 preceding weeks:

```
week_ending = 2025-12-26

Window: [2025-11-21, 2025-11-28, 2025-12-05, 2025-12-12, 2025-12-19, 2025-12-26]
         Week 1      Week 2      Week 3      Week 4      Week 5      Week 6 (latest)
```

### Metrics Per Symbol

For each symbol with data in the window:

```python
rolling = {
    "avg_6w_volume": SUM(weekly_volume) / weeks_in_window,
    "avg_6w_trades": SUM(weekly_trades) / weeks_in_window,
    "trend_direction": "UP" | "DOWN" | "FLAT",  # Based on trend_pct
    "trend_pct": ((last_2w_avg - first_2w_avg) / first_2w_avg) * 100,
    "weeks_in_window": actual_weeks_with_data,  # 1-6
    "is_complete_window": weeks_in_window == 6
}
```

### Trend Calculation

```python
# Get first 2 weeks and last 2 weeks with data
first_2w = sorted_weeks[:2]
last_2w = sorted_weeks[-2:]

first_2w_avg = avg(volume for week in first_2w)
last_2w_avg = avg(volume for week in last_2w)

trend_pct = ((last_2w_avg - first_2w_avg) / first_2w_avg) * 100

if trend_pct > 5.0:
    trend_direction = "UP"
elif trend_pct < -5.0:
    trend_direction = "DOWN"
else:
    trend_direction = "FLAT"
```

### Completeness Flags

**Critical Design Decision**: Rolling metrics are computed even with incomplete windows.

This allows:
- New symbols to have rolling data immediately
- Graceful handling of missing weeks
- Clear indication via `is_complete_window` flag

```python
# Symbol has data in 4 of 6 weeks
rolling = RollingSymbolMetrics(
    ...
    weeks_in_window=4,
    is_complete_window=False  # Consumer can filter if needed
)
```

---

## Implementation

### File: `domains/otc/pipelines/compute_rolling.py`

```python
"""
OTC Compute Rolling 6-Week Pipeline

Computes 6-week rolling metrics (moving averages, trends) for all symbols.
Handles incomplete windows gracefully with completeness flags.

Idempotency: Level 3 (State-Idempotent)
- Re-running DELETEs existing rolling data for week, then re-inserts
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import sqlite3

from spine.core.pipeline import Pipeline, PipelineResult, PipelineStatus
from spine.core.registry import register_pipeline

from ..enums import Tier, ManifestStage, TrendDirection, QualityStatus, QualityCategory
from ..validators import WeekEnding
from ..models import RollingSymbolMetrics, QualityCheck

logger = logging.getLogger(__name__)

ROLLING_VERSION = "v1.0.0"
TREND_THRESHOLD_PCT = Decimal("5.0")  # ±5% for UP/DOWN, else FLAT


@register_pipeline("otc.compute_rolling_6w")
class ComputeRolling6wPipeline(Pipeline):
    """
    Compute 6-week rolling metrics for all symbols in a tier.
    
    Creates:
    - Rolling metrics in otc_symbol_rolling_6w
    - Quality check results in otc_quality_checks
    - Updates otc_week_manifest stage to ROLLING
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
        
        # week_ending is optional - "latest" is default
        week_ending = params.get("week_ending", "latest")
        if week_ending != "latest":
            try:
                WeekEnding(week_ending)
            except ValueError as e:
                return str(e)
        
        return None
    
    def run(self) -> PipelineResult:
        """Execute the rolling metrics pipeline."""
        validation_error = self.validate_params()
        if validation_error:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=validation_error,
                metrics={}
            )
        
        tier = Tier.from_string(self.params["tier"])
        force = self.params.get("force", False)
        rolling_version = self.params.get("rolling_version", ROLLING_VERSION)
        
        conn = self.get_connection()
        
        # Determine week_ending
        week_ending_param = self.params.get("week_ending", "latest")
        if week_ending_param == "latest":
            # Find most recent aggregated week
            latest = conn.execute("""
                SELECT MAX(week_ending) as latest_week
                FROM otc_week_manifest
                WHERE tier = ? AND stage >= ?
            """, (tier.value, ManifestStage.AGGREGATED.value)).fetchone()
            
            if not latest or not latest["latest_week"]:
                return PipelineResult(
                    status=PipelineStatus.FAILED,
                    error=f"No aggregated weeks found for {tier.value}",
                    metrics={}
                )
            
            week = WeekEnding(latest["latest_week"])
        else:
            week = WeekEnding(week_ending_param)
        
        # Check if already computed (unless force=True)
        if not force:
            existing = conn.execute("""
                SELECT COUNT(*) as cnt FROM otc_symbol_rolling_6w
                WHERE week_ending = ? AND tier = ?
            """, (str(week), tier.value)).fetchone()
            
            if existing and existing["cnt"] > 0:
                return PipelineResult(
                    status=PipelineStatus.COMPLETED,
                    metrics={
                        "week_ending": str(week),
                        "tier": tier.value,
                        "skipped": True,
                        "reason": "Rolling already computed (use force=true to re-compute)"
                    }
                )
        
        # Generate 6-week window
        window_weeks = self._generate_week_window(week, weeks=6)
        
        # Fetch symbol summaries for all weeks in window
        symbol_data = self._fetch_symbol_data(conn, tier.value, window_weeks)
        
        if not symbol_data:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                metrics={
                    "week_ending": str(week),
                    "tier": tier.value,
                    "symbols_computed": 0,
                    "warning": "No symbol data found in 6-week window"
                }
            )
        
        # Clear existing rolling data (idempotency)
        self._clear_existing_data(conn, str(week), tier.value)
        
        # Compute rolling metrics for each symbol
        rolling_metrics = self._compute_rolling_metrics(
            symbol_data, str(week), tier.value, window_weeks, rolling_version
        )
        
        # Insert rolling metrics
        self._insert_rolling_metrics(conn, rolling_metrics)
        
        # Run quality checks
        quality_results = self._run_quality_checks(
            str(week), tier.value, rolling_metrics, len(window_weeks)
        )
        self._insert_quality_checks(conn, quality_results)
        
        # Update manifest for the target week
        self._update_manifest(conn, str(week), tier.value)
        
        conn.commit()
        
        # Stats
        complete_count = sum(1 for r in rolling_metrics if r.is_complete_window)
        incomplete_count = len(rolling_metrics) - complete_count
        
        logger.info(
            f"Computed rolling 6w for {len(rolling_metrics)} symbols "
            f"({complete_count} complete, {incomplete_count} incomplete) "
            f"for {tier.value}/{str(week)}"
        )
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            metrics={
                "week_ending": str(week),
                "tier": tier.value,
                "symbols_computed": len(rolling_metrics),
                "symbols_complete_window": complete_count,
                "symbols_incomplete_window": incomplete_count,
                "rolling_version": rolling_version
            }
        )
    
    def _generate_week_window(self, end_week: WeekEnding, weeks: int = 6) -> list[str]:
        """Generate list of week_ending dates for the rolling window."""
        window = []
        current = end_week.value
        for i in range(weeks):
            window.append(current.isoformat())
            current = current - timedelta(weeks=1)
        # Return in chronological order (oldest first)
        return list(reversed(window))
    
    def _fetch_symbol_data(
        self,
        conn: sqlite3.Connection,
        tier: str,
        window_weeks: list[str]
    ) -> dict[str, list[dict]]:
        """
        Fetch symbol summary data for all weeks in window.
        
        Returns:
            Dict mapping symbol -> list of {week_ending, volume, trades}
        """
        placeholders = ",".join("?" * len(window_weeks))
        rows = conn.execute(f"""
            SELECT week_ending, symbol, total_volume, total_trades
            FROM otc_symbol_summary
            WHERE tier = ? AND week_ending IN ({placeholders})
            ORDER BY symbol, week_ending
        """, [tier] + window_weeks).fetchall()
        
        by_symbol = defaultdict(list)
        for row in rows:
            by_symbol[row["symbol"]].append({
                "week_ending": row["week_ending"],
                "volume": row["total_volume"],
                "trades": row["total_trades"]
            })
        
        return dict(by_symbol)
    
    def _compute_rolling_metrics(
        self,
        symbol_data: dict[str, list[dict]],
        week_ending: str,
        tier: str,
        window_weeks: list[str],
        rolling_version: str
    ) -> list[RollingSymbolMetrics]:
        """Compute rolling metrics for all symbols."""
        metrics = []
        
        for symbol, weeks_data in symbol_data.items():
            # Sort by week
            weeks_data = sorted(weeks_data, key=lambda x: x["week_ending"])
            
            weeks_in_window = len(weeks_data)
            is_complete = weeks_in_window == len(window_weeks)
            
            # Compute averages
            total_volume = sum(w["volume"] for w in weeks_data)
            total_trades = sum(w["trades"] for w in weeks_data)
            
            avg_volume = total_volume // weeks_in_window
            avg_trades = total_trades // weeks_in_window
            
            # Compute trend
            trend_direction, trend_pct = self._compute_trend(weeks_data)
            
            metrics.append(RollingSymbolMetrics(
                week_ending=week_ending,
                tier=tier,
                symbol=symbol,
                avg_6w_volume=avg_volume,
                avg_6w_trades=avg_trades,
                trend_direction=trend_direction,
                trend_pct=trend_pct,
                weeks_in_window=weeks_in_window,
                is_complete_window=is_complete,
                rolling_version=rolling_version,
                execution_id=self.execution_id,
                batch_id=self.batch_id
            ))
        
        return metrics
    
    def _compute_trend(
        self, 
        weeks_data: list[dict]
    ) -> tuple[TrendDirection, Decimal]:
        """
        Compute trend direction and percentage.
        
        Compares average of first 2 weeks vs last 2 weeks.
        Returns (TrendDirection, trend_pct)
        """
        if len(weeks_data) < 2:
            # Not enough data for trend
            return TrendDirection.FLAT, Decimal("0")
        
        # Get first 2 and last 2 weeks (may overlap if < 4 weeks)
        n = len(weeks_data)
        if n <= 2:
            first_weeks = weeks_data[:1]
            last_weeks = weeks_data[-1:]
        elif n <= 4:
            first_weeks = weeks_data[:2]
            last_weeks = weeks_data[-2:]
        else:
            first_weeks = weeks_data[:2]
            last_weeks = weeks_data[-2:]
        
        first_avg = sum(w["volume"] for w in first_weeks) / len(first_weeks)
        last_avg = sum(w["volume"] for w in last_weeks) / len(last_weeks)
        
        if first_avg == 0:
            # Avoid division by zero
            if last_avg > 0:
                return TrendDirection.UP, Decimal("100")
            else:
                return TrendDirection.FLAT, Decimal("0")
        
        trend_pct = ((last_avg - first_avg) / first_avg) * 100
        trend_pct = Decimal(str(trend_pct)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        if trend_pct > TREND_THRESHOLD_PCT:
            return TrendDirection.UP, trend_pct
        elif trend_pct < -TREND_THRESHOLD_PCT:
            return TrendDirection.DOWN, trend_pct
        else:
            return TrendDirection.FLAT, trend_pct
    
    def _clear_existing_data(
        self, 
        conn: sqlite3.Connection, 
        week_ending: str, 
        tier: str
    ) -> None:
        """Clear existing rolling data for idempotency."""
        conn.execute(
            "DELETE FROM otc_symbol_rolling_6w WHERE week_ending = ? AND tier = ?",
            (week_ending, tier)
        )
        conn.execute(
            "DELETE FROM otc_quality_checks WHERE week_ending = ? AND tier = ? AND pipeline_name = ?",
            (week_ending, tier, "otc.compute_rolling_6w")
        )
    
    def _insert_rolling_metrics(
        self, 
        conn: sqlite3.Connection, 
        metrics: list[RollingSymbolMetrics]
    ) -> None:
        """Insert rolling metrics."""
        for m in metrics:
            conn.execute("""
                INSERT INTO otc_symbol_rolling_6w (
                    week_ending, tier, symbol,
                    avg_6w_volume, avg_6w_trades,
                    trend_direction, trend_pct,
                    weeks_in_window, is_complete_window,
                    rolling_version, execution_id, batch_id, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                m.week_ending,
                m.tier,
                m.symbol,
                m.avg_6w_volume,
                m.avg_6w_trades,
                m.trend_direction.value,
                str(m.trend_pct),
                m.weeks_in_window,
                1 if m.is_complete_window else 0,
                m.rolling_version,
                m.execution_id,
                m.batch_id
            ))
    
    def _run_quality_checks(
        self,
        week_ending: str,
        tier: str,
        metrics: list[RollingSymbolMetrics],
        expected_weeks: int
    ) -> list[QualityCheck]:
        """Run rolling-specific quality checks."""
        checks = []
        
        # Check 1: At least some symbols have complete windows
        complete_count = sum(1 for m in metrics if m.is_complete_window)
        complete_pct = (complete_count / len(metrics) * 100) if metrics else 0
        
        checks.append(QualityCheck(
            week_ending=week_ending,
            tier=tier,
            pipeline_name="otc.compute_rolling_6w",
            check_name="rolling_window_complete",
            check_category=QualityCategory.COMPLETENESS,
            status=QualityStatus.PASS if complete_pct >= 50 else QualityStatus.WARN,
            check_value=f"{complete_count}/{len(metrics)} ({complete_pct:.1f}%)",
            expected_value=f">50% of symbols",
            message=f"{complete_count} of {len(metrics)} symbols have complete 6-week window",
            execution_id=self.execution_id,
            batch_id=self.batch_id
        ))
        
        # Check 2: No zero averages (data quality indicator)
        zero_volume = sum(1 for m in metrics if m.avg_6w_volume == 0)
        checks.append(QualityCheck(
            week_ending=week_ending,
            tier=tier,
            pipeline_name="otc.compute_rolling_6w",
            check_name="no_zero_rolling_volume",
            check_category=QualityCategory.INTEGRITY,
            status=QualityStatus.PASS if zero_volume == 0 else QualityStatus.WARN,
            check_value=str(zero_volume),
            expected_value="0",
            message=f"{zero_volume} symbols with zero rolling average volume",
            execution_id=self.execution_id,
            batch_id=self.batch_id
        ))
        
        return checks
    
    def _insert_quality_checks(
        self, 
        conn: sqlite3.Connection, 
        checks: list[QualityCheck]
    ) -> None:
        """Insert quality check results."""
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
        """Update manifest to ROLLING stage."""
        conn.execute("""
            UPDATE otc_week_manifest
            SET stage = ?,
                execution_id = ?,
                batch_id = ?,
                updated_at = datetime('now')
            WHERE week_ending = ? AND tier = ?
        """, (
            ManifestStage.ROLLING.value,
            self.execution_id,
            self.batch_id,
            week_ending,
            tier
        ))
```

---

## CLI Usage

```powershell
# Compute rolling for latest aggregated week
spine run otc.compute_rolling_6w -p tier=NMS_TIER_1

# Compute for specific week
spine run otc.compute_rolling_6w `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26

# Force re-compute
spine run otc.compute_rolling_6w `
  -p tier=NMS_TIER_1 `
  -p week_ending=2025-12-26 `
  -p force=true
```

---

## Verification Queries

```sql
-- Rolling metrics with completeness
SELECT symbol, avg_6w_volume, avg_6w_trades, 
       trend_direction, trend_pct, 
       weeks_in_window, is_complete_window
FROM otc_symbol_rolling_6w
WHERE week_ending = '2025-12-26' AND tier = 'NMS_TIER_1'
ORDER BY avg_6w_volume DESC;

-- Symbols with incomplete windows
SELECT symbol, weeks_in_window
FROM otc_symbol_rolling_6w
WHERE week_ending = '2025-12-26' AND is_complete_window = 0;

-- Trending up symbols
SELECT symbol, trend_pct, avg_6w_volume
FROM otc_symbol_rolling_6w
WHERE week_ending = '2025-12-26' 
  AND trend_direction = 'UP'
ORDER BY trend_pct DESC;

-- Quality check results
SELECT check_name, status, check_value, message
FROM otc_quality_checks
WHERE week_ending = '2025-12-26' 
  AND pipeline_name = 'otc.compute_rolling_6w';
```

---

## Next: Read [07-pipelines-snapshot.md](07-pipelines-snapshot.md) for research snapshot pipeline
