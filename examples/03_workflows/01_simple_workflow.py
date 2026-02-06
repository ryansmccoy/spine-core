#!/usr/bin/env python3
"""Simple Workflow - Basic multi-step orchestration.

A workflow is a series of tasks that execute in order, where
later steps can depend on results from earlier steps.

Run: python examples/03_workflows/01_simple_workflow.py
"""
import asyncio
from spine.execution import Dispatcher, HandlerRegistry, WorkSpec
from spine.execution.executors import MemoryExecutor


# === Step handlers ===

async def step_validate_input(params: dict) -> dict:
    """Step 1: Validate input parameters."""
    required = ["ticker", "start_date"]
    missing = [k for k in required if k not in params]
    
    if missing:
        raise ValueError(f"Missing required params: {missing}")
    
    return {
        "valid": True,
        "ticker": params["ticker"].upper(),
        "start_date": params["start_date"],
    }


async def step_fetch_data(params: dict) -> dict:
    """Step 2: Fetch data (simulated)."""
    ticker = params.get("ticker", "UNKNOWN")
    
    # Simulate fetching
    await asyncio.sleep(0.01)
    
    return {
        "ticker": ticker,
        "data": [
            {"date": "2024-01-01", "close": 150.0},
            {"date": "2024-01-02", "close": 152.5},
            {"date": "2024-01-03", "close": 151.0},
        ],
    }


async def step_analyze(params: dict) -> dict:
    """Step 3: Analyze the data."""
    data = params.get("data", [])
    
    if not data:
        return {"error": "No data to analyze"}
    
    closes = [d["close"] for d in data]
    
    return {
        "count": len(data),
        "min": min(closes),
        "max": max(closes),
        "avg": sum(closes) / len(closes),
    }


async def step_generate_report(params: dict) -> dict:
    """Step 4: Generate final report."""
    ticker = params.get("ticker", "UNKNOWN")
    analysis = params.get("analysis", {})
    
    return {
        "report": f"Analysis for {ticker}",
        "summary": {
            "data_points": analysis.get("count", 0),
            "price_range": f"${analysis.get('min', 0):.2f} - ${analysis.get('max', 0):.2f}",
            "average": f"${analysis.get('avg', 0):.2f}",
        },
    }


async def main():
    print("=" * 60)
    print("Simple Workflow")
    print("=" * 60)
    
    # === Setup ===
    registry = HandlerRegistry()
    registry.register("task", "validate_input", step_validate_input)
    registry.register("task", "fetch_data", step_fetch_data)
    registry.register("task", "analyze", step_analyze)
    registry.register("task", "generate_report", step_generate_report)
    
    handlers = {
        "task:validate_input": step_validate_input,
        "task:fetch_data": step_fetch_data,
        "task:analyze": step_analyze,
        "task:generate_report": step_generate_report,
    }
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    # === Workflow execution ===
    print("\n[Workflow] Analysis Pipeline")
    
    initial_params = {
        "ticker": "aapl",
        "start_date": "2024-01-01",
    }
    
    # Step 1: Validate
    print("\n  Step 1: Validating input...")
    run1 = await dispatcher.submit_task("validate_input", initial_params)
    result1 = (await dispatcher.get_run(run1)).result
    print(f"    Valid: {result1['valid']}, Ticker: {result1['ticker']}")
    
    # Step 2: Fetch (uses result from step 1)
    print("\n  Step 2: Fetching data...")
    run2 = await dispatcher.submit_task("fetch_data", {"ticker": result1["ticker"]})
    result2 = (await dispatcher.get_run(run2)).result
    print(f"    Fetched {len(result2['data'])} data points")
    
    # Step 3: Analyze (uses result from step 2)
    print("\n  Step 3: Analyzing...")
    run3 = await dispatcher.submit_task("analyze", {"data": result2["data"]})
    result3 = (await dispatcher.get_run(run3)).result
    print(f"    Min: ${result3['min']:.2f}, Max: ${result3['max']:.2f}, Avg: ${result3['avg']:.2f}")
    
    # Step 4: Report (uses results from multiple steps)
    print("\n  Step 4: Generating report...")
    run4 = await dispatcher.submit_task("generate_report", {
        "ticker": result1["ticker"],
        "analysis": result3,
    })
    result4 = (await dispatcher.get_run(run4)).result
    
    print(f"\n  === {result4['report']} ===")
    for key, value in result4["summary"].items():
        print(f"    {key}: {value}")
    
    # === Workflow as a helper function ===
    print("\n[Helper] Workflow as reusable function")
    
    async def run_analysis_workflow(ticker: str, start_date: str) -> dict:
        """Encapsulate the workflow as a reusable function."""
        # Validate
        r1 = await dispatcher.submit_task("validate_input", {
            "ticker": ticker,
            "start_date": start_date,
        })
        validated = (await dispatcher.get_run(r1)).result
        
        # Fetch
        r2 = await dispatcher.submit_task("fetch_data", {"ticker": validated["ticker"]})
        fetched = (await dispatcher.get_run(r2)).result
        
        # Analyze
        r3 = await dispatcher.submit_task("analyze", {"data": fetched["data"]})
        analysis = (await dispatcher.get_run(r3)).result
        
        # Report
        r4 = await dispatcher.submit_task("generate_report", {
            "ticker": validated["ticker"],
            "analysis": analysis,
        })
        return (await dispatcher.get_run(r4)).result
    
    # Run workflow multiple times
    for ticker in ["MSFT", "GOOG"]:
        report = await run_analysis_workflow(ticker, "2024-01-01")
        print(f"  {report['report']}: {report['summary']['average']}")
    
    print("\n" + "=" * 60)
    print("[OK] Simple Workflow Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
