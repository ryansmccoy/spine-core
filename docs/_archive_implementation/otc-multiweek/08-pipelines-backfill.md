# 08: Pipeline - Backfill Range (Orchestration)

> **Purpose**: Orchestrate the full 6-week backfill workflow. This is the top-level pipeline that coordinates ingest → normalize → aggregate for each week, then computes rolling metrics and builds the snapshot.

---

## Pipeline Specification

| Property | Value |
|----------|-------|
| **Name** | `otc.backfill_range` |
| **Idempotency** | Level 3: State-Idempotent (each sub-pipeline is idempotent) |
| **Dependencies** | Source files must exist for each week |
| **Writes To** | All tables (via sub-pipelines) |
| **Lane** | NORMAL |

---

## Parameters Schema

```python
@dataclass
class BackfillRangeParams:
    """Parameters for otc.backfill_range pipeline."""
    
    # Required
    tier: str                       # "NMS_TIER_1" | "NMS_TIER_2" | "OTC"
    
    # Week specification (one required)
    weeks_back: int = None          # N weeks back from today (inclusive of today's week)
    start_week: str = None          # ISO Friday date (explicit range start)
    end_week: str = None            # ISO Friday date (explicit range end, inclusive)
    
    # Source
    source_dir: str = None          # Directory containing week files (default: data/otc/{tier})
    file_pattern: str = "week_{week_ending}.psv"  # File naming pattern
    
    # Options
    force: bool = False             # Re-process all stages even if complete
    skip_rolling: bool = False      # Skip rolling computation
    skip_snapshot: bool = False     # Skip snapshot build
```

---

## Workflow

### Execution Flow (Synchronous)

```
backfill_range
│
├── Create batch_id: "backfill_{tier}_{start}_{end}_{timestamp}"
│
├── For each week in range (chronologically):
│   │
│   ├── otc.ingest_week
│   │   └── parent_execution_id = backfill execution
│   │
│   ├── otc.normalize_week  
│   │   └── parent_execution_id = ingest execution
│   │
│   └── otc.aggregate_week
│       └── parent_execution_id = normalize execution
│
├── otc.compute_rolling_6w (for latest week)
│   └── parent_execution_id = backfill execution
│
└── otc.research_snapshot_week (for latest week)
    └── parent_execution_id = rolling execution
```

### Batch Identity

```python
batch_id = f"backfill_{tier}_{start_week}_{end_week}_{timestamp}"
# Example: "backfill_NMS_TIER_1_2025-11-21_2025-12-26_20260102T150022"
```

All sub-pipeline executions share this `batch_id`, enabling:
- "Show me everything from this backfill run"
- "Which backfill created this data?"
- "Re-run this entire backfill if needed"

---

## Implementation

### File: `domains/otc/pipelines/backfill_range.py`

