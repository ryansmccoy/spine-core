"""
Pattern 07: Aggregation Template

Use for rollup calculations: weekly aggregates, summaries, derived metrics.
Covers: windowing, provenance tracking, quality gates for history.

Run: uv run python -m examples.patterns.07_aggregation_template
"""

from datetime import datetime, timezone, date, timedelta
from typing import Any, Protocol
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


# =============================================================================
# Aggregation Base Class
# =============================================================================

class Aggregation(ABC):
    """
    Base class for aggregation calculations.
    
    Key Differences from Calculation:
    - Operates on windows of data (weekly, monthly, etc.)
    - Tracks provenance: input_min_capture_id, input_max_capture_id
    - Has quality gates (minimum history requirements)
    
    Provenance Pattern:
        output.input_min_capture_id = min(input[*].capture_id)
        output.input_max_capture_id = max(input[*].capture_id)
    """
    
    # Override in subclass
    version: str = "1.0.0"
    min_history_weeks: int = 1  # Quality gate
    window_size: str = "week"  # week, month, quarter
    
    @abstractmethod
    def aggregate(
        self,
        rows: list[dict],
        window_key: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict]:
        """
        Aggregate rows within a window.
        
        Args:
            rows: Input records with capture_id
            window_key: The window to aggregate (e.g., "2025-W23")
            params: Additional parameters
        
        Returns:
            List of aggregated records with provenance
        """
        pass
    
    def extract_provenance(self, rows: list[dict]) -> dict:
        """Extract min/max capture_id from input rows."""
        capture_ids = [
            r.get("capture_id", "")
            for r in rows
            if r.get("capture_id")
        ]
        
        if not capture_ids:
            return {
                "input_min_capture_id": None,
                "input_max_capture_id": None,
                "input_row_count": 0,
            }
        
        return {
            "input_min_capture_id": min(capture_ids),
            "input_max_capture_id": max(capture_ids),
            "input_row_count": len(rows),
        }
    
    def check_quality_gate(self, weeks_available: int) -> tuple[bool, str]:
        """
        Check if we have enough history.
        
        Returns (passed, reason).
        """
        if weeks_available < self.min_history_weeks:
            return False, f"Need {self.min_history_weeks} weeks, have {weeks_available}"
        return True, "OK"


# =============================================================================
# Window Utilities
# =============================================================================

def get_week_key(dt: date) -> str:
    """Get ISO week key (YYYY-Www)."""
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def get_week_ending(week_key: str) -> date:
    """Get the Sunday that ends the ISO week."""
    year, week = week_key.split("-W")
    # ISO week 1 day 1 is a Monday
    first_day = date.fromisocalendar(int(year), int(week), 1)
    return first_day + timedelta(days=6)  # Sunday


def group_by_window(
    rows: list[dict],
    date_field: str = "trade_date",
    window_type: str = "week",
) -> dict[str, list[dict]]:
    """Group rows by window (week, month, etc.)."""
    grouped: dict[str, list[dict]] = {}
    
    for row in rows:
        dt = row.get(date_field)
        if dt is None:
            continue
        
        if isinstance(dt, str):
            dt = date.fromisoformat(dt)
        elif isinstance(dt, datetime):
            dt = dt.date()
        
        if window_type == "week":
            key = get_week_key(dt)
        elif window_type == "month":
            key = dt.strftime("%Y-%m")
        else:
            key = get_week_key(dt)
        
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(row)
    
    return grouped


# =============================================================================
# Example: Weekly Volume Aggregation
# =============================================================================

