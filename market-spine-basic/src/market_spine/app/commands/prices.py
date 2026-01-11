"""
Price query commands.

Dataclass-based commands for querying price data.
Pydantic models are only used at the API boundary.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from market_spine.app.models import (
    CommandError,
    ErrorCode,
    Result,
)
from market_spine.db import get_connection


# =============================================================================
# Data Models (Dataclasses - NOT Pydantic)
# =============================================================================


@dataclass
class PriceCandle:
    """Single price candle (OHLCV)."""
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    change: float | None = None
    change_percent: float | None = None
    source: str = "alpha_vantage"


@dataclass
class PriceMetadata:
    """Metadata about the price query."""
    capture_id: str | None = None
    captured_at: str | None = None
    content_hash: str | None = None
    source: str = "alpha_vantage"
    is_latest: bool = True


# =============================================================================
# Query Prices Command
# =============================================================================


@dataclass
class QueryPricesRequest:
    """Input for querying price history."""
    symbol: str
    days: int = 30
    capture_id: str | None = None  # For as-of queries
    offset: int = 0
    limit: int = 100


@dataclass
class QueryPricesResult(Result):
    """Output from querying prices."""
    symbol: str | None = None
    candles: list[PriceCandle] = field(default_factory=list)
    count: int = 0
    total: int = 0  # Total matching rows (for pagination)
    metadata: PriceMetadata | None = None
    has_more: bool = False


class QueryPricesCommand:
    """
    Query price history for a symbol.

    Supports:
    - Latest data (default): most recent capture per date
    - As-of: specific capture_id for point-in-time queries
    - Pagination: offset/limit
    - Guardrails: max 365 days, max 1000 rows

    Example:
        command = QueryPricesCommand()
        result = command.execute(QueryPricesRequest(symbol="AAPL", days=30))
        for candle in result.candles:
            print(f"{candle.date}: {candle.close}")
    """

    MAX_DAYS = 365
    MAX_LIMIT = 1000

    def execute(self, request: QueryPricesRequest) -> QueryPricesResult:
        """Execute the query prices command."""
        # Validate and normalize
        symbol = request.symbol.upper()
        days = min(request.days, self.MAX_DAYS)
        limit = min(request.limit, self.MAX_LIMIT)
        offset = max(0, request.offset)

        conn = get_connection()
        cursor = conn.cursor()

        try:
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='market_data_prices_daily'
            """)
            if not cursor.fetchone():
                return QueryPricesResult(
                    success=True,
                    symbol=symbol,
                    candles=[],
                    count=0,
                    total=0,
                    metadata=None,
                )

            # Build query based on mode
            if request.capture_id:
                # As-of query: get data from specific capture
                query = """
                    SELECT symbol, date, open, high, low, close, volume,
                           change, change_percent, source, capture_id, captured_at
                    FROM market_data_prices_daily
                    WHERE symbol = ? AND capture_id = ? AND is_valid = 1
                    ORDER BY date DESC
                    LIMIT ? OFFSET ?
                """
                params = (symbol, request.capture_id, limit, offset)
                
                count_query = """
                    SELECT COUNT(*) FROM market_data_prices_daily
                    WHERE symbol = ? AND capture_id = ? AND is_valid = 1
                """
                count_params = (symbol, request.capture_id)
            else:
                # Latest query: get most recent capture per date
                query = """
                    SELECT * FROM (
                        SELECT symbol, date, open, high, low, close, volume,
                               change, change_percent, source, capture_id, captured_at,
                               ROW_NUMBER() OVER (
                                   PARTITION BY symbol, date 
                                   ORDER BY captured_at DESC
                               ) as rn
                        FROM market_data_prices_daily
                        WHERE symbol = ? AND is_valid = 1
                    ) WHERE rn = 1
                    ORDER BY date DESC
                    LIMIT ? OFFSET ?
                """
                params = (symbol, limit, offset)
                
                count_query = """
                    SELECT COUNT(DISTINCT date) FROM market_data_prices_daily
                    WHERE symbol = ? AND is_valid = 1
                """
                count_params = (symbol,)

            # Execute count query
            cursor.execute(count_query, count_params)
            total = cursor.fetchone()[0]

            # Execute main query
            cursor.execute(query, params)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            if not rows:
                return QueryPricesResult(
                    success=True,
                    symbol=symbol,
                    candles=[],
                    count=0,
                    total=0,
                    metadata=None,
                )

            # Convert to dataclasses
            row_dicts = [dict(zip(columns, row)) for row in rows]
            candles = [
                PriceCandle(
                    symbol=row["symbol"],
                    date=row["date"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    change=row.get("change"),
                    change_percent=row.get("change_percent"),
                    source=row.get("source", "alpha_vantage"),
                )
                for row in row_dicts
            ]

            # Build metadata from first row
            first_row = row_dicts[0]
            metadata = PriceMetadata(
                capture_id=first_row.get("capture_id"),
                captured_at=first_row.get("captured_at"),
                source=first_row.get("source", "alpha_vantage"),
                is_latest=request.capture_id is None,
            )

            return QueryPricesResult(
                success=True,
                symbol=symbol,
                candles=candles,
                count=len(candles),
                total=total,
                metadata=metadata,
                has_more=(offset + len(candles)) < total,
            )

        except Exception as e:
            return QueryPricesResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Database error: {str(e)}",
                ),
            )


# =============================================================================
# Query Latest Price Command
# =============================================================================


