"""Shared domain enumerations.

Stability: stable
Tier: none
Since: 0.1.0
Dependencies: stdlib-only
Doc-Types: API_REFERENCE
Tags: enum, domain
"""

from enum import Enum


class RunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