```python
"""
OTC Backfill Range Pipeline (Orchestration)

Orchestrates the full multi-week workflow:
1. For each week: ingest → normalize → aggregate
2. Compute rolling metrics for latest week
3. Build research snapshot for latest week

This is the canonical Basic tier entry point for multi-week processing.

Idempotency: Level 3 (State-Idempotent)
- Each sub-pipeline is idempotent
- Re-running produces same final state
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional
import sqlite3

from spine.core.pipeline import Pipeline, PipelineResult, PipelineStatus
from spine.core.registry import register_pipeline
from spine.core.dispatcher import get_dispatcher

from ..enums import Tier
from ..validators import WeekEnding

logger = logging.getLogger(__name__)


@dataclass
class BackfillMetrics:
    """Accumulated metrics from backfill run."""
    weeks_processed: int = 0
    total_ingested: int = 0
    total_normalized: int = 0
    total_rejected: int = 0
    rolling_computed: bool = False
    snapshot_built: bool = False
    errors: list[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@register_pipeline("otc.backfill_range")
class BackfillRangePipeline(Pipeline):
    """
    Orchestrate multi-week OTC data processing.
    
    This pipeline runs synchronously in Basic tier, executing
    each sub-pipeline in sequence. In higher tiers, this would
    submit async tasks instead.
    """
    
    def validate_params(self) -> Optional[str]:
        """Validate parameters."""
        params = self.params
        
        # Tier required
        if not params.get("tier"):
            return "Missing required parameter: tier"
        try:
            Tier.from_string(params["tier"])
        except ValueError as e:
            return str(e)
        
        # Week specification: either weeks_back OR start_week+end_week
        weeks_back = params.get("weeks_back")
        start_week = params.get("start_week")
        end_week = params.get("end_week")
        
        if weeks_back is not None:
            if not isinstance(weeks_back, int) or weeks_back < 1:
                return "weeks_back must be a positive integer"
        elif start_week and end_week:
            try:
                sw = WeekEnding(start_week)
                ew = WeekEnding(end_week)
                if sw.value > ew.value:
                    return f"start_week ({start_week}) must be <= end_week ({end_week})"
            except ValueError as e:
                return str(e)
        else:
            return "Must specify either weeks_back OR both start_week and end_week"
        
        return None
    
    def run(self) -> PipelineResult:
        """Execute the backfill orchestration."""
        validation_error = self.validate_params()
        if validation_error:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error=validation_error,
                metrics={}
            )
        
        tier = Tier.from_string(self.params["tier"])
        force = self.params.get("force", False)
        skip_rolling = self.params.get("skip_rolling", False)
        skip_snapshot = self.params.get("skip_snapshot", False)
        
        # Determine week range
        week_list = self._compute_week_list()
        
        if not week_list:
            return PipelineResult(
                status=PipelineStatus.FAILED,
                error="No weeks to process",
                metrics={}
            )
        
        # Create batch identity
        start_week = week_list[0]
        end_week = week_list[-1]
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        batch_id = f"backfill_{tier.value}_{start_week}_{end_week}_{timestamp}"
        
        logger.info(f"Starting backfill: {batch_id}")
        logger.info(f"Processing {len(week_list)} weeks: {start_week} to {end_week}")
        
        # Resolve source directory
        source_dir = self._resolve_source_dir(tier)
        file_pattern = self.params.get("file_pattern", "week_{week_ending}.psv")
        
        # Get dispatcher for sub-pipeline execution
        dispatcher = get_dispatcher()
        
        # Accumulated metrics
        metrics = BackfillMetrics()
        
        # Process each week
        for week in week_list:
            week_result = self._process_week(
                dispatcher=dispatcher,
                tier=tier,
                week=week,
                source_dir=source_dir,
                file_pattern=file_pattern,
                batch_id=batch_id,
                force=force
            )
            
            if week_result["success"]:
                metrics.weeks_processed += 1
                metrics.total_ingested += week_result.get("ingested", 0)
                metrics.total_normalized += week_result.get("normalized", 0)
                metrics.total_rejected += week_result.get("rejected", 0)
            else:
                metrics.errors.append(f"{week}: {week_result.get('error', 'Unknown error')}")
        
        # Compute rolling (for latest week)
        if not skip_rolling and metrics.weeks_processed > 0:
            rolling_result = self._run_rolling(
                dispatcher=dispatcher,
                tier=tier,
                week=end_week,
                batch_id=batch_id,
                force=force
            )
            metrics.rolling_computed = rolling_result["success"]
            if not rolling_result["success"]:
                metrics.errors.append(f"Rolling: {rolling_result.get('error')}")
        
        # Build snapshot (for latest week)
        if not skip_snapshot and metrics.weeks_processed > 0:
            snapshot_result = self._run_snapshot(
                dispatcher=dispatcher,
                tier=tier,
                week=end_week,
                batch_id=batch_id,
                force=force
            )
            metrics.snapshot_built = snapshot_result["success"]
            if not snapshot_result["success"]:
                metrics.errors.append(f"Snapshot: {snapshot_result.get('error')}")
        
        # Determine overall status
        if metrics.weeks_processed == 0:
            status = PipelineStatus.FAILED
        elif metrics.errors:
            status = PipelineStatus.COMPLETED  # Partial success
        else:
            status = PipelineStatus.COMPLETED
        
        logger.info(
            f"Backfill complete: {metrics.weeks_processed}/{len(week_list)} weeks, "
            f"{metrics.total_ingested} records ingested, "
            f"{metrics.total_rejected} rejected"
        )
        
        return PipelineResult(
            status=status,
            error="; ".join(metrics.errors) if metrics.errors else None,
            metrics={
                "batch_id": batch_id,
                "tier": tier.value,
                "weeks_requested": len(week_list),
                "weeks_processed": metrics.weeks_processed,
                "total_ingested": metrics.total_ingested,
                "total_normalized": metrics.total_normalized,
                "total_rejected": metrics.total_rejected,
                "rolling_computed": metrics.rolling_computed,
                "snapshot_built": metrics.snapshot_built,
                "errors": metrics.errors
            }
        )
    
    def _compute_week_list(self) -> list[str]:
        """Compute list of week_ending dates to process."""
        params = self.params
        
        if params.get("weeks_back") is not None:
            weeks_back = params["weeks_back"]
            weeks = []
            
            # Find this week's Friday
            today = date.today()
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0 and today.weekday() != 4:
                days_until_friday = 7
            this_friday = today + timedelta(days=days_until_friday)
            
            # Generate weeks going back
            for i in range(weeks_back - 1, -1, -1):
                week_date = this_friday - timedelta(weeks=i)
                weeks.append(week_date.isoformat())
            
            return weeks
        else:
            start = WeekEnding(params["start_week"])
            end = WeekEnding(params["end_week"])
            
            weeks = []
            current = start.value
            while current <= end.value:
                weeks.append(current.isoformat())
                current = current + timedelta(weeks=1)
            
            return weeks
    
    def _resolve_source_dir(self, tier: Tier) -> Path:
        """Resolve source directory for week files."""
        source_dir = self.params.get("source_dir")
        
        if source_dir:
            return Path(source_dir)
        else:
            # Default: data/otc/{tier}/ or data/fixtures/otc/
            default_paths = [
                Path(f"data/otc/{tier.value.lower()}"),
                Path("data/fixtures/otc"),
                Path("data/otc"),
            ]
            for p in default_paths:
                if p.exists():
                    return p
            return Path("data/fixtures/otc")
    
    def _process_week(
        self,
        dispatcher,
        tier: Tier,
        week: str,
        source_dir: Path,
        file_pattern: str,
        batch_id: str,
        force: bool
    ) -> dict:
        """Process a single week: ingest → normalize → aggregate."""
        result = {
            "success": False,
            "ingested": 0,
            "normalized": 0,
            "rejected": 0
        }
        
        # Resolve file path
        file_name = file_pattern.format(week_ending=week)
        file_path = source_dir / file_name
        
        if not file_path.exists():
            result["error"] = f"Source file not found: {file_path}"
            logger.warning(result["error"])
            return result
        
        try:
            # 1. Ingest
            ingest_exec = dispatcher.submit(
                "otc.ingest_week",
                params={
                    "tier": tier.value,
                    "week_ending": week,
                    "source_type": "file",
                    "file_path": str(file_path),
                    "force": force
                },
                parent_execution_id=self.execution_id,
                batch_id=batch_id
            )
            
            if ingest_exec.status == PipelineStatus.FAILED:
                result["error"] = f"Ingest failed: {ingest_exec.error}"
                return result
            
            result["ingested"] = ingest_exec.metrics.get("records_inserted", 0)
            
            # 2. Normalize
            normalize_exec = dispatcher.submit(
                "otc.normalize_week",
                params={
                    "tier": tier.value,
                    "week_ending": week,
                    "force": force
                },
                parent_execution_id=ingest_exec.execution_id,
                batch_id=batch_id
            )
            
            if normalize_exec.status == PipelineStatus.FAILED:
                result["error"] = f"Normalize failed: {normalize_exec.error}"
                return result
            
            result["normalized"] = normalize_exec.metrics.get("records_accepted", 0)
            result["rejected"] += normalize_exec.metrics.get("records_rejected", 0)
            
            # 3. Aggregate
            aggregate_exec = dispatcher.submit(
                "otc.aggregate_week",
                params={
                    "tier": tier.value,
                    "week_ending": week,
                    "force": force
                },
                parent_execution_id=normalize_exec.execution_id,
                batch_id=batch_id
            )
            
            if aggregate_exec.status == PipelineStatus.FAILED:
                result["error"] = f"Aggregate failed: {aggregate_exec.error}"
                return result
            
            result["success"] = True
            logger.info(f"Processed week {week}: {result['ingested']} ingested, {result['normalized']} normalized")
            
        except Exception as e:
            result["error"] = str(e)
            logger.exception(f"Error processing week {week}")
        
        return result
    
    def _run_rolling(
        self,
        dispatcher,
        tier: Tier,
        week: str,
        batch_id: str,
        force: bool
    ) -> dict:
        """Compute rolling metrics for latest week."""
        try:
            rolling_exec = dispatcher.submit(
                "otc.compute_rolling_6w",
                params={
                    "tier": tier.value,
                    "week_ending": week,
                    "force": force
                },
                parent_execution_id=self.execution_id,
                batch_id=batch_id
            )
            
            if rolling_exec.status == PipelineStatus.FAILED:
                return {"success": False, "error": rolling_exec.error}
            
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _run_snapshot(
        self,
        dispatcher,
        tier: Tier,
        week: str,
        batch_id: str,
        force: bool
    ) -> dict:
        """Build research snapshot for latest week."""
        try:
            snapshot_exec = dispatcher.submit(
                "otc.research_snapshot_week",
                params={
                    "tier": tier.value,
                    "week_ending": week,
                    "force": force
                },
                parent_execution_id=self.execution_id,
                batch_id=batch_id
            )
            
            if snapshot_exec.status == PipelineStatus.FAILED:
                return {"success": False, "error": snapshot_exec.error}
            
            return {"success": True}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

## CLI Usage

```powershell
# Backfill last 6 weeks (most common use case)
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p source_dir=data/fixtures/otc

