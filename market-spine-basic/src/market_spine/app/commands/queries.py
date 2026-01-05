"""
Data query commands.

These commands provide data querying capabilities for both CLI and API,
allowing inspection of available weeks and symbol data.
"""

from dataclasses import dataclass, field

from market_spine.app.models import (
    CommandError,
    ErrorCode,
    Result,
    SymbolInfo,
    SymbolWeekData,
    WeekInfo,
)
from market_spine.app.services.data import DataSourceConfig
from market_spine.app.services.params import ParameterResolver
from market_spine.app.services.tier import TierNormalizer
from market_spine.db import get_connection

# =============================================================================
# Query Weeks Command
# =============================================================================


@dataclass
class QueryWeeksRequest:
    """Input for querying available weeks."""

    tier: str
    limit: int = 10


@dataclass
class QueryWeeksResult(Result):
    """Output from querying weeks."""

    tier: str | None = None  # Canonical tier value
    weeks: list[WeekInfo] = field(default_factory=list)
    count: int = 0
    limit: int = 10


class QueryWeeksCommand:
    """
    Query available weeks of data for a tier.

    Example:
        command = QueryWeeksCommand()
        result = command.execute(QueryWeeksRequest(tier="tier1", limit=5))
        for week in result.weeks:
            print(f"{week.week_ending}: {week.symbol_count} symbols")
    """

    def __init__(
        self,
        tier_normalizer: TierNormalizer | None = None,
        data_source: DataSourceConfig | None = None,
    ) -> None:
        """Initialize with optional service overrides."""
        self._tier_normalizer = tier_normalizer or TierNormalizer()
        self._data_source = data_source or DataSourceConfig()

    def execute(self, request: QueryWeeksRequest) -> QueryWeeksResult:
        """
        Execute the query weeks command.

        Args:
            request: Request with tier and limit

        Returns:
            Result containing list of available weeks
        """
        # Normalize tier
        try:
            canonical_tier = self._tier_normalizer.normalize(request.tier)
        except ValueError as e:
            return QueryWeeksResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INVALID_TIER,
                    message=str(e),
                ),
            )

        # Query database
        try:
            conn = get_connection()
            cursor = conn.cursor()

            table = self._data_source.normalized_data_table
            cursor.execute(
                f"""
                SELECT week_ending, COUNT(DISTINCT symbol) as symbol_count
                FROM {table}
                WHERE tier = ?
                GROUP BY week_ending
                ORDER BY week_ending DESC
                LIMIT ?
                """,
                (canonical_tier, request.limit),
            )

            rows = cursor.fetchall()

            weeks = [
                WeekInfo(
                    week_ending=row["week_ending"] if hasattr(row, "__getitem__") else row[0],
                    symbol_count=row["symbol_count"] if hasattr(row, "__getitem__") else row[1],
                )
                for row in rows
            ]

            return QueryWeeksResult(
                success=True,
                tier=canonical_tier,
                weeks=weeks,
                count=len(weeks),
                limit=request.limit,
            )

        except Exception as e:
            return QueryWeeksResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.DATABASE_ERROR,
                    message=f"Query failed: {e}",
                ),
            )


# =============================================================================
# Query Symbols Command
# =============================================================================


@dataclass
class QuerySymbolsRequest:
    """Input for querying top symbols."""

    tier: str
    week: str
    top: int = 10


@dataclass
class QuerySymbolsResult(Result):
    """Output from querying symbols."""

    tier: str | None = None
    week: str | None = None
    symbols: list[SymbolInfo] = field(default_factory=list)
    count: int = 0
    top: int = 10


class QuerySymbolsCommand:
    """
    Query top symbols by volume for a specific week.

    Example:
        command = QuerySymbolsCommand()
        result = command.execute(QuerySymbolsRequest(
            tier="NMS_TIER_1",
            week="2025-12-19",
            top=10,
        ))
        for sym in result.symbols:
            print(f"{sym.symbol}: {sym.volume} shares")
    """

    def __init__(
        self,
        tier_normalizer: TierNormalizer | None = None,
        param_resolver: ParameterResolver | None = None,
        data_source: DataSourceConfig | None = None,
    ) -> None:
        """Initialize with optional service overrides."""
        self._tier_normalizer = tier_normalizer or TierNormalizer()
        self._param_resolver = param_resolver or ParameterResolver()
        self._data_source = data_source or DataSourceConfig()

    def execute(self, request: QuerySymbolsRequest) -> QuerySymbolsResult:
        """
        Execute the query symbols command.

        Args:
            request: Request with tier, week, and top count

        Returns:
            Result containing list of top symbols
        """
        # Validate date format
        if not self._param_resolver.validate_date(request.week):
            return QuerySymbolsResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INVALID_DATE,
                    message=f"Invalid date format: '{request.week}'. Expected YYYY-MM-DD.",
                ),
            )

        # Normalize tier
        try:
            canonical_tier = self._tier_normalizer.normalize(request.tier)
        except ValueError as e:
            return QuerySymbolsResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INVALID_TIER,
                    message=str(e),
                ),
            )

        # Query database
        try:
            conn = get_connection()
            cursor = conn.cursor()

            table = self._data_source.normalized_data_table
            cursor.execute(
                f"""
                SELECT symbol, SUM(total_shares) as volume, AVG(average_price) as avg_price
                FROM {table}
                WHERE week_ending = ? AND tier = ?
                GROUP BY symbol
                ORDER BY volume DESC
                LIMIT ?
                """,
                (request.week, canonical_tier, request.top),
            )

            rows = cursor.fetchall()

            symbols = []
            for row in rows:
                # Handle both dict-like and tuple-like rows
                if hasattr(row, "__getitem__") and not isinstance(row, tuple):
                    symbol = row["symbol"]
                    volume = row["volume"]
                    avg_price = row["avg_price"]
                else:
                    symbol, volume, avg_price = row

                symbols.append(
                    SymbolInfo(
                        symbol=symbol,
                        volume=int(volume) if volume else 0,
                        avg_price=float(avg_price) if avg_price else None,
                    )
                )

            return QuerySymbolsResult(
                success=True,
                tier=canonical_tier,
                week=request.week,
                symbols=symbols,
                count=len(symbols),
                top=request.top,
            )

        except Exception as e:
            return QuerySymbolsResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.DATABASE_ERROR,
                    message=f"Query failed: {e}",
                ),
            )


