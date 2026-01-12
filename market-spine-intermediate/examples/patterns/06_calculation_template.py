"""
Pattern 06: Calculation Template

Use this for implementing new calculations (rolling averages, aggregations, scores).
Covers: versioning, determinism, invariants, capture_id semantics.

Run: uv run python -m examples.patterns.06_calculation_template
"""

from datetime import datetime, timezone
from typing import Any
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


# =============================================================================
# Calculation Base Class
# =============================================================================

class Calculation(ABC):
    """
    Base class for deterministic calculations.
    
    Key Properties:
    - version: Semantic version - increment when logic changes
    - invariants: Fields that define identity (for deduplication)
    - metadata: Introspection info for documentation
    
    Contracts:
    - compute() must be deterministic: same inputs → same outputs
    - compare() excludes audit fields (captured_at, batch_id, execution_id)
    """
    
    # Override in subclass
    version: str = "1.0.0"
    invariants: set[str] = set()
    metadata: dict[str, Any] = {}
    
    # Fields to exclude from determinism comparisons
    AUDIT_FIELDS = {"captured_at", "batch_id", "execution_id", "capture_id"}
    
    @abstractmethod
    def compute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """
        Compute the calculation.
        
        Args:
            inputs: Dict with input data and params
        
        Returns:
            Dict with results and metadata
        """
        pass
    
    def compare(
        self,
        result1: dict[str, Any],
        result2: dict[str, Any],
        exclude_fields: set[str] | None = None,
    ) -> bool:
        """
        Compare two results for equality, excluding audit fields.
        
        Used for determinism testing.
        """
        exclude = exclude_fields or self.AUDIT_FIELDS
        
        def strip_audit(d: dict) -> dict:
            return {k: v for k, v in d.items() if k not in exclude}
        
        return strip_audit(result1) == strip_audit(result2)


# =============================================================================
# Example: Rolling Average Calculation
# =============================================================================

class RollingAverageCalculation(Calculation):
    """
    Compute rolling N-week average for a metric.
    
    Mathematical Definition:
        rolling_avg(week, window) = sum(values[week-window:week]) / window
    
    Inputs:
        - rows: List of {week_ending, symbol, value}
        - params: {window_weeks: int}
    
    Output:
        - results: List of {week_ending, symbol, rolling_avg, weeks_in_window}
    """
    
    version = "1.0.0"
    invariants = {"symbol", "week_ending", "window_weeks"}
    metadata = {
        "description": "Compute rolling average over N weeks",
        "category": "rolling",
        "inputs": ["weekly_values"],
        "outputs": ["rolling_averages"],
    }
    
    def compute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Compute rolling averages."""
        rows = inputs["rows"]
        window_weeks = inputs.get("params", {}).get("window_weeks", 6)
        
        # Group by symbol
        by_symbol: dict[str, list[dict]] = {}
        for row in rows:
            symbol = row["symbol"]
            if symbol not in by_symbol:
                by_symbol[symbol] = []
            by_symbol[symbol].append(row)
        
        results = []
        for symbol, symbol_rows in by_symbol.items():
            # Sort by week
            sorted_rows = sorted(symbol_rows, key=lambda r: r["week_ending"])
            
            # Compute rolling average for each week with enough history
            for i, row in enumerate(sorted_rows):
                if i < window_weeks - 1:
                    continue  # Not enough history
                
                window = sorted_rows[i - window_weeks + 1:i + 1]
                values = [r["value"] for r in window if r["value"] is not None]
                
                if len(values) < window_weeks:
                    continue  # Incomplete window
                
                avg = sum(values) / len(values)
                
                results.append({
                    "symbol": symbol,
                    "week_ending": row["week_ending"],
                    "rolling_avg": round(avg, 4),
                    "weeks_in_window": len(values),
                    "window_weeks": window_weeks,
                    "calc_version": self.version,
                })
        
        return {
            "results": results,
            "metadata": {
                "version": self.version,
                "input_count": len(rows),
                "output_count": len(results),
                "window_weeks": window_weeks,
            },
        }


# =============================================================================
# Example: Score Calculation
# =============================================================================

class VolumeScoreCalculation(Calculation):
    """
    Compute volume score relative to market average.
    
    Mathematical Definition:
        score = (symbol_volume / market_avg_volume) * 100
        normalized = min(max(score, 0), 200)  # Cap at 200
    
    Inputs:
        - rows: List of {symbol, volume}
    
    Output:
        - results: List of {symbol, volume_score, percentile}
    """
    
    version = "1.0.0"
    invariants = {"symbol", "week_ending"}
    metadata = {
        "description": "Score symbols by volume relative to market",
        "category": "score",
        "inputs": ["symbol_volumes"],
        "outputs": ["volume_scores"],
    }
    
    def compute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Compute volume scores."""
        rows = inputs["rows"]
        
        if not rows:
            return {"results": [], "metadata": {"version": self.version}}
        
        # Calculate market average
        volumes = [r["volume"] for r in rows if r.get("volume") is not None]
        if not volumes:
            return {"results": [], "metadata": {"version": self.version}}
        
        market_avg = sum(volumes) / len(volumes)
        
        # Calculate percentiles
        sorted_volumes = sorted(volumes)
        
        def percentile(v: float) -> float:
            rank = sum(1 for x in sorted_volumes if x <= v)
            return (rank / len(sorted_volumes)) * 100
        
        # Compute scores
        results = []
        for row in rows:
            volume = row.get("volume")
            if volume is None:
                continue
            
            raw_score = (volume / market_avg) * 100 if market_avg > 0 else 0
            normalized = min(max(raw_score, 0), 200)  # Cap at 200
            
            results.append({
                "symbol": row["symbol"],
                "volume": volume,
                "volume_score": round(normalized, 2),
                "percentile": round(percentile(volume), 2),
                "calc_version": self.version,
            })
        
        return {
            "results": results,
            "metadata": {
                "version": self.version,
                "input_count": len(rows),
                "output_count": len(results),
                "market_avg": round(market_avg, 2),
            },
        }


