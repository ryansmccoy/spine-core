#!/usr/bin/env python3
"""Document-Spine Ingestion Example - Document Parsing and Search.

Run: python examples/ecosystem/04_document_spine_ingestion.py
"""
import asyncio
from typing import Any

from spine.execution import Dispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor


async def parse_pdf_document(params: dict[str, Any]) -> dict[str, Any]:
    """Parse PDF and extract text."""
    path = params.get("document_path", "")
    await asyncio.sleep(0.02)
    return {"document_path": path, "page_count": 42, "text_length": 125000}


async def index_to_search(params: dict[str, Any]) -> dict[str, Any]:
    """Index document for full-text search."""
    doc_id = params.get("document_id", "")
    return {"document_id": doc_id, "indexed": True, "index_name": "documents"}


async def full_text_search(params: dict[str, Any]) -> dict[str, Any]:
    """Perform full-text search."""
    query = params.get("query", "")
    results = [{"id": f"doc_{i}", "score": 0.9 - i * 0.1, "title": f"Result {i+1}"} for i in range(5)]
    return {"query": query, "results": results, "total_hits": 127}


async def run_ingestion_pipeline(params: dict[str, Any]) -> dict[str, Any]:
    """Full document ingestion pipeline."""
    path = params.get("document_path", "/docs/report.pdf")
    doc_id = params.get("document_id", "DOC_001")
    parsed = await parse_pdf_document({"document_path": path})
    indexed = await index_to_search({"document_id": doc_id})
    return {"pipeline": "document_ingestion", "status": "completed",
            "document_id": doc_id, "pages": parsed["page_count"], "indexed": indexed["indexed"]}


async def main():
    print("=" * 70)
    print("Document-Spine Ingestion Example")
    print("Using spine-core Unified Execution Contract")
    print("=" * 70)
    
    handlers = {
        "task:parse_pdf_document": parse_pdf_document,
        "task:index_to_search": index_to_search,
        "task:full_text_search": full_text_search,
        "pipeline:document_ingestion": run_ingestion_pipeline,
    }
    
    registry = HandlerRegistry()
    registry.register("task", "parse_pdf_document", parse_pdf_document, tags={"domain": "document"})
    registry.register("task", "index_to_search", index_to_search, tags={"domain": "document"})
    registry.register("task", "full_text_search", full_text_search, tags={"domain": "document"})
    registry.register("pipeline", "document_ingestion", run_ingestion_pipeline, tags={"domain": "document"})
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    print("\n[1] Task: parse_pdf_document")
    run_id = await dispatcher.submit_task("parse_pdf_document", {"document_path": "/filings/AAPL_10K.pdf"})
    run = await dispatcher.get_run(run_id)
    print(f"  Status: {run.status.value}, Pages: {run.result.get('page_count')}")
    
    print("\n[2] Pipeline: document_ingestion")
    p_id = await dispatcher.submit_pipeline("document_ingestion", 
        {"document_path": "/filings/MSFT_10K.pdf", "document_id": "MSFT_10K_2025"})
    p = await dispatcher.get_run(p_id)
    print(f"  Status: {p.status.value}, Doc: {p.result.get('document_id')}, Indexed: {p.result.get('indexed')}")
    
    print("\n[3] Task: full_text_search")
    s_id = await dispatcher.submit_task("full_text_search", {"query": "revenue growth"}, priority="realtime")
    s = await dispatcher.get_run(s_id)
    print(f"  Status: {s.status.value}, Hits: {s.result.get('total_hits')}")
    
    print("\n" + "=" * 70)
    print("[OK] Document-Spine Example Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