@dataclass
class QueryLatestPriceRequest:
    """Input for querying latest price."""
    symbol: str
    capture_id: str | None = None  # For as-of queries


@dataclass
class QueryLatestPriceResult(Result):
    """Output from querying latest price."""
    candle: PriceCandle | None = None
    metadata: PriceMetadata | None = None


class QueryLatestPriceCommand:
    """
    Query the latest available price for a symbol.

    Returns the most recent date's price data.
    """

    def execute(self, request: QueryLatestPriceRequest) -> QueryLatestPriceResult:
        """Execute the query latest price command."""
        symbol = request.symbol.upper()

        conn = get_connection()
        cursor = conn.cursor()

        try:
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='market_data_prices_daily'
            """)
            if not cursor.fetchone():
                return QueryLatestPriceResult(
                    success=False,
                    error=CommandError(
                        code=ErrorCode.NOT_FOUND,
                        message=f"No price data available for {symbol}",
                    ),
                )

            # Build query based on mode
            if request.capture_id:
                query = """
                    SELECT symbol, date, open, high, low, close, volume,
                           change, change_percent, source, capture_id, captured_at
                    FROM market_data_prices_daily
                    WHERE symbol = ? AND capture_id = ? AND is_valid = 1
                    ORDER BY date DESC
                    LIMIT 1
                """
                params = (symbol, request.capture_id)
            else:
                query = """
                    SELECT * FROM (
                        SELECT symbol, date, open, high, low, close, volume,
                               change, change_percent, source, capture_id, captured_at,
                               ROW_NUMBER() OVER (
                                   PARTITION BY symbol 
                                   ORDER BY date DESC, captured_at DESC
                               ) as rn
                        FROM market_data_prices_daily
                        WHERE symbol = ? AND is_valid = 1
                    ) WHERE rn = 1
                """
                params = (symbol,)

            cursor.execute(query, params)
            row = cursor.fetchone()

            if not row:
                return QueryLatestPriceResult(
                    success=False,
                    error=CommandError(
                        code=ErrorCode.NOT_FOUND,
                        message=f"No price data available for {symbol}",
                    ),
                )

            columns = [desc[0] for desc in cursor.description]
            row_dict = dict(zip(columns, row))

            candle = PriceCandle(
                symbol=row_dict["symbol"],
                date=row_dict["date"],
                open=row_dict["open"],
                high=row_dict["high"],
                low=row_dict["low"],
                close=row_dict["close"],
                volume=row_dict["volume"],
                change=row_dict.get("change"),
                change_percent=row_dict.get("change_percent"),
                source=row_dict.get("source", "alpha_vantage"),
            )

            metadata = PriceMetadata(
                capture_id=row_dict.get("capture_id"),
                captured_at=row_dict.get("captured_at"),
                source=row_dict.get("source", "alpha_vantage"),
                is_latest=request.capture_id is None,
            )

            return QueryLatestPriceResult(
                success=True,
                candle=candle,
                metadata=metadata,
            )

        except Exception as e:
            return QueryLatestPriceResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Database error: {str(e)}",
                ),
            )


# =============================================================================
# Price Metadata Query Command
# =============================================================================


@dataclass
class QueryPriceMetadataRequest:
    """Input for querying price data metadata."""
    symbol: str | None = None  # If None, returns all symbols


@dataclass
class SymbolPriceInfo:
    """Summary info for a symbol's price data."""
    symbol: str
    earliest_date: str
    latest_date: str
    row_count: int
    capture_count: int
    source: str


@dataclass
class QueryPriceMetadataResult(Result):
    """Output from querying price metadata."""
    symbols: list[SymbolPriceInfo] = field(default_factory=list)
    count: int = 0


class QueryPriceMetadataCommand:
    """Query metadata about available price data."""

    def execute(self, request: QueryPriceMetadataRequest) -> QueryPriceMetadataResult:
        """Execute the query price metadata command."""
        conn = get_connection()
        cursor = conn.cursor()

        try:
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='market_data_prices_daily'
            """)
            if not cursor.fetchone():
                return QueryPriceMetadataResult(success=True, symbols=[], count=0)

            if request.symbol:
                symbol = request.symbol.upper()
                query = """
                    SELECT 
                        symbol,
                        MIN(date) as earliest_date,
                        MAX(date) as latest_date,
                        COUNT(*) as row_count,
                        COUNT(DISTINCT capture_id) as capture_count,
                        source
                    FROM market_data_prices_daily
                    WHERE symbol = ? AND is_valid = 1
                    GROUP BY symbol, source
                """
                cursor.execute(query, (symbol,))
            else:
                query = """
                    SELECT 
                        symbol,
                        MIN(date) as earliest_date,
                        MAX(date) as latest_date,
                        COUNT(*) as row_count,
                        COUNT(DISTINCT capture_id) as capture_count,
                        source
                    FROM market_data_prices_daily
                    WHERE is_valid = 1
                    GROUP BY symbol, source
                    ORDER BY symbol
                """
                cursor.execute(query)

            rows = cursor.fetchall()
            symbols = [
                SymbolPriceInfo(
                    symbol=row[0],
                    earliest_date=row[1],
                    latest_date=row[2],
                    row_count=row[3],
                    capture_count=row[4],
                    source=row[5],
                )
                for row in rows
            ]

            return QueryPriceMetadataResult(
                success=True,
                symbols=symbols,
                count=len(symbols),
            )

        except Exception as e:
            return QueryPriceMetadataResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INTERNAL_ERROR,
                    message=f"Database error: {str(e)}",
                ),
            )