# =============================================================================
# Calculation Registry
# =============================================================================

_CALC_REGISTRY: dict[str, type[Calculation]] = {}


def register_calculation(name: str):
    """Decorator to register a calculation class."""
    def decorator(cls: type[Calculation]) -> type[Calculation]:
        _CALC_REGISTRY[name] = cls
        return cls
    return decorator


def get_calculation(name: str) -> Calculation:
    """Get a calculation instance by name."""
    if name not in _CALC_REGISTRY:
        available = ", ".join(_CALC_REGISTRY.keys())
        raise KeyError(f"Unknown calculation: {name}. Available: {available}")
    return _CALC_REGISTRY[name]()


# Register our examples
register_calculation("rolling_average")(RollingAverageCalculation)
register_calculation("volume_score")(VolumeScoreCalculation)


# =============================================================================
# Pipeline Integration Pattern
# =============================================================================

@dataclass
class CalculationResult:
    """Result of running a calculation via pipeline."""
    success: bool
    results: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    capture_id: str = ""
    error: str | None = None


def run_calculation_pipeline(
    calc_name: str,
    inputs: dict[str, Any],
    domain: str = "example",
    stage: str = "CALC",
) -> CalculationResult:
    """
    Run a calculation with pipeline semantics.
    
    Adds:
    - capture_id to all output records
    - execution tracking
    - error handling
    """
    # Generate capture_id
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    partition = inputs.get("params", {}).get("partition_key", "default")
    capture_id = f"{domain}.{stage}.{partition}.{timestamp}"
    captured_at = datetime.now(timezone.utc).isoformat()
    
    try:
        calc = get_calculation(calc_name)
        output = calc.compute(inputs)
        
        # Add capture_id to all results
        for result in output.get("results", []):
            result["capture_id"] = capture_id
            result["captured_at"] = captured_at
        
        return CalculationResult(
            success=True,
            results=output.get("results", []),
            metadata=output.get("metadata", {}),
            capture_id=capture_id,
        )
        
    except Exception as e:
        return CalculationResult(
            success=False,
            error=str(e),
            capture_id=capture_id,
        )


# =============================================================================
# Demo
# =============================================================================

def main():
    print("=" * 70)
    print("Pattern 06: Calculation Template")
    print("=" * 70)
    
    # Demo 1: Rolling Average
    print("\n📊 Rolling Average Calculation:")
    print("-" * 50)
    
    calc = RollingAverageCalculation()
    print(f"  Version: {calc.version}")
    print(f"  Invariants: {calc.invariants}")
    
    # Sample data: 8 weeks of AAPL data
    input_rows = [
        {"symbol": "AAPL", "week_ending": f"2025-01-0{i}", "value": 100 + i * 10}
        for i in range(1, 9)
    ]
    
    result = calc.compute({"rows": input_rows, "params": {"window_weeks": 4}})
    
    print(f"  Input rows: {len(input_rows)}")
    print(f"  Output rows: {result['metadata']['output_count']}")
    print("  Results:")
    for r in result["results"][:3]:
        print(f"    {r['week_ending']}: avg={r['rolling_avg']}")
    
    # Demo 2: Determinism Test
    print("\n🔬 Determinism Test:")
    print("-" * 50)
    
    result1 = calc.compute({"rows": input_rows, "params": {"window_weeks": 4}})
    result2 = calc.compute({"rows": input_rows, "params": {"window_weeks": 4}})
    
    is_deterministic = all(
        calc.compare(r1, r2)
        for r1, r2 in zip(result1["results"], result2["results"])
    )
    print(f"  Same inputs → Same outputs: {is_deterministic}")
    
    # Demo 3: Volume Score
    print("\n📈 Volume Score Calculation:")
    print("-" * 50)
    
    volume_rows = [
        {"symbol": "AAPL", "volume": 1000000},
        {"symbol": "TSLA", "volume": 500000},
        {"symbol": "MSFT", "volume": 2000000},
        {"symbol": "GOOG", "volume": 750000},
    ]
    
    score_calc = VolumeScoreCalculation()
    scores = score_calc.compute({"rows": volume_rows})
    
    print(f"  Market avg volume: {scores['metadata']['market_avg']:,.0f}")
    print("  Scores:")
    for s in sorted(scores["results"], key=lambda x: -x["volume_score"]):
        print(f"    {s['symbol']}: score={s['volume_score']}, percentile={s['percentile']}")
    
    # Demo 4: Pipeline Integration
    print("\n🔧 Pipeline Integration:")
    print("-" * 50)
    
    pipeline_result = run_calculation_pipeline(
        calc_name="rolling_average",
        inputs={"rows": input_rows, "params": {"window_weeks": 4}},
        domain="finra.otc",
        stage="ROLLING",
    )
    
    print(f"  Success: {pipeline_result.success}")
    print(f"  Capture ID: {pipeline_result.capture_id}")
    print(f"  Results with capture_id: {len(pipeline_result.results)}")
    if pipeline_result.results:
        sample = pipeline_result.results[0]
        print(f"    Sample: {sample}")
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
