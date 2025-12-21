"""
Environment-file discovery and loading.

Manifesto:
    Configuration cascading must be predictable and debuggable.  This
    module implements a strict load order with no hidden magic: earlier
    values are overridden by later files, and real environment variables
    always win.

Implements the cascading load order::

    .env.base  →  .env.{tier}  →  .env.local  →  .env  →  real env vars

All parsing is pure-Python (no ``python-dotenv`` dependency).
Earlier values are overridden by later files, and real environment
variables always win.

Tags:
    spine-core, configuration, env-files, cascading, pure-python, loader

Doc-Types:
    api-reference
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_VAR_RE = re.compile(
    r"""
    ^                         # start of line
    \s*                       # optional leading whitespace
    (?:export\s+)?            # optional "export " prefix
    (?P<key>[A-Za-z_]\w*)     # variable name
    \s*=\s*                   # equals with optional whitespace
    (?P<value>.*)             # everything after =
    $                         # end of line
    """,
    re.VERBOSE,
)


def find_project_root(start: Path | None = None) -> Path:
    """Walk upward from *start* to find the project root.

    Recognised root markers (checked in order):

    * ``pyproject.toml``
    * ``.git`` directory
    * ``setup.py``

    Falls back to *start* (or cwd) when no marker is found.
    """
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if (directory / "pyproject.toml").exists():
            return directory
        if (directory / ".git").exists():
            return directory
        if (directory / "setup.py").exists():
            return directory
    return current


def discover_env_files(
    project_root: Path | None = None,
    tier: str | None = None,
) -> list[Path]:
    """Return an ordered list of ``.env`` files that exist on disk.

    Load order:

    1. ``.env.base``
    2. ``.env.{tier}`` (if *tier* is provided or ``SPINE_TIER`` is set)
    3. ``.env.local``
    4. ``.env``

    Parameters
    ----------
    project_root:
        Directory to search in.  Defaults to :func:`find_project_root`.
    tier:
        Explicit tier name (``"minimal"``, ``"standard"``, ``"full"``).
        If *None*, falls back to ``SPINE_TIER`` environment variable.
    """
    root = (project_root or find_project_root()).resolve()
    tier = tier or os.environ.get("SPINE_TIER")

    candidates: list[Path] = [root / ".env.base"]
    if tier:
        candidates.append(root / f".env.{tier}")
    candidates.append(root / ".env.local")
    candidates.append(root / ".env")

    return [p for p in candidates if p.is_file()]


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a single ``.env`` file into a ``{key: value}`` mapping.

    Handles:
    * blank/comment lines
    * ``export VAR=value``
    * quoted values (single or double)
    * inline ``# comments`` outside of quotes
    """
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _VAR_RE.match(line)
        if match is None:
            continue
        key = match.group("key")
        value = match.group("value").strip()

        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        else:
            # Remove inline comment (only outside of quoted values)
            if " #" in value:
                value = value[: value.index(" #")].rstrip()

        result[key] = value
    return result


def load_env_files(files: list[Path]) -> dict[str, str]:
    """Parse and merge several ``.env`` files.

    Later files override earlier values.
    """
    merged: dict[str, str] = {}
    for path in files:
        merged.update(_parse_env_file(path))
    return merged


def get_effective_env(
    project_root: Path | None = None,
    tier: str | None = None,
) -> dict[str, str]:
    """Return the fully-resolved environment mapping.

    Merge order (last wins):

    1. Parsed ``.env`` files (via :func:`discover_env_files`)
    2. Real process environment variables

    This mirrors how Pydantic ``BaseSettings`` resolves values but is
    useful for inspection without instantiating a settings object.
    """
    files = discover_env_files(project_root, tier)
    env = load_env_files(files)
    # Real env vars always override file values
    env.update(os.environ)
    return env
