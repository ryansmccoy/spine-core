# OTC API Design

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/otc/weekly/symbols` | GET | List symbols with OTC data |
| `/api/v1/otc/weekly/symbols/{symbol}` | GET | Weekly data for a symbol |
| `/api/v1/otc/weekly/symbols/{symbol}/venues` | GET | Venue breakdown |
| `/api/v1/otc/weekly/symbols/{symbol}/rolling` | GET | Rolling averages |
| `/api/v1/otc/weekly/venues` | GET | All venues with market share |
| `/api/v1/otc/weekly/venues/{mpid}` | GET | Weekly data for a venue |
| `/api/v1/otc/quality/{week_ending}` | GET | Quality metrics |

---

## Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `week_ending` | date | Filter by week | `2025-12-29` |
| `week_start` | date | Range start | `2025-11-01` |
| `week_end` | date | Range end | `2025-12-29` |
| `tier` | string | "T1", "T2", or "all" | `T1` |
| `as_of` | datetime | Point-in-time query | `2026-01-15T10:00:00Z` |
| `limit` | int | Pagination limit | `100` |
| `offset` | int | Pagination offset | `0` |
| `sort` | string | Sort field | `total_volume` |
| `order` | string | "asc" or "desc" | `desc` |

---

## Response Models

```python
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class SymbolWeeklyResponse(BaseModel):
    symbol: str
    week_ending: date
    tier: str
    
    total_volume: int
    total_trades: int
    venue_count: int
    avg_trade_size: Decimal | None
    
    top_venue_mpid: str
    top_venue_name: str | None
    top_venue_share_pct: Decimal
    
    hhi: Decimal | None = None
    concentration_level: str | None = None
    
    computed_at: datetime
    capture_id: str


class SymbolRollingResponse(BaseModel):
    symbol: str
    week_ending: date
    
    current_volume: int
    current_trades: int
    
    avg_6w_volume: int
    avg_6w_trades: int
    avg_6w_venue_count: Decimal
    
    volume_vs_avg_pct: Decimal
    trend_direction: str
    weeks_in_window: int


class VenueVolumeItem(BaseModel):
    mpid: str
    venue_name: str | None
    share_volume: int
    trade_count: int
    market_share_pct: Decimal
    avg_trade_size: Decimal | None


class VenueBreakdownResponse(BaseModel):
    symbol: str
    week_ending: date
    total_volume: int
    venues: list[VenueVolumeItem]


class VenueMarketShareResponse(BaseModel):
    mpid: str
    venue_name: str | None
    week_ending: date
    
    total_volume: int
    total_trades: int
    symbol_count: int
    
    market_share_pct: Decimal
    rank: int
    
    avg_6w_volume: int | None
    avg_6w_market_share: Decimal | None
    trend_direction: str | None


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


class PaginatedResponse(BaseModel):
    data: list
    pagination: PaginationMeta
```

---

## FastAPI Implementation

```python
from datetime import date, datetime
from fastapi import APIRouter, Query, HTTPException, Depends

router = APIRouter(prefix="/api/v1/otc/weekly", tags=["otc"])


@router.get("/symbols/{symbol}")
async def get_symbol_weekly(
    symbol: str,
    week_ending: date = Query(...),
    tier: str = Query("all"),
    as_of: datetime | None = Query(None),
    db = Depends(get_db),
) -> SymbolWeeklyResponse:
    """Get weekly OTC summary for a symbol."""
    
    query = """
        SELECT 
            s.symbol, s.week_ending, s.total_volume, s.total_trades,
            s.venue_count, s.avg_trade_size, s.top_venue as top_venue_mpid,
            s.top_venue_pct as top_venue_share_pct,
            s.computed_at, s.capture_id
        FROM otc.symbol_weekly_summary s
        WHERE s.symbol = $1 AND s.week_ending = $2
    """
    
    if as_of:
        query += " AND s.computed_at <= $3"
        query += " ORDER BY s.computed_at DESC LIMIT 1"
        row = await db.fetch_one(query, symbol, week_ending, as_of)
    else:
        query += " ORDER BY s.computed_at DESC LIMIT 1"
        row = await db.fetch_one(query, symbol, week_ending)
    
    if not row:
        raise HTTPException(404, f"No data for {symbol}")
    
    return SymbolWeeklyResponse(**row)


