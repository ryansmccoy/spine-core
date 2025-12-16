"""Example auto-discovery registry.

Adapts the filesystem convention (numbered dirs + numbered scripts with
docstrings) into a typed, queryable catalog.  No example files need
modification — the registry reads metadata from the filesystem and
module docstrings.

Usage::

    from examples._registry import ExampleRegistry

    registry = ExampleRegistry()

    # All examples, auto-discovered
    for ex in registry.examples:
        print(ex.category, ex.name, ex.title)

    # Filtered
    for ex in registry.by_category("10_operations"):
        print(ex)

    # As pytest params
    params = registry.as_pytest_params()
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ExampleInfo:
    """Metadata for a single example script.

    Attributes:
        category: Directory name, e.g. ``"01_core"``.
        name: Relative display path, e.g. ``"01_core/01_result_pattern"``.
        path: Absolute path to the ``.py`` file.
        title: First line of the module docstring (or filename fallback).
        description: Full module docstring (stripped).
        order: Numeric prefix parsed from the filename (for sorting).
    """

    category: str
    name: str
    path: Path
    title: str = ""
    description: str = ""
    order: int = 0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_NUM_PREFIX = re.compile(r"^(\d+)_")


class ExampleRegistry:
    """Auto-discovers examples from a root directory.

    Discovery rules:

    1. Scan for subdirectories matching ``\\d+_*`` (e.g. ``01_core``).
    2. Within each, collect ``*.py`` files excluding ``__init__.py``
       and files starting with ``_``.
    3. Extract metadata from each file's module docstring via
       :func:`ast.parse` (no imports executed).
    4. Sort categories by numeric prefix, files by numeric prefix
       within each category.

    Parameters:
        root: Path to the ``examples/`` directory.  Defaults to the
            directory containing this module.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or Path(__file__).parent
        self._examples: list[ExampleInfo] | None = None

    # -- public API --------------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    @property
    def examples(self) -> list[ExampleInfo]:
        """All discovered examples, sorted by category then order."""
        if self._examples is None:
            self._examples = list(self._discover())
        return self._examples

    @property
    def categories(self) -> list[str]:
        """Sorted unique category names."""
        seen: dict[str, None] = {}
        for ex in self.examples:
            seen.setdefault(ex.category, None)
        return list(seen)

    def by_category(self, category: str) -> list[ExampleInfo]:
        """Return examples in a single category."""
        return [e for e in self.examples if e.category == category]

    def as_pytest_params(self) -> list[tuple[str, Path]]:
        """Return ``(name, path)`` tuples ready for ``@pytest.mark.parametrize``."""
        return [(e.name, e.path) for e in self.examples]

    def refresh(self) -> None:
        """Force re-discovery (useful after adding files)."""
        self._examples = None

    # -- discovery ---------------------------------------------------------

    def _discover(self) -> Iterator[ExampleInfo]:
        """Walk numbered subdirectories and yield :class:`ExampleInfo`."""
        category_dirs = sorted(
            d for d in self._root.iterdir()
            if d.is_dir() and _NUM_PREFIX.match(d.name)
        )

        for cat_dir in category_dirs:
            py_files = sorted(
                f for f in cat_dir.glob("*.py")
                if f.name != "__init__.py" and not f.name.startswith("_")
            )
            for py_file in py_files:
                yield self._build_info(cat_dir.name, py_file)

    def _build_info(self, category: str, path: Path) -> ExampleInfo:
        """Build :class:`ExampleInfo` for a single file."""
        stem = path.stem
        m = _NUM_PREFIX.match(stem)
        order = int(m.group(1)) if m else 0

        title, description = _extract_docstring(path)
        if not title:
            title = stem.replace("_", " ").strip()

        return ExampleInfo(
            category=category,
            name=f"{category}/{stem}",
            path=path,
            title=title,
            description=description,
            order=order,
        )

    def __len__(self) -> int:
        return len(self.examples)

    def __iter__(self) -> Iterator[ExampleInfo]:
        return iter(self.examples)

    def __repr__(self) -> str:
        return (
            f"ExampleRegistry(root={self._root!r}, "
            f"categories={len(self.categories)}, "
            f"examples={len(self)})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_docstring(path: Path) -> tuple[str, str]:
    """Extract the module docstring from a Python file via AST.

    Returns ``(first_line, full_docstring)``; both empty on failure.
    """
    try:
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        docstring = ast.get_docstring(tree)
        if docstring:
            first_line = docstring.strip().split("\n")[0].strip()
            return first_line, docstring.strip()
    except Exception:
        pass
    return "", ""
