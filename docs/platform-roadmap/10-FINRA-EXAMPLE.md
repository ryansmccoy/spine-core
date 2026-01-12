# FINRA Example: End-to-End Integration

> **Purpose:** Demonstrate all new features using FINRA OTC Transparency domain.
> **Tier:** Intermediate (target)
> **Last Updated:** 2026-01-11

---

## Overview

This document shows how all platform-roadmap features integrate using the FINRA OTC Transparency ingestion as a complete example:

- Source protocol for API access
- Structured errors for failure handling
- Database adapters for storage
- Orchestration for workflow
- Scheduling for automation
- Alerting for notifications
- History for audit trail

---

## Current Implementation

The existing FINRA implementation in `spine-domains/src/spine/domains/finra/`:

```
finra/
├── __init__.py
├── domain_spec.yaml
├── models/
│   └── fact_bond_trade_activity.py
├── otc_transparency/
│   ├── __init__.py
│   ├── pipelines.py
│   ├── sources.py
│   └── quality.py
└── data_hub/
    └── ...
```

---

## Enhanced Implementation

### 1. Source Definition

```python
# spine/domains/finra/otc_transparency/sources.py
"""
FINRA OTC Transparency data sources.
"""

from dataclasses import dataclass
from typing import Any, Iterator
import requests

from spine.framework.sources import (
    Source,
    SourceResult,
    SourceMetadata,
    register_source,
)
from spine.core.errors import (
    SourceError,
    TransientError,
    RateLimitError,
    ValidationError,
)


@dataclass
class FINRAConfig:
    """FINRA API configuration."""
    base_url: str = "https://api.finra.org"
    api_key: str = ""
    timeout: int = 30
    
    @classmethod
    def from_env(cls) -> "FINRAConfig":
        import os
        return cls(
            base_url=os.environ.get("FINRA_API_URL", "https://api.finra.org"),
            api_key=os.environ["FINRA_API_KEY"],
            timeout=int(os.environ.get("FINRA_TIMEOUT", "30")),
        )


@register_source("finra.otc_transparency")
class FINRAOTCSource:
    """
    FINRA OTC Transparency weekly data source.
    
    Fetches bond trading activity data from FINRA API.
    
    Required params:
        tier: str - Trading tier (T1, T2, T3)
        week_ending: str - Week ending date (YYYY-MM-DD)
    """
    
    name = "finra.otc_transparency"
    
    def __init__(self, config: FINRAConfig | None = None):
        self.config = config or FINRAConfig.from_env()
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {self.config.api_key}"
    
    def validate(self, params: dict[str, Any]) -> list[str]:
        """Validate required parameters."""
        errors = []
        
        if "tier" not in params:
            errors.append("Missing required parameter: tier")
        elif params["tier"] not in ("T1", "T2", "T3"):
            errors.append(f"Invalid tier: {params['tier']}. Must be T1, T2, or T3")
        
        if "week_ending" not in params:
            errors.append("Missing required parameter: week_ending")
        
        return errors
    
    def fetch(self, params: dict[str, Any]) -> SourceResult:
        """Fetch weekly OTC transparency data."""
        # Validate params
        errors = self.validate(params)
        if errors:
            return SourceResult.fail("; ".join(errors))
        
        tier = params["tier"]
        week_ending = params["week_ending"]
        
        url = f"{self.config.base_url}/otc/transparency/weekly"
        query_params = {
            "tier": tier,
            "weekEnding": week_ending,
        }
        
        try:
            response = self._session.get(
                url,
                params=query_params,
                timeout=self.config.timeout,
            )
            
            # Handle HTTP errors
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise RateLimitError(
                    "FINRA API rate limit exceeded",
                    retry_after=retry_after,
                )
            
            if response.status_code >= 500:
                raise TransientError(
                    f"FINRA API server error: {response.status_code}",
                    metadata={"url": url, "status": response.status_code},
                )
            
            if response.status_code >= 400:
                raise SourceError(
                    f"FINRA API client error: {response.status_code}",
                    metadata={"url": url, "status": response.status_code},
                )
            
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            records = data.get("results", [])
            
            return SourceResult.success(
                records=records,
                metadata=SourceMetadata(
                    source_name=self.name,
                    record_count=len(records),
                    params=params,
                    response_headers={
                        "content-type": response.headers.get("content-type"),
                        "x-request-id": response.headers.get("x-request-id"),
                    },
                ),
            )
            
        except requests.Timeout as e:
            raise TransientError(
                "FINRA API request timeout",
                cause=e,
                metadata={"url": url, "timeout": self.config.timeout},
            )
        
        except requests.ConnectionError as e:
            raise TransientError(
                "FINRA API connection failed",
                cause=e,
                metadata={"url": url},
            )
    
    def stream(
        self,
        params: dict[str, Any],
        batch_size: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        """Stream records for large datasets."""
        result = self.fetch(params)
        
        if not result.success:
            raise SourceError(result.error or "Fetch failed")
        
        for record in result.records:
            yield record
```

