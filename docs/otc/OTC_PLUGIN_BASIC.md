# OTC Weekly Transparency Plugin — Basic Tier

> **Target:** `market-spine-basic`  
> **Complexity:** Minimal  
> **Prerequisites:** See [SHARED_MODELS.md](SHARED_MODELS.md) for common code

---

## 1. What Basic Tier Does

The Basic tier is intentionally simple:

| Feature | Basic Tier |
|---------|------------|
| Data source | Local CSV files |
| Database | SQLite |
| Execution | Synchronous CLI |
| Pipelines | Ingest → Normalize → Summarize |
| API | None |
| Quality checks | None |
| Scheduling | None |

**That's it.** No background workers, no HTTP downloads, no quality gates.

---

## 2. Files to Create

```
market-spine-basic/
├── migrations/
│   └── 020_otc_tables.sql           # Copy from SHARED_MODELS.md (SQLite version)
├── src/market_spine/
│   └── domains/
│       └── otc/
│           ├── __init__.py
│           ├── models.py            # Copy from SHARED_MODELS.md
│           ├── parser.py            # Copy from SHARED_MODELS.md
│           ├── normalizer.py        # Copy from SHARED_MODELS.md
│           ├── calculations.py      # Copy from SHARED_MODELS.md
│           └── pipelines.py         # Basic-specific (below)
└── tests/
    └── domains/
        └── otc/
            └── test_otc.py
```

---

## 3. Domain Init

```python
# src/market_spine/domains/otc/__init__.py

"""OTC Weekly Transparency domain."""

from market_spine.domains.otc import pipelines  # noqa: F401
```

---

## 4. Pipelines (Basic-Specific)

This is the only file that's unique to Basic tier:

```python
# src/market_spine/domains/otc/pipelines.py

"""OTC pipelines for Basic tier - synchronous, simple."""

import uuid
from datetime import datetime
from pathlib import Path

from market_spine.db import get_connection
from market_spine.pipelines.base import Pipeline, PipelineResult, PipelineStatus
from market_spine.registry import register_pipeline

from market_spine.domains.otc.models import IngestResult
from market_spine.domains.otc.parser import parse_finra_file
from market_spine.domains.otc.normalizer import normalize_records
from market_spine.domains.otc.calculations import (
    compute_symbol_summaries,
    compute_venue_shares,
)


@register_pipeline("otc.ingest")
class OTCIngestPipeline(Pipeline):
    """
    Ingest a FINRA file into otc_raw table.
    
    Params:
        file_path: Path to FINRA CSV file
    """
    
    name = "otc.ingest"
    description = "Ingest FINRA OTC file"
    
    def run(self) -> PipelineResult:
        started = datetime.now()
        file_path = Path(self.params["file_path"])
        batch_id = str(uuid.uuid4())[:8]
        
        # Parse file
        records = list(parse_finra_file(file_path))
        
        # Insert with dedup
        conn = get_connection()
        existing = {r[0] for r in conn.execute(
            "SELECT record_hash FROM otc_raw"
        ).fetchall()}
        
        inserted = 0
        for r in records:
            if r.record_hash not in existing:
                conn.execute("""
                    INSERT INTO otc_raw (
                        batch_id, record_hash, week_ending, tier,
                        symbol, issue_name, venue_name, mpid,
                        share_volume, trade_count, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    batch_id, r.record_hash, r.week_ending.isoformat(),
                    r.tier, r.symbol, r.issue_name, r.venue_name,
                    r.mpid, r.share_volume, r.trade_count, str(file_path)
                ))
                inserted += 1
        conn.commit()
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={"records": len(records), "inserted": inserted},
        )


@register_pipeline("otc.normalize")
class OTCNormalizePipeline(Pipeline):
    """Normalize raw records into venue_volume table."""
    
    name = "otc.normalize"
    description = "Normalize raw OTC data"
    
    def run(self) -> PipelineResult:
        started = datetime.now()
        conn = get_connection()
        
        # Fetch unnormalized raw records
        from market_spine.domains.otc.models import RawRecord
        from datetime import date
        
        rows = conn.execute("""
            SELECT * FROM otc_raw 
            WHERE record_hash NOT IN (SELECT record_hash FROM otc_venue_volume)
        """).fetchall()
        
        records = [
            RawRecord(
                tier=r["tier"],
                symbol=r["symbol"],
                issue_name=r["issue_name"],
                venue_name=r["venue_name"],
                mpid=r["mpid"],
                share_volume=r["share_volume"],
                trade_count=r["trade_count"],
                week_ending=date.fromisoformat(r["week_ending"]),
                record_hash=r["record_hash"],
            )
            for r in rows
        ]
        
        # Normalize
        result = normalize_records(records)
        
        # Insert
        for v in result.records:
            conn.execute("""
                INSERT OR REPLACE INTO otc_venue_volume (
                    week_ending, tier, symbol, mpid,
                    share_volume, trade_count, avg_trade_size, record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                v.week_ending.isoformat(), v.tier.value, v.symbol, v.mpid,
                v.share_volume, v.trade_count,
                str(v.avg_trade_size) if v.avg_trade_size else None,
                v.record_hash,
            ))
        conn.commit()
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={"accepted": result.accepted, "rejected": result.rejected},
        )


@register_pipeline("otc.summarize")
class OTCSummarizePipeline(Pipeline):
    """Compute symbol and venue summaries."""
    
    name = "otc.summarize"
    description = "Compute OTC summaries"
    
    def run(self) -> PipelineResult:
        started = datetime.now()
        conn = get_connection()
        
        # Load venue data
        from market_spine.domains.otc.models import VenueVolume, Tier
        from datetime import date
        from decimal import Decimal
        
        rows = conn.execute("SELECT * FROM otc_venue_volume").fetchall()
        
        venue_data = [
            VenueVolume(
                week_ending=date.fromisoformat(r["week_ending"]),
                tier=Tier(r["tier"]),
                symbol=r["symbol"],
                mpid=r["mpid"],
                share_volume=r["share_volume"],
                trade_count=r["trade_count"],
                avg_trade_size=Decimal(r["avg_trade_size"]) if r["avg_trade_size"] else None,
                record_hash=r["record_hash"],
            )
            for r in rows
        ]
        
        # Compute summaries
        symbols = compute_symbol_summaries(venue_data)
        venues = compute_venue_shares(venue_data)
        
        # Store
        for s in symbols:
            conn.execute("""
                INSERT OR REPLACE INTO otc_symbol_summary (
                    week_ending, tier, symbol, total_volume,
                    total_trades, venue_count, avg_trade_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                s.week_ending.isoformat(), s.tier.value, s.symbol,
                s.total_volume, s.total_trades, s.venue_count,
                str(s.avg_trade_size) if s.avg_trade_size else None,
            ))
        
        for v in venues:
            conn.execute("""
                INSERT OR REPLACE INTO otc_venue_share (
                    week_ending, mpid, total_volume, total_trades,
                    symbol_count, market_share_pct, rank
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                v.week_ending.isoformat(), v.mpid, v.total_volume,
                v.total_trades, v.symbol_count, str(v.market_share_pct), v.rank,
            ))
        conn.commit()
        
        return PipelineResult(
            status=PipelineStatus.COMPLETED,
            started_at=started,
            completed_at=datetime.now(),
            metrics={"symbols": len(symbols), "venues": len(venues)},
        )
```

