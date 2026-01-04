# OTC Weekly Transparency Plugin — Intermediate Tier

> **Target:** `market-spine-intermediate`  
> **Builds on:** Basic tier  
> **Prerequisites:** See [SHARED_MODELS.md](SHARED_MODELS.md) for common code

---

## 1. What Intermediate Adds to Basic

| Feature | Basic | Intermediate |
|---------|-------|--------------|
| Data source | Local files | + HTTP download |
| Database | SQLite | PostgreSQL |
| Execution | Sync CLI | + Background worker |
| API | None | REST endpoints |
| Quality | None | Quality checks + grades |
| Repository | Direct SQL | Repository pattern |

**Same core logic**, different infrastructure.

---

## 2. Files to Create

```
market-spine-intermediate/
├── migrations/
│   └── 020_otc_tables.sql           # Copy from SHARED_MODELS.md (PostgreSQL version)
├── src/market_spine/
│   ├── api/routes/
│   │   └── otc.py                   # NEW: REST API
│   └── domains/
│       └── otc/
│           ├── __init__.py
│           ├── models.py            # Copy from SHARED_MODELS.md (same as Basic)
│           ├── parser.py            # Copy from SHARED_MODELS.md (same as Basic)
│           ├── normalizer.py        # Copy from SHARED_MODELS.md (same as Basic)
│           ├── calculations.py      # Copy from SHARED_MODELS.md (same as Basic)
│           ├── connector.py         # NEW: HTTP download capability
│           ├── repository.py        # NEW: Async data access
│           ├── quality.py           # NEW: Quality checks
│           └── pipelines.py         # Modified for async + quality
└── tests/
    └── domains/otc/
```

**Key point:** `models.py`, `parser.py`, `normalizer.py`, `calculations.py` are **identical copies** from Basic.

---

## 3. New: HTTP Connector

```python
# src/market_spine/domains/otc/connector.py

"""HTTP download capability - Intermediate tier adds this."""

import httpx
from pathlib import Path

from market_spine.domains.otc.parser import parse_finra_content
from market_spine.domains.otc.models import RawRecord


class OTCConnector:
    """
    Fetch FINRA files via HTTP.
    
    Basic tier only reads local files.
    Intermediate adds HTTP download.
    """
    
    FINRA_BASE = "https://www.finra.org/finra-data"
    TIMEOUT = 30
    
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or Path("data/finra")
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def download(self, url: str) -> list[RawRecord]:
        """Download and parse FINRA file from URL."""
        with httpx.Client(timeout=self.TIMEOUT) as client:
            response = client.get(url)
            response.raise_for_status()
            content = response.text
        
        return list(parse_finra_content(content))
    
    def download_and_cache(self, url: str, filename: str) -> Path:
        """Download file and save locally."""
        with httpx.Client(timeout=self.TIMEOUT) as client:
            response = client.get(url)
            response.raise_for_status()
        
        path = self.data_dir / filename
        path.write_text(response.text)
        return path
```

---

## 4. New: Repository Pattern

```python
# src/market_spine/domains/otc/repository.py

"""Async repository for PostgreSQL - Intermediate tier adds this."""

from datetime import date
from typing import Any

from market_spine.db import get_pool


class OTCRepository:
    """
    Async data access for OTC tables.
    
    Basic tier uses direct SQL.
    Intermediate adds repository pattern for cleaner code.
    """
    
    def __init__(self):
        self.pool = get_pool()
    
    async def insert_raw_batch(
        self, 
        records: list[dict], 
        batch_id: str
    ) -> tuple[int, int]:
        """Insert raw records, return (inserted, duplicates)."""
        async with self.pool.acquire() as conn:
            existing = await conn.fetch(
                "SELECT record_hash FROM otc.raw"
            )
            existing_hashes = {r["record_hash"] for r in existing}
            
            new_records = [
                r for r in records 
                if r["record_hash"] not in existing_hashes
            ]
            
            for r in new_records:
                await conn.execute("""
                    INSERT INTO otc.raw (
                        batch_id, record_hash, week_ending, tier,
                        symbol, issue_name, venue_name, mpid,
                        share_volume, trade_count, source_file
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """, batch_id, r["record_hash"], r["week_ending"],
                    r["tier"], r["symbol"], r["issue_name"], 
                    r["venue_name"], r["mpid"], r["share_volume"],
                    r["trade_count"], r.get("source_file"))
            
            return len(new_records), len(records) - len(new_records)
    
    async def get_week_stats(self, week_ending: date) -> dict[str, Any]:
        """Get summary stats for a week."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    COUNT(DISTINCT mpid) as venue_count,
                    COUNT(DISTINCT symbol) as symbol_count,
                    SUM(share_volume) as total_volume
                FROM otc.venue_volume
                WHERE week_ending = $1
            """, week_ending)
            
            return {
                "venue_count": row["venue_count"] or 0,
                "symbol_count": row["symbol_count"] or 0,
                "total_volume": row["total_volume"] or 0,
            }
    
    async def upsert_venue_volume(self, records: list[dict]) -> int:
        """Insert or update venue volume records."""
        async with self.pool.acquire() as conn:
            for r in records:
                await conn.execute("""
                    INSERT INTO otc.venue_volume (
                        week_ending, tier, symbol, mpid,
                        share_volume, trade_count, avg_trade_size, record_hash
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (week_ending, tier, symbol, mpid) 
                    DO UPDATE SET
                        share_volume = EXCLUDED.share_volume,
                        trade_count = EXCLUDED.trade_count,
                        avg_trade_size = EXCLUDED.avg_trade_size
                """, r["week_ending"], r["tier"], r["symbol"], r["mpid"],
                    r["share_volume"], r["trade_count"], 
                    r.get("avg_trade_size"), r["record_hash"])
            return len(records)
```

