"""
Shared API router utilities.

Provides helper functions used across multiple router modules:
- ``_dc()`` — convert a dataclass or dict to a plain dict
- ``_handle_error()`` — convert a failed OperationResult to a ``problem_response``

These were previously duplicated in 9 router files. Centralised here
as part of SMELL-LAYER-0002 remediation.

Manifesto:
    Utility functions shared across routers should live in one place
    so bug-fixes propagate everywhere and routers stay thin.

Tags:
    spine-core, api, utils, shared, dataclass-conversion

Doc-Types: API_INFRASTRUCTURE
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from spine.api.middleware.errors import problem_response, status_for_error_code


def _dc(obj: Any) -> dict[str, Any]:
    """Convert a dataclass (or dict) to a plain dict.

    Returns an empty dict for objects that are neither dataclasses nor dicts.
    """
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    return obj if isinstance(obj, dict) else {}


def _handle_error(result):
    """Convert a failed ``OperationResult`` into a Problem Details response.

    Uses the error code from the result to determine the HTTP status code,
    and the error message as the problem title.
    """
    code = result.error.code if result.error else "INTERNAL"
    return problem_response(
        status=status_for_error_code(code),
        title=result.error.message if result.error else "Operation failed",
    )
