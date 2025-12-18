#!/usr/bin/env python3
"""WorkflowPackager — pack workflows into portable .pyz archives.

================================================================================
WHY WorkflowPackager?
================================================================================

Moving a workflow from a dev machine to production requires packaging all
its handler code into a single portable artifact.  ``WorkflowPackager``
creates PEP 441 ``.pyz`` archives containing:

- The serialized workflow definition
- Extracted handler source code (via ``inspect.getsource()``)
- A ``PackageManifest`` with metadata (step count, python version, tags)

::

    Workflow + handlers
        │
        ▼
    ┌──────────────────┐
    │ WorkflowPackager  │
    │   .package()      │
    └──────────────────┘
        │
        ▼
    output.pyz
    ├── __main__.py         (entrypoint)
    ├── workflow.json        (serialized workflow)
    ├── handlers/            (extracted handler code)
    └── manifest.json        (PackageManifest)

NOTE: The packager currently has limitations:
- No dependency management (requirements.txt not generated)
- No cross-platform testing
- Handlers using closures or lambdas cannot be packaged


================================================================================
WHAT THIS EXAMPLE DEMONSTRATES
================================================================================

::

    1  Package a simple workflow into a .pyz archive
    2  Inspect the archive metadata (PackageManifest)
    3  Unpack an archive to a directory
    4  Check if a step can be packaged (can_package_step)
    5  Verify round-trip: pack → inspect → unpack


================================================================================
RUN IT
================================================================================

::

    python examples/02_execution/23_workflow_packager.py

See Also:
    - ``19_local_process_adapter.py`` — Run packaged workflows locally
    - ``docs/architecture/WORKFLOW_PACKAGER_AUDIT.md`` — Known gaps
    - ``src/spine/execution/packaging/packager.py`` — Implementation
"""

import tempfile
from pathlib import Path

from spine.orchestration.workflow import Workflow, Step
from spine.execution.packaging import WorkflowPackager, PackageManifest


# Define some handler functions that can be packaged
# (must be top-level functions, not closures or lambdas)

def extract_handler(context):
    """Extract raw data from source."""
    print("  [extract] Reading from source...")
    return {"records": 100}


def transform_handler(context):
    """Transform and clean data."""
    print("  [transform] Cleaning records...")
    return {"cleaned": 95}


def load_handler(context):
    """Load data into destination."""
    print("  [load] Writing to destination...")
    return {"loaded": 95}


def _build_test_workflow():
    """Build a simple ETL workflow for packaging tests."""
    steps = [
        Step.lambda_(name="extract", handler=extract_handler),
        Step.lambda_(name="transform", handler=transform_handler, depends_on=["extract"]),
        Step.lambda_(name="load", handler=load_handler, depends_on=["transform"]),
    ]
    wf = Workflow(name="etl-pipeline", steps=steps, version=1)
    return wf


# ── Section 1: Package a workflow ─────────────────────────────────────────

def demo_package():
    """Package a workflow into a .pyz archive."""
    print("=" * 70)
    print("SECTION 1 — Package Workflow into .pyz Archive")
    print("=" * 70)

    packager = WorkflowPackager()
    wf = _build_test_workflow()

    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "etl_pipeline.pyz"
        archive_path, manifest = packager.package(wf, output=output)

        print(f"  Archive:       {archive_path}")
        print(f"  Size:          {archive_path.stat().st_size} bytes")
        print(f"  Exists:        {archive_path.exists()}")
        print(f"  Suffix:        {archive_path.suffix}")

        assert archive_path.exists()
        assert archive_path.suffix == ".pyz"
        print("  ✓ Archive created\n")

        return archive_path, manifest


# ── Section 2: Inspect archive metadata ───────────────────────────────────

def demo_inspect(archive_path):
    """Read the PackageManifest from an existing archive."""
    print("=" * 70)
    print("SECTION 2 — Inspect Archive (PackageManifest)")
    print("=" * 70)

    packager = WorkflowPackager()
    manifest: PackageManifest = packager.inspect(archive_path)

    print(f"  workflow_name:    {manifest.workflow_name}")
    print(f"  workflow_version: {manifest.workflow_version}")
    print(f"  step_count:       {manifest.step_count}")
    print(f"  packaged_at:      {manifest.packaged_at}")
    print(f"  handler_files:    {manifest.handler_files}")
    print(f"  python_version:   {manifest.python_version}")
    print(f"  warnings:         {manifest.warnings}")
    print(f"  tags:             {manifest.tags}")

    assert manifest.workflow_name == "etl-pipeline"
    assert manifest.step_count == 3
    print("  ✓ Manifest inspected\n")