---

## 5. New: Quality Checks

```python
# src/market_spine/domains/otc/quality.py

"""Quality checks - Intermediate tier adds this."""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class QualityIssue:
    code: str
    message: str
    severity: Severity


@dataclass
class QualityResult:
    week_ending: date
    issues: list[QualityIssue]
    grade: str  # A, B, C, D, F
    score: float  # 0-100


class OTCQualityChecker:
    """
    Run quality checks on OTC data.
    
    Basic tier has no quality checks.
    Intermediate adds: volume validation, venue coverage.
    """
    
    def __init__(self, repository):
        self.repo = repository
    
    async def check_week(self, week_ending: date) -> QualityResult:
        """Run all checks for a week."""
        issues = []
        
        current = await self.repo.get_week_stats(week_ending)
        prior = await self.repo.get_week_stats(
            week_ending - timedelta(days=7)
        )
        
        # Check 1: Has any data
        if current["total_volume"] == 0:
            issues.append(QualityIssue(
                code="NO_DATA",
                message="No volume data for week",
                severity=Severity.ERROR,
            ))
        
        # Check 2: Venue count drop
        if prior and prior["venue_count"] > 0:
            drop = (prior["venue_count"] - current["venue_count"]) / prior["venue_count"]
            if drop > 0.2:  # 20% drop
                issues.append(QualityIssue(
                    code="VENUE_DROP",
                    message=f"Venue count dropped {drop:.0%}",
                    severity=Severity.WARNING,
                ))
        
        # Check 3: Volume swing
        if prior and prior["total_volume"] > 0:
            change = abs(current["total_volume"] - prior["total_volume"]) / prior["total_volume"]
            if change > 0.5:  # 50% swing
                issues.append(QualityIssue(
                    code="VOLUME_SWING",
                    message=f"Volume changed {change:.0%}",
                    severity=Severity.WARNING,
                ))
        
        # Compute grade
        errors = sum(1 for i in issues if i.severity == Severity.ERROR)
        warnings = sum(1 for i in issues if i.severity == Severity.WARNING)
        
        if errors > 0:
            grade, score = "F", 0
        elif warnings == 0:
            grade, score = "A", 100
        elif warnings <= 2:
            grade, score = "B", 80
        else:
            grade, score = "C", 60
        
        return QualityResult(
            week_ending=week_ending,
            issues=issues,
            grade=grade,
            score=score,
        )
```

---

## 6. Modified: Async Pipelines

