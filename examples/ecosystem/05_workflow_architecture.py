#!/usr/bin/env python3
"""Workflow Architecture Example - Cross-Spine Orchestration.

Run: python examples/ecosystem/05_workflow_architecture.py
"""
import asyncio
from typing import Any

from spine.execution import Dispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor


async def resolve_entity(params): return {"step": "resolve_entity", "cik": "0000320193"}
async def fetch_filings(params): return {"step": "fetch_filings", "count": 3}
async def parse_document(params): return {"step": "parse_document", "pages": 85}
async def generate_embeddings(params): return {"step": "generate_embeddings", "vectors": 500}
async def index_for_search(params): return {"step": "index_for_search", "indexed": True}
async def send_notification(params): return {"step": "send_notification", "sent": True}


async def run_cross_spine_workflow(params: dict[str, Any]) -> dict[str, Any]:
    """Full cross-spine workflow: Entity -> Filing -> Parse -> Embed -> Index."""
    ticker = params.get("ticker", "AAPL")
    
    entity = await resolve_entity({"ticker": ticker})
    filings = await fetch_filings({"cik": entity["cik"]})
    parsed = await parse_document({"filing": filings})
    embeddings = await generate_embeddings({"text_length": parsed["pages"] * 3000})
    indexed = await index_for_search({"document_id": f"{ticker}_10K"})
    notification = await send_notification({"message": f"Processed {ticker}"})
    
    return {
        "workflow": "cross_spine_filing_ingestion",
        "status": "completed",
        "ticker": ticker,
        "summary": {"pages": parsed["pages"], "vectors": embeddings["vectors"], "indexed": indexed["indexed"]},
        "steps_completed": 6,
    }


async def main():
    print("=" * 70)
    print("Workflow Architecture Example")
    print("Cross-Spine Orchestration with Unified Execution Contract")
    print("=" * 70)
    
    handlers = {
        "step:resolve_entity": resolve_entity,
        "step:fetch_filings": fetch_filings,
        "step:parse_document": parse_document,
        "step:generate_embeddings": generate_embeddings,
        "step:index_for_search": index_for_search,
        "step:send_notification": send_notification,
        "workflow:cross_spine_filing_ingestion": run_cross_spine_workflow,
    }
    
    registry = HandlerRegistry()
    registry.register("step", "resolve_entity", resolve_entity, tags={"spine": "entityspine"})
    registry.register("step", "fetch_filings", fetch_filings, tags={"spine": "entityspine"})
    registry.register("step", "parse_document", parse_document, tags={"spine": "document-spine"})
    registry.register("step", "generate_embeddings", generate_embeddings, tags={"spine": "genai-spine"})
    registry.register("step", "index_for_search", index_for_search, tags={"spine": "document-spine"})
    registry.register("step", "send_notification", send_notification, tags={"spine": "feedspine"})
    registry.register("workflow", "cross_spine_filing_ingestion", run_cross_spine_workflow, tags={"type": "orchestration"})
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    print("\n[1] Cross-Spine Workflow: SEC Filing Ingestion")
    print("  Orchestrating: EntitySpine -> Document-Spine -> GenAI-Spine -> FeedSpine")
    
    wf_id = await dispatcher.submit_workflow("cross_spine_filing_ingestion", {"ticker": "NVDA"}, 
        correlation_id="batch_2026Q1")
    wf = await dispatcher.get_run(wf_id)
    
    print(f"\n  Status: {wf.status.value}")
    if wf.result:
        print(f"  Ticker: {wf.result.get('ticker')}")
        summary = wf.result.get("summary", {})
        print(f"  Pages: {summary.get('pages')}, Vectors: {summary.get('vectors')}, Indexed: {summary.get('indexed')}")
        print(f"  Steps: {wf.result.get('steps_completed')}")
    
    print("\n[2] Handler Discovery by Spine")
    spines = {}
    for kind, name in registry.list_handlers():
        meta = registry.get_metadata(kind, name) or {}
        spine = meta.get("tags", {}).get("spine", "core")
        spines.setdefault(spine, []).append(f"{kind}:{name}")
    
    for spine, handlers_list in sorted(spines.items()):
        print(f"  {spine}: {len(handlers_list)} handlers")
    
    print("\n" + "=" * 70)
    print("[OK] Workflow Architecture Example Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
