#!/usr/bin/env python3
"""Auto-generate examples/README.md from the ExampleRegistry.

Scans numbered example directories, extracts docstring metadata via AST,
and produces a Markdown README with category tables, learning path, and
cross-references.  The generated README should NEVER be hand-edited — run
this script again after adding/removing examples.

Usage::

    python examples/generate_readme.py                 # writes README.md
    python examples/generate_readme.py --check         # exit 1 if stale
    python examples/generate_readme.py --stdout        # print to stdout
    python examples/generate_readme.py --project-name "My Project"

This script is designed to be **identical** across all spine ecosystem
projects.  Only the auto-detected project name changes.
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure _registry.py is importable
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))
from _registry import ExampleInfo, ExampleRegistry  # noqa: E402


# ---------------------------------------------------------------------------
# Category description extraction
# ---------------------------------------------------------------------------

_CATEGORY_DESCRIPTIONS: dict[str, str] = {}


def _category_description(category: str, examples: list[ExampleInfo]) -> str:
    """Best-effort description for a category.

    Priority:
    1. __init__.py module docstring (if present)
    2. First example's title
    3. Prettified directory name
    """
    cat_dir = _SCRIPT_DIR / category
    init_py = cat_dir / "__init__.py"
    if init_py.exists():
        try:
            import ast as _ast

            tree = _ast.parse(init_py.read_text(encoding="utf-8-sig"))
            doc = _ast.get_docstring(tree)
            if doc:
                return doc.strip().split("\n")[0].strip()
        except Exception:
            pass

    # Fall back to prettified name
    pretty = re.sub(r"^\d+_", "", category).replace("_", " ").title()
    return pretty


# ---------------------------------------------------------------------------
# Docstring section extraction
# ---------------------------------------------------------------------------

_SECTION_RE = re.compile(
    r"^(Demonstrates|Architecture|Key Concepts|See Also|Run|Requires|Expected Output):\s*$",
    re.MULTILINE,
)


def _extract_sections(description: str) -> dict[str, str]:
    """Parse structured docstring into named sections."""
    sections: dict[str, str] = {}
    parts = _SECTION_RE.split(description)
    # parts alternates: [preamble, section_name, section_body, ...]
    for i in range(1, len(parts) - 1, 2):
        key = parts[i].strip()
        body = parts[i + 1].strip()
        sections[key] = body
    return sections


def _first_sentence(text: str) -> str:
    """Extract the first sentence from a docstring title line."""
    # Remove em-dash prefix pattern: "Title — description"
    line = text.strip().split("\n")[0]
    # Trim trailing period
    return line.rstrip(".")


# ---------------------------------------------------------------------------
# Project name detection
# ---------------------------------------------------------------------------


def _detect_project_name(examples_dir: Path) -> str:
    """Try to detect the project name from pyproject.toml or directory name."""
    project_root = examples_dir.parent

    # Try pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            text = pyproject.read_text(encoding="utf-8")
            m = re.search(r'^\s*name\s*=\s*"([^"]+)"', text, re.MULTILINE)
            if m:
                return m.group(1).replace("-", " ").replace("_", " ").title()
        except Exception:
            pass

    # Fall back to directory name
    return project_root.name.replace("-", " ").replace("_", " ").title()


# ---------------------------------------------------------------------------
# README renderer
# ---------------------------------------------------------------------------


def generate_readme(
    registry: ExampleRegistry,
    project_name: str | None = None,
) -> str:
    """Render the full README.md content from registry metadata."""
    if project_name is None:
        project_name = _detect_project_name(registry.root)

    lines: list[str] = []

    def w(text: str = "") -> None:
        lines.append(text)

    total = len(registry.examples)
    cats = registry.categories

    # Header
    w(f"# {project_name} — Examples")
    w()
    w(
        f"> **{total} examples** across **{len(cats)} categories** — "
        f"auto-generated from docstrings."
    )
    w(f"> Regenerate: `python examples/generate_readme.py`")
    w()
    w("---")
    w()

    # Quick Start
    w("## Quick Start")
    w()
    w("```bash")
    w("# Run ALL examples (auto-discovered, isolated subprocesses)")
    w("python examples/run_all.py")
    w()
    first = registry.examples[0] if registry.examples else None
    if first:
        rel = first.path.relative_to(registry.root.parent)
        w(f"# Run a single example")
        w(f"python {rel.as_posix()}")
    w("```")
    w()

    # Learning Path
    w("## Learning Path")
    w()
    w(
        "Categories are numbered by conceptual dependency — start at `01` and "
        "work forward."
    )
    w()
    w("| # | Category | Examples | Description |")
    w("|---|----------|---------|-------------|")
    for cat in cats:
        cat_examples = registry.by_category(cat)
        num = re.match(r"(\d+)", cat)
        num_str = num.group(1) if num else "?"
        desc = _category_description(cat, cat_examples)
        pretty_name = f"`{cat}/`"
        w(f"| {num_str} | {pretty_name} | {len(cat_examples)} | {desc} |")
    w()

    # Per-category detail
    w("## Examples by Category")
    w()
    for cat in cats:
        cat_examples = registry.by_category(cat)
        desc = _category_description(cat, cat_examples)
        pretty_cat = re.sub(r"^\d+_", "", cat).replace("_", " ").title()
        w(f"### {cat} — {pretty_cat}")
        w()
        w("| # | Example | Description |")
        w("|---|---------|-------------|")
        for ex in cat_examples:
            rel_path = f"{cat}/{ex.path.name}"
            title = _first_sentence(ex.title) if ex.title else ex.path.stem
            order_str = f"{ex.order:02d}"
            w(f"| {order_str} | [{ex.path.name}]({rel_path}) | {title} |")
        w()

    # Architecture diagrams (extracted from docstrings)
    arch_examples = []
    for ex in registry.examples:
        if ex.description:
            sections = _extract_sections(ex.description)
            if "Architecture" in sections:
                arch_examples.append((ex, sections["Architecture"]))

    if arch_examples:
        w("## Architecture Highlights")
        w()
        w(
            "These examples include architecture diagrams — key for "
            "understanding data flow and component interaction."
        )
        w()
        for ex, arch_text in arch_examples:
            w(f"### {ex.title}")
            w(f"*From [{ex.path.name}]({ex.category}/{ex.path.name})*")
            w()
            # Check if it looks like mermaid
            if "```mermaid" in arch_text or "graph " in arch_text:
                if not arch_text.startswith("```"):
                    w("```mermaid")
                    w(arch_text)
                    w("```")
                else:
                    w(arch_text)
            else:
                w("```")
                w(arch_text)
                w("```")
            w()

    # Prerequisites
    requires: list[str] = []
    for ex in registry.examples:
        if ex.description:
            sections = _extract_sections(ex.description)
            if "Requires" in sections:
                req = sections["Requires"].strip()
                if req and req not in requires:
                    requires.append(req)

    if requires:
        w("## Prerequisites")
        w()
        w("Some examples require optional dependencies:")
        w()
        w("```bash")
        for req in requires:
            w(req)
        w("```")
        w()

    # Infrastructure
    w("## Infrastructure")
    w()
    w("| File | Purpose |")
    w("|------|---------|")
    w("| [`_registry.py`](_registry.py) | Auto-discovers examples via AST — no hardcoded lists |")
    w("| [`run_all.py`](run_all.py) | Runs every example as an isolated subprocess (60s timeout) |")
    w("| [`generate_readme.py`](generate_readme.py) | Generates this README from docstrings |")
    w()
    mock_dir = registry.root / "mock"
    if mock_dir.exists():
        w(
            "The [`mock/`](mock/) directory contains shared test fixtures "
            "and mock implementations used by integration examples."
        )
        w()

    # Footer
    w("---")
    w()
    w(
        f"*Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d')} "
        f"from {total} examples across {len(cats)} categories.*"
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-generate examples/README.md from ExampleRegistry."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the current README.md is stale (CI mode).",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print to stdout instead of writing README.md.",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Override the auto-detected project name.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Path to the examples/ directory (default: directory containing this script).",
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else _SCRIPT_DIR
    registry = ExampleRegistry(root=root)

    content = generate_readme(registry, project_name=args.project_name)

    if args.stdout:
        print(content, end="")
        return

    readme_path = root / "README.md"

    if args.check:
        if readme_path.exists():
            existing = readme_path.read_text(encoding="utf-8")
            # Compare ignoring the generation timestamp line
            def _strip_timestamp(t: str) -> str:
                return re.sub(r"\*Generated on .+?\*", "", t)

            if _strip_timestamp(existing) == _strip_timestamp(content):
                print("✓ README.md is up to date.")
                sys.exit(0)
            else:
                print("✗ README.md is stale. Run: python examples/generate_readme.py")
                sys.exit(1)
        else:
            print("✗ README.md does not exist. Run: python examples/generate_readme.py")
            sys.exit(1)

    readme_path.write_text(content, encoding="utf-8")
    print(f"✓ Generated {readme_path} ({total} examples, {len(registry.categories)} categories)")


if __name__ == "__main__":
    # Quick summary variables for the final print
    _reg = ExampleRegistry(root=_SCRIPT_DIR)
    total = len(_reg.examples)
    main()
