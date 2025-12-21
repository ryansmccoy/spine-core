"""
ULID generation and timestamp utilities (stdlib-only).

Shared platform primitives for generating time-sortable unique IDs
and working with UTC timestamps. All spines should import from here
instead of maintaining their own copies.

Manifesto:
    Every spine needs unique IDs and UTC timestamps. Without a shared
    module, each project reinvents these with subtle differences
    (timezone handling, ID format, precision). This module provides:

    - **generate_ulid():** Time-sortable unique IDs (26-char, base32)
    - **utc_now():** Timezone-aware UTC datetime
    - **to_iso8601() / from_iso8601():** Safe serialization round-trip

Features:
    - **ULID generation:** Time-sortable, 26-char, Crockford base32
    - **UTC utilities:** utc_now(), to_iso8601(), from_iso8601()
    - **stdlib-only:** No external dependencies
    - **Deterministic ordering:** ULIDs sort by creation time

Tags:
    timestamps, ulid, utc, datetime, spine-core, stdlib-only,
    unique-id, serialization

Doc-Types:
    - API Reference
    - Utility Documentation

STDLIB ONLY - NO PYDANTIC.
"""

import random
import time
from datetime import UTC, datetime


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


def generate_ulid() -> str:
    """
    Generate a ULID-like identifier.

    Format: 26 characters, base32 encoded, time-sortable.
    This is a simplified implementation for stdlib-only usage.
    """
    # Time component: milliseconds since epoch (48 bits -> 10 chars)
    timestamp_ms = int(time.time() * 1000)
    timestamp_chars = _encode_base32(timestamp_ms, 10)

    # Random component (80 bits -> 16 chars)
    random_part = "".join(random.choices(_ENCODING, k=16))

    return timestamp_chars + random_part


def to_iso8601(dt: datetime | None) -> str | None:
    """Convert datetime to ISO 8601 string."""
    if dt is None:
        return None
    return dt.isoformat()


def from_iso8601(s: str | None) -> datetime | None:
    """Parse ISO 8601 string to datetime."""
    if s is None:
        return None
    return datetime.fromisoformat(s)


# ULID base32 alphabet (Crockford's)
_ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ENCODING_LEN = len(_ENCODING)


def _encode_base32(value: int, length: int) -> str:
    """Encode integer to base32 string of fixed length."""
    result = []
    for _ in range(length):
        result.append(_ENCODING[value % _ENCODING_LEN])
        value //= _ENCODING_LEN
    return "".join(reversed(result))
