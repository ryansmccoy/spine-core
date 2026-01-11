# OTC Weekly Transparency Plugin — Advanced Tier

> **Target:** `market-spine-advanced`  
> **Builds on:** Intermediate tier  
> **Prerequisites:** See [SHARED_MODELS.md](SHARED_MODELS.md) for common code

---

## 1. What Advanced Adds to Intermediate

| Feature | Intermediate | Advanced |
|---------|--------------|----------|
| Worker | LocalBackend (thread) | Celery + Redis |
| Storage | Database only | + S3/MinIO |
| Scheduling | Manual CLI | Celery Beat |
| Retry | None | DLQ with retries |
| Calculations | Basic summaries | + Rolling averages, HHI |
| API ingestion | Simple HTTP | + Retry, rate limiting |

**Same core logic**, distributed execution.

---

## 2. Files to Create

```
market-spine-advanced/
├── migrations/
│   ├── 020_otc_tables.sql           # Copy from SHARED_MODELS.md (PostgreSQL)
│   ├── 021_otc_rolling.sql          # NEW: Rolling average tables
│   └── 022_otc_concentration.sql    # NEW: HHI tables
├── src/market_spine/
│   └── domains/
│       └── otc/
│           ├── __init__.py
│           ├── models.py            # Copy (same as Basic/Intermediate)
│           ├── parser.py            # Copy (same)
│           ├── normalizer.py        # Copy (same)
│           ├── calculations.py      # Extended with new calcs
│           ├── connector.py         # Copy from Intermediate
│           ├── repository.py        # Copy from Intermediate
│           ├── quality.py           # Copy from Intermediate
│           ├── storage.py           # NEW: S3 integration
│           ├── schedule.py          # NEW: Celery Beat config
│           └── pipelines.py         # Modified for Celery
```

---

## 3. New: Extended Calculations

Add to `calculations.py` (on top of shared calculations):

```python
# src/market_spine/domains/otc/calculations.py (additions)

"""Advanced calculations - rolling averages and concentration metrics."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from market_spine.domains.otc.models import VenueVolume


@dataclass
class SymbolRollingAvg:
    """6-week rolling average for a symbol."""
    week_ending: date
    symbol: str
    avg_6w_volume: int
    avg_6w_trades: int
    current_volume: int
    volume_vs_avg_pct: float
    trend: str  # "up", "down", "stable"


@dataclass
class SymbolConcentration:
    """HHI concentration metrics for a symbol."""
    week_ending: date
    symbol: str
    venue_count: int
    hhi: float
    concentration_level: str  # "competitive", "moderate", "concentrated"
    top_venue_share_pct: float


def compute_rolling_averages(
    venue_data: list[VenueVolume],
    target_week: date,
    window_weeks: int = 6,
) -> list[SymbolRollingAvg]:
    """
    Compute rolling averages over a window.
    
    Basic/Intermediate don't have this.
    Advanced adds multi-week analytics.
    """
    window_start = target_week - timedelta(weeks=window_weeks - 1)
    
    # Filter to window
    in_window = [v for v in venue_data 
                 if window_start <= v.week_ending <= target_week]
    
    # Group by (week, symbol)
    weekly = defaultdict(lambda: {"volume": 0, "trades": 0})
    for v in in_window:
        key = (v.week_ending, v.symbol)
        weekly[key]["volume"] += v.share_volume
        weekly[key]["trades"] += v.trade_count
    
    # Group by symbol across weeks
    by_symbol = defaultdict(list)
    for (week, symbol), data in weekly.items():
        by_symbol[symbol].append({
            "week": week,
            "volume": data["volume"],
            "trades": data["trades"],
        })
    
    results = []
    for symbol, weeks in by_symbol.items():
        if not weeks:
            continue
        
        avg_vol = sum(w["volume"] for w in weeks) / len(weeks)
        avg_trades = sum(w["trades"] for w in weeks) / len(weeks)
        
        current = next((w for w in weeks if w["week"] == target_week), None)
        current_vol = current["volume"] if current else 0
        
        pct = 0.0
        trend = "stable"
        if avg_vol > 0:
            pct = (current_vol - avg_vol) / avg_vol * 100
            if pct > 10:
                trend = "up"
            elif pct < -10:
                trend = "down"
        
        results.append(SymbolRollingAvg(
            week_ending=target_week,
            symbol=symbol,
            avg_6w_volume=int(avg_vol),
            avg_6w_trades=int(avg_trades),
            current_volume=current_vol,
            volume_vs_avg_pct=round(pct, 2),
            trend=trend,
        ))
    
    return results


def compute_concentration(
    venue_data: list[VenueVolume],
    week_ending: date,
) -> list[SymbolConcentration]:
    """
    Compute HHI (Herfindahl-Hirschman Index) per symbol.
    
    HHI = sum of squared market shares
    < 1500: Competitive
    1500-2500: Moderate  
    > 2500: Concentrated
    """
    # Filter to week
    week_data = [v for v in venue_data if v.week_ending == week_ending]
    
    # Group by symbol
    by_symbol = defaultdict(list)
    for v in week_data:
        by_symbol[v.symbol].append(v)
    
    results = []
    for symbol, venues in by_symbol.items():
        total = sum(v.share_volume for v in venues)
        if total == 0:
            continue
        
        # Calculate market shares and HHI
        shares = [(v.share_volume / total * 100) for v in venues]
        hhi = sum(s ** 2 for s in shares)
        
        top_share = max(shares) if shares else 0
        
        if hhi < 1500:
            level = "competitive"
        elif hhi < 2500:
            level = "moderate"
        else:
            level = "concentrated"
        
        results.append(SymbolConcentration(
            week_ending=week_ending,
            symbol=symbol,
            venue_count=len(venues),
            hhi=round(hhi, 2),
            concentration_level=level,
            top_venue_share_pct=round(top_share, 2),
        ))
    
    return results
```