---

### 2. Pipeline Definition

```python
# spine/domains/finra/otc_transparency/pipelines.py
"""
FINRA OTC Transparency pipelines.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from spine.framework.pipelines import Pipeline, PipelineResult, register_pipeline
from spine.framework.quality import QualityRunner
from spine.framework.sources import get_source
from spine.core.errors import TransformError, LoadError, ValidationError
from spine.core.storage import DatabaseAdapter


@register_pipeline("finra.otc_transparency.ingest_week")
class IngestWeekPipeline(Pipeline):
    """
    Ingest weekly OTC transparency data.
    
    Parameters:
        tier: str - Trading tier (T1, T2, T3)
        week_ending: str - Week ending date
    """
    
    name = "finra.otc_transparency.ingest_week"
    domain = "finra"
    
    def __init__(
        self,
        db: DatabaseAdapter,
        params: dict[str, Any],
    ):
        self.db = db
        self.params = params
        self.tier = params["tier"]
        self.week_ending = params["week_ending"]
    
    def run(self) -> PipelineResult:
        """Execute the ingestion pipeline."""
        
        # Step 1: Fetch from source
        source = get_source("finra.otc_transparency")
        result = source.fetch({
            "tier": self.tier,
            "week_ending": self.week_ending,
        })
        
        if not result.success:
            return PipelineResult.failed(error=result.error)
        
        raw_records = result.records
        
        # Step 2: Transform records
        try:
            records = self._transform(raw_records)
        except Exception as e:
            raise TransformError(
                f"Failed to transform records: {e}",
                cause=e,
            )
        
        # Step 3: Quality checks
        quality_runner = QualityRunner(self.db)
        quality_result = quality_runner.run(
            domain=self.domain,
            pipeline=self.name,
            records=records,
            checks=["record_count", "null_check", "duplicate_check"],
        )
        
        if not quality_result.passed:
            return PipelineResult.failed(
                error=f"Quality check failed: {quality_result.summary}",
                metrics={"quality": quality_result.metrics},
            )
        
        # Step 4: Load to database
        try:
            inserted = self._load(records)
        except Exception as e:
            raise LoadError(
                f"Failed to load records: {e}",
                cause=e,
            )
        
        return PipelineResult.completed(
            metrics={
                "fetched": len(raw_records),
                "transformed": len(records),
                "inserted": inserted,
                "quality": quality_result.metrics,
            },
        )
    
    def _transform(self, raw_records: list[dict]) -> list[dict]:
        """Transform raw API records to database format."""
        records = []
        
        for raw in raw_records:
            records.append({
                "week_ending": self.week_ending,
                "tier": self.tier,
                "cusip": raw.get("cusip") or raw.get("CUSIP"),
                "symbol": raw.get("symbol"),
                "issuer_name": raw.get("issuerName"),
                "volume_total": int(raw.get("totalVolume", 0)),
                "volume_customer": int(raw.get("customerVolume", 0)),
                "trade_count": int(raw.get("tradeCount", 0)),
                "avg_price": float(raw.get("avgPrice", 0)),
                "source": "FINRA_OTC",
                "loaded_at": datetime.utcnow().isoformat(),
            })
        
        return records
    
    def _load(self, records: list[dict]) -> int:
        """Load records to database."""
        if not records:
            return 0
        
        # Use upsert for idempotency
        columns = list(records[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        
        with self.db.transaction():
            self.db.execute_many(
                f"""
                INSERT OR REPLACE INTO fact_bond_trade_activity 
                ({", ".join(columns)})
                VALUES ({placeholders})
                """,
                [tuple(r[c] for c in columns) for r in records],
            )
        
        return len(records)
```

