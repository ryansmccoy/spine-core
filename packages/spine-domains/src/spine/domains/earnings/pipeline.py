"""
Earnings Pipeline — Orchestrates ingestion and surprise computation.

This pipeline:
1. Fetches earnings calendar from adapters (Polygon, etc.)
2. Stores raw events and estimates
3. Computes surprise metrics when actuals arrive
4. Tracks all work in spine-core manifest

Example:
    from spine.domains.earnings import EarningsPipeline, EarningsConfig
    from spine.core import new_context
    
    config = EarningsConfig(
        date_from=date(2026, 1, 30),
        date_to=date(2026, 2, 6),
    )
    
    pipeline = EarningsPipeline(config)
    async with pipeline:
        results = await pipeline.run(ctx=new_context())
        print(f"Processed {len(results.surprises)} surprises")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from spine.core import (
    ExecutionContext,
    ManifestRow,
    WorkManifest,
    new_batch_id,
    new_context,
)
from spine.domains.earnings.models import (
    EarningsActual,
    EarningsEvent,
    EarningsSurprise,
    EstimateSnapshot,
)
from spine.domains.earnings.schema import (
    DOMAIN,
    MetricCode,
    ReportTime,
    Stage,
    SurpriseDirection,
    SurpriseMagnitude,
    TABLES,
    partition_key,
)

if TYPE_CHECKING:
    from feedspine.adapter.polygon_earnings import (
        PolygonEarningsAdapter,
        PolygonEstimateHistoryAdapter,
    )
    from feedspine.analysis.comparison import ComparisonResult


@dataclass
class EarningsConfig:
    """Configuration for earnings pipeline."""
    
    # Date range for calendar fetch
    date_from: date = field(default_factory=date.today)
    date_to: date | None = None
    
    # Ticker filtering
    tickers: list[str] | None = None
    
    # API configuration
    polygon_api_key: str | None = None
    
    # Processing options
    compute_surprises: bool = True
    store_estimates: bool = True
    
    # Thresholds
    inline_threshold_pct: Decimal = Decimal("0.01")  # 1%
    
    def __post_init__(self):
        if self.date_to is None:
            self.date_to = self.date_from + timedelta(days=7)


@dataclass
class PipelineResult:
    """Result of pipeline execution."""
    
    events: list[EarningsEvent] = field(default_factory=list)
    estimates: list[EstimateSnapshot] = field(default_factory=list)
    actuals: list[EarningsActual] = field(default_factory=list)
    surprises: list[EarningsSurprise] = field(default_factory=list)
    
    # Tracking
    errors: list[str] = field(default_factory=list)
    batch_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    
    @property
    def success(self) -> bool:
        return len(self.errors) == 0
    
    @property
    def summary(self) -> dict[str, Any]:
        return {
            "events": len(self.events),
            "estimates": len(self.estimates),
            "actuals": len(self.actuals),
            "surprises": len(self.surprises),
            "errors": len(self.errors),
            "batch_id": self.batch_id,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.completed_at
                else None
            ),
        }


class EarningsPipeline:
    """
    Orchestrates earnings data ingestion and surprise computation.
    
    Stages:
    1. RAW: Fetch calendar events from Polygon
    2. ESTIMATES: Extract/store consensus estimates
    3. ACTUALS: Extract/store reported actuals
    4. SURPRISES: Compute surprise metrics
    
    Example:
        config = EarningsConfig(
            date_from=date(2026, 1, 30),
            tickers=["AAPL", "MSFT"],
        )
        
        pipeline = EarningsPipeline(config)
        await pipeline.initialize()
        
        result = await pipeline.run()
        for surprise in result.surprises:
            print(f"{surprise.ticker}: {surprise.direction.value}")
    """
    
    def __init__(
        self,
        config: EarningsConfig,
        manifest: WorkManifest | None = None,
    ):
        self.config = config
        self.manifest = manifest
        self._adapter = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize adapters and resources."""
        # Lazy import to avoid hard dependency
        try:
            from feedspine.adapter.polygon_earnings import PolygonEarningsAdapter
            
            self._adapter = PolygonEarningsAdapter(
                api_key=self.config.polygon_api_key,
                date_from=self.config.date_from,
                date_to=self.config.date_to,
                tickers=self.config.tickers,
            )
            await self._adapter.initialize()
        except ImportError:
            # FeedSpine not installed - use mock mode
            self._adapter = None
        
        self._initialized = True
    
    async def close(self) -> None:
        """Clean up resources."""
        if self._adapter:
            await self._adapter.close()
        self._initialized = False
    
    async def __aenter__(self) -> "EarningsPipeline":
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
    
    async def run(self, ctx: ExecutionContext | None = None) -> PipelineResult:
        """
        Execute the full pipeline.
        
        Args:
            ctx: Execution context for lineage tracking
        
        Returns:
            PipelineResult with all processed data
        """
        if not self._initialized:
            await self.initialize()
        
        ctx = ctx or new_context()
        result = PipelineResult(batch_id=ctx.batch_id or new_batch_id("earnings"))
        
        try:
            # Stage 1: Fetch raw calendar events
            events = await self._fetch_events(ctx, result)
            result.events = events
            
            # Stage 2: Extract estimates
            if self.config.store_estimates:
                estimates = self._extract_estimates(events, result)
                result.estimates = estimates
            
            # Stage 3: Extract actuals
            actuals = self._extract_actuals(events, result)
            result.actuals = actuals
            
            # Stage 4: Compute surprises
            if self.config.compute_surprises:
                surprises = await self._compute_surprises(
                    estimates=result.estimates,
                    actuals=result.actuals,
                    result=result,
                )
                result.surprises = surprises
            
        except Exception as e:
            result.errors.append(f"Pipeline error: {e}")
        
        result.completed_at = datetime.now(UTC)
        return result
    
    async def _fetch_events(
        self,
        ctx: ExecutionContext,
        result: PipelineResult,
    ) -> list[EarningsEvent]:
        """Stage 1: Fetch calendar events from adapter."""
        events = []
        
        if self._adapter is None:
            # Mock mode - return demo data
            return self._get_demo_events()
        
        try:
            async for record in self._adapter.fetch():
                content = record.content
                
                event = EarningsEvent(
                    ticker=content.get("ticker", ""),
                    report_date=content.get("report_date", ""),
                    fiscal_year=content.get("fiscal_year", 0),
                    fiscal_period=content.get("fiscal_period", ""),
                    fiscal_quarter=content.get("fiscal_quarter"),
                    report_time=ReportTime(content.get("report_time", "unknown")),
                    company_name=content.get("company_name", ""),
                    source_vendor=content.get("source_vendor", "polygon"),
                    source_feed=content.get("source_feed", ""),
                    natural_key=record.natural_key,
                    captured_at=record.published_at,
                    batch_id=result.batch_id,
                )
                events.append(event)
                
        except Exception as e:
            result.errors.append(f"Fetch error: {e}")
        
        return events
    
    def _extract_estimates(
        self,
        events: list[EarningsEvent],
        result: PipelineResult,
    ) -> list[EstimateSnapshot]:
        """Stage 2: Extract estimates from events."""
        estimates = []
        
        if self._adapter is None:
            return estimates
        
        # Get raw data from adapter's last fetch
        for record in getattr(self._adapter, "_last_items", []):
            eps_est = record.get("eps", {}).get("estimated")
            rev_est = record.get("revenue", {}).get("estimated")
            
            ticker = record.get("ticker", "")
            period = record.get("fiscal_period", "")
            
            if eps_est is not None:
                estimates.append(EstimateSnapshot(
                    ticker=ticker,
                    fiscal_period=f"{record.get('fiscal_year')}:{period}",
                    metric_code=MetricCode.EPS,
                    estimate_value=Decimal(str(eps_est)),
                    captured_at=datetime.now(UTC),
                    num_analysts=record.get("analyst_count"),
                    source_vendor="polygon",
                    batch_id=result.batch_id,
                ))
            
            if rev_est is not None:
                estimates.append(EstimateSnapshot(
                    ticker=ticker,
                    fiscal_period=f"{record.get('fiscal_year')}:{period}",
                    metric_code=MetricCode.REVENUE,
                    estimate_value=Decimal(str(rev_est)),
                    captured_at=datetime.now(UTC),
                    num_analysts=record.get("analyst_count"),
                    source_vendor="polygon",
                    batch_id=result.batch_id,
                ))
        
        return estimates
    
    def _extract_actuals(
        self,
        events: list[EarningsEvent],
        result: PipelineResult,
    ) -> list[EarningsActual]:
        """Stage 3: Extract actuals from events (where released)."""
        actuals = []
        
        if self._adapter is None:
            return actuals
        
        for record in getattr(self._adapter, "_last_items", []):
            eps_act = record.get("eps", {}).get("actual")
            rev_act = record.get("revenue", {}).get("actual")
            
            ticker = record.get("ticker", "")
            period = f"{record.get('fiscal_year')}:{record.get('fiscal_period', '')}"
            report_date = record.get("report_date", "")
            
            if eps_act is not None:
                actuals.append(EarningsActual(
                    ticker=ticker,
                    fiscal_period=period,
                    metric_code=MetricCode.EPS,
                    actual_value=Decimal(str(eps_act)),
                    reported_at=datetime.fromisoformat(report_date) if report_date else datetime.now(UTC),
                    source_vendor="polygon",
                    batch_id=result.batch_id,
                ))
            
            if rev_act is not None:
                actuals.append(EarningsActual(
                    ticker=ticker,
                    fiscal_period=period,
                    metric_code=MetricCode.REVENUE,
                    actual_value=Decimal(str(rev_act)),
                    reported_at=datetime.fromisoformat(report_date) if report_date else datetime.now(UTC),
                    source_vendor="polygon",
                    batch_id=result.batch_id,
                ))
        
        return actuals
    
    async def _compute_surprises(
        self,
        estimates: list[EstimateSnapshot],
        actuals: list[EarningsActual],
        result: PipelineResult,
    ) -> list[EarningsSurprise]:
        """Stage 4: Compute surprise metrics."""
        surprises = []
        
        # Build lookup for estimates by (ticker, period, metric)
        estimate_lookup: dict[tuple[str, str, str], EstimateSnapshot] = {}
        for est in estimates:
            key = (est.ticker.upper(), est.fiscal_period, est.metric_code.value)
            estimate_lookup[key] = est
        
        # Compute surprise for each actual
        for actual in actuals:
            key = (actual.ticker.upper(), actual.fiscal_period, actual.metric_code.value)
            estimate = estimate_lookup.get(key)
            
            surprise = self._compute_single_surprise(actual, estimate, result.batch_id)
            surprises.append(surprise)
        
        return surprises
    
    def _compute_single_surprise(
        self,
        actual: EarningsActual,
        estimate: EstimateSnapshot | None,
        batch_id: str,
    ) -> EarningsSurprise:
        """Compute surprise for a single actual."""
        
        if estimate is None:
            return EarningsSurprise(
                ticker=actual.ticker,
                fiscal_period=actual.fiscal_period,
                metric_code=actual.metric_code,
                actual_value=actual.actual_value,
                actual_reported_at=actual.reported_at,
                direction=SurpriseDirection.NO_ESTIMATE,
                actual_source=actual.source_vendor,
                batch_id=batch_id,
            )
        
        # Calculate surprise
        surprise_amount = actual.actual_value - estimate.estimate_value
        
        # Avoid division by zero
        if estimate.estimate_value == 0:
            surprise_pct = Decimal("0")
        else:
            surprise_pct = surprise_amount / abs(estimate.estimate_value)
        
        # Determine direction
        threshold = self.config.inline_threshold_pct
        if surprise_pct > threshold:
            direction = SurpriseDirection.BEAT
        elif surprise_pct < -threshold:
            direction = SurpriseDirection.MISS
        else:
            direction = SurpriseDirection.INLINE
        
        # Determine magnitude
        abs_pct = abs(surprise_pct)
        if abs_pct < Decimal("0.03"):
            magnitude = SurpriseMagnitude.SMALL
        elif abs_pct < Decimal("0.10"):
            magnitude = SurpriseMagnitude.MODERATE
        else:
            magnitude = SurpriseMagnitude.LARGE
        
        return EarningsSurprise(
            ticker=actual.ticker,
            fiscal_period=actual.fiscal_period,
            metric_code=actual.metric_code,
            actual_value=actual.actual_value,
            actual_reported_at=actual.reported_at,
            direction=direction,
            estimate_value=estimate.estimate_value,
            estimate_as_of=estimate.captured_at,
            surprise_amount=surprise_amount,
            surprise_pct=surprise_pct,
            magnitude=magnitude,
            estimate_source=estimate.source_vendor,
            actual_source=actual.source_vendor,
            batch_id=batch_id,
        )
    
    def _get_demo_events(self) -> list[EarningsEvent]:
        """Return demo events when no adapter available."""
        return [
            EarningsEvent(
                ticker="AAPL",
                report_date=self.config.date_from.isoformat(),
                fiscal_year=2026,
                fiscal_period="Q1",
                fiscal_quarter=1,
                report_time=ReportTime.AMC,
                company_name="Apple Inc.",
                source_vendor="demo",
            ),
            EarningsEvent(
                ticker="MSFT",
                report_date=self.config.date_from.isoformat(),
                fiscal_year=2026,
                fiscal_period="Q2",
                fiscal_quarter=2,
                report_time=ReportTime.AMC,
                company_name="Microsoft Corporation",
                source_vendor="demo",
            ),
        ]
