# OTC Analytics & Metrics

## Computed Metrics

| Metric | Granularity | Description |
|--------|-------------|-------------|
| Total volume | Symbol × Week | Sum across all venues |
| Market share | Venue × Week | % of total OTC volume |
| Venue count | Symbol × Week | How many venues traded |
| 6-week rolling avg | Symbol or Venue | Smoothed trend |
| HHI | Symbol × Week | Concentration index |

---

## Six-Week Rolling Averages

### Symbol Rolling Average Table

```sql
CREATE TABLE otc.symbol_rolling_avg (
    id BIGSERIAL,
    execution_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,
    symbol TEXT NOT NULL,
    
    -- 6-week rolling averages
    avg_6w_volume BIGINT,
    avg_6w_trades INT,
    avg_6w_venue_count NUMERIC(4,1),
    avg_6w_trade_size NUMERIC(12,2),
    
    -- Trend (current vs 6-week avg)
    volume_vs_avg_pct NUMERIC(8,2),
    trend_direction TEXT,  -- 'up', 'down', 'stable'
    
    weeks_in_window INT,
    earliest_week DATE,
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, symbol)
);
```

### Computation SQL

```sql
WITH rolling_data AS (
    SELECT
        s.week_ending,
        s.symbol,
        s.total_volume,
        s.total_trades,
        s.venue_count,
        
        AVG(s.total_volume) OVER w AS avg_6w_volume,
        AVG(s.total_trades) OVER w AS avg_6w_trades,
        AVG(s.venue_count) OVER w AS avg_6w_venue_count,
        COUNT(*) OVER w AS weeks_in_window,
        MIN(s.week_ending) OVER w AS earliest_week
        
    FROM otc.symbol_weekly_summary s
    WINDOW w AS (
        PARTITION BY s.symbol 
        ORDER BY s.week_ending 
        ROWS BETWEEN 5 PRECEDING AND CURRENT ROW
    )
)
INSERT INTO otc.symbol_rolling_avg (
    execution_id, week_ending, symbol,
    avg_6w_volume, avg_6w_trades, avg_6w_venue_count,
    volume_vs_avg_pct, trend_direction,
    weeks_in_window, earliest_week
)
SELECT
    $1,
    week_ending,
    symbol,
    
    avg_6w_volume::bigint,
    avg_6w_trades::int,
    ROUND(avg_6w_venue_count, 1),
    
    ROUND((total_volume - avg_6w_volume)::numeric / 
          NULLIF(avg_6w_volume, 0) * 100, 2),
    
    CASE 
        WHEN total_volume > avg_6w_volume * 1.1 THEN 'up'
        WHEN total_volume < avg_6w_volume * 0.9 THEN 'down'
        ELSE 'stable'
    END,
    
    weeks_in_window,
    earliest_week
    
FROM rolling_data
WHERE week_ending = $2;
```

---

## Venue Rolling Averages

```sql
CREATE TABLE otc.venue_rolling_avg (
    id BIGSERIAL,
    execution_id TEXT NOT NULL,
    
    week_ending DATE NOT NULL,
    mpid TEXT NOT NULL,
    
    avg_6w_volume BIGINT,
    avg_6w_market_share NUMERIC(5,2),
    avg_6w_symbol_count INT,
    avg_6w_rank NUMERIC(4,1),
    
    volume_vs_avg_pct NUMERIC(8,2),
    share_vs_avg_pct NUMERIC(5,2),
    trend_direction TEXT,
    
    weeks_in_window INT,
    
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    PRIMARY KEY (id, week_ending),
    UNIQUE (week_ending, mpid)
);
```

---

## Concentration Metrics (HHI)

**Herfindahl-Hirschman Index** measures market concentration on a 0-10,000 scale.

| HHI Range | Interpretation |
|-----------|----------------|
| < 1,500 | Competitive |
| 1,500 - 2,500 | Moderate |
| > 2,500 | Concentrated |

### HHI Calculation

```sql
-- HHI per symbol
SELECT
    s.week_ending,
    s.symbol,
    SUM(POWER(v.share_volume::numeric / s.total_volume * 100, 2)) as hhi
FROM otc.symbol_weekly_summary s
JOIN otc.venue_volume v 
    ON s.week_ending = v.week_ending AND s.symbol = v.symbol
WHERE s.week_ending = '2025-12-29'
GROUP BY s.week_ending, s.symbol;
```

### Python Model

```python
from decimal import Decimal
from pydantic import BaseModel, computed_field


class SymbolConcentration(BaseModel):
    week_ending: date
    symbol: str
    
    hhi: Decimal
    top_venue_share: Decimal
    top_3_venue_share: Decimal
    
    @computed_field
    @property
    def concentration_level(self) -> str:
        if self.hhi < 1500:
            return "competitive"
        elif self.hhi < 2500:
            return "moderate"
        return "concentrated"
```

---

## Example Queries

### Top venues by market share this week

```sql
SELECT mpid, market_share_pct, rank, symbol_count
FROM otc.venue_market_share
WHERE week_ending = '2025-12-29'
ORDER BY rank
LIMIT 10;
```

### Symbols with most venue coverage

```sql
SELECT symbol, venue_count, total_volume, top_venue_pct
FROM otc.symbol_weekly_summary
WHERE week_ending = '2025-12-29'
ORDER BY venue_count DESC
LIMIT 20;
```

### Venue market share trend (8 weeks)

```sql
SELECT week_ending, mpid, market_share_pct, rank
FROM otc.venue_market_share
WHERE mpid IN ('SGMT', 'INCR', 'UBSA')
  AND week_ending >= '2025-11-01'
ORDER BY week_ending, mpid;
```

### Symbols trending up

```sql
SELECT symbol, avg_6w_volume, volume_vs_avg_pct
FROM otc.symbol_rolling_avg
WHERE week_ending = '2025-12-29'
  AND trend_direction = 'up'
ORDER BY volume_vs_avg_pct DESC
LIMIT 20;
```