---

### 3. Workflow Definition

```python
# spine/domains/finra/otc_transparency/workflows.py
"""
FINRA OTC Transparency workflows.
"""

from spine.orchestration.v2 import (
    Workflow,
    Step,
    WorkflowContext,
    StepResult,
)
from spine.framework.sources import get_source
from spine.framework.quality import QualityRunner


def create_ingest_workflow() -> Workflow:
    """
    Create the weekly ingestion workflow.
    
    Steps:
    1. Fetch data from FINRA API
    2. Transform to internal format
    3. Run quality checks
    4. Load to database
    5. Send notification
    """
    
    return Workflow(
        name="finra.otc_transparency.ingest",
        steps=[
            Step.lambda_("fetch", fetch_step),
            Step.lambda_("transform", transform_step),
            Step.lambda_("quality_check", quality_step),
            Step.lambda_("load", load_step),
            Step.lambda_("notify", notify_step),
        ],
    )


def fetch_step(context: WorkflowContext, config: dict) -> StepResult:
    """Fetch data from FINRA API."""
    source = get_source("finra.otc_transparency")
    
    result = source.fetch({
        "tier": context.params["tier"],
        "week_ending": context.params["week_ending"],
    })
    
    if not result.success:
        return StepResult.fail(error=result.error)
    
    return StepResult.ok(
        output={"raw_records": result.records},
        metrics={"fetched": len(result.records)},
    )


def transform_step(context: WorkflowContext, config: dict) -> StepResult:
    """Transform raw records."""
    raw_records = context.outputs.get("fetch", {}).get("raw_records", [])
    
    records = []
    for raw in raw_records:
        records.append({
            "week_ending": context.params["week_ending"],
            "tier": context.params["tier"],
            "cusip": raw.get("cusip") or raw.get("CUSIP"),
            "volume_total": int(raw.get("totalVolume", 0)),
            # ... other fields
        })
    
    return StepResult.ok(
        output={"records": records},
        metrics={"transformed": len(records)},
    )


def quality_step(context: WorkflowContext, config: dict) -> StepResult:
    """Run quality checks."""
    records = context.outputs.get("transform", {}).get("records", [])
    
    # Basic quality checks
    issues = []
    
    # Check record count
    if len(records) < 100:
        issues.append(f"Low record count: {len(records)}")
    
    # Check for nulls
    null_cusips = sum(1 for r in records if not r.get("cusip"))
    if null_cusips > 0:
        issues.append(f"Records with null CUSIP: {null_cusips}")
    
    if issues:
        return StepResult.fail(
            error="; ".join(issues),
            quality_passed=False,
            quality_metrics={
                "record_count": len(records),
                "null_cusips": null_cusips,
            },
        )
    
    return StepResult.ok(
        quality_passed=True,
        quality_metrics={
            "record_count": len(records),
            "null_cusips": 0,
        },
    )


def load_step(context: WorkflowContext, config: dict) -> StepResult:
    """Load records to database."""
    records = context.outputs.get("transform", {}).get("records", [])
    
    # Get database from config
    db = config.get("db")
    if not db:
        return StepResult.fail(error="Database not configured")
    
    with db.transaction():
        # Insert records
        inserted = 0
        for record in records:
            db.execute(
                """
                INSERT OR REPLACE INTO fact_bond_trade_activity 
                (week_ending, tier, cusip, volume_total)
                VALUES (?, ?, ?, ?)
                """,
                (record["week_ending"], record["tier"], 
                 record["cusip"], record["volume_total"]),
            )
            inserted += 1
    
    return StepResult.ok(
        output={"inserted": inserted},
        metrics={"inserted": inserted},
    )


def notify_step(context: WorkflowContext, config: dict) -> StepResult:
    """Send completion notification."""
    alerter = config.get("alerter")
    if not alerter:
        return StepResult.skip("Alerter not configured")
    
    # Gather metrics
    total_records = context.outputs.get("load", {}).get("inserted", 0)
    
    from spine.framework.alerts import Alert, AlertSeverity
    
    alerter.send(Alert(
        severity=AlertSeverity.INFO,
        title="FINRA Ingestion Complete",
        message=f"Processed {total_records} records for {context.params['tier']} "
                f"week ending {context.params['week_ending']}",
        source="finra.otc_transparency.ingest",
        execution_id=context.run_id,
        metadata={
            "tier": context.params["tier"],
            "week_ending": context.params["week_ending"],
            "records": total_records,
        },
    ))
    
    return StepResult.ok()
```

