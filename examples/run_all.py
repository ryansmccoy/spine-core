#!/usr/bin/env python3
"""Run all spine-core examples and verify they work.

This script discovers and runs all examples in the organized folder structure.

Run: python examples/run_all.py
"""
import subprocess
import sys
from pathlib import Path

# Example directories in order
EXAMPLE_DIRS = [
    "01_basics",
    "02_executors",
    "03_workflows",
    "04_integration",
]


def discover_examples() -> list[tuple[str, Path]]:
    """Discover all example files in organized directories."""
    examples_root = Path(__file__).parent
    examples = []
    
    for dir_name in EXAMPLE_DIRS:
        dir_path = examples_root / dir_name
        if dir_path.exists():
            # Get all Python files in order
            py_files = sorted(dir_path.glob("*.py"))
            for py_file in py_files:
                if py_file.name != "__init__.py":
                    examples.append((f"{dir_name}/{py_file.name}", py_file))
    
    return examples


def run_example(name: str, path: Path) -> bool:
    """Run a single example and return success status."""
    print(f"\n{'=' * 60}")
    print(f"Running: {name}")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=path.parent.parent,  # Run from examples/
        )
        
        if result.returncode == 0:
            # Show last few lines of output
            lines = result.stdout.strip().split("\n")
            if len(lines) > 10:
                print("  ...")
            for line in lines[-10:]:
                print(f"  {line}")
            print(f"\n  ✓ PASSED")
            return True
        else:
            print(f"  STDOUT: {result.stdout}")
            print(f"  STDERR: {result.stderr}")
            print(f"\n  ✗ FAILED (exit code {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ TIMEOUT (60s)")
        return False
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
        return False


def main():
    """Run all examples and report results."""
    print("=" * 60)
    print("Spine-Core Examples Runner")
    print("=" * 60)
    
    examples = discover_examples()
    print(f"\nDiscovered {len(examples)} examples:")
    for name, _ in examples:
        print(f"  - {name}")
    
    # Run each example
    results = []
    for name, path in examples:
        success = run_example(name, path)
        results.append((name, success))
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, s in results if s)
    failed = len(results) - passed
    
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {name}")
    
    print(f"\nTotal: {len(results)} | Passed: {passed} | Failed: {failed}")
    
    if failed > 0:
        sys.exit(1)
    
    print("\n[OK] All examples passed!")


if __name__ == "__main__":
    main()