@router.get("/symbols/{symbol}/venues")
async def get_symbol_venues(
    symbol: str,
    week_ending: date = Query(...),
    tier: str = Query("all"),
    db = Depends(get_db),
) -> VenueBreakdownResponse:
    """Get venue breakdown for a symbol."""
    
    rows = await db.fetch_all("""
        SELECT 
            mpid, venue_name, share_volume, trade_count, avg_trade_size,
            share_volume::numeric / SUM(share_volume) OVER () * 100 as market_share_pct
        FROM otc.venue_volume
        WHERE symbol = $1 AND week_ending = $2
          AND ($3 = 'all' OR tier = $3)
        ORDER BY share_volume DESC
    """, symbol, week_ending, tier)
    
    if not rows:
        raise HTTPException(404, f"No venue data for {symbol}")
    
    return VenueBreakdownResponse(
        symbol=symbol,
        week_ending=week_ending,
        total_volume=sum(r['share_volume'] for r in rows),
        venues=[VenueVolumeItem(**r) for r in rows],
    )


@router.get("/venues")
async def list_venues(
    week_ending: date = Query(...),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("total_volume"),
    order: str = Query("desc"),
    db = Depends(get_db),
) -> PaginatedResponse:
    """List venues with market share."""
    
    allowed_sorts = {"total_volume", "market_share_pct", "symbol_count", "rank"}
    if sort not in allowed_sorts:
        raise HTTPException(400, f"sort must be one of: {allowed_sorts}")
    
    total = await db.fetch_val("""
        SELECT COUNT(*) FROM otc.venue_market_share WHERE week_ending = $1
    """, week_ending)
    
    rows = await db.fetch_all(f"""
        SELECT m.mpid, m.total_volume, m.total_trades, m.symbol_count,
               m.market_share_pct, m.rank,
               r.avg_6w_volume, r.avg_6w_market_share, r.trend_direction
        FROM otc.venue_market_share m
        LEFT JOIN otc.venue_rolling_avg r 
            ON m.mpid = r.mpid AND m.week_ending = r.week_ending
        WHERE m.week_ending = $1
        ORDER BY m.{sort} {order}
        LIMIT $2 OFFSET $3
    """, week_ending, limit, offset)
    
    return PaginatedResponse(
        data=[VenueMarketShareResponse(**r) for r in rows],
        pagination=PaginationMeta(
            total=total, limit=limit, offset=offset,
            has_more=(offset + len(rows)) < total,
        ),
    )
```

---

## Usage Examples

### Get weekly summary for AAPL

```bash
curl "https://api.example.com/api/v1/otc/weekly/symbols/AAPL?week_ending=2025-12-29"
```

```json
{
  "symbol": "AAPL",
  "week_ending": "2025-12-29",
  "total_volume": 45234567,
  "total_trades": 125430,
  "venue_count": 18,
  "top_venue_mpid": "INCR",
  "top_venue_share_pct": 23.5,
  "hhi": 1245.67,
  "concentration_level": "competitive"
}
```

### Get venue breakdown

```bash
curl "https://api.example.com/api/v1/otc/weekly/symbols/AAOI/venues?week_ending=2025-12-29"
```

```json
{
  "symbol": "AAOI",
  "week_ending": "2025-12-29",
  "total_volume": 4234567,
  "venues": [
    {"mpid": "EBXL", "share_volume": 639234, "market_share_pct": 15.10},
    {"mpid": "UBSA", "share_volume": 576612, "market_share_pct": 13.62},
    {"mpid": "INCR", "share_volume": 526088, "market_share_pct": 12.42}
  ]
}
```

### Point-in-time query

```bash
curl "https://api.example.com/api/v1/otc/weekly/symbols/AAPL?week_ending=2025-12-29&as_of=2026-01-15T10:00:00Z"
```