---

### 4. Schedule Configuration

```yaml
# config/schedules/finra.yaml
schedules:
  # T1 Tier - Daily at 6 AM ET on weekdays
  - name: finra_otc_t1_daily
    pipeline: finra.otc_transparency.ingest_week
    cron: "0 6 * * 1-5"
    timezone: America/New_York
    params:
      tier: T1
    enabled: true
  
  # T2 Tier - Daily at 6:15 AM ET on weekdays
  - name: finra_otc_t2_daily
    pipeline: finra.otc_transparency.ingest_week
    cron: "15 6 * * 1-5"
    timezone: America/New_York
    params:
      tier: T2
    enabled: true
  
  # T3 Tier - Weekly on Monday at 7 AM ET
  - name: finra_otc_t3_weekly
    pipeline: finra.otc_transparency.ingest_week
    cron: "0 7 * * 1"
    timezone: America/New_York
    params:
      tier: T3
    enabled: true
  
  # Backfill job - manual trigger only
  - name: finra_otc_backfill
    pipeline: finra.otc_transparency.backfill
    cron: null  # Manual only
    enabled: false
```

---

### 5. Alert Configuration

```python
# config/alerts.py
"""
Alert routing configuration.
"""

from spine.framework.alerts import (
    AlertRouter,
    SlackChannel,
    SlackConfig,
    EmailChannel,
    EmailConfig,
    ThrottledChannel,
    AlertSeverity,
)
from spine.core.errors import ErrorCategory


def configure_alerts() -> AlertRouter:
    """Configure alert routing for FINRA domain."""
    router = AlertRouter()
    
    # Slack channel for all alerts
    slack = SlackChannel(SlackConfig(
        webhook_url=os.environ["SPINE_SLACK_WEBHOOK"],
        channel="#data-pipelines",
        min_severity=AlertSeverity.WARNING,
    ))
    
    # Add throttling (max 10 per 5 minutes per source)
    throttled_slack = ThrottledChannel(
        slack,
        window_seconds=300,
        max_per_window=10,
    )
    
    router.add_channel(throttled_slack)
    
    # Email for errors
    email = EmailChannel(EmailConfig(
        smtp_host=os.environ["SPINE_SMTP_HOST"],
        smtp_port=587,
        from_address="alerts@company.com",
        to_addresses=["data-team@company.com"],
        min_severity=AlertSeverity.ERROR,
    ))
    
    router.add_channel(email)
    
    # Extra routing for critical errors
    router.add_severity_channel(AlertSeverity.CRITICAL, email)
    
    # Route dependency errors to ops
    ops_slack = SlackChannel(SlackConfig(
        webhook_url=os.environ["SPINE_SLACK_OPS_WEBHOOK"],
        channel="#ops-alerts",
        min_severity=AlertSeverity.ERROR,
    ))
    
    router.add_category_channel(ErrorCategory.DEPENDENCY, ops_slack)
    
    return router
```

---

### 6. API Endpoints