---

## 5. CLI Usage

```bash
# Initialize database
spine db init

# Ingest a file
spine run otc.ingest --param file_path=data/finra/tier1_2025-12-12.csv

# Normalize
spine run otc.normalize

# Compute summaries
spine run otc.summarize

# Query results
spine query "SELECT symbol, total_volume FROM otc_symbol_summary ORDER BY total_volume DESC LIMIT 10"
```

---

## 6. Tests

```python
# tests/domains/otc/test_otc.py

import pytest
from pathlib import Path
from datetime import date

from market_spine.domains.otc.models import RawRecord, Tier
from market_spine.domains.otc.parser import parse_finra_file
from market_spine.domains.otc.normalizer import normalize_records
from market_spine.domains.otc.calculations import compute_symbol_summaries


@pytest.fixture
def sample_csv(tmp_path):
    content = """tierDescription|issueSymbolIdentifier|issueName|marketParticipantName|MPID|totalWeeklyShareQuantity|totalWeeklyTradeCount|lastUpdateDate
NMS Tier 1|AAPL|Apple Inc.|VENUE A|VENA|1000000|5000|2025-12-12
NMS Tier 1|AAPL|Apple Inc.|VENUE B|VENB|500000|2500|2025-12-12
NMS Tier 1|MSFT|Microsoft|VENUE A|VENA|800000|4000|2025-12-12"""
    file = tmp_path / "test.csv"
    file.write_text(content)
    return file


class TestParser:
    def test_parse_file(self, sample_csv):
        records = list(parse_finra_file(sample_csv))
        assert len(records) == 3
        assert records[0].symbol == "AAPL"
        assert records[0].share_volume == 1000000


class TestNormalizer:
    def test_normalize(self, sample_csv):
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)
        
        assert result.accepted == 3
        assert result.rejected == 0
        assert result.records[0].tier == Tier.NMS_TIER_1


class TestCalculations:
    def test_symbol_summary(self, sample_csv):
        records = list(parse_finra_file(sample_csv))
        result = normalize_records(records)
        
        summaries = compute_symbol_summaries(result.records)
        
        aapl = next(s for s in summaries if s.symbol == "AAPL")
        assert aapl.total_volume == 1500000  # 1M + 500K
        assert aapl.venue_count == 2
```

---

## 7. What's NOT in Basic

These features are added in higher tiers:

| Feature | Added In |
|---------|----------|
| HTTP downloads | Intermediate |
| PostgreSQL | Intermediate |
| Background workers | Intermediate |
| REST API | Intermediate |
| Quality checks | Intermediate |
| Celery scheduling | Advanced |
| S3 storage | Advanced |
| Rolling calculations | Advanced |
| TimescaleDB | Full |
| Event sourcing | Full |
| Observability | Full |

**Next:** See [OTC_PLUGIN_INTERMEDIATE.md](OTC_PLUGIN_INTERMEDIATE.md) for the next tier.