# ── Section 3: Unpack archive ─────────────────────────────────────────────

def demo_unpack(archive_path):
    """Unpack a .pyz archive to a directory."""
    print("=" * 70)
    print("SECTION 3 — Unpack Archive to Directory")
    print("=" * 70)

    packager = WorkflowPackager()

    with tempfile.TemporaryDirectory() as dest:
        dest_path = Path(dest) / "unpacked"
        result_path = packager.unpack(archive_path, destination=dest_path)

        print(f"  Unpacked to: {result_path}")
        print(f"  Contents:")
        for item in sorted(result_path.rglob("*")):
            rel = item.relative_to(result_path)
            prefix = "  📁 " if item.is_dir() else "  📄 "
            print(f"    {prefix}{rel}")

        print("  ✓ Archive unpacked\n")


# ── Section 4: Check if step can be packaged ──────────────────────────────

def demo_can_package():
    """Check which steps can be packaged (source extractable)."""
    print("=" * 70)
    print("SECTION 4 — Can Package Step?")
    print("=" * 70)

    packager = WorkflowPackager()

    # Normal function — should be packageable
    step_ok = Step.lambda_(name="good-step", handler=extract_handler)
    can_ok, reason_ok = packager.can_package_step(step_ok)
    print(f"  Named function: can_package={can_ok}, reason='{reason_ok}'")

    # Lambda — cannot extract source reliably
    step_lambda = Step.lambda_(name="lambda-step", handler=lambda ctx: ctx)
    can_lambda, reason_lambda = packager.can_package_step(step_lambda)
    print(f"  Lambda:         can_package={can_lambda}, reason='{reason_lambda}'")

    assert can_ok is True
    print("  ✓ Packaging checks work\n")


# ── Section 5: Full round-trip ────────────────────────────────────────────

def demo_round_trip():
    """Pack → inspect → unpack round-trip verification."""
    print("=" * 70)
    print("SECTION 5 — Full Round-Trip (Pack → Inspect → Unpack)")
    print("=" * 70)

    packager = WorkflowPackager()
    wf = _build_test_workflow()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Pack
        archive, manifest = packager.package(wf, output=tmpdir / "pipeline.pyz")
        print(f"  1. Packed:     {archive.name} ({manifest.step_count} steps)")

        # Inspect
        manifest2 = packager.inspect(archive)
        print(f"  2. Inspected:  {manifest2.workflow_name} v{manifest2.workflow_version}")
        assert manifest2.workflow_name == manifest.workflow_name

        # Unpack
        dest = packager.unpack(archive, destination=tmpdir / "unpacked")
        file_count = len(list(dest.rglob("*")))
        print(f"  3. Unpacked:   {file_count} files to {dest.name}/")

        print("  ✓ Round-trip complete\n")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Sections 1-3 share an archive, so use a temp directory
    with tempfile.TemporaryDirectory() as session_tmp:
        # Section 1: Package
        packager = WorkflowPackager()
        wf = _build_test_workflow()
        archive_path, manifest = packager.package(
            wf, output=Path(session_tmp) / "example.pyz",
        )
        print("=" * 70)
        print("SECTION 1 — Package Workflow into .pyz Archive")
        print("=" * 70)
        print(f"  Archive: {archive_path}")
        print(f"  Size:    {archive_path.stat().st_size} bytes")
        print("  ✓ Archive created\n")

        # Section 2: Inspect
        demo_inspect(archive_path)

        # Section 3: Unpack
        demo_unpack(archive_path)

    # Section 4: Can-package check (independent)
    demo_can_package()

    # Section 5: Round-trip (independent)
    demo_round_trip()

    print("=" * 70)
    print("ALL SECTIONS PASSED ✓")
    print("=" * 70)
