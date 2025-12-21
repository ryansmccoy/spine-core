"""Canonical protocol definitions for spine-core.

Stability: stable
Tier: none
Since: 0.1.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE, ADR
Tags: protocol, connection, database, dispatcher

This module defines the SINGLE SOURCE OF TRUTH for all structural
protocols used across spine-core.

Architecture::

    protocols.py
    ├── Connection      — sync DB protocol
    ├── AsyncConnection — async DB protocol
    └── StorageBackend  — sync storage protocol
"""

from __future__ import annotations
from typing import Any, Protocol


class Connection(Protocol):
    """Minimal synchronous connection interface."""

    def execute(self, sql: str, params: tuple = ()) -> Any: ...
    def fetchone(self) -> Any: ...
    def fetchall(self) -> list[Any]: ...
    def commit(self) -> None: ...