---

## 4. New: S3 Storage

```python
# src/market_spine/domains/otc/storage.py

"""S3 storage for FINRA files - Advanced tier adds this."""

import boto3
from datetime import date
from pathlib import Path


class OTCStorage:
    """
    Cache FINRA files in S3.
    
    Intermediate downloads directly.
    Advanced caches in S3 for replay/audit.
    """
    
    def __init__(self, bucket: str, prefix: str = "finra/otc"):
        self.bucket = bucket
        self.prefix = prefix
        self.client = boto3.client("s3")
    
    def _key(self, tier: str, week: date) -> str:
        tier_slug = tier.lower().replace(" ", "_")
        return f"{self.prefix}/{tier_slug}/{week.isoformat()}.csv"
    
    def exists(self, tier: str, week: date) -> bool:
        """Check if file is cached."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(tier, week))
            return True
        except:
            return False
    
    def read(self, tier: str, week: date) -> str:
        """Read cached file."""
        response = self.client.get_object(
            Bucket=self.bucket, 
            Key=self._key(tier, week)
        )
        return response["Body"].read().decode("utf-8")
    
    def write(self, tier: str, week: date, content: str) -> None:
        """Cache file to S3."""
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(tier, week),
            Body=content.encode("utf-8"),
            ContentType="text/csv",
        )
```

---

## 5. New: Celery Schedule

```python
# src/market_spine/domains/otc/schedule.py

"""Celery Beat schedule - Advanced tier adds this."""

from celery.schedules import crontab

OTC_SCHEDULES = {
    # Tier 1: Wednesday 6am (2 weeks after week end)
    "otc-tier1-weekly": {
        "task": "market_spine.tasks.run_pipeline",
        "schedule": crontab(hour=6, minute=0, day_of_week="wed"),
        "kwargs": {"pipeline": "otc.ingest", "params": {"tier": "NMS Tier 1"}},
    },
    
    # Tier 2 + OTC: Wednesday 7am (4 weeks after week end)
    "otc-tier2-weekly": {
        "task": "market_spine.tasks.run_pipeline",
        "schedule": crontab(hour=7, minute=0, day_of_week="wed"),
        "kwargs": {"pipeline": "otc.ingest", "params": {"tier": "NMS Tier 2"}},
    },
    
    # Rolling averages: Wednesday 8am (after ingestion)
    "otc-rolling-weekly": {
        "task": "market_spine.tasks.run_pipeline",
        "schedule": crontab(hour=8, minute=0, day_of_week="wed"),
        "kwargs": {"pipeline": "otc.rolling_avg"},
    },
}
```

---

## 6. New: Database Tables

```sql
-- migrations/021_otc_rolling.sql

CREATE TABLE otc.symbol_rolling_avg (
    id BIGSERIAL PRIMARY KEY,
    week_ending DATE NOT NULL,
    symbol TEXT NOT NULL,
    avg_6w_volume BIGINT,
    avg_6w_trades INTEGER,
    current_volume BIGINT,
    volume_vs_avg_pct NUMERIC(8, 2),
    trend TEXT,
    computed_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(week_ending, symbol)
);

-- migrations/022_otc_concentration.sql

CREATE TABLE otc.symbol_concentration (
    id BIGSERIAL PRIMARY KEY,
    week_ending DATE NOT NULL,
    symbol TEXT NOT NULL,
    venue_count INTEGER,
    hhi NUMERIC(8, 2),
    concentration_level TEXT,
    top_venue_share_pct NUMERIC(5, 2),
    computed_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(week_ending, symbol)
);
```

---

## 7. Modified: Celery Pipelines

```python
# Key changes to pipelines.py for Celery:

from celery import shared_task
from market_spine.celery_app import app


@app.task(bind=True, max_retries=3)
def run_otc_ingest(self, file_path: str):
    """Celery task wrapper for OTC ingestion."""
    try:
        # ... same logic as Intermediate, but as Celery task
        pass
    except Exception as e:
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
```

---

## 8. What's NOT in Advanced

| Feature | Added In |
|---------|----------|
| TimescaleDB hypertables | Full |
| Continuous aggregates | Full |
| Event sourcing | Full |
| Observability (OTEL) | Full |
| Kubernetes deployment | Full |
| Retention policies | Full |

**Next:** See [OTC_PLUGIN_FULL.md](OTC_PLUGIN_FULL.md) for the next tier.
