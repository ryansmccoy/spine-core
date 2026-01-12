"""
Pattern 01: Pipeline Only

Use this pattern when:
- Single, focused operation
- No coordination with other steps needed
- No validation between steps
- Simple input → output transformation

Examples:
- Fetch data from an API
- Parse a file
- Store records to database
- Run a calculation

Run: uv run python -m examples.patterns.01_pipeline_only
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from dataclasses import dataclass


# =============================================================================
# Base Pipeline Class (from market_spine.pipelines.base)
# =============================================================================

class Pipeline(ABC):
    """Base class for all pipelines."""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """Execute the pipeline with given parameters."""
        ...


# =============================================================================
# Example 1: Simple Fetch Pipeline
# =============================================================================

class FetchPricesPipeline(Pipeline):
    """
    Fetch stock prices from Alpha Vantage API.
    
    Single responsibility: Get data from external source.
    """
    
    name = "prices.fetch"
    description = "Fetch stock prices from Alpha Vantage"
    
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        symbol = params["symbol"]
        api_key = params.get("api_key", "demo")
        
        # In real implementation: call API
        # response = requests.get(f"https://api.alphavantage.co/...")
        
        # Simulated response
        prices = [
            {"date": "2026-01-10", "close": 150.25},
            {"date": "2026-01-09", "close": 149.50},
            {"date": "2026-01-08", "close": 151.00},
        ]
        
        return {
            "symbol": symbol,
            "records": len(prices),
            "prices": prices,
            "fetched_at": datetime.now().isoformat(),
        }


# =============================================================================
# Example 2: Parse Pipeline
# =============================================================================

@dataclass
class ParsedRecord:
    """Parsed FINRA record."""
    symbol: str
    venue: str
    volume: int
    week_ending: str


class ParseFilePipeline(Pipeline):
    """
    Parse a FINRA PSV file into records.
    
    Single responsibility: Transform file → structured data.
    """
    
    name = "finra.parse_file"
    description = "Parse FINRA PSV file"
    
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = params["file_path"]
        
        # In real implementation: read and parse file
        # with open(file_path) as f:
        #     records = [parse_line(line) for line in f]
        
        # Simulated parsing
        records = [
            ParsedRecord("AAPL", "NYSE", 1000000, "2026-01-10"),
            ParsedRecord("MSFT", "NASDAQ", 500000, "2026-01-10"),
        ]
        
        return {
            "file_path": file_path,
            "records": len(records),
            "parsed_data": [
                {"symbol": r.symbol, "venue": r.venue, "volume": r.volume}
                for r in records
            ],
        }


# =============================================================================
# Example 3: Store Pipeline
# =============================================================================

class StorePricesPipeline(Pipeline):
    """
    Store prices to database.
    
    Single responsibility: Persist data.
    """
    
    name = "prices.store"
    description = "Store prices to database"
    
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        prices = params["prices"]
        symbol = params["symbol"]
        
        # In real implementation: insert to database
        # with get_connection() as conn:
        #     conn.execute("INSERT INTO prices ...")
        
        # Simulated storage
        inserted = len(prices)
        
        return {
            "symbol": symbol,
            "inserted": inserted,
            "stored_at": datetime.now().isoformat(),
        }


# =============================================================================
# Example 4: Calculation Pipeline
# =============================================================================

class CalculateMovingAveragePipeline(Pipeline):
    """
    Calculate moving average for a symbol.
    
    Single responsibility: Compute derived value.
    """
    
    name = "prices.calculate_ma"
    description = "Calculate moving average"
    
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        symbol = params["symbol"]
        window = params.get("window", 20)
        
        # In real implementation: query DB and calculate
        # prices = db.query(f"SELECT close FROM prices WHERE symbol = ?", symbol)
        # ma = sum(prices[-window:]) / window
        
        # Simulated calculation
        ma_value = 150.50
        
        return {
            "symbol": symbol,
            "window": window,
            "moving_average": ma_value,
            "calculated_at": datetime.now().isoformat(),
        }


# =============================================================================
# How to Use: Direct Execution
# =============================================================================

def demo_pipeline_only():
    """Demonstrate pipeline-only pattern."""
    
    print("=" * 60)
    print("PATTERN 01: Pipeline Only")
    print("=" * 60)
    print()
    
    # Example 1: Fetch
    print("1. Fetch Pipeline")
    fetch = FetchPricesPipeline()
    result = fetch.execute({"symbol": "AAPL"})
    print(f"   Fetched {result['records']} prices for {result['symbol']}")
    print()
    
    # Example 2: Parse
    print("2. Parse Pipeline")
    parse = ParseFilePipeline()
    result = parse.execute({"file_path": "/data/finra.psv"})
    print(f"   Parsed {result['records']} records from {result['file_path']}")
    print()
    
    # Example 3: Store
    print("3. Store Pipeline")
    store = StorePricesPipeline()
    result = store.execute({
        "symbol": "AAPL",
        "prices": [{"date": "2026-01-10", "close": 150.25}],
    })
    print(f"   Stored {result['inserted']} records for {result['symbol']}")
    print()
    
    # Example 4: Calculate
    print("4. Calculate Pipeline")
    calc = CalculateMovingAveragePipeline()
    result = calc.execute({"symbol": "AAPL", "window": 20})
    print(f"   MA({result['window']}) = {result['moving_average']}")
    print()
    
    print("=" * 60)
    print("KEY TAKEAWAYS:")
    print("  - Each pipeline does ONE thing well")
    print("  - Input params → Output dict")
    print("  - No coordination or validation needed")
    print("  - Can be run independently via CLI or API")
    print("=" * 60)


# =============================================================================
# How to Register: For use with Workflows or CLI
# =============================================================================

def register_pipelines(registry):
    """
    Register these pipelines with the registry.
    
    After registration, they can be:
    - Called via CLI: spine run prices.fetch --symbol AAPL
    - Used in Workflows: Step.pipeline("fetch", "prices.fetch")
    """
    registry.register(FetchPricesPipeline)
    registry.register(ParseFilePipeline)
    registry.register(StorePricesPipeline)
    registry.register(CalculateMovingAveragePipeline)


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    demo_pipeline_only()