```python
# src/market_spine/domains/otc/pipelines.py

"""OTC pipelines - Intermediate version with async + quality."""

import uuid
from datetime import datetime
from pathlib import Path

from market_spine.pipelines.base import Pipeline, PipelineResult, PipelineStatus
from market_spine.pipelines.registry import PipelineRegistry

from market_spine.domains.otc.parser import parse_finra_file
from market_spine.domains.otc.normalizer import normalize_records
from market_spine.domains.otc.calculations import (
    compute_symbol_summaries,
    compute_venue_shares,
)
from market_spine.domains.otc.repository import OTCRepository
from market_spine.domains.otc.quality import OTCQualityChecker


@PipelineRegistry.register
class OTCIngestPipeline(Pipeline):
    """Ingest FINRA file with quality check."""
    
    name = "otc.ingest"
    description = "Ingest and validate FINRA OTC file"
    
    async def run(self) -> PipelineResult:
        started = datetime.now()
        file_path = Path(self.params["file_path"])
        batch_id = str(uuid.uuid4())[:8]
        
        repo = OTCRepository()
        
        # Parse file (same as Basic)
        records = list(parse_finra_file(file_path))
        
        # Convert to dicts for repo
        record_dicts = [
            {
                "record_hash": r.record_hash,
                "week_ending": r.week_ending,
                "tier": r.tier,
                "symbol": r.symbol,
                "issue_name": r.issue_name,
                "venue_name": r.venue_name,
                "mpid": r.mpid,
                "share_volume": r.share_volume,
                "trade_count": r.trade_count,
                "source_file": str(file_path),
            }
            for r in records
        ]
        
        # Insert via repository
        inserted, dupes = await repo.insert_raw_batch(record_dicts, batch_id)
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={"records": len(records), "inserted": inserted, "duplicates": dupes},
        )


@PipelineRegistry.register
class OTCNormalizePipeline(Pipeline):
    """Normalize with quality check at end."""
    
    name = "otc.normalize"
    description = "Normalize OTC data with quality validation"
    
    async def run(self) -> PipelineResult:
        started = datetime.now()
        repo = OTCRepository()
        
        # ... normalization logic same as Basic but async ...
        # After normalizing, run quality check
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={},
        )


@PipelineRegistry.register  
class OTCQualityCheckPipeline(Pipeline):
    """Run quality checks on a week."""
    
    name = "otc.quality_check"
    description = "Validate data quality for a week"
    
    async def run(self) -> PipelineResult:
        started = datetime.now()
        week = self.params.get("week_ending")
        
        repo = OTCRepository()
        checker = OTCQualityChecker(repo)
        
        from datetime import date
        week_date = date.fromisoformat(week) if week else date.today()
        
        result = await checker.check_week(week_date)
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={
                "grade": result.grade,
                "score": result.score,
                "issues": len(result.issues),
            },
        )
```

---

## 7. New: REST API

```python
# src/market_spine/api/routes/otc.py

"""OTC REST endpoints - Intermediate tier adds this."""

from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from market_spine.domains.otc.repository import OTCRepository

router = APIRouter(prefix="/api/v1/otc", tags=["otc"])


class WeekStats(BaseModel):
    week_ending: date
    venue_count: int
    symbol_count: int
    total_volume: int


@router.get("/weeks/{week_ending}", response_model=WeekStats)
async def get_week_stats(week_ending: date):
    """Get stats for a specific week."""
    repo = OTCRepository()
    stats = await repo.get_week_stats(week_ending)
    
    if stats["total_volume"] == 0:
        raise HTTPException(404, f"No data for week {week_ending}")
    
    return WeekStats(week_ending=week_ending, **stats)


@router.get("/weeks")
async def list_weeks(limit: int = 10):
    """List available weeks."""
    repo = OTCRepository()
    # ... implementation
    return []
```

---

## 8. Tests

```python
# tests/domains/otc/test_otc.py

"""Same tests as Basic, plus quality checks."""

import pytest
from datetime import date

# Import same test classes from Basic (copy them)
from market_spine.domains.otc.quality import OTCQualityChecker, Severity


class TestQualityChecker:
    @pytest.fixture
    def mock_repo(self):
        """Mock repository for testing."""
        class MockRepo:
            async def get_week_stats(self, week):
                return {"venue_count": 10, "symbol_count": 100, "total_volume": 1000000}
        return MockRepo()
    
    @pytest.mark.asyncio
    async def test_good_week(self, mock_repo):
        checker = OTCQualityChecker(mock_repo)
        result = await checker.check_week(date(2025, 12, 12))
        
        assert result.grade == "A"
        assert result.score == 100
        assert len(result.issues) == 0
```

---

## 9. What's NOT in Intermediate

| Feature | Added In |
|---------|----------|
| Celery workers | Advanced |
| Redis broker | Advanced |
| S3 storage | Advanced |
| Scheduled jobs | Advanced |
| Rolling calculations | Advanced |
| DLQ handling | Advanced |
| TimescaleDB | Full |
| Event sourcing | Full |
| Observability | Full |

**Next:** See [OTC_PLUGIN_ADVANCED.md](OTC_PLUGIN_ADVANCED.md) for the next tier.
