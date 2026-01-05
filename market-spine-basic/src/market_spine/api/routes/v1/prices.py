"""
Price data query endpoints.

Provides access to market price data (daily OHLCV).

Endpoints:
- GET /v1/data/prices/{symbol} — Price history with pagination
- GET /v1/data/prices/{symbol}/latest — Latest price
- GET /v1/data/prices/metadata — Available symbols and date ranges

Follows Option A pattern for external data resources:
- Resource-oriented under /v1/data/
- Supports latest (default) and as-of (capture_id) modes
- Pagination via offset/limit
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from market_spine.app.commands.prices import (
    QueryPricesCommand,
    QueryPricesRequest,
    QueryLatestPriceCommand,
    QueryLatestPriceRequest,
    QueryPriceMetadataCommand,
    QueryPriceMetadataRequest,
)

router = APIRouter(prefix="/data/prices", tags=["prices"])


# =============================================================================
# Response Models (Pydantic - API boundary only)
# =============================================================================


class PriceCandle(BaseModel):
    """Single price candle (OHLCV)."""
    
    symbol: str = Field(..., description="Stock ticker symbol")
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    open: float = Field(..., description="Opening price")
    high: float = Field(..., description="High price")
    low: float = Field(..., description="Low price")
    close: float = Field(..., description="Closing price")
    volume: int = Field(..., description="Trading volume")
    change: Optional[float] = Field(None, description="Price change from previous close")
    change_percent: Optional[float] = Field(None, description="Percentage change")


class PaginationMeta(BaseModel):
    """Pagination metadata."""
    offset: int = Field(..., description="Current offset")
    limit: int = Field(..., description="Page size")
    total: int = Field(..., description="Total matching rows")
    has_more: bool = Field(..., description="Whether more pages exist")


class CaptureMeta(BaseModel):
    """Capture metadata for lineage."""
    capture_id: Optional[str] = Field(None, description="Capture ID")
    captured_at: Optional[str] = Field(None, description="Capture timestamp")
    is_latest: bool = Field(True, description="Whether this is the latest capture")
    source: str = Field("alpha_vantage", description="Data source")


class PriceDataResponse(BaseModel):
    """Response for price history query with pagination."""
    
    symbol: str = Field(..., description="Stock ticker symbol")
    candles: list[PriceCandle] = Field(..., description="Price candles (most recent first)")
    count: int = Field(..., description="Number of candles in this response")
    pagination: PaginationMeta = Field(..., description="Pagination info")
    capture: Optional[CaptureMeta] = Field(None, description="Capture metadata")


class PriceLatestResponse(BaseModel):
    """Response for latest price query."""
    
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    change: Optional[float] = None
    change_percent: Optional[float] = None
    capture: Optional[CaptureMeta] = None


class SymbolPriceInfoResponse(BaseModel):
    """Summary info for a symbol's price data."""
    symbol: str
    earliest_date: str
    latest_date: str
    row_count: int
    capture_count: int
    source: str


class PriceMetadataResponse(BaseModel):
    """Response for price metadata query."""
    symbols: list[SymbolPriceInfoResponse]
    count: int


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/metadata",
    response_model=PriceMetadataResponse,
    summary="Get metadata about available price data",
    description="Returns summary information about symbols with price data.",
)
async def get_price_metadata(
    symbol: Optional[str] = Query(None, description="Filter by symbol (optional)"),
):
    """Get metadata about available price data."""
    command = QueryPriceMetadataCommand()
    result = command.execute(QueryPriceMetadataRequest(symbol=symbol))
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error.message if result.error else "Unknown error")
    
    return PriceMetadataResponse(
        symbols=[
            SymbolPriceInfoResponse(
                symbol=s.symbol,
                earliest_date=s.earliest_date,
                latest_date=s.latest_date,
                row_count=s.row_count,
                capture_count=s.capture_count,
                source=s.source,
            )
            for s in result.symbols
        ],
        count=result.count,
    )


@router.get(
    "/{symbol}",
    response_model=PriceDataResponse,
    summary="Get price history for a symbol",
    description="Returns daily OHLCV price data for the specified symbol. "
                "Data is ordered by date descending (most recent first). "
                "Supports pagination and as-of queries via capture_id.",
)
async def get_price_history(
    symbol: str,
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
    capture_id: Optional[str] = Query(None, description="Specific capture ID for as-of query"),
):
    """
    Get price history for a symbol.
    
    Returns up to `days` of daily OHLCV data with pagination.
    Use capture_id for point-in-time (as-of) queries.
    """
    command = QueryPricesCommand()
    result = command.execute(QueryPricesRequest(
        symbol=symbol,
        days=days,
        offset=offset,
        limit=limit,
        capture_id=capture_id,
    ))
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error.message if result.error else "Unknown error")
    
    # Convert dataclass candles to Pydantic models
    candles = [
        PriceCandle(
            symbol=c.symbol,
            date=c.date,
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
            volume=c.volume,
            change=c.change,
            change_percent=c.change_percent,
        )
        for c in result.candles
    ]
    
    # Build capture metadata
    capture = None
    if result.metadata:
        capture = CaptureMeta(
            capture_id=result.metadata.capture_id,
            captured_at=result.metadata.captured_at,
            is_latest=result.metadata.is_latest,
            source=result.metadata.source,
        )
    
    return PriceDataResponse(
        symbol=result.symbol or symbol.upper(),
        candles=candles,
        count=result.count,
        pagination=PaginationMeta(
            offset=offset,
            limit=limit,
            total=result.total,
            has_more=result.has_more,
        ),
        capture=capture,
    )


@router.get(
    "/{symbol}/latest",
    response_model=PriceLatestResponse,
    summary="Get latest price for a symbol",
    description="Returns the most recent available price data for the symbol. "
                "Supports as-of queries via capture_id.",
)
async def get_latest_price(
    symbol: str,
    capture_id: Optional[str] = Query(None, description="Specific capture ID for as-of query"),
):
    """Get the latest available price for a symbol."""
    command = QueryLatestPriceCommand()
    result = command.execute(QueryLatestPriceRequest(
        symbol=symbol,
        capture_id=capture_id,
    ))
    
    if not result.success:
        if result.error and result.error.code.value == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result.error.message)
        raise HTTPException(status_code=500, detail=result.error.message if result.error else "Unknown error")
    
    if not result.candle:
        raise HTTPException(status_code=404, detail=f"No price data available for {symbol.upper()}")
    
    c = result.candle
    capture = None
    if result.metadata:
        capture = CaptureMeta(
            capture_id=result.metadata.capture_id,
            captured_at=result.metadata.captured_at,
            is_latest=result.metadata.is_latest,
            source=result.metadata.source,
        )
    
    return PriceLatestResponse(
        symbol=c.symbol,
        date=c.date,
        open=c.open,
        high=c.high,
        low=c.low,
        close=c.close,
        volume=c.volume,
        change=c.change,
        change_percent=c.change_percent,
        capture=capture,
    )