# =============================================================================
# Query Symbol History Command
# =============================================================================


@dataclass
class QuerySymbolHistoryRequest:
    """Input for querying symbol history."""

    symbol: str
    tier: str
    weeks: int = 12  # Default to 12 weeks of history


@dataclass
class QuerySymbolHistoryResult(Result):
    """Output from querying symbol history."""

    symbol: str | None = None
    tier: str | None = None
    history: list[SymbolWeekData] = field(default_factory=list)
    count: int = 0


class QuerySymbolHistoryCommand:
    """
    Query historical trading data for a specific symbol.

    Returns weekly trading data for the specified symbol, sorted
    chronologically (oldest to newest) for charting.

    Example:
        command = QuerySymbolHistoryCommand()
        result = command.execute(QuerySymbolHistoryRequest(
            symbol="AAPL",
            tier="NMS_TIER_1",
            weeks=12,
        ))
        for week in result.history:
            print(f"{week.week_ending}: {week.total_shares} shares")
    """

    def __init__(
        self,
        tier_normalizer: TierNormalizer | None = None,
        data_source: DataSourceConfig | None = None,
    ) -> None:
        """Initialize with optional service overrides."""
        self._tier_normalizer = tier_normalizer or TierNormalizer()
        self._data_source = data_source or DataSourceConfig()

    def execute(self, request: QuerySymbolHistoryRequest) -> QuerySymbolHistoryResult:
        """
        Execute the query symbol history command.

        Args:
            request: Request with symbol, tier, and weeks limit

        Returns:
            Result containing weekly history data
        """
        # Validate symbol
        if not request.symbol or not request.symbol.strip():
            return QuerySymbolHistoryResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.MISSING_REQUIRED,
                    message="Symbol is required",
                ),
            )

        symbol = request.symbol.strip().upper()

        # Normalize tier
        try:
            canonical_tier = self._tier_normalizer.normalize(request.tier)
        except ValueError as e:
            return QuerySymbolHistoryResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.INVALID_TIER,
                    message=str(e),
                ),
            )

        # Query database
        try:
            conn = get_connection()
            cursor = conn.cursor()

            table = self._data_source.normalized_data_table
            # Aggregate by week since normalized table has per-MPID rows
            cursor.execute(
                f"""
                SELECT 
                    week_ending, 
                    SUM(total_shares) as total_shares, 
                    SUM(total_trades) as total_trades
                FROM {table}
                WHERE symbol = ? AND tier = ?
                GROUP BY week_ending
                ORDER BY week_ending DESC
                LIMIT ?
                """,
                (symbol, canonical_tier, request.weeks),
            )

            rows = cursor.fetchall()

            history = []
            for row in rows:
                # Handle both dict-like and tuple-like rows
                if hasattr(row, "__getitem__") and not isinstance(row, tuple):
                    week_ending = row["week_ending"]
                    total_shares = row["total_shares"]
                    total_trades = row["total_trades"]
                else:
                    week_ending, total_shares, total_trades = row

                history.append(
                    SymbolWeekData(
                        week_ending=week_ending,
                        total_shares=int(total_shares) if total_shares else 0,
                        total_trades=int(total_trades) if total_trades else 0,
                        average_price=None,  # Not available in normalized table
                    )
                )

            # Reverse to get chronological order (oldest first) for charting
            history.reverse()

            return QuerySymbolHistoryResult(
                success=True,
                symbol=symbol,
                tier=canonical_tier,
                history=history,
                count=len(history),
            )

        except Exception as e:
            return QuerySymbolHistoryResult(
                success=False,
                error=CommandError(
                    code=ErrorCode.DATABASE_ERROR,
                    message=f"Query failed: {e}",
                ),
            )
