#!/usr/bin/env python3
"""EntitySpine Workflow Example - SEC Filing Entity Resolution.

Run: python examples/ecosystem/02_entityspine_workflow.py
"""
import asyncio
from typing import Any

from spine.execution import Dispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor


async def resolve_company_cik(params: dict[str, Any]) -> dict[str, Any]:
    """Resolve company to SEC CIK number."""
    company_name = params.get("company_name", "")
    cik_map = {"APPLE INC": "0000320193", "MICROSOFT CORPORATION": "0000789019"}
    cik = cik_map.get(company_name.upper(), "0000000000")
    return {"company_name": company_name, "cik": cik, "resolved": cik != "0000000000"}


async def fetch_sec_filings(params: dict[str, Any]) -> dict[str, Any]:
    """Fetch SEC filings for a CIK."""
    cik = params.get("cik", "")
    filings = [{"accession": f"0001193125-26-00{i}001", "type": "10-K"} for i in range(3)]
    return {"cik": cik, "filings": filings, "count": len(filings)}


async def run_entity_workflow(params: dict[str, Any]) -> dict[str, Any]:
    """Full entity resolution workflow."""
    company_name = params.get("company_name", "Apple Inc")
    resolution = await resolve_company_cik({"company_name": company_name})
    if not resolution["resolved"]:
        return {"status": "failed", "error": f"Could not resolve {company_name}"}
    filings = await fetch_sec_filings({"cik": resolution["cik"]})
    return {"workflow": "entity_resolution", "status": "completed",
            "cik": resolution["cik"], "filings_found": filings["count"]}


async def main():
    print("=" * 70)
    print("EntitySpine Workflow Example")
    print("Using spine-core Unified Execution Contract")
    print("=" * 70)
    
    handlers = {
        "task:resolve_company_cik": resolve_company_cik,
        "task:fetch_sec_filings": fetch_sec_filings,
        "workflow:entity_resolution": run_entity_workflow,
    }
    
    registry = HandlerRegistry()
    registry.register("task", "resolve_company_cik", resolve_company_cik, tags={"domain": "entityspine"})
    registry.register("task", "fetch_sec_filings", fetch_sec_filings, tags={"domain": "entityspine"})
    registry.register("workflow", "entity_resolution", run_entity_workflow, tags={"domain": "entityspine"})
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    print("\n[1] Task: resolve_company_cik")
    run_id = await dispatcher.submit_task("resolve_company_cik", {"company_name": "Microsoft Corporation"})
    run = await dispatcher.get_run(run_id)
    print(f"  Status: {run.status.value}, CIK: {run.result.get('cik')}")
    
    print("\n[2] Workflow: entity_resolution")
    wf_id = await dispatcher.submit_workflow("entity_resolution", {"company_name": "Apple Inc"})
    wf = await dispatcher.get_run(wf_id)
    print(f"  Status: {wf.status.value}, CIK: {wf.result.get('cik')}, Filings: {wf.result.get('filings_found')}")
    
    print("\n" + "=" * 70)
    print("[OK] EntitySpine Example Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