# Explicit date range
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p start_week=2025-11-21 `
  -p end_week=2025-12-26 `
  -p source_dir=data/fixtures/otc

# Force re-process all
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p force=true

# Skip rolling/snapshot (just ingest+normalize+aggregate)
spine run otc.backfill_range `
  -p tier=NMS_TIER_1 `
  -p weeks_back=6 `
  -p skip_rolling=true `
  -p skip_snapshot=true
```

---

## Expected Output

```
Pipeline: otc.backfill_range
Status: COMPLETED
Metrics:
  batch_id: backfill_NMS_TIER_1_2025-11-21_2025-12-26_20260102T150022
  tier: NMS_TIER_1
  weeks_requested: 6
  weeks_processed: 6
  total_ingested: 72
  total_normalized: 71
  total_rejected: 1
  rolling_computed: true
  snapshot_built: true
  errors: []
```

---

## Verification Queries

```sql
-- Check manifest shows all weeks processed
SELECT week_ending, tier, stage, row_count_inserted, row_count_normalized
FROM otc_week_manifest
WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
ORDER BY week_ending;

-- Check lineage via batch_id
SELECT 
    'raw' as stage, COUNT(*) as records
FROM otc_raw WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
UNION ALL
SELECT 'normalized', COUNT(*) FROM otc_venue_volume WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
UNION ALL
SELECT 'summary', COUNT(*) FROM otc_symbol_summary WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
UNION ALL
SELECT 'rolling', COUNT(*) FROM otc_symbol_rolling_6w WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
UNION ALL
SELECT 'snapshot', COUNT(*) FROM otc_research_snapshot WHERE batch_id LIKE 'backfill_NMS_TIER_1%';

-- Find execution chain
SELECT execution_id, pipeline_name, parent_execution_id, batch_id
FROM executions
WHERE batch_id LIKE 'backfill_NMS_TIER_1%'
ORDER BY started_at;
```

---

## Next: Read [09-fixtures.md](09-fixtures.md) for test fixture files