```python
# spine/api/finra.py
"""
FINRA-specific API endpoints.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from datetime import date

from spine.orchestration.v2 import WorkflowRunner
from spine.orchestration.scheduler import SchedulerService, Schedule
from spine.orchestration.history import HistoryStore, WorkflowStatus
from spine.core.storage import DatabaseAdapter


router = APIRouter(prefix="/finra", tags=["finra"])


# Request/Response models
class IngestRequest(BaseModel):
    tier: str
    week_ending: str


class IngestResponse(BaseModel):
    execution_id: str
    status: str


class TradeActivityQuery(BaseModel):
    tier: str | None = None
    week_ending: str | None = None
    cusip: str | None = None
    limit: int = 100


class TradeActivityRecord(BaseModel):
    week_ending: str
    tier: str
    cusip: str
    volume_total: int
    trade_count: int


# Endpoints
@router.post("/ingest")
async def trigger_ingest(
    request: IngestRequest,
    runner: WorkflowRunner = Depends(get_runner),
) -> IngestResponse:
    """
    Trigger FINRA OTC transparency ingestion.
    
    Runs asynchronously and returns execution ID.
    """
    if request.tier not in ("T1", "T2", "T3"):
        raise HTTPException(400, f"Invalid tier: {request.tier}")
    
    execution_id = await runner.run_async(
        "finra.otc_transparency.ingest_week",
        params={
            "tier": request.tier,
            "week_ending": request.week_ending,
        },
    )
    
    return IngestResponse(
        execution_id=execution_id,
        status="started",
    )


@router.get("/ingest/status/{execution_id}")
async def get_ingest_status(
    execution_id: str,
    store: HistoryStore = Depends(get_store),
) -> dict:
    """Get ingestion execution status."""
    run = store.get_workflow_run(execution_id)
    if not run:
        raise HTTPException(404, "Execution not found")
    
    steps = store.get_step_runs(execution_id)
    
    return {
        "execution_id": execution_id,
        "status": run.status.value,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "steps": [
            {
                "name": s.step_name,
                "status": s.status.value,
                "records_processed": s.records_processed,
                "duration_seconds": s.duration_seconds,
            }
            for s in steps
        ],
        "metrics": run.metrics,
        "error": run.error,
    }


@router.get("/trade-activity")
async def get_trade_activity(
    db: DatabaseAdapter = Depends(get_db),
    tier: str | None = None,
    week_ending: str | None = None,
    cusip: str | None = None,
    limit: int = Query(default=100, le=1000),
) -> list[TradeActivityRecord]:
    """Query trade activity data."""
    conditions = []
    params = []
    
    if tier:
        conditions.append("tier = ?")
        params.append(tier)
    
    if week_ending:
        conditions.append("week_ending = ?")
        params.append(week_ending)
    
    if cusip:
        conditions.append("cusip = ?")
        params.append(cusip)
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    result = db.query(
        f"""
        SELECT week_ending, tier, cusip, volume_total, trade_count
        FROM fact_bond_trade_activity
        WHERE {where_clause}
        ORDER BY week_ending DESC, volume_total DESC
        LIMIT ?
        """,
        tuple(params + [limit]),
    )
    
    return [TradeActivityRecord(**row) for row in result]


@router.get("/schedules")
async def list_finra_schedules(
    scheduler: SchedulerService = Depends(get_scheduler),
) -> list[dict]:
    """List FINRA-related schedules."""
    jobs = scheduler.get_jobs()
    
    return [
        job for job in jobs
        if job["name"].startswith("finra_")
    ]


@router.post("/schedules/{name}/run")
async def trigger_schedule(
    name: str,
    scheduler: SchedulerService = Depends(get_scheduler),
) -> dict:
    """Manually trigger a FINRA schedule."""
    if not name.startswith("finra_"):
        raise HTTPException(400, "Not a FINRA schedule")
    
    run_id = scheduler.run_now(name)
    if not run_id:
        raise HTTPException(404, "Schedule not found")
    
    return {"run_id": run_id, "schedule": name}
```

---

### 7. Frontend Integration

