# OTC Data Quality Framework

## Quality Dimensions

| Dimension | Definition | Measurement |
|-----------|------------|-------------|
| **Completeness** | All expected venues reported | % of known venues with data |
| **Timeliness** | Data published on schedule | Days late from expected |
| **Accuracy** | Volumes are plausible | Validation pass rate |
| **Consistency** | Week-over-week reasonable | % change vs prior week |
| **Coverage** | Symbols have multiple venues | Avg venues per symbol |

---

## Quality Checker

```python
from datetime import date, timedelta
from dataclasses import dataclass


@dataclass
class Warning:
    code: str
    message: str
    severity: str = "warning"


@dataclass
class QualityResult:
    week_ending: date
    warnings: list[Warning]
    grade: str  # A, B, C, D, F


class WeeklyDataQualityChecker:
    """Quality checks for OTC weekly transparency data."""
    
    async def check_week(self, week_ending: date) -> QualityResult:
        warnings = []
        
        # 1. VENUE COVERAGE
        venues_this_week = await self.db.fetch_val("""
            SELECT COUNT(DISTINCT mpid) FROM otc.venue_volume
            WHERE week_ending = $1
        """, week_ending)
        
        venues_prior = await self.db.fetch_val("""
            SELECT COUNT(DISTINCT mpid) FROM otc.venue_volume
            WHERE week_ending = $1 - INTERVAL '7 days'
        """, week_ending)
        
        if venues_prior and venues_this_week < venues_prior:
            missing = venues_prior - venues_this_week
            warnings.append(Warning("missing_venues",
                f"{missing} fewer venues than prior week"))
        
        # 2. VOLUME SANITY
        volume_change = await self.db.fetch_one("""
            WITH this_week AS (
                SELECT SUM(share_volume) as vol FROM otc.venue_volume 
                WHERE week_ending = $1
            ),
            prior_week AS (
                SELECT SUM(share_volume) as vol FROM otc.venue_volume 
                WHERE week_ending = $1 - INTERVAL '7 days'
            )
            SELECT 
                (this_week.vol - prior_week.vol)::float / 
                    NULLIF(prior_week.vol, 0) * 100 as pct_change
            FROM this_week, prior_week
        """, week_ending)
        
        if volume_change and abs(volume_change.pct_change or 0) > 50:
            warnings.append(Warning("volume_swing",
                f"Volume changed {volume_change.pct_change:.1f}% vs prior week"))
        
        # 3. MARKET SHARE STABILITY
        share_changes = await self.db.fetch_all("""
            WITH this_week AS (
                SELECT mpid, market_share_pct 
                FROM otc.venue_market_share WHERE week_ending = $1
            ),
            prior_week AS (
                SELECT mpid, market_share_pct 
                FROM otc.venue_market_share WHERE week_ending = $1 - INTERVAL '7 days'
            )
            SELECT 
                t.mpid,
                t.market_share_pct - p.market_share_pct as share_change
            FROM this_week t
            JOIN prior_week p ON t.mpid = p.mpid
            WHERE ABS(t.market_share_pct - p.market_share_pct) > 10
        """, week_ending)
        
        for change in share_changes:
            warnings.append(Warning("market_share_shift",
                f"{change.mpid} share changed {change.share_change:+.1f}pp"))
        
        # 4. ZERO VOLUME CHECK
        zero_count = await self.db.fetch_val("""
            SELECT COUNT(*) FROM otc.venue_volume
            WHERE week_ending = $1 AND share_volume = 0
        """, week_ending)
        
        if zero_count > 0:
            warnings.append(Warning("zero_volume",
                f"{zero_count} records with zero volume"))
        
        return QualityResult(
            week_ending=week_ending,
            warnings=warnings,
            grade=self._grade(warnings)
        )
    
    def _grade(self, warnings: list[Warning]) -> str:
        errors = len([w for w in warnings if w.severity == 'error'])
        warn_count = len(warnings)
        
        if errors > 0: return 'F'
        if warn_count == 0: return 'A'
        if warn_count <= 2: return 'B'
        if warn_count <= 5: return 'C'
        return 'D'
```

---

## Quality Metrics Table

```sql
CREATE TABLE otc.weekly_quality_metrics (
    id BIGSERIAL PRIMARY KEY,
    week_ending DATE NOT NULL UNIQUE,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- Coverage
    venue_count INT,
    symbol_count INT,
    total_records INT,
    
    -- Completeness
    expected_venues INT,
    venue_coverage_pct NUMERIC(5,2),
    
    -- Consistency
    volume_change_pct NUMERIC(8,2),
    max_share_change_pct NUMERIC(5,2),
    
    -- Validation
    zero_volume_count INT,
    rejected_count INT,
    
    -- Overall
    quality_grade TEXT,
    warnings JSONB
);
```

---

## Quality Gates

Quality checks **block** downstream computation:

```python
async def run_compute_with_gate(week_ending: date):
    quality = await checker.check_week(week_ending)
    
    if quality.grade == 'F':
        raise QualityGateError(
            f"Cannot compute summaries: {quality.warnings}"
        )
    
    if quality.grade in ('C', 'D'):
        logger.warning(f"Proceeding with warnings: {quality.warnings}")
    
    # Attach warnings to computed metrics
    await compute_summaries(
        week_ending, 
        quality_flags={"grade": quality.grade, "warnings": quality.warnings}
    )
```

| Grade | Action |
|-------|--------|
| A | Proceed normally |
| B | Proceed, log info |
| C | Proceed, log warning |
| D | Proceed, alert on-call |
| F | Block computation, alert |
