"""Metrics calculator - computes daily aggregates."""

from datetime import date
from decimal import Decimal
from typing import Any

from market_spine.core.models import OTCMetricsDaily
from market_spine.repositories.otc import OTCRepository
from market_spine.observability.logging import get_logger
from market_spine.observability.metrics import otc_metrics_computed_counter

logger = get_logger(__name__)


class MetricsCalculator:
    """Calculates daily OTC metrics from normalized trades."""

    def __init__(self, repository: OTCRepository | None = None):
        """Initialize with optional repository."""
        self.repository = repository or OTCRepository()

    def compute_daily_metrics(
        self,
        target_date: date | None = None,
        symbol: str | None = None,
    ) -> list[OTCMetricsDaily]:
        """
        Compute daily metrics for trades.

        Args:
            target_date: Specific date to compute (None = all dates)
            symbol: Specific symbol to compute (None = all symbols)

        Returns:
            List of computed metrics
        """
        metrics = self.repository.compute_daily_metrics(
            target_date=target_date,
            symbol=symbol,
        )

        for m in metrics:
            otc_metrics_computed_counter.labels(symbol=m.symbol).inc()

        logger.info(
            "metrics_computed",
            date=str(target_date) if target_date else "all",
            symbol=symbol or "all",
            count=len(metrics),
        )

        return metrics

    def compute_range(
        self,
        start_date: date,
        end_date: date,
        symbols: list[str] | None = None,
    ) -> list[OTCMetricsDaily]:
        """
        Compute metrics for a date range.

        Args:
            start_date: Start of range (inclusive)
            end_date: End of range (inclusive)
            symbols: Specific symbols to compute (None = all)

        Returns:
            List of all computed metrics
        """
        from datetime import timedelta

        all_metrics = []
        current = start_date

        while current <= end_date:
            if symbols:
                for symbol in symbols:
                    metrics = self.compute_daily_metrics(
                        target_date=current,
                        symbol=symbol,
                    )
                    all_metrics.extend(metrics)
            else:
                metrics = self.compute_daily_metrics(target_date=current)
                all_metrics.extend(metrics)

            current += timedelta(days=1)

        return all_metrics

    def get_summary(
        self,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """
        Get summary statistics for a symbol.

        Returns:
            Dictionary with summary stats
        """
        metrics = self.repository.get_daily_metrics(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

        if not metrics:
            return {
                "symbol": symbol,
                "days": 0,
                "total_trades": 0,
                "total_volume": 0,
                "total_notional": Decimal("0"),
                "avg_vwap": None,
            }

        total_trades = sum(m.trade_count for m in metrics)
        total_volume = sum(m.total_volume for m in metrics)
        total_notional = sum(m.total_notional for m in metrics)
        avg_vwap = total_notional / Decimal(total_volume) if total_volume > 0 else None

        return {
            "symbol": symbol,
            "days": len(metrics),
            "total_trades": total_trades,
            "total_volume": total_volume,
            "total_notional": total_notional,
            "avg_vwap": avg_vwap,
            "start_date": min(m.date for m in metrics),
            "end_date": max(m.date for m in metrics),
        }
