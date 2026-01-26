"""
Earnings Domain — Earnings calendar, estimates, and surprises.

This domain manages:
- Earnings calendar events (announcements)
- EPS/Revenue estimates and actuals
- Surprise calculations (beat/miss/inline)
- Historical estimate revisions

Ingestion cadence: Daily (new announcements, estimate updates)
Source type: FeedSpine adapters (Polygon, Zacks, etc.)

Integration with FeedSpine:
    - Uses PolygonEarningsAdapter from feedspine.adapter
    - Uses ComparisonResult from feedspine.analysis

Example:
    from spine.domains.earnings import (
        DOMAIN,
        EarningsEvent,
        EarningsSurprise,
        SurpriseDirection,
    )
    
    # Pipeline tracks in manifest
    manifest.start(domain=DOMAIN, stage="raw", partition_key="2026-01-30")
"""

from spine.domains.earnings.models import (
    EarningsEvent,
    EarningsSurprise,
    EstimateSnapshot,
)
from spine.domains.earnings.schema import (
    DOMAIN,
    TABLES,
    MetricCode,
    ReportTime,
    SurpriseDirection,
    SurpriseMagnitude,
    partition_key,
)
from spine.domains.earnings.pipeline import (
    EarningsPipeline,
    EarningsConfig,
)

__all__ = [
    # Schema
    "DOMAIN",
    "TABLES",
    "MetricCode",
    "ReportTime",
    "SurpriseDirection",
    "SurpriseMagnitude",
    "partition_key",
    # Models
    "EarningsEvent",
    "EarningsSurprise",
    "EstimateSnapshot",
    # Pipeline
    "EarningsPipeline",
    "EarningsConfig",
]