```typescript
// frontend/src/api/finraApi.ts
import { apiClient } from './client';

export interface IngestRequest {
  tier: 'T1' | 'T2' | 'T3';
  week_ending: string;
}

export interface IngestStatus {
  execution_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  started_at: string | null;
  completed_at: string | null;
  steps: {
    name: string;
    status: string;
    records_processed: number | null;
    duration_seconds: number | null;
  }[];
  metrics: Record<string, number>;
  error: string | null;
}

export interface TradeActivity {
  week_ending: string;
  tier: string;
  cusip: string;
  volume_total: number;
  trade_count: number;
}

export const finraApi = {
  // Trigger ingestion
  triggerIngest: (request: IngestRequest) =>
    apiClient.post<{ execution_id: string }>('/finra/ingest', request),
  
  // Get ingestion status
  getIngestStatus: (executionId: string) =>
    apiClient.get<IngestStatus>(`/finra/ingest/status/${executionId}`),
  
  // Query trade activity
  getTradeActivity: (params: {
    tier?: string;
    week_ending?: string;
    cusip?: string;
    limit?: number;
  }) => apiClient.get<TradeActivity[]>('/finra/trade-activity', { params }),
  
  // List schedules
  getSchedules: () =>
    apiClient.get<{ name: string; next_run: string }[]>('/finra/schedules'),
  
  // Trigger schedule
  triggerSchedule: (name: string) =>
    apiClient.post<{ run_id: string }>(`/finra/schedules/${name}/run`),
};


// frontend/src/hooks/useFinraIngest.ts
import { useMutation, useQuery } from '@tanstack/react-query';
import { finraApi, IngestRequest, IngestStatus } from '../api/finraApi';

export function useFinraIngest() {
  const mutation = useMutation({
    mutationFn: (request: IngestRequest) => finraApi.triggerIngest(request),
  });
  
  return {
    trigger: mutation.mutate,
    isLoading: mutation.isPending,
    executionId: mutation.data?.execution_id,
  };
}

export function useFinraIngestStatus(executionId: string | undefined) {
  return useQuery({
    queryKey: ['finra-ingest-status', executionId],
    queryFn: () => finraApi.getIngestStatus(executionId!),
    enabled: !!executionId,
    refetchInterval: (data) =>
      data?.status === 'RUNNING' ? 2000 : false,
  });
}


// frontend/src/components/FINRAIngestPanel.tsx
import { useState } from 'react';
import { useFinraIngest, useFinraIngestStatus } from '../hooks/useFinraIngest';

export function FINRAIngestPanel() {
  const [tier, setTier] = useState<'T1' | 'T2' | 'T3'>('T1');
  const [weekEnding, setWeekEnding] = useState('');
  
  const { trigger, isLoading, executionId } = useFinraIngest();
  const { data: status } = useFinraIngestStatus(executionId);
  
  const handleIngest = () => {
    trigger({ tier, week_ending: weekEnding });
  };
  
  return (
    <Card>
      <CardHeader>
        <h2>FINRA OTC Transparency Ingestion</h2>
      </CardHeader>
      
      <CardContent>
        <div className="space-y-4">
          <Select value={tier} onValueChange={setTier}>
            <SelectItem value="T1">Tier 1</SelectItem>
            <SelectItem value="T2">Tier 2</SelectItem>
            <SelectItem value="T3">Tier 3</SelectItem>
          </Select>
          
          <DatePicker
            value={weekEnding}
            onChange={setWeekEnding}
            label="Week Ending"
          />
          
          <Button
            onClick={handleIngest}
            disabled={isLoading || !weekEnding}
          >
            {isLoading ? 'Starting...' : 'Run Ingestion'}
          </Button>
        </div>
        
        {status && (
          <div className="mt-4">
            <StatusBadge status={status.status} />
            
            <StepTimeline steps={status.steps} />
            
            {status.status === 'COMPLETED' && (
              <MetricsSummary metrics={status.metrics} />
            )}
            
            {status.error && (
              <ErrorAlert message={status.error} />
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

---

## Complete Data Flow

1. **User Action**: User selects tier "T1" and week "2025-01-10" in frontend
2. **API Request**: POST `/finra/ingest` with `{tier: "T1", week_ending: "2025-01-10"}`
3. **Orchestration**: WorkflowRunner starts workflow execution
4. **Source**: FINRAOTCSource.fetch() calls FINRA API
5. **Transform**: Records converted to internal format
6. **Quality**: QualityRunner validates data
7. **Load**: Records inserted to `fact_bond_trade_activity`
8. **History**: Execution recorded to `workflow_runs` and `workflow_step_runs`
9. **Alert**: Slack notification sent on completion
10. **Frontend**: Polls `/finra/ingest/status/{id}` until completed
11. **Display**: Shows success with metrics

---

## Next Steps

1. Review implementation order: [11-IMPLEMENTATION-ORDER.md](./11-IMPLEMENTATION-ORDER.md)