class WeeklyVolumeAggregation(Aggregation):
    """
    Aggregate daily volumes into weekly totals.
    
    Input: Daily volume records
        {symbol, trade_date, volume, capture_id}
    
    Output: Weekly volume summaries
        {symbol, week_ending, total_volume, avg_daily_volume, trade_days, ...}
    """
    
    version = "1.0.0"
    min_history_weeks = 1
    window_size = "week"
    
    def aggregate(
        self,
        rows: list[dict],
        window_key: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Aggregate into weekly volumes."""
        if not rows:
            return []
        
        # Group by symbol
        by_symbol: dict[str, list[dict]] = {}
        for row in rows:
            symbol = row.get("symbol")
            if symbol:
                if symbol not in by_symbol:
                    by_symbol[symbol] = []
                by_symbol[symbol].append(row)
        
        # Get provenance for all rows
        provenance = self.extract_provenance(rows)
        week_ending = get_week_ending(window_key)
        
        results = []
        for symbol, symbol_rows in by_symbol.items():
            volumes = [r.get("volume", 0) for r in symbol_rows]
            total = sum(volumes)
            trade_days = len([v for v in volumes if v > 0])
            
            results.append({
                "symbol": symbol,
                "week_ending": week_ending.isoformat(),
                "week_key": window_key,
                "total_volume": total,
                "avg_daily_volume": total / trade_days if trade_days > 0 else 0,
                "trade_days": trade_days,
                "agg_version": self.version,
                # Provenance
                "input_min_capture_id": provenance["input_min_capture_id"],
                "input_max_capture_id": provenance["input_max_capture_id"],
                "input_row_count": len(symbol_rows),
            })
        
        return results


# =============================================================================
# Example: Rolling Metric Aggregation
# =============================================================================

class RollingMetricAggregation(Aggregation):
    """
    Compute rolling metrics over multiple weeks.
    
    Used for: 6-week rolling averages, trailing metrics.
    Quality gate ensures we have enough history.
    """
    
    version = "1.0.0"
    min_history_weeks = 6
    window_size = "week"
    
    def aggregate(
        self,
        rows: list[dict],
        window_key: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Compute rolling metrics."""
        params = params or {}
        lookback_weeks = params.get("lookback_weeks", 6)
        metric_field = params.get("metric_field", "value")
        
        # Group by symbol
        by_symbol: dict[str, list[dict]] = {}
        for row in rows:
            symbol = row.get("symbol")
            if symbol:
                if symbol not in by_symbol:
                    by_symbol[symbol] = []
                by_symbol[symbol].append(row)
        
        provenance = self.extract_provenance(rows)
        week_ending = get_week_ending(window_key)
        
        results = []
        for symbol, symbol_rows in by_symbol.items():
            # Check quality gate
            weeks_available = len(set(r.get("week_key", "") for r in symbol_rows))
            passed, reason = self.check_quality_gate(weeks_available)
            
            if not passed:
                # Skip symbol - not enough history
                continue
            
            # Get last N weeks
            sorted_rows = sorted(symbol_rows, key=lambda r: r.get("week_key", ""))
            recent = sorted_rows[-lookback_weeks:]
            
            values = [r.get(metric_field, 0) for r in recent]
            
            results.append({
                "symbol": symbol,
                "week_ending": week_ending.isoformat(),
                "rolling_sum": sum(values),
                "rolling_avg": sum(values) / len(values) if values else 0,
                "rolling_min": min(values) if values else 0,
                "rolling_max": max(values) if values else 0,
                "weeks_in_window": len(recent),
                "agg_version": self.version,
                # Provenance
                "input_min_capture_id": provenance["input_min_capture_id"],
                "input_max_capture_id": provenance["input_max_capture_id"],
                "input_row_count": len(symbol_rows),
            })
        
        return results


# =============================================================================
# Aggregation Pipeline Runner
# =============================================================================

@dataclass
class AggregationResult:
    """Result from running an aggregation."""
    success: bool
    results: list[dict] = field(default_factory=list)
    windows_processed: int = 0
    skipped_quality_gate: int = 0
    capture_id: str = ""
    error: str | None = None


def run_aggregation(
    agg_class: type[Aggregation],
    rows: list[dict],
    date_field: str = "trade_date",
    params: dict[str, Any] | None = None,
    domain: str = "example",
    stage: str = "AGG",
) -> AggregationResult:
    """
    Run aggregation across all windows in input data.
    
    Groups rows by window, applies aggregation to each.
    """
    # Generate capture_id
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    capture_id = f"{domain}.{stage}.{timestamp}"
    captured_at = datetime.now(timezone.utc).isoformat()
    
    try:
        agg = agg_class()
        
        # Group by window
        grouped = group_by_window(rows, date_field, agg.window_size)
        
        all_results = []
        skipped = 0
        
        for window_key in sorted(grouped.keys()):
            window_rows = grouped[window_key]
            
            results = agg.aggregate(window_rows, window_key, params)
            
            if not results:
                skipped += 1
                continue
            
            # Add capture_id to results
            for r in results:
                r["capture_id"] = capture_id
                r["captured_at"] = captured_at
            
            all_results.extend(results)
        
        return AggregationResult(
            success=True,
            results=all_results,
            windows_processed=len(grouped),
            skipped_quality_gate=skipped,
            capture_id=capture_id,
        )
        
    except Exception as e:
        return AggregationResult(
            success=False,
            error=str(e),
            capture_id=capture_id,
        )


# =============================================================================
# Demo
# =============================================================================

def main():
    print("=" * 70)
    print("Pattern 07: Aggregation Template")
    print("=" * 70)
    
    # Generate sample daily data for 3 weeks
    base_date = date(2025, 6, 1)  # Sunday
    daily_rows = []
    
    for week in range(3):
        for day in range(5):  # Mon-Fri
            trade_date = base_date + timedelta(weeks=week, days=day + 1)
            capture_id = f"ingest.DAILY.{trade_date.isoformat()}"
            
            daily_rows.append({
                "symbol": "AAPL",
                "trade_date": trade_date.isoformat(),
                "volume": 1000000 + (week * 100000) + (day * 10000),
                "capture_id": capture_id,
            })
            daily_rows.append({
                "symbol": "TSLA",
                "trade_date": trade_date.isoformat(),
                "volume": 500000 + (week * 50000) + (day * 5000),
                "capture_id": capture_id,
            })
    
    print(f"\n📊 Sample Data: {len(daily_rows)} daily records")
    print(f"  Date range: {daily_rows[0]['trade_date']} to {daily_rows[-1]['trade_date']}")
    
    # Demo 1: Weekly Volume Aggregation
    print("\n📈 Weekly Volume Aggregation:")
    print("-" * 50)
    
    result = run_aggregation(
        WeeklyVolumeAggregation,
        daily_rows,
        domain="finra.otc",
        stage="WEEKLY",
    )
    
    print(f"  Success: {result.success}")
    print(f"  Windows processed: {result.windows_processed}")
    print(f"  Results: {len(result.results)}")
    print(f"  Capture ID: {result.capture_id}")
    
    print("\n  Results by symbol/week:")
    for r in sorted(result.results, key=lambda x: (x["symbol"], x["week_key"])):
        print(f"    {r['symbol']} {r['week_key']}: vol={r['total_volume']:,}, days={r['trade_days']}")
    
    # Demo 2: Provenance Tracking
    print("\n🔗 Provenance Tracking:")
    print("-" * 50)
    
    sample = result.results[0]
    print(f"  Sample output for {sample['symbol']} {sample['week_key']}:")
    print(f"    input_min_capture_id: {sample['input_min_capture_id']}")
    print(f"    input_max_capture_id: {sample['input_max_capture_id']}")
    print(f"    input_row_count: {sample['input_row_count']}")
    
    # Demo 3: Quality Gate
    print("\n🚧 Quality Gate (Rolling Metrics):")
    print("-" * 50)
    
    # Build weekly data with limited history
    weekly_rows = [
        {"symbol": "AAPL", "week_key": f"2025-W{w:02d}", "value": 100 + w}
        for w in range(1, 5)  # Only 4 weeks
    ]
    weekly_rows[-1]["capture_id"] = "test.cap.001"
    
    agg = RollingMetricAggregation()
    print(f"  Required weeks: {agg.min_history_weeks}")
    print(f"  Available weeks: 4")
    
    passed, reason = agg.check_quality_gate(4)
    print(f"  Gate passed: {passed}")
    print(f"  Reason: {reason}")
    
    # Demo 4: Window Grouping Utility
    print("\n📆 Window Grouping:")
    print("-" * 50)
    
    grouped = group_by_window(daily_rows[:10], "trade_date", "week")
    print(f"  Grouped {len(daily_rows[:10])} rows into {len(grouped)} weeks:")
    for week_key, rows in sorted(grouped.items()):
        print(f"    {week_key}: {len(rows)} rows")
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
