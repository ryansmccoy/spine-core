"""Parse Doc Headers from Python module docstrings.

Stability: stable
Tier: none
Since: 0.4.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE
Tags: changelog, parser, docstring, ast

Walks a Python source tree, extracts module-level docstrings using
``ast.get_docstring()``, and parses the structured Doc Header block
at the top of each docstring.

Usage::

    from spine.tools.changelog.parse_docstrings import scan_modules

    modules = scan_modules(Path("src/spine"))
    for mod in modules:
        print(f"{mod.module_path}: {mod.header.summary}")
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from .model import (
    VALID_DOC_TYPES,
    VALID_STABILITY,
    VALID_TIER,
    DocHeader,
    DocType,
    ModuleInfo,
    Stability,
    Tier,
    ValidationWarning,
)

logger = logging.getLogger(__name__)

# Header field names we recognize (lowercase)
_HEADER_FIELDS = frozenset({
    "stability", "tier", "since", "dependencies", "doc-types", "tags",
})


def parse_doc_header(
    docstring: str,
    *,
    source: str = "<unknown>",
) -> tuple[DocHeader, list[ValidationWarning]]:
    """Parse a Doc Header from a module docstring.

    Args:
        docstring: The raw docstring text.
        source: File path for warning messages.

    Returns:
        Tuple of (DocHeader, list of validation warnings).
    """
    if not docstring or not docstring.strip():
        return DocHeader(summary="", raw=docstring or ""), []

    lines = docstring.strip().splitlines()
    summary = lines[0].strip()

    field_map: dict[str, str] = {}
    body_start = 1
    warns: list[ValidationWarning] = []

    # Skip blank line after summary
    if len(lines) > 1 and not lines[1].strip():
        body_start = 2

    # Parse key: value lines until blank line or non-header line
    for i in range(body_start, len(lines)):
        line = lines[i].strip()
        if not line:
            # Blank line terminates header block
            body_start = i + 1
            break
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            key, _, value = line.partition(":")
            key_lower = key.strip().lower()
            if key_lower in _HEADER_FIELDS:
                field_map[key_lower] = value.strip()
            else:
                # Not a recognized header field — this is body content
                body_start = i
                break
        else:
            # Not a header line — body starts here
            body_start = i
            break
    else:
        # Exhausted all lines in header parsing
        body_start = len(lines)

    body = "\n".join(lines[body_start:]).strip()

    # Parse stability
    stability = Stability.STABLE
    if "stability" in field_map:
        val = field_map["stability"].lower()
        if val in VALID_STABILITY:
            stability = Stability(val)
        else:
            warns.append(ValidationWarning(
                source=source, field="Stability", value=val,
                message=f"Unknown stability '{val}', valid: {sorted(VALID_STABILITY)}",
            ))

    # Parse tier
    tier = Tier.NONE
    if "tier" in field_map:
        val = field_map["tier"].lower()
        if val in VALID_TIER:
            tier = Tier(val)
        else:
            warns.append(ValidationWarning(
                source=source, field="Tier", value=val,
                message=f"Unknown tier '{val}', valid: {sorted(VALID_TIER)}",
            ))

    # Parse since
    since = field_map.get("since")

    # Parse dependencies
    dependencies = field_map.get("dependencies", "stdlib-only")

    # Parse doc-types
    doc_types: list[DocType] = []
    if "doc-types" in field_map:
        raw_types = [t.strip().upper() for t in field_map["doc-types"].split(",")]
        for t in raw_types:
            # Normalize spaces/hyphens
            t_norm = t.replace(" ", "_").replace("-", "_")
            if t_norm in VALID_DOC_TYPES:
                doc_types.append(DocType(t_norm))
            else:
                warns.append(ValidationWarning(
                    source=source, field="Doc-Types", value=t,
                    message=f"Unknown doc-type '{t}', valid: {sorted(VALID_DOC_TYPES)}",
                ))
    if not doc_types:
        doc_types = [DocType.API_REFERENCE]

    # Parse tags
    tags: tuple[str, ...] = ()
    if "tags" in field_map:
        tags = tuple(t.strip().lower() for t in field_map["tags"].split(",") if t.strip())

    return DocHeader(
        summary=summary,
        stability=stability,
        tier=tier,
        since=since,
        dependencies=dependencies,
        doc_types=tuple(doc_types),
        tags=tags,
        body=body,
        raw=docstring,
    ), warns


def extract_docstring(source_code: str) -> str | None:
    """Extract the module-level docstring from Python source code.

    Uses ``ast.parse`` + ``ast.get_docstring`` for reliable extraction.

    Args:
        source_code: Python source text.

    Returns:
        The module docstring, or None if absent.
    """
    try:
        tree = ast.parse(source_code)
        return ast.get_docstring(tree)
    except SyntaxError:
        return None


def _path_to_module(path: Path, root: Path) -> str:
    """Convert a file path to a dotted module path.

    Args:
        path: Absolute or relative path to a .py file.
        root: The root directory (parent of the top-level package).

    Returns:
        Dotted module path (e.g., ``spine.core.cache``).
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path

    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def scan_modules(
    source_root: Path,
    *,
    exclude_patterns: tuple[str, ...] = ("__pycache__",),
) -> tuple[list[ModuleInfo], list[ValidationWarning]]:
    """Walk a source tree and extract Doc Headers from all Python modules.

    Args:
        source_root: Path to source root (e.g., ``src/spine``).
            The parent of this path is used as the module root for
            dotted-path computation.
        exclude_patterns: Directory name patterns to skip.

    Returns:
        Tuple of (list of ModuleInfo, list of validation warnings).
    """
    modules: list[ModuleInfo] = []
    all_warns: list[ValidationWarning] = []

    # Module root is parent of source_root (e.g., src/)
    module_root = source_root.parent

    for py_file in sorted(source_root.rglob("*.py")):
        # Skip excluded directories
        if any(exc in py_file.parts for exc in exclude_patterns):
            continue

        # Skip non-Python files that somehow match
        if not py_file.is_file():
            continue

        try:
            source_code = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Cannot read %s: %s", py_file, exc)
            continue

        docstring = extract_docstring(source_code)

        rel_path = str(py_file.relative_to(module_root)).replace("\\", "/")
        module_path = _path_to_module(py_file, module_root)

        if docstring:
            header, warns = parse_doc_header(docstring, source=rel_path)
            has_fields = any(
                f in docstring.lower()
                for f in ("stability:", "tier:", "doc-types:", "since:")
            )
            all_warns.extend(warns)

            modules.append(ModuleInfo(
                path=rel_path,
                module_path=module_path,
                header=header,
                has_header_fields=has_fields,
                docstring_length=len(docstring),
            ))
        else:
            modules.append(ModuleInfo(
                path=rel_path,
                module_path=module_path,
                header=None,
                has_header_fields=False,
                docstring_length=0,
            ))

    return modules, all_warns


def detect_missing_headers(
    modules: list[ModuleInfo],
    *,
    min_docstring_length: int = 20,
) -> list[ModuleInfo]:
    """Find modules that have docstrings but no Doc Header fields.

    Useful for incremental migration: shows which modules should get
    headers added.

    Args:
        modules: List of parsed ModuleInfo objects.
        min_docstring_length: Skip tiny docstrings (e.g., ``__init__.py``
            with just a package name).

    Returns:
        List of modules missing headers, sorted by path.
    """
    missing: list[ModuleInfo] = []
    for mod in modules:
        if mod.header is not None and not mod.has_header_fields:
            if mod.docstring_length >= min_docstring_length:
                missing.append(mod)
    return sorted(missing, key=lambda m: m.path)
