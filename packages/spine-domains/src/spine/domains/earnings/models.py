"""
Data models for Earnings domain.

These are dataclasses representing database rows and pipeline outputs.
They complement the FeedSpine Pydantic models for analysis.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from spine.domains.earnings.schema import (
    MetricCode,
    ReportTime,
    SurpriseDirection,
    SurpriseMagnitude,
)


@dataclass
class EarningsEvent:
    """
    An earnings announcement event on the calendar.
    
    Represents a scheduled or completed earnings release.
    """
    
    ticker: str
    report_date: str  # ISO date YYYY-MM-DD
    fiscal_year: int
    fiscal_period: str  # e.g., "Q4" or "FY"
    
    # Optional fields
    fiscal_quarter: int | None = None
    report_time: ReportTime = ReportTime.UNKNOWN
    company_name: str = ""
    
    # Source tracking
    source_vendor: str = ""
    source_feed: str = ""
    natural_key: str = ""
    
    # Metadata
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    batch_id: str | None = None
    
    def __post_init__(self):
        if not self.natural_key:
            self.natural_key = f"{self.source_vendor}:{self.ticker}:{self.fiscal_year}:{self.fiscal_period}".lower()


@dataclass
class EstimateSnapshot:
    """
    A point-in-time snapshot of consensus estimate.
    
    Critical for the two-timestamp pattern: we need the estimate
    as it was BEFORE the actual was announced.
    """
    
    ticker: str
    fiscal_period: str
    metric_code: MetricCode
    estimate_value: Decimal
    captured_at: datetime
    
    # Optional fields
    num_analysts: int | None = None
    source_vendor: str = ""
    natural_key: str = ""
    batch_id: str | None = None
    
    def __post_init__(self):
        if not self.natural_key:
            date_str = self.captured_at.strftime("%Y%m%d")
            self.natural_key = f"{self.source_vendor}:estimate:{self.ticker}:{self.fiscal_period}:{self.metric_code}:{date_str}".lower()


@dataclass
class EarningsActual:
    """
    A reported actual value from earnings release.
    """
    
    ticker: str
    fiscal_period: str
    metric_code: MetricCode
    actual_value: Decimal
    reported_at: datetime
    
    # Source tracking
    source_vendor: str = ""
    natural_key: str = ""
    batch_id: str | None = None
    
    def __post_init__(self):
        if not self.natural_key:
            self.natural_key = f"{self.source_vendor}:actual:{self.ticker}:{self.fiscal_period}:{self.metric_code}".lower()


@dataclass
class EarningsSurprise:
    """
    Computed earnings surprise from estimate vs actual.
    
    This is the primary output of the comparison pipeline,
    stored for querying and analysis.
    """
    
    ticker: str
    fiscal_period: str
    metric_code: MetricCode
    actual_value: Decimal
    actual_reported_at: datetime
    direction: SurpriseDirection
    
    # Estimate data (optional if no estimate available)
    estimate_value: Decimal | None = None
    estimate_as_of: datetime | None = None
    
    # Computed metrics
    surprise_amount: Decimal | None = None
    surprise_pct: Decimal | None = None
    magnitude: SurpriseMagnitude | None = None
    
    # Source tracking
    estimate_source: str | None = None
    actual_source: str | None = None
    natural_key: str = ""
    
    # Metadata
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    batch_id: str | None = None
    
    def __post_init__(self):
        if not self.natural_key:
            self.natural_key = f"surprise:{self.ticker}:{self.fiscal_period}:{self.metric_code}".lower()
    
    @classmethod
    def from_comparison_result(cls, result, batch_id: str | None = None) -> "EarningsSurprise":
        """
        Create from FeedSpine ComparisonResult.
        
        Args:
            result: ComparisonResult from feedspine.analysis
            batch_id: Optional batch ID for tracking
        
        Returns:
            EarningsSurprise instance
        """
        return cls(
            ticker=result.ticker,
            fiscal_period=result.period,
            metric_code=MetricCode(result.metric_code),
            actual_value=result.actual_value,
            actual_reported_at=result.actual_as_of,
            direction=SurpriseDirection(result.direction.value),
            estimate_value=result.estimate_value,
            estimate_as_of=result.estimate_as_of,
            surprise_amount=result.surprise_amount,
            surprise_pct=result.surprise_pct,
            magnitude=SurpriseMagnitude(result.magnitude.value) if result.magnitude else None,
            estimate_source=result.estimate_source.vendor if result.estimate_source else None,
            actual_source=result.actual_source.vendor if result.actual_source else None,
            batch_id=batch_id,
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        return {
            "ticker": self.ticker,
            "fiscal_period": self.fiscal_period,
            "metric_code": self.metric_code.value if isinstance(self.metric_code, MetricCode) else self.metric_code,
            "actual_value": float(self.actual_value) if self.actual_value else None,
            "actual_reported_at": self.actual_reported_at.isoformat() if self.actual_reported_at else None,
            "direction": self.direction.value if isinstance(self.direction, SurpriseDirection) else self.direction,
            "estimate_value": float(self.estimate_value) if self.estimate_value else None,
            "estimate_as_of": self.estimate_as_of.isoformat() if self.estimate_as_of else None,
            "surprise_amount": float(self.surprise_amount) if self.surprise_amount else None,
            "surprise_pct": float(self.surprise_pct) if self.surprise_pct else None,
            "magnitude": self.magnitude.value if self.magnitude else None,
            "estimate_source": self.estimate_source,
            "actual_source": self.actual_source,
            "natural_key": self.natural_key,
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "batch_id": self.batch_id,
        }
