#!/usr/bin/env python3
"""Run all ecosystem examples.

Usage:
    python examples/ecosystem/run_all.py
"""
import subprocess, sys
from pathlib import Path
from datetime import datetime, timezone

EXAMPLES = [
    ("01_feedspine_pipeline.py", "FeedSpine - Market Data Feed Ingestion"),
    ("02_entityspine_workflow.py", "EntitySpine - SEC Filing Entity Resolution"),
    ("03_genai_spine_tasks.py", "GenAI-Spine - Embeddings and RAG"),
    ("04_document_spine_ingestion.py", "Document-Spine - Document Parsing"),
    ("05_workflow_architecture.py", "Cross-Spine Workflow Orchestration"),
]

def main():
    print("=" * 70)
    print("Spine-Core Ecosystem Examples Runner")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)
    
    examples_dir = Path(__file__).parent
    results = []
    
    for script_name, description in EXAMPLES:
        script_path = examples_dir / script_name
        print(f"\n{'=' * 60}")
        print(f"Running: {description}")
        print("=" * 60)
        
        if not script_path.exists():
            print(f"  [SKIP] File not found")
            results.append((script_name, "SKIP"))
            continue
        
        try:
            result = subprocess.run([sys.executable, str(script_path)], 
                capture_output=True, text=True, timeout=60,
                cwd=script_path.parent.parent.parent)
            if result.returncode == 0:
                print(result.stdout)
                results.append((script_name, "PASS"))
            else:
                print(f"  [FAIL] {result.stderr[:200] if result.stderr else result.stdout[:200]}")
                results.append((script_name, "FAIL"))
        except Exception as e:
            print(f"  [FAIL] {e}")
            results.append((script_name, "FAIL"))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for _, s in results if s == "PASS")
    for script, status in results:
        icon = {"PASS": "[OK]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
        print(f"  {icon} {script}")
    print(f"\nTotal: {len(results)} | Passed: {passed} | Failed: {len(results) - passed}")
    sys.exit(0 if passed == len(results) else 1)

if __name__ == "__main__":
    main()
