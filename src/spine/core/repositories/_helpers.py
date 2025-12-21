"""Shared helpers for repository classes.

Tags:
    spine-core, repository, helpers

Doc-Types:
    api-reference
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PageSlice:
    """Pagination params used by list operations."""

    limit: int = 50
    offset: int = 0


def _build_where(
    conditions: dict[str, Any],
    dialect_ph: Any,
    *,
    extra_clauses: list[str] | None = None,
) -> tuple[str, tuple]:
    """Build a WHERE clause from a conditions dict.

    Returns ``(where_fragment, params_tuple)``.  Skips ``None`` values.
    ``extra_clauses`` are appended literally (no params).
    """
    parts: list[str] = []
    params: list[Any] = []
    idx = 0
    for col, val in conditions.items():
        if val is None:
            continue
        parts.append(f"{col} = ?")
        params.append(val)
        idx += 1
    if extra_clauses:
        parts.extend(extra_clauses)
    where = " AND ".join(parts) if parts else "1=1"
    return where, tuple(params)
