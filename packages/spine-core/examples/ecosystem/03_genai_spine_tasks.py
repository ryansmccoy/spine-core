#!/usr/bin/env python3
"""GenAI-Spine Tasks Example - Embeddings and RAG.

Run: python examples/ecosystem/03_genai_spine_tasks.py
"""
import asyncio
from typing import Any
import hashlib

from spine.execution import Dispatcher, HandlerRegistry
from spine.execution.executors import MemoryExecutor


async def generate_embeddings(params: dict[str, Any]) -> dict[str, Any]:
    """Generate embeddings for text chunks."""
    texts = params.get("texts", [])
    model = params.get("model", "text-embedding-3-small")
    await asyncio.sleep(0.02)
    return {"embeddings_count": len(texts), "model": model, "dimension": 1536}


async def semantic_search(params: dict[str, Any]) -> dict[str, Any]:
    """Search vector store."""
    query = params.get("query", "")
    top_k = params.get("top_k", 5)
    results = [{"id": f"doc_{i}", "score": 0.95 - i * 0.1} for i in range(min(top_k, 5))]
    return {"query": query, "results": results, "count": len(results)}


async def run_rag_pipeline(params: dict[str, Any]) -> dict[str, Any]:
    """Full RAG pipeline: chunk -> embed -> index."""
    document = params.get("document", "Sample text")
    chunks = [document[i:i+200] for i in range(0, len(document), 180)]
    embeddings = await generate_embeddings({"texts": chunks})
    return {"pipeline": "rag_indexing", "status": "completed",
            "chunks": len(chunks), "embeddings": embeddings["embeddings_count"]}


async def main():
    print("=" * 70)
    print("GenAI-Spine Tasks Example")
    print("Using spine-core Unified Execution Contract")
    print("=" * 70)
    
    handlers = {
        "task:generate_embeddings": generate_embeddings,
        "task:semantic_search": semantic_search,
        "pipeline:rag_indexing": run_rag_pipeline,
    }
    
    registry = HandlerRegistry()
    registry.register("task", "generate_embeddings", generate_embeddings, tags={"domain": "genai", "gpu": "preferred"})
    registry.register("task", "semantic_search", semantic_search, tags={"domain": "genai"})
    registry.register("pipeline", "rag_indexing", run_rag_pipeline, tags={"domain": "genai"})
    
    executor = MemoryExecutor(handlers=handlers)
    dispatcher = Dispatcher(executor=executor, registry=registry)
    
    print("\n[1] Task: generate_embeddings (GPU lane)")
    run_id = await dispatcher.submit_task("generate_embeddings", 
        {"texts": ["Revenue grew 15%", "Profit margins improved"], "model": "text-embedding-3-small"},
        lane="gpu")
    run = await dispatcher.get_run(run_id)
    print(f"  Status: {run.status.value}, Embeddings: {run.result.get('embeddings_count')}")
    
    print("\n[2] Pipeline: rag_indexing")
    doc = "Apple Inc reported strong Q4 results with revenue of $95 billion. " * 10
    p_id = await dispatcher.submit_pipeline("rag_indexing", {"document": doc})
    p = await dispatcher.get_run(p_id)
    print(f"  Status: {p.status.value}, Chunks: {p.result.get('chunks')}, Embeddings: {p.result.get('embeddings')}")
    
    print("\n[3] Task: semantic_search")
    s_id = await dispatcher.submit_task("semantic_search", {"query": "What was Apple revenue?", "top_k": 3})
    s = await dispatcher.get_run(s_id)
    print(f"  Status: {s.status.value}, Results: {s.result.get('count')}")
    
    print("\n" + "=" * 70)
    print("[OK] GenAI-Spine Example Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
